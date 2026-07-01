"""
00.collector/data/manual/industrial/ 폴더의 CSV 3개를 읽어 DB 테이블에 upsert.
'?' 값(광업 석탄 등 해당없음)은 NULL로 처리.
컬럼 위치(iloc) 기반 매핑.

대상 테이블 (schema.sql 기준, industry PK):
  표5-3-3 → industry_energy_by_source   표5-4-3 → industry_energy_trend
  표5-7-3 → industry_energy_by_firm_size
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import upsert, get_engine, query

engine = get_engine()
INDUSTRIAL = Path(__file__).resolve().parent.parent / "00.collector" / "data" / "manual" / "industrial"


def read_csv(filename: str) -> pd.DataFrame:
    path = INDUSTRIAL / filename
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    # 첫 열(업종명): 공백 정리
    df.iloc[:, 0] = df.iloc[:, 0].str.strip().str.replace(r"\s+", " ", regex=True)
    # 나머지 열: 쉼표 제거 → 숫자 변환 ('?' → NaN)
    for col in df.columns[1:]:
        df[col] = df[col].str.replace(",", "").replace("?", None)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load(table: str, df: pd.DataFrame, db_cols: list[str]) -> None:
    df = df.copy()
    df.columns = db_cols
    n = upsert(df, table, ["industry"], engine=engine)
    print(f"  [{table}] {n}행 upsert 완료")


# ── industry_energy_by_source (표5-3-3) ──────────────────────────────────────
# CSV: 업종 | 합계 | [합계비중 SKIP] | 석탄 | 석탄% | 석유 | 석유% |
#      도시가스 | 도시가스% | 기타 | 기타% | 열 | 열% | 전력 | 전력%
df_533 = read_csv("표5-3-3-1_산업부문_업종별_에너지_사용_현황_단위_천toe.csv")
df_533 = df_533.iloc[:, [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]]
load("industry_energy_by_source", df_533, [
    "industry", "total_ktoe",
    "coal_ktoe", "coal_pct",
    "oil_ktoe", "oil_pct",
    "city_gas_ktoe", "city_gas_pct",
    "other_energy_ktoe", "other_energy_pct",
    "heat_ktoe", "heat_pct",
    "electricity_ktoe", "electricity_pct",
])

# ── industry_energy_trend (표5-4-3) ──────────────────────────────────────────
# CSV: 업종 | '20년 | '21년 | '22년 | '23년 | '24년 |
#      '20→'21 | '21→'22 | '22→'23 | '23→'24 | CAGR
df_543 = read_csv("표5-4-3-1_산업부문_업종별_에너지_사용량_변화_단위_천toe.csv")
load("industry_energy_trend", df_543, [
    "industry",
    "energy_2020", "energy_2021", "energy_2022", "energy_2023", "energy_2024",
    "change_20_21", "change_21_22", "change_22_23", "change_23_24",
    "cagr_5yr_pct",
])

# ── industry_energy_by_firm_size (표5-7-3) ───────────────────────────────────
# CSV: 업종 | 업체수 | 합계 | [합계비중 SKIP] |
#      대기업 | 대기업% | 중견 | 중견% | 중소 | 중소% | 기타 | 기타%
df_573 = read_csv("표5-7-3-1_기업_규모_업종별_에너지_사용_현황_단위_천toe.csv")
df_573 = df_573.iloc[:, [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11]]
load("industry_energy_by_firm_size", df_573, [
    "industry", "company_count", "total_ktoe",
    "large_ktoe", "large_pct",
    "medium_ktoe", "medium_pct",
    "small_ktoe", "small_pct",
    "other_ktoe", "other_pct",
])

# ── 검증 ─────────────────────────────────────────────────────────────────────
print("\n완료. DB 확인:")
for t in ["industry_energy_by_source", "industry_energy_trend", "industry_energy_by_firm_size"]:
    n = query(f"SELECT COUNT(*) FROM {t}", engine=engine).iloc[0, 0]
    print(f"  {t}: {n}행")

# 샘플 검증 (산업부문전체 합계 에너지)
r = query("SELECT industry, total_ktoe FROM industry_energy_by_source WHERE industry = '산업부문 전체'", engine=engine)
print(f"\n  industry_energy_by_source 산업부문 전체 total_ktoe = {r.iloc[0,1]}")
r2 = query("SELECT industry, energy_2024 FROM industry_energy_trend WHERE industry = '화학'", engine=engine)
print(f"  industry_energy_trend 화학 energy_2024 = {r2.iloc[0,1]}")
r3 = query("SELECT industry, large_ktoe FROM industry_energy_by_firm_size WHERE industry = '정유'", engine=engine)
print(f"  industry_energy_by_firm_size 정유 large_ktoe = {r3.iloc[0,1]}")
