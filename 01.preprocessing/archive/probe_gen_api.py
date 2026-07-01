"""
gen_by_source_hist API 현황 탐침
  - page 1만 호출해서 totalCount와 최신 날짜 확인
  - 기존 parquet (20260608) totalCount=278,424 과 비교
  - 결측 날짜 중 1개(2024-01-05)가 API에 있는지 spot-check
"""
import sys, os, json
sys.stdout.reconfigure(encoding="utf-8")

import requests
import pandas as pd
from pathlib import Path

BASE = Path("c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal")
PROC = BASE / "00.collector/data/processed/gen_by_source_hist"

SERVICE_KEY = "d47f78e731dc70b60955f50d7cd2e0b21c388bdee5c1b4400c01cb91978e9209"
URL = "https://apis.data.go.kr/B552115/PvAmountByPwrGen/getPvAmountByPwrGen"

# ── 1. 기존 parquet 현황 ────────────────────────────────────────────
files = sorted(f for f in os.listdir(PROC) if f.endswith(".parquet"))
print(f"기존 parquet: {files}")

df_old = pd.read_parquet(PROC / files[0])
df_old["datetime"] = pd.to_datetime(df_old["tradeYmd"].astype(str), format="%Y%m%d", errors="coerce") \
                    + pd.to_timedelta(df_old["tradeNo"].astype(int), unit="h")

print(f"기존 총행수  : {len(df_old):,}")
print(f"기존 기간    : {df_old['datetime'].min()} ~ {df_old['datetime'].max()}")

# 연료원별 행 수
print("\n기존 연료원별 행 수:")
for fuel in sorted(df_old["fuelTpCd"].unique()):
    cnt = (df_old["fuelTpCd"] == fuel).sum()
    print(f"  {fuel:<15}: {cnt:,}")

# ── 2. API page 1 호출 → totalCount 확인 ────────────────────────────
print("\n" + "="*60)
print("API 현재 totalCount 확인 (page 1)")
print("="*60)

params = {
    "serviceKey": SERVICE_KEY,
    "dataType":   "json",
    "numOfRows":  1,   # 1건만 → totalCount 확인용
    "pageNo":     1,
}

try:
    r = requests.get(URL, params=params, timeout=15)
    r.raise_for_status()
    body = r.json()

    resp = body.get("response", body)
    header = resp.get("header", {})
    b      = resp.get("body", {})

    total_count = int(b.get("totalCount", -1))
    result_code = header.get("resultCode", "?")
    result_msg  = header.get("resultMsg", "?")

    print(f"resultCode  : {result_code}")
    print(f"resultMsg   : {result_msg}")
    print(f"totalCount  : {total_count:,}")
    print(f"기존 행수   : {len(df_old):,}")
    print(f"차이        : {total_count - len(df_old):+,}")

    # 첫 번째 아이템 확인
    items = b.get("items", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    if items:
        print(f"\n첫 번째 항목 샘플: {items[0]}")

except Exception as e:
    print(f"API 호출 오류: {e}")
    total_count = -1

# ── 3. 결측 날짜 spot-check ────────────────────────────────────────
# LNG 기준으로 2023-2025 결측 구간 확인
print("\n" + "="*60)
print("결측 구간 확인 (LNG, 2023-2025)")
print("="*60)

lng_old = df_old[(df_old["fuelTpCd"] == "LNG") &
                 (df_old["datetime"] >= "2023-01-01") &
                 (df_old["datetime"] < "2026-01-01")]

expected = pd.date_range("2023-01-01 01:00", "2026-01-01 00:00", freq="h")
missing  = sorted(set(expected) - set(lng_old["datetime"]))
miss_days = sorted(set(pd.Series(missing).dt.normalize()))
print(f"LNG 결측 시간수: {len(missing):,}개 / {len(miss_days)}일")

# 연속 구간 찾기
from itertools import groupby
from datetime import timedelta

ranges = []
for k, g in groupby(enumerate(miss_days), lambda x: x[1] - timedelta(days=x[0])):
    group = list(g)
    ranges.append((group[0][1], group[-1][1]))

print(f"결측 구간 ({len(ranges)}개):")
for s, e in ranges:
    days = (e - s).days + 1
    print(f"  {s.date()} ~ {e.date()} ({days}일)")

# ── 4. 재수집 여부 판정 ────────────────────────────────────────────
print("\n" + "="*60)
print("판정")
print("="*60)

OLD_COUNT = len(df_old)
if total_count > OLD_COUNT:
    extra = total_count - OLD_COUNT
    print(f"[증가] API에 {extra:,}행 추가됨 → 재수집하면 일부 결측 해소 가능")
    print("  → 권장: 수집기 재실행 (20260620 단위 신규 수집)")
elif total_count == OLD_COUNT:
    print(f"[동일] totalCount={total_count:,} 기존과 동일")
    print("  → API 자체에 결측 구간 데이터 없음, 재수집해도 동일")
    print("  → 대안: 결측 구간 보간 또는 다른 출처 탐색")
elif total_count < 0:
    print("[미확인] API 응답 파싱 실패 - 재시도 필요")
else:
    print(f"[감소?] totalCount={total_count:,} < 기존 {OLD_COUNT:,} → 이상")
