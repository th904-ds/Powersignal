"""
filter_features.py
------------------
수집된 raw 데이터 → Model 1 / Model 2 입력용 기본 변수 추출·병합

출력 (data/features/):
  base_merged.parquet      모든 추출 가능한 원시 변수 (시간 인덱스)
  model1_filtered.parquet  Model 1 입력용 원시 변수 (lag/rolling은 전처리 단계에서 생성)
  model2_filtered.parquet  Model 2 입력용 원시 변수 (SMP 이력 lag/rolling 제외)

미수집으로 누락된 변수 (추가 API 수집 필요):
  supply_capacity, facility_capacity
  supply_reserve_power, supply_reserve_rate
  reserve_to_max_demand
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROC = Path(__file__).parents[2] / "00.collector" / "data" / "processed"
OUT = Path(__file__).parents[2] / "00.collector" / "data" / "features"
OUT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def _load_all_parquets(folder: Path) -> pd.DataFrame:
    files = sorted(folder.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"parquet 파일 없음: {folder}")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _date_hour_to_datetime(date_series: pd.Series, hour_series: pd.Series) -> pd.Series:
    """
    date(YYYYMMDD str) + hour(1~24 int/str) → datetime
    hour=1  → 당일 01:00
    hour=24 → 익일 00:00  (pd.to_timedelta로 자동 처리)
    """
    base = pd.to_datetime(date_series.astype(str), format="%Y%m%d", errors="coerce")
    h = pd.to_numeric(hour_series, errors="coerce")
    return base + pd.to_timedelta(h, unit="h")


# ---------------------------------------------------------------------------
# 1. SMP + 수요예측  (smp_dayahead)
# ---------------------------------------------------------------------------
# 사용 컬럼: smp(육지), jlfd, slfd, mlfd
# hour 범위: 1~24 → 01:00~익일 00:00

def load_smp(area: str = "육지") -> pd.DataFrame:
    df = _load_all_parquets(PROC / "smp_dayahead")
    df["datetime"] = _date_hour_to_datetime(df["date"], df["hour"])
    df = df[df["areaName"] == area].copy()
    for col in ["smp", "jlfd", "slfd", "mlfd"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    result = (
        df[["datetime", "smp", "jlfd", "slfd", "mlfd"]]
        .dropna(subset=["datetime"])
        .drop_duplicates("datetime")
        .sort_values("datetime")
        .reset_index(drop=True)
    )
    print(f"  [smp_dayahead] {len(result):,}행  "
          f"{result['datetime'].min()} ~ {result['datetime'].max()}")
    return result


# ---------------------------------------------------------------------------
# 2. 발전원별 발전량  (gen_by_source_hist)
# ---------------------------------------------------------------------------
# API 원본 fuelTpCd → gen_* 컬럼명 매핑 (원본 한글명 그대로 유지)
# tradeNo(01~24)가 거래시간 = hour

_FUEL_RENAME = {
    "원자력":      "gen_원자력",
    "LNG":         "gen_LNG",
    "유연탄":      "gen_유연탄",
    "무연탄":      "gen_무연탄",
    "신재생·기타": "gen_신재생·기타",
    "수력":        "gen_수력",
    "양수":        "gen_양수",
    "유전":        "gen_유전",
}


def load_gen() -> pd.DataFrame:
    df = _load_all_parquets(PROC / "gen_by_source_hist")
    # tradeNo = 거래 시간 (01~24), tradeYmd = YYYYMMDD
    df["datetime"] = _date_hour_to_datetime(df["tradeYmd"], df["tradeNo"])
    df["amgo"] = pd.to_numeric(df["amgo"], errors="coerce")

    # long → wide (fuelTpCd별 컬럼, 원본 한글명 유지)
    wide = (
        df.pivot_table(index="datetime", columns="fuelTpCd", values="amgo", aggfunc="sum")
        .rename(columns=_FUEL_RENAME)
    )
    wide.columns.name = None

    # 전체 발전량
    gen_sum_cols = [c for c in wide.columns if c.startswith("gen_") and "_ratio" not in c]
    wide["gen_total"] = wide[gen_sum_cols].sum(axis=1)

    # 전체 발전원 비율 (model parquet 기준: 모든 gen_ 변수에 ratio 생성)
    for col in gen_sum_cols:
        wide[f"{col}_ratio"] = wide[col] / wide["gen_total"]

    result = wide.reset_index().sort_values("datetime").reset_index(drop=True)
    print(f"  [gen_by_source_hist] {len(result):,}행  "
          f"{result['datetime'].min()} ~ {result['datetime'].max()}")
    return result


# ---------------------------------------------------------------------------
# 3. 월간 연료비용  (monthly_fuel_cost)
# ---------------------------------------------------------------------------
# day: YYYYMM → 월 첫날 datetime
# wide pivot 후 시간 인덱스에 left join (ffill로 당월 값 전파)

_FUEL_COST_RENAME = {
    "유연탄": "fuel_cost_유연탄",
    "무연탄": "fuel_cost_무연탄",
    "유류":   "fuel_cost_유류",
    "원자력": "fuel_cost_원자력",
    "LNG":    "fuel_cost_LNG",
}


def load_fuel_cost() -> pd.DataFrame:
    df = _load_all_parquets(PROC / "monthly_fuel_cost")
    df["month"] = pd.to_datetime(df["day"].astype(str), format="%Y%m", errors="coerce")
    df["untpc"] = pd.to_numeric(df["untpc"], errors="coerce")
    wide = (
        df.pivot_table(index="month", columns="fuelType", values="untpc", aggfunc="mean")
        .rename(columns=_FUEL_COST_RENAME)
    )
    wide.columns.name = None
    result = wide.reset_index().sort_values("month").reset_index(drop=True)
    print(f"  [monthly_fuel_cost] {len(result)}개월  "
          f"{result['month'].min().strftime('%Y-%m')} ~ {result['month'].max().strftime('%Y-%m')}")
    return result


# ---------------------------------------------------------------------------
# 4. SMP 결정 횟수  (smp_decision_count, 일별)
# ---------------------------------------------------------------------------
# 모델에서 smp_decision_cnt_LNG 사용 (육지 기준)
# 일별 데이터 → 시간별 left join 후 ffill

def load_smp_decision(area: str = "육지") -> pd.DataFrame:
    df = _load_all_parquets(PROC / "smp_decision_count")
    df["date"] = pd.to_datetime(df["tradeDay"].astype(str), format="%Y%m%d", errors="coerce")
    df["cnt"] = pd.to_numeric(df["cnt"], errors="coerce")
    df = df[df["areaNm"] == area]
    df["col"] = "smp_dec_" + df["fuelType"].str.strip()
    wide = df.pivot_table(index="date", columns="col", values="cnt", aggfunc="sum")
    wide.columns.name = None
    # LNG 결정 횟수만 모델이 사용 (나머지는 보존)
    if "smp_dec_LNG" in wide.columns:
        wide = wide.rename(columns={"smp_dec_LNG": "smp_decision_cnt_LNG"})
    result = wide.reset_index().sort_values("date").reset_index(drop=True)
    print(f"  [smp_decision_count] {len(result):,}일  "
          f"{result['date'].min().date()} ~ {result['date'].max().date()}")
    return result


# ---------------------------------------------------------------------------
# 5. 전력수급실적 (일별 → 시간별)
# ---------------------------------------------------------------------------
# GCS: energy-collector/power_supply_today/HOME_전력수급_전력수급실적.csv
# 로컬: data/processed/power_supply_today/HOME_전력수급_전력수급실적.csv
# 컬럼 매핑:
#   설비용량(MW)  → facility_capacity
#   공급능력(MW)  → supply_capacity
#   최대전력(MW)  → daily_max_demand
#   공급예비력(MW) → supply_reserve_power
#   공급예비율(%) → supply_reserve_rate
#   파생           → reserve_to_max_demand = 공급예비력 / 최대전력
# 일별 데이터 → 당일 전 시간에 동일값 적용 (모델 parquet 확인 결과)

_SUPPLY_CSV = PROC / "power_supply_today" / "HOME_전력수급_전력수급실적.csv"


def load_power_supply_hist() -> pd.DataFrame:
    if not _SUPPLY_CSV.exists():
        print(f"  [전력수급실적] 경고: {_SUPPLY_CSV} 없음 — 수동 일별 전력수급실적 스킵")
        return pd.DataFrame(columns=[
            "date",
            "facility_capacity",
            "supply_capacity",
            "daily_max_demand",
            "supply_reserve_power",
            "supply_reserve_rate",
            "reserve_to_max_demand",
        ])

    df = pd.read_csv(_SUPPLY_CSV, encoding="cp949")
    df["date"] = pd.to_datetime(
        df[["년", "월", "일"]].rename(columns={"년": "year", "월": "month", "일": "day"})
    )
    df["최소전력(MW)"] = pd.to_numeric(
        df["최소전력(MW)"].astype(str).str.replace(",", ""), errors="coerce"
    )
    df["facility_capacity"]      = pd.to_numeric(df["설비용량(MW)"], errors="coerce")
    df["supply_capacity"]        = pd.to_numeric(df["공급능력(MW)"], errors="coerce")
    df["daily_max_demand"]       = pd.to_numeric(df["최대전력(MW)"], errors="coerce")
    df["supply_reserve_power"]   = pd.to_numeric(df["공급예비력(MW)"], errors="coerce")
    df["supply_reserve_rate"]    = pd.to_numeric(df["공급예비율(%)"], errors="coerce")
    df["reserve_to_max_demand"]  = df["supply_reserve_power"] / df["daily_max_demand"]

    result = (
        df[["date", "facility_capacity", "supply_capacity", "daily_max_demand",
            "supply_reserve_power", "supply_reserve_rate", "reserve_to_max_demand"]]
        .drop_duplicates("date")
        .sort_values("date")
        .reset_index(drop=True)
    )
    print(f"  [전력수급실적] {len(result):,}일  "
          f"{result['date'].min().date()} ~ {result['date'].max().date()}")
    return result


# ---------------------------------------------------------------------------
# 6. 기상  (asos_hourly, 4개 관측소 평균)
# ---------------------------------------------------------------------------
# 기온(temp_c), 습도(humidity_pct), 풍속(wind_speed_ms)
# PDF에서 추가 요청: 냉/난방 지수는 전처리 단계에서 파생

_ASOS_RENAME = {
    "ta": "temp_c",
    "hm": "humidity_pct",
    "ws": "wind_speed_ms",
    "td": "dew_point_c",
}
_WEATHER_COLS = ["temp_c", "humidity_pct", "wind_speed_ms", "dew_point_c"]


def load_weather() -> pd.DataFrame:
    dfs = [pd.read_parquet(f) for f in sorted((PROC / "asos_hourly").glob("*.parquet"))]
    df = pd.concat(dfs, ignore_index=True)
    df = df.rename(columns=_ASOS_RENAME)
    df["datetime"] = pd.to_datetime(df["tm"], format="%Y-%m-%d %H:%M", errors="coerce")
    for col in _WEATHER_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # 4개 관측소 단순 평균 (서울·대전·대구·부산)
    avg = (
        df.groupby("datetime")[[c for c in _WEATHER_COLS if c in df.columns]]
        .mean()
        .reset_index()
    )
    print(f"  [asos_hourly] {len(avg):,}행  "
          f"{avg['datetime'].min()} ~ {avg['datetime'].max()}")
    return avg.sort_values("datetime").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 병합
# ---------------------------------------------------------------------------

def build_base() -> pd.DataFrame:
    print("▶ 데이터 로드 중...")
    smp        = load_smp()
    gen        = load_gen()
    fuel_cost  = load_fuel_cost()
    smp_dec    = load_smp_decision()
    supply     = load_power_supply_hist()
    weather    = load_weather()

    print("\n▶ 병합 중 (기준: smp_dayahead datetime)...")
    base = smp.merge(gen, on="datetime", how="left")

    # 일별 데이터 조인용 date 키
    base["_date"] = base["datetime"].dt.normalize()

    # SMP 결정 횟수: 일별 → 시간별
    base = base.merge(smp_dec.rename(columns={"date": "_date"}), on="_date", how="left")

    # 전력수급실적: 일별 → 시간별 (당일 모든 시간에 동일값)
    # 수동 CSV가 없는 GitHub Actions 환경에서는 빈 DF가 반환되므로 merge를 건너뛴다.
    if not supply.empty:
        base = base.merge(supply.rename(columns={"date": "_date"}), on="_date", how="left")

    base = base.drop(columns=["_date"])

    # 연료비용: 월별 → 시간별
    base["_month"] = base["datetime"].dt.to_period("M").dt.to_timestamp()
    base = base.merge(fuel_cost, left_on="_month", right_on="month", how="left")
    base = base.drop(columns=["_month", "month"])

    # 기상
    base = base.merge(weather, on="datetime", how="left")

    base = base.sort_values("datetime").reset_index(drop=True)
    return base


# ---------------------------------------------------------------------------
# 모델별 필터링 및 저장
# ---------------------------------------------------------------------------

# 공통 원시 변수 (lag/rolling/시간/공휴일 파생 변수는 전처리 단계에서 추가)
# 컬럼명은 smp_master_model1_performance2.parquet 기준으로 맞춤
_COMMON = [
    "datetime",
    # Target
    "smp",
    # 수요예측
    "jlfd", "slfd", "mlfd",
    # 발전량 (원본 한글명 유지 — 모델 기준)
    "gen_LNG", "gen_무연탄", "gen_수력", "gen_신재생·기타",
    "gen_양수", "gen_원자력", "gen_유연탄", "gen_유전",
    "gen_total",
    # 발전원 비율 (모든 gen_ 변수에 ratio 생성)
    "gen_LNG_ratio", "gen_무연탄_ratio", "gen_수력_ratio", "gen_신재생·기타_ratio",
    "gen_양수_ratio", "gen_원자력_ratio", "gen_유연탄_ratio", "gen_유전_ratio",
    # 연료비용 (월별)
    "fuel_cost_LNG", "fuel_cost_유연탄", "fuel_cost_무연탄",
    "fuel_cost_유류", "fuel_cost_원자력",
    # SMP 결정 횟수 (일별)
    "smp_decision_cnt_LNG",
    # 전력수급실적 (일별, HOME_전력수급_전력수급실적.csv)
    "facility_capacity", "supply_capacity", "daily_max_demand",
    "supply_reserve_power", "supply_reserve_rate", "reserve_to_max_demand",
    # 기상
    "temp_c", "humidity_pct", "wind_speed_ms", "dew_point_c",
    # ── 전처리 단계에서 생성 예정 ──────────────────────────────────────────
    # date_key, month_key
    # hour_of_day, weekday, month_num, is_weekend
    # hour_sin, hour_cos, month_sin, month_cos
    # is_holiday, is_before_holiday, is_after_holiday
]

# Model 2는 SMP 이력(lag/rolling) 없이 실제 전력시장 변수만 → 동일 원시 변수에서 출발
# (lag/rolling 분기는 preprocessing 단계에서 처리)
_MODEL1_EXTRA: list[str] = []   # lag/rolling은 preprocessing에서 추가
_MODEL2_EXCLUDE: list[str] = [] # smp 자체는 유지 (target으로 필요), lag만 나중에 제외


def filter_and_save(base: pd.DataFrame) -> None:
    available = [c for c in _COMMON if c in base.columns]
    missing_from_common = [c for c in _COMMON if c not in base.columns
                           and not c.startswith("#") and c != "datetime"]

    print(f"\n▶ 필터링 결과")
    print(f"  base 전체 컬럼: {len(base.columns)}개")
    print(f"  모델 공통 변수 확보: {len(available)}개")

    # 미수집/미생성 변수 리포트 (전력수급실적 CSV 추가 후 전부 확보)
    not_collected: list[str] = []
    to_generate = [
        # daily_max_demand: HOME_전력수급_전력수급실적.csv에서 직접 확보됨 → 제거
        "hour_of_day", "weekday", "month_num", "is_weekend",
        "hour_sin", "hour_cos", "month_sin", "month_cos",
        "date_key", "month_key",
        "is_holiday", "is_before_holiday", "is_after_holiday",
        # Model 1 전용
        "smp_lag1", "smp_lag24", "smp_lag48", "smp_lag72", "smp_lag168", "smp_lag336",
        "smp_roll_mean_24", "smp_roll_mean_168",
        "smp_roll_std_24", "smp_roll_std_168",
        "smp_roll_max_24", "smp_roll_min_24", "smp_roll_max_168", "smp_roll_min_168",
        "jlfd_lag24", "jlfd_lag168", "slfd_lag24", "slfd_lag168", "mlfd_lag24", "mlfd_lag168",
        "jlfd_diff_24", "slfd_diff_24", "mlfd_diff_24",
        "jlfd_pct_change_24", "slfd_pct_change_24", "mlfd_pct_change_24",
    ]
    print(f"\n  [전처리 단계 생성 예정] {len(to_generate)}개:")
    for v in to_generate:
        print(f"    + {v}")
    print(f"\n  [미수집 - 추가 API 수집 필요] {len(not_collected)}개:")
    for v in not_collected:
        print(f"    [없음] {v}")

    # 저장
    base_out = base[available]
    base_out.to_parquet(OUT / "base_merged.parquet", index=False)
    print(f"\n  → base_merged.parquet  {base_out.shape}")

    # Model 1: 원시 변수 전체 (lag/rolling을 전처리 단계에서 추가할 기반)
    m1 = base_out.copy()
    m1.to_parquet(OUT / "model1_filtered.parquet", index=False)
    print(f"  → model1_filtered.parquet  {m1.shape}")

    # Model 2: smp 컬럼 유지(target), 나중에 lag/rolling 추가하지 않음
    #   현 단계에서는 m1과 동일 (전처리 단계에서 lag 생성 여부로 분기)
    m2 = base_out.copy()
    m2.to_parquet(OUT / "model2_filtered.parquet", index=False)
    print(f"  → model2_filtered.parquet  {m2.shape}")

    # 컬럼별 결측치 현황 출력
    print("\n▶ 변수별 결측치 현황 (base_merged):")
    null_summary = base_out.isnull().sum()
    null_pct = (null_summary / len(base_out) * 100).round(1)
    summary_df = pd.DataFrame({
        "결측수": null_summary,
        "결측률(%)": null_pct,
    }).query("결측수 > 0").sort_values("결측률(%)", ascending=False)
    if summary_df.empty:
        print("  결측치 없음")
    else:
        print(summary_df.to_string())
