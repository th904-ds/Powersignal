"""gen_by_source_hist 결측 구간 정밀 진단"""
import pandas as pd, sys
sys.stdout.reconfigure(encoding="utf-8")

BASE = "c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal"
PROC = f"{BASE}/00.collector/data/processed/gen_by_source_hist"

# raw parquet 로드
import os
files = sorted(f for f in os.listdir(PROC) if f.endswith(".parquet"))
print(f"parquet 파일 수: {len(files)}  →  {files}")

df = pd.read_parquet(f"{PROC}/{files[0]}")

# datetime 재구성 (tradeYmd YYYYMMDD + tradeNo 01-24)
df["hour"] = df["tradeNo"].astype(int)
df["datetime"] = pd.to_datetime(df["tradeYmd"].astype(str), format="%Y%m%d", errors="coerce") \
                 + pd.to_timedelta(df["hour"], unit="h")

print(f"\n전체 raw: {len(df):,}행  {df['datetime'].min()} ~ {df['datetime'].max()}")
print(f"fuelTpCd unique: {sorted(df['fuelTpCd'].unique())}")

# 연료원별 datetime 커버리지
print("\n=== 연료원별 수집 기간 ===")
for fuel in sorted(df["fuelTpCd"].unique()):
    sub = df[df["fuelTpCd"] == fuel]
    print(f"  {fuel:<15}  {sub['datetime'].min()} ~ {sub['datetime'].max()}  ({len(sub):,}행)")

# 2023-2025 구간에서 LNG 기준 결측 날짜 파악
print("\n=== LNG 기준 2023-2025 결측 분석 ===")
lng = df[(df["fuelTpCd"] == "LNG") &
         (df["datetime"] >= "2023-01-01") &
         (df["datetime"] < "2026-01-01")].copy()

# 기대 datetime 집합: 2023-01-01 01:00 ~ 2025-12-31 24:00
expected = pd.date_range("2023-01-01 01:00", "2026-01-01 00:00", freq="h")
have     = set(lng["datetime"])
missing  = sorted(set(expected) - have)

print(f"  기대: {len(expected):,}개  실제: {len(have):,}개  결측: {len(missing):,}개")

if missing:
    miss_dates = pd.Series(missing)
    # 연속 구간으로 묶기
    miss_days = sorted(set(miss_dates.dt.normalize()))
    print(f"\n  결측 날짜 수: {len(miss_days)}일")

    # 연속 구간 찾기
    from itertools import groupby
    from datetime import timedelta

    ranges = []
    for k, g in groupby(enumerate(miss_days), lambda x: x[1] - timedelta(days=x[0])):
        group = list(g)
        ranges.append((group[0][1], group[-1][1]))

    print(f"  연속 구간 수: {len(ranges)}개")
    for s, e in ranges:
        days = (e - s).days + 1
        print(f"    {s.date()} ~ {e.date()}  ({days}일)")

# 원자력과 비교 (원자력도 동일한 패턴인지)
print("\n=== 원자력 기준 2023-2025 결측 ===")
nuc = df[(df["fuelTpCd"] == "원자력") &
         (df["datetime"] >= "2023-01-01") &
         (df["datetime"] < "2026-01-01")].copy()
nuc_missing = sorted(set(expected) - set(nuc["datetime"]))
print(f"  결측: {len(nuc_missing):,}개  (LNG와 동일: {sorted(nuc_missing) == sorted(missing)})")

# 신재생과 비교 (신재생은 결측 적음)
print("\n=== 신재생·기타 기준 2023-2025 결측 ===")
ren = df[(df["fuelTpCd"] == "신재생·기타") &
         (df["datetime"] >= "2023-01-01") &
         (df["datetime"] < "2026-01-01")].copy()
ren_missing = sorted(set(expected) - set(ren["datetime"]))
print(f"  결측: {len(ren_missing):,}개")
if ren_missing:
    print(f"  결측 datetime 샘플: {ren_missing[:10]}")

# tradeYmd 형식 재확인 — API가 어떤 날짜 범위를 지원하는지
print("\n=== tradeYmd 분포 확인 ===")
df["date_only"] = df["tradeYmd"].astype(str)
print(df.groupby("fuelTpCd")["date_only"].agg(["min","max","count"]).to_string())
