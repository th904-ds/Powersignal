"""
EDA Step 5 — Model 1 vs Model 2 입력 변수 최종 점검
  - EDA 1~4 발견사항 반영
  - 변수별 상태: 확보완료 / 생성필요 / 결측처리필요 / 제거권고
  - Model 1 vs Model 2 차이 명시
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path("c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal")

WEATHER = ["temp_c", "humidity_pct", "wind_speed_ms", "dew_point_c"]

df = pd.read_parquet(BASE / "00.collector/data/features/base_merged.parquet")
df["datetime"] = pd.to_datetime(df["datetime"])
df23 = df[(df["datetime"] >= "2023-01-01") & (df["datetime"] < "2026-01-01")].copy()
df23 = df23.drop(columns=[c for c in WEATHER if c in df23.columns])

N = len(df23)

# ── 변수 정의 ──────────────────────────────────────────────────────────

# EDA 발견: 상수 변수 (정보 없음)
CONST_VARS = ["fuel_cost_무연탄", "fuel_cost_원자력"]

# EDA 발견: jlfd = slfd - mlfd (완전 선형종속)
COLLINEAR_NOTE = {"jlfd": "slfd - mlfd (파생, 선형종속)"}

# 현재 base_merged에 있는 변수 (기상 제외)
HAVE = [c for c in df23.columns
        if c not in ["datetime"] + WEATHER
        and not c.startswith("_")]

# Model 1 & 2 공통 원시변수 (래그/롤링 제외)
COMMON_RAW = [
    # 타깃
    "smp",
    # 수요예측
    "jlfd", "slfd", "mlfd",
    # 발전원별 (절대량)
    "gen_원자력", "gen_LNG", "gen_유연탄", "gen_무연탄",
    "gen_신재생·기타", "gen_수력", "gen_양수", "gen_유전", "gen_total",
    # 발전원 비중
    "gen_원자력_ratio", "gen_LNG_ratio", "gen_유연탄_ratio", "gen_무연탄_ratio",
    "gen_신재생·기타_ratio", "gen_수력_ratio", "gen_양수_ratio", "gen_유전_ratio",
    # 연료비
    "fuel_cost_LNG", "fuel_cost_유연탄", "fuel_cost_무연탄",
    "fuel_cost_유류", "fuel_cost_원자력",
    # SMP 결정 횟수
    "smp_decision_cnt_LNG",
    # 전력수급
    "facility_capacity", "supply_capacity", "daily_max_demand",
    "supply_reserve_power", "supply_reserve_rate", "reserve_to_max_demand",
    # 기상 (별도 처리 예정)
    # "temp_c", "humidity_pct", "wind_speed_ms", "dew_point_c",
]

# 전처리 생성 변수
DATETIME_FEATS = [
    "date_key", "month_key",
    "hour_of_day", "weekday", "month_num", "is_weekend",
    "is_holiday", "is_before_holiday", "is_after_holiday",
    "hour_sin", "hour_cos", "month_sin", "month_cos",
]

LOAD_LAG_FEATS = [
    "jlfd_lag24", "jlfd_lag168",
    "slfd_lag24", "slfd_lag168",
    "mlfd_lag24", "mlfd_lag168",
    "jlfd_diff_24", "jlfd_pct_change_24",
    "slfd_diff_24", "slfd_pct_change_24",
    "mlfd_diff_24", "mlfd_pct_change_24",
]

# Model 1 전용 (SMP 자기회귀)
SMP_LAG_FEATS = [
    "smp_lag1", "smp_lag24", "smp_lag48", "smp_lag72", "smp_lag168", "smp_lag336",
]
SMP_ROLL_FEATS = [
    "smp_roll_mean_24", "smp_roll_mean_168",
    "smp_roll_std_24",  "smp_roll_std_168",
    "smp_roll_max_24",  "smp_roll_min_24",
    "smp_roll_max_168", "smp_roll_min_168",
]

# ── 결측률 계산 ───────────────────────────────────────────────────────
def miss_pct(col):
    if col not in df23.columns:
        return None
    return df23[col].isnull().mean() * 100

# ── 출력 헬퍼 ─────────────────────────────────────────────────────────
SEP = "─" * 75

def print_block(title, vars_list, model_tag="공통"):
    print(f"\n{'━'*75}")
    print(f"  {title}  [{model_tag}]")
    print(f"{'━'*75}")
    fmt = "  {:<38}  {:>6}  {:<10}  {}"
    print(fmt.format("변수명", "결측률", "상태", "비고"))
    print(f"  {SEP}")
    for col in vars_list:
        pct = miss_pct(col)
        if pct is None:
            status = "[생성예정]"
            pct_str = "  -   "
            note = ""
        elif col in CONST_VARS:
            status = "[제거권고]"
            pct_str = f"{pct:5.1f}%"
            note = "EDA4: 상수 (unique=1, 정보없음)"
        elif pct > 10:
            status = "[보간필요]"
            pct_str = f"{pct:5.1f}%"
            note = "API 공백 21구간 175일"
        elif pct > 0:
            status = "[미소결측]"
            pct_str = f"{pct:5.1f}%"
            note = ""
        else:
            status = "[확보완료]"
            pct_str = "  0.0%"
            note = ""

        if col in COLLINEAR_NOTE:
            note = f"EDA: {COLLINEAR_NOTE[col]}"

        print(fmt.format(col, pct_str, status, note))

# ══════════════════════════════════════════════════════════════════════
print("=" * 75)
print("  EDA Step 5 — Model 1 / Model 2 변수 최종 점검")
print("=" * 75)
print(f"  분석 기간  : 2023-01-01 ~ 2025-12-31")
print(f"  총 행 수   : {N:,}  /  기대 26,304 (충족률 {N/26304*100:.0f}%)")
print(f"  기상 변수  : 별도 처리 예정 (이 점검에서 제외)")

# ── 공통 원시변수 ─────────────────────────────────────────────────────
print_block("공통 원시변수 (Model 1 & 2)", COMMON_RAW, "공통")

# ── 전처리 생성: datetime ─────────────────────────────────────────────
print_block("전처리 생성 — datetime / 공휴일 피처", DATETIME_FEATS, "공통")

# ── 전처리 생성: load lag ─────────────────────────────────────────────
print_block("전처리 생성 — 수요예측 래그/차분", LOAD_LAG_FEATS, "공통")

# ── Model 1 전용 ──────────────────────────────────────────────────────
print_block("전처리 생성 — SMP 래그", SMP_LAG_FEATS, "Model 1 전용")
print_block("전처리 생성 — SMP 롤링 통계", SMP_ROLL_FEATS, "Model 1 전용")

# ── 요약 카운트 ───────────────────────────────────────────────────────
all_common = COMMON_RAW + DATETIME_FEATS + LOAD_LAG_FEATS
all_m1     = all_common + SMP_LAG_FEATS + SMP_ROLL_FEATS

have_count   = sum(1 for c in COMMON_RAW if miss_pct(c) == 0.0)
interp_count = sum(1 for c in COMMON_RAW if miss_pct(c) is not None and miss_pct(c) > 10)
const_count  = sum(1 for c in COMMON_RAW if c in CONST_VARS)
gen_count    = sum(1 for c in DATETIME_FEATS + LOAD_LAG_FEATS + SMP_LAG_FEATS + SMP_ROLL_FEATS)

print(f"\n{'━'*75}")
print(f"  변수 수 요약")
print(f"{'━'*75}")
print(f"  공통 원시변수   : {len(COMMON_RAW)}개")
print(f"    확보완료      : {have_count}개")
print(f"    보간필요(gen) : {interp_count}개   ← 12.8% 결측, 전처리 1순위")
print(f"    제거권고      : {const_count}개   ← fuel_cost_무연탄·원자력 (상수)")
print(f"  전처리 생성예정 : {gen_count}개")
print(f"    datetime/공휴일 : {len(DATETIME_FEATS)}개")
print(f"    수요 래그/차분  : {len(LOAD_LAG_FEATS)}개")
print(f"    SMP 자기회귀   : {len(SMP_LAG_FEATS+SMP_ROLL_FEATS)}개 (Model 1 전용)")
print(f"\n  Model 1 최종 변수 수 : {len(all_m1)}개  (기상 4개 + 추후 추가 예정)")
print(f"  Model 2 최종 변수 수 : {len(all_common)}개  (SMP 자기회귀 14개 제외)")

# ── EDA 전체 액션 아이템 ──────────────────────────────────────────────
print(f"\n{'━'*75}")
print(f"  EDA 전체 발견사항 → 전처리 액션 아이템")
print(f"{'━'*75}")
items = [
    ("P1", "gen 5종 결측 보간",
     "gen_LNG/원자력/유연탄/무연탄/유전 12.8% (API 공백)\n"
     "       → 시간 선형 보간 후 일합산-24h 반복 (모델팀 동일 방식)"),
    ("P2", "fuel_cost 상수 변수 처리",
     "fuel_cost_무연탄·원자력 unique=1, std=0\n"
     "       → 모델팀과 협의 후 제거 or 유지 결정"),
    ("P3", "jlfd 선형종속 명시",
     "jlfd = slfd - mlfd (100% 일치)\n"
     "       → 모델 파켓과 동일하게 세 변수 유지. SHAP 해석 시 중복 인지 필요"),
    ("P4", "SMP 이상치(spike) 처리",
     "상위 0.5%(≥272.7원) 132시간, 최대 310.4원\n"
     "       → clip 여부는 모델 개발자와 협의"),
    ("P5", "기상 4종 별도 처리",
     "매일 00:00 1시간 구조적 결측 (startHh=01 설정)\n"
     "       → 시간 선형 보간으로 해결, 별도 처리"),
    ("P6", "SMP lag/rolling 생성",
     "lag 1,24,48,72,168,336h + rolling 8종\n"
     "       → ACF로 근거 확인 완료"),
    ("P7", "datetime / 공휴일 피처 생성",
     "hour_sin/cos, month_sin/cos, is_holiday 등 13개"),
    ("P8", "수요예측 래그/차분 생성",
     "jlfd/slfd/mlfd 각 lag24, lag168, diff24, pct_change24"),
]
for prio, title, desc in items:
    print(f"\n  [{prio}] {title}")
    print(f"       {desc}")

print(f"\n{'━'*75}")
print(f"  전처리 우선순위: P1(gen 보간) → P5(기상 별도) → P6~P8(피처 생성) → P2/P3/P4(협의사항)")
print(f"{'━'*75}")
