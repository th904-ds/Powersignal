"""GCS에서 HOME_전력수급_전력수급실적.csv 다운로드 및 내용 확인"""
import sys, io, os
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from google.cloud import storage

BASE = "c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
    f"{BASE}/00.collector/reference/contest-motie-5203a088a52a.json"
)

client = storage.Client()
bucket = client.bucket("powersignal-energy-data")
blob = bucket.blob("energy-collector/power_supply_today/HOME_전력수급_전력수급실적.csv")
content = blob.download_as_bytes()

df = pd.read_csv(io.BytesIO(content), encoding="cp949")

# 날짜 컬럼 생성
df["date"] = pd.to_datetime(
    df[["년", "월", "일"]].rename(columns={"년": "year", "월": "month", "일": "day"})
)

# 최소전력 콤마 제거 후 숫자 변환
df["최소전력(MW)"] = pd.to_numeric(
    df["최소전력(MW)"].astype(str).str.replace(",", ""), errors="coerce"
)

print("=== HOME_전력수급_전력수급실적.csv ===")
print(f"Shape: {df.shape}")
print(f"기간: {df['date'].min().date()} ~ {df['date'].max().date()}")
print(f"행 수: {len(df):,}일")
print()
print("샘플 (최신 5일):")
print(df[["date","설비용량(MW)","공급능력(MW)","최대전력(MW)","공급예비력(MW)","공급예비율(%)"]].head(5).to_string(index=False))
print()

# 2023-2025 구간 확인
df23 = df[(df["date"] >= "2023-01-01") & (df["date"] <= "2025-12-31")]
print(f"2023-2025 행 수: {len(df23)}일  (기대: 1,095일)")
print("2023-2025 결측:")
print(df23[["설비용량(MW)","공급능력(MW)","최대전력(MW)","공급예비력(MW)","공급예비율(%)"]].isnull().sum())
print()

# 연도별 행 수
print("연도별 행 수:")
print(df.groupby(df["date"].dt.year).size().to_string())
print()

# 모델 변수 매핑 확인
df["facility_capacity"]     = df["설비용량(MW)"]
df["supply_capacity"]       = df["공급능력(MW)"]
df["daily_max_demand"]      = df["최대전력(MW)"]
df["supply_reserve_power"]  = df["공급예비력(MW)"]
df["supply_reserve_rate"]   = df["공급예비율(%)"]
df["reserve_to_max_demand"] = df["공급예비력(MW)"] / df["최대전력(MW)"]

print("모델 변수 매핑 결과 샘플:")
cols = ["date","facility_capacity","supply_capacity","daily_max_demand",
        "supply_reserve_power","supply_reserve_rate","reserve_to_max_demand"]
print(df[cols].head(5).to_string(index=False))

# 로컬 저장
out = f"{BASE}/00.collector/data/processed/power_supply_today/HOME_전력수급_전력수급실적.csv"
with open(out, "wb") as f:
    f.write(content)
print(f"\n로컬 저장 완료: {out}")
