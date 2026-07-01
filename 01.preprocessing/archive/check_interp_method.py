"""
모델팀 보간 방법 역추적
  - 우리 API gen_LNG 경계값 vs 모델파켓 결측 구간 값 비교
  - linear interpolation vs forward-fill 판별
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path("c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal")
PROC = BASE / "00.collector/data/processed/gen_by_source_hist"

# ── 로드 ────────────────────────────────────────────────────────────
df_old = pd.read_parquet(PROC / "20260608.parquet")
df_old["datetime"] = pd.to_datetime(df_old["tradeYmd"].astype(str), format="%Y%m%d", errors="coerce") \
                   + pd.to_timedelta(df_old["tradeNo"].astype(int), unit="h")

df_model = pd.read_parquet(BASE / "01.preprocessing/archive/smp_master_model1_performance2.parquet")
df_model["datetime"] = pd.to_datetime(df_model["datetime"])

# LNG 시계열 (피벗)
lng_api = df_old[df_old["fuelTpCd"] == "LNG"][["datetime","amgo"]].set_index("datetime").sort_index()
lng_model = df_model[["datetime","gen_LNG"]].set_index("datetime").sort_index()

# ── 구간 1: 2023-12-21 ~ 2024-01-14 (25일, 가장 긴 구간) ─────────────
GAP_S = "2023-12-21"
GAP_E = "2024-01-14"
PRE_DAYS = 3   # 경계 전 3일치 확인
POST_DAYS = 3  # 경계 후 3일치 확인

pre_start  = pd.Timestamp(GAP_S) - pd.Timedelta(days=PRE_DAYS)
post_end   = pd.Timestamp(GAP_E) + pd.Timedelta(days=POST_DAYS)

# API: 경계 전후
api_pre  = lng_api.loc[pre_start:pd.Timestamp(GAP_S) - pd.Timedelta(hours=1), "amgo"]
api_post = lng_api.loc[pd.Timestamp(GAP_E) + pd.Timedelta(hours=1):post_end, "amgo"]

# 모델: 결측 구간
model_gap = lng_model.loc[GAP_S:GAP_E, "gen_LNG"]

print(f"=== 구간: {GAP_S} ~ {GAP_E} (25일) ===")
print(f"\nAPI 경계 전 마지막 5개 (2023-12-20):")
print(api_pre.tail(5).to_string())
print(f"\nAPI 경계 후 첫 5개 (2024-01-15):")
print(api_post.head(5).to_string())
print(f"\n모델파켓 구간 중 첫 12개:")
print(model_gap.head(12).to_string())
print(f"\n모델파켓 구간 중 마지막 12개:")
print(model_gap.tail(12).to_string())

# ── linear interpolation 시뮬레이션 ─────────────────────────────────
print("\n=== linear interpolation 시뮬레이션 ===")

# API LNG 전체 시계열 (2023-2025 범위)
lng_all = lng_api[(lng_api.index >= "2023-01-01") & (lng_api.index < "2026-01-01")]["amgo"].copy()

# 완전한 시간 인덱스 만들기
full_idx = pd.date_range("2023-01-01 01:00", "2026-01-01 00:00", freq="h")
lng_full = lng_all.reindex(full_idx)  # 결측은 NaN

# 선형 보간
lng_linear = lng_full.interpolate(method="time")

# 구간 비교
interp_gap = lng_linear.loc[GAP_S:GAP_E]
print(f"\n보간값 vs 모델값 (처음 12행):")
comp = pd.DataFrame({
    "interp_linear": interp_gap.head(12),
    "model": model_gap.head(12),
})
comp["diff_pct"] = (comp["interp_linear"] - comp["model"]).abs() / comp["model"].abs() * 100
print(comp.to_string())

print(f"\n오차 통계 (전체 구간):")
comp_all = pd.DataFrame({
    "interp": interp_gap,
    "model": model_gap,
})
comp_all["diff_pct"] = (comp_all["interp"] - comp_all["model"]).abs() / comp_all["model"].abs() * 100
print(f"  평균 오차율: {comp_all['diff_pct'].mean():.1f}%")
print(f"  최대 오차율: {comp_all['diff_pct'].max():.1f}%")
print(f"  중간 오차율: {comp_all['diff_pct'].median():.1f}%")

# ── ffill 시뮬레이션 ─────────────────────────────────────────────────
print("\n=== ffill 시뮬레이션 ===")
lng_ffill = lng_full.ffill()
ffill_gap = lng_ffill.loc[GAP_S:GAP_E]
comp_ff = pd.DataFrame({
    "ffill": ffill_gap,
    "model": model_gap,
})
comp_ff["diff_pct"] = (comp_ff["ffill"] - comp_ff["model"]).abs() / comp_ff["model"].abs() * 100
print(f"  평균 오차율: {comp_ff['diff_pct'].mean():.1f}%")
print(f"  최대 오차율: {comp_ff['diff_pct'].max():.1f}%")

# ── 짧은 구간에서 비교 (2023-11-22~23, 2일) ──────────────────────────
print("\n=== 짧은 구간: 2023-11-22 ~ 2023-11-23 (2일) ===")
s2, e2 = "2023-11-22", "2023-11-23"
interp2 = lng_linear.loc[s2:e2]
model2  = model_gap_2 = lng_model.loc[s2:e2, "gen_LNG"]
comp2 = pd.DataFrame({"interp": interp2, "model": model_gap_2})
comp2["diff_pct"] = (comp2["interp"] - comp2["model"]).abs() / comp2["model"].abs() * 100
print(comp2.to_string())
print(f"  평균 오차율: {comp2['diff_pct'].mean():.1f}%")
