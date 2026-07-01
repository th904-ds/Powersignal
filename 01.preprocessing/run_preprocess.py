"""
전처리 실행 스크립트 — 단계별 실행 및 중간 검증
"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
from pathlib import Path
from preprocess import (
    step1_drop, step2_gen_impute, step3_minor_impute, step3b_smp_outlier,
    stepW_weather_merge, stepNBTP_merge, stepSUKUB_merge,
    step4_datetime_feats, step5_holiday_feats,
    step6_load_lags, stepRESERVE_lags, step7_smp_lags, step8_filter_save,
    FEAT, OUT,
)

# DB 모듈 (PG_URL 없으면 조용히 비활성화)
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "02.database"))
_DB_AVAILABLE = False
try:
    from db import upsert as _db_upsert, rename_for_db as _rename_for_db
    _DB_AVAILABLE = True
except Exception as _e:
    print(f"[DB] 비활성: {_e}")


def _write_model_features_to_db(df: pd.DataFrame, model_id: str) -> None:
    """전처리 완료 DataFrame을 model_features 테이블에 upsert."""
    if not _DB_AVAILABLE:
        return
    try:
        out = _rename_for_db(df.copy())
        out["model_id"] = model_id

        # model2는 SMP 자기회귀 컬럼이 없으므로 NaN으로 채워 스키마 맞춤
        smp_ar = (
            [f"smp_lag{l}" for l in [1, 24, 48, 72, 168, 336]]
            + [f"smp_roll_{s}_{w}" for s in ["mean","std","max","min"] for w in [24, 168]]
        )
        for col in smp_ar:
            if col not in out.columns:
                out[col] = np.nan

        # sukub 미수집 시 예비력 컬럼을 NaN으로 채워 스키마 맞춤
        reserve_cols = [
            "supply_capacity", "current_demand", "forecast_load",
            "supply_reserve_power", "supply_reserve_rate",
            "operating_reserve_power", "operating_reserve_rate",
            "operating_reserve_rate_lag24", "operating_reserve_rate_lag168",
            "operating_reserve_power_lag24", "operating_reserve_power_lag168",
            "supply_capacity_lag24", "supply_capacity_lag168",
            "current_demand_lag24", "current_demand_lag168",
            "forecast_load_lag24", "forecast_load_lag168",
            "operating_reserve_rate_roll_mean_24_lag24",
            "operating_reserve_rate_roll_min_24_lag24",
            "operating_reserve_rate_roll_std_24_lag24",
            "operating_reserve_rate_roll_mean_168_lag24",
            "operating_reserve_rate_roll_min_168_lag24",
            "operating_reserve_rate_roll_std_168_lag24",
            "operating_reserve_power_to_demand_lag24",
        ]
        for col in reserve_cols:
            if col not in out.columns:
                out[col] = np.nan

        n = _db_upsert(out, "model_features", ["datetime", "model_id"])
        print(f"[DB] model_features [{model_id}] {n:,}행 upsert 완료")
    except Exception as e:
        print(f"[DB] 경고 — DB 저장 실패 (parquet은 정상 저장됨): {e}")

# ── 원본 로드 ──────────────────────────────────────────────────────────
print("=" * 60)
print("전처리 파이프라인 시작")
print("=" * 60)
df = pd.read_parquet(FEAT / "base_merged.parquet")
df["datetime"] = pd.to_datetime(df["datetime"])
df = df.sort_values("datetime").reset_index(drop=True)
print(f"원본: {df.shape}  ({df['datetime'].min()} ~ {df['datetime'].max()})")

# ── Step 1 ────────────────────────────────────────────────────────────
print("\n[Step 1] 변수 제거")
df = step1_drop(df)

# ── Step 2 ────────────────────────────────────────────────────────────
print("\n[Step 2] gen 결측 보간 → 일합산 → ratio 재계산")
df = step2_gen_impute(df)

# ── Step 3 ────────────────────────────────────────────────────────────
print("\n[Step 3] 미소결측 처리")
df = step3_minor_impute(df)

# ── Step 3b ───────────────────────────────────────────────────────────
print("\n[Step 3b] SMP 이상치 처리")
df = step3b_smp_outlier(df)

# ── Step W ────────────────────────────────────────────────────────────
print("\n[Step W] 기상변수 처리 + 병합")
df = stepW_weather_merge(df)

# ── Step NBTP ─────────────────────────────────────────────────────────
print("\n[Step NBTP] NBTP 월별 전파")
df = stepNBTP_merge(df)

# ── Step SUKUB ────────────────────────────────────────────────────────
print("\n[Step SUKUB] 5분단위 전력수급 집계 & 병합")
df = stepSUKUB_merge(df)

# ── Step 4 ────────────────────────────────────────────────────────────
print("\n[Step 4] datetime 피처")
df = step4_datetime_feats(df)

# ── Step 5 ────────────────────────────────────────────────────────────
print("\n[Step 5] 공휴일 피처")
df = step5_holiday_feats(df)

# ── Step 6 ────────────────────────────────────────────────────────────
print("\n[Step 6] 수요예측 래그/차분")
df = step6_load_lags(df)

# ── Step RESERVE ──────────────────────────────────────────────────────
print("\n[Step RESERVE] 예비력 lag/rolling 피처")
df = stepRESERVE_lags(df)

# ── Step 7 ────────────────────────────────────────────────────────────
print("\n[Step 7] SMP 자기회귀 피처")
df = step7_smp_lags(df)

# ── Step 8 ────────────────────────────────────────────────────────────
print("\n[Step 8] 훈련 기간 필터 & 저장")
m1, m2 = step8_filter_save(df)

# ── DB 저장 ───────────────────────────────────────────────────────────
print("\n[DB] model_features 테이블 upsert 중...")
_write_model_features_to_db(m1, "model1")
_write_model_features_to_db(m2, "model2")

print("\n" + "=" * 60)
print("전처리 완료")
print("=" * 60)
print(f"  Model 1: {m1.shape}  컬럼={m1.shape[1]}")
print(f"  Model 2: {m2.shape}  컬럼={m2.shape[1]}")
print(f"  저장 위치: 01.preprocessing/output/")
print(f"  기상 컬럼 포함 여부: {'avg_temp_c' in m1.columns}")
