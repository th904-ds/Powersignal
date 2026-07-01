"""
변수 커버리지 최종 분석
  - smp_master_model1_performance2.parquet 기준 73개 변수와 비교
  - 2023-01-01 ~ 2025-12-31 구간 시간 단위 데이터 확보 현황 집중 확인
"""
import pandas as pd
import sys
sys.stdout.reconfigure(encoding="utf-8")

BASE = "c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal"

# ── 데이터 로드 ────────────────────────────────────────────────────────────────
df_model = pd.read_parquet(f"{BASE}/01.preprocessing/archive/smp_master_model1_performance2.parquet")
df_base  = pd.read_parquet(f"{BASE}/00.collector/data/features/base_merged.parquet")

model_cols = list(df_model.columns)
have_cols  = set(df_base.columns)

# 전처리 단계 생성 예정
to_generate = {
    # daily_max_demand: HOME_전력수급_전력수급실적.csv에서 직접 확보됨
    "date_key", "month_key",
    "hour_of_day", "weekday", "month_num", "is_weekend",
    "is_holiday", "is_before_holiday", "is_after_holiday",
    "hour_sin", "hour_cos", "month_sin", "month_cos",
    "smp_lag1", "smp_lag24", "smp_lag48", "smp_lag72", "smp_lag168", "smp_lag336",
    "smp_roll_mean_24", "smp_roll_mean_168",
    "smp_roll_std_24", "smp_roll_std_168",
    "smp_roll_max_24", "smp_roll_min_24", "smp_roll_max_168", "smp_roll_min_168",
    "jlfd_lag24", "jlfd_lag168", "slfd_lag24", "slfd_lag168", "mlfd_lag24", "mlfd_lag168",
    "jlfd_diff_24", "jlfd_pct_change_24",
    "slfd_diff_24", "slfd_pct_change_24",
    "mlfd_diff_24", "mlfd_pct_change_24",
}

# ── 1. 변수 커버리지 분류 ──────────────────────────────────────────────────────
covered_have, covered_gen, missing = [], [], []
for col in model_cols:
    if col in have_cols:
        covered_have.append(col)
    elif col in to_generate:
        covered_gen.append(col)
    else:
        missing.append(col)

print("=" * 70)
print(f"  모델 파일 기준 변수 총 {len(model_cols)}개 커버리지")
print("=" * 70)
print(f"  [O] 현재 확보:   {len(covered_have)}개")
print(f"  [+] 생성 예정:   {len(covered_gen)}개")
print(f"  [X] 미확보:      {len(missing)}개")
print(f"  합계:            {len(covered_have)+len(covered_gen)+len(missing)}개")
print()

# ── 2. 2023-2025 시간 단위 데이터 커버리지 ──────────────────────────────────
TRAIN_START = "2023-01-01 00:00"
TRAIN_END   = "2025-12-31 23:00"

# 전체 기대 행 수: 2023-01-01 01:00 ~ 2025-12-31 24:00 (= 2026-01-01 00:00)
# smp_dayahead는 hour=1~24 (01:00~익일 00:00)
expected_hours = pd.date_range(
    start="2023-01-01 01:00", end="2026-01-01 00:00", freq="h"
)
N_EXPECTED = len(expected_hours)  # 3년 × 8760(+24 for leap) ≈ 26,280

df_train = df_base[
    (df_base["datetime"] >= TRAIN_START) &
    (df_base["datetime"] <= TRAIN_END + " 23:00")
].copy()
# 실제로는 smp 기준 2023-2025 기간
df_train = df_base[
    (df_base["datetime"] >= "2023-01-01") &
    (df_base["datetime"] < "2026-01-01")
]

N_ROWS = len(df_train)
print("=" * 70)
print(f"  2023-01-01 ~ 2025-12-31  시간 단위 데이터 현황")
print("=" * 70)
print(f"  기대 행 수: {N_EXPECTED:,}  (3년 × 8760h + 24h 윤년)")
print(f"  실제 행 수: {N_ROWS:,}")
print()

# 각 변수별 결측 현황 (확보된 변수만)
print(f"  {'변수':<38}  {'결측수':>7}  {'결측률':>7}  {'상태'}")
print(f"  {'-'*38}  {'-'*7}  {'-'*7}  {'-'*30}")

for col in covered_have:
    if col == "datetime":
        continue
    n_null = df_train[col].isnull().sum()
    pct    = n_null / N_ROWS * 100
    if pct == 0:
        status = "완전"
    elif pct < 5:
        status = "양호 (기상 결측 등)"
    elif pct < 20:
        status = "주의 (gen 수집 기간 갭)"
    else:
        status = "불량"
    print(f"  {col:<38}  {n_null:>7,}  {pct:>6.1f}%  {status}")

print()
print(f"  {'생성 예정 변수':<38}  {'기준 컬럼'}")
print(f"  {'-'*38}  {'-'*40}")
gen_basis = {
    "daily_max_demand":     "mlfd 일별 최대값",
    "date_key":             "datetime.dt.date",
    "month_key":            "datetime.dt.to_period('M')",
    "hour_of_day":          "datetime.dt.hour",
    "weekday":              "datetime.dt.dayofweek",
    "month_num":            "datetime.dt.month",
    "is_weekend":           "weekday >= 5",
    "is_holiday":           "holidays 라이브러리 (한국)",
    "is_before_holiday":    "is_holiday.shift(-24)",
    "is_after_holiday":     "is_holiday.shift(+24)",
    "hour_sin/cos":         "sin/cos(2π * hour / 24)",
    "month_sin/cos":        "sin/cos(2π * month / 12)",
    "smp_lag*":             "smp.shift(N)",
    "smp_roll_*":           "smp.rolling(W).agg()",
    "jlfd/slfd/mlfd_lag*":  "jlfd.shift(N) etc.",
    "*_diff_24":            "x - x.shift(24)",
    "*_pct_change_24":      "(x - x.shift(24)) / x.shift(24)",
}
for k, v in gen_basis.items():
    print(f"  {k:<38}  {v}")

print()
print("=" * 70)
print(f"  [X] 미확보 변수 ({len(missing)}개) - 추가 수집 필요")
print("=" * 70)
for c in missing:
    print(f"  {c}")

print()
print("=" * 70)
print("  CSV 파일 분석: energy-collector_industry_energy_ghg_...")
print("=" * 70)
df_csv = pd.read_csv(
    f"{BASE}/00.collector/data/manual/한국에너지공단_원본/energy-collector_industry_energy_ghg_한국에너지공단_산업부문 에너지사용 및 온실가스배출량 통계_20231231.csv",
    encoding="utf-8"
)
print(f"  Shape: {df_csv.shape}   단위: {df_csv['단위명'].unique().tolist()}")
print(f"  업종 ({df_csv['업종'].nunique()}개): {sorted(df_csv['업종'].unique())[:3]}...")
print(f"  연료명 ({df_csv['연료명'].nunique()}개): {df_csv['연료명'].unique()[:5].tolist()}...")
print()
print("  => 이 파일은 한국에너지공단 '산업부문 에너지사용 및 온실가스배출량' 연간 통계")
print("     (업종별 tCO2 기준 단면 데이터, 2023-12-31 기준)")
print("     supply_capacity / facility_capacity 등 시간별 전력수급 운영 변수 없음")
print()
print("  미수집 5개 실제 출처:")
print("    facility_capacity    : KPX 전력수급현황 이력 (sukub5m 일별 이력 API)")
print("    supply_capacity      : KPX 전력수급현황 이력")
print("    supply_reserve_power : KPX 전력수급현황 이력")
print("    supply_reserve_rate  : KPX 전력수급현황 이력")
print("    reserve_to_max_demand: supply_reserve_power / daily_max_demand (파생)")
