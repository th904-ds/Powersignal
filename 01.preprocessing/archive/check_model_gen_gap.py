"""
레퍼런스 모델 파켓의 gen 결측 구간 확인
  - 우리 API에서 빠진 175일에 모델파켓이 어떤 값을 가지는지
  - 모델팀이 보간했는지 vs 동일하게 결측인지
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from pathlib import Path

BASE = Path("c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal")

df_model = pd.read_parquet(BASE / "01.preprocessing/archive/smp_master_model1_performance2.parquet")
df_model["datetime"] = pd.to_datetime(df_model["datetime"])

print(f"모델 파켓: {df_model.shape}, {df_model['datetime'].min()} ~ {df_model['datetime'].max()}")
print()

# 우리 API에서 확인된 결측 구간 (LNG = 원자력 = 유연탄 = 무연탄 = 유전)
MISSING_RANGES = [
    ("2023-11-22", "2023-11-23"),
    ("2023-12-21", "2024-01-14"),
    ("2024-01-25", "2024-01-29"),
    ("2024-02-01", "2024-02-04"),
    ("2024-02-15", "2024-02-16"),
    ("2024-02-22", "2024-02-25"),
    ("2024-03-06", "2024-03-16"),
    ("2024-03-21", "2024-04-07"),
    ("2024-04-11", "2024-04-12"),
    ("2024-04-19", "2024-04-29"),
    ("2024-05-01", "2024-05-13"),
    ("2024-05-16", "2024-05-17"),
    ("2024-05-22", "2024-06-01"),
    ("2024-06-13", "2024-06-16"),
    ("2024-06-19", "2024-07-15"),
    ("2024-07-18", "2024-07-22"),
    ("2024-07-26", "2024-07-27"),
    ("2024-08-01", "2024-08-04"),
    ("2024-09-11", "2024-09-17"),
    ("2025-07-13", "2025-07-27"),
    ("2026-01-01", "2026-01-01"),
]

# 모델파켓에 gen_LNG 가 있는지
gen_col = "gen_LNG" if "gen_LNG" in df_model.columns else None
if gen_col is None:
    gen_candidates = [c for c in df_model.columns if "gen" in c.lower() and "lng" in c.lower()]
    print(f"gen_LNG 없음. 후보: {gen_candidates}")
    gen_col = gen_candidates[0] if gen_candidates else None

if gen_col is None:
    print("gen 관련 컬럼 없음 - 컬럼 목록:")
    gen_cols = [c for c in df_model.columns if c.startswith("gen")]
    print(gen_cols)
    sys.exit()

print(f"확인 컬럼: {gen_col}")
print(f"{'구간':<30}  {'모델 행수':>8}  {'결측수':>6}  {'결측률':>6}  {'샘플값'}")
print("-" * 80)

total_model_rows = 0
total_missing    = 0

for start, end in MISSING_RANGES:
    mask = (df_model["datetime"] >= start) & (df_model["datetime"] <= end + " 23:59")
    sub  = df_model[mask]
    n    = len(sub)
    nm   = sub[gen_col].isnull().sum()
    pct  = nm / n * 100 if n > 0 else 0
    sample = sub[gen_col].dropna().iloc[:1].values[0] if nm < n else "NaN"
    print(f"  {start} ~ {end}  {n:>8,}  {nm:>6,}  {pct:>5.0f}%  {sample}")
    total_model_rows += n
    total_missing    += nm

print("-" * 80)
print(f"  합계                              {total_model_rows:>8,}  {total_missing:>6,}")
print()

# 모델 파켓 전체 gen_LNG 결측률
print(f"모델파켓 전체 {gen_col} 결측: {df_model[gen_col].isnull().sum():,} / {len(df_model):,} "
      f"({df_model[gen_col].isnull().mean()*100:.1f}%)")

# 2023-2025 gen_LNG 결측
sub23 = df_model[(df_model["datetime"] >= "2023-01-01") & (df_model["datetime"] < "2026-01-01")]
nm23  = sub23[gen_col].isnull().sum()
print(f"2023-2025 {gen_col} 결측: {nm23:,} / {len(sub23):,} ({nm23/len(sub23)*100:.1f}%)")
print()

# 결론
if total_missing == total_model_rows:
    print("[결론] 모델파켓도 동일하게 결측 → 모델팀도 이 구간에 gen 없음")
    print("       → LightGBM NaN 처리 방식 사용 or 보간 필요")
elif total_missing == 0:
    print("[결론] 모델파켓은 결측 없음 → 모델팀이 보간/대체값 적용함")
    print("       → 동일한 방식으로 보간 적용 필요")
else:
    print(f"[결론] 일부 결측: {total_missing}/{total_model_rows}행 결측")
    print("       → 모델팀이 부분적으로 보간함")
