"""
00.collector/data/manual/regional/ 폴더의 CSV 5개를 읽어 DB 테이블에 upsert.
컬럼 이름이 한글이므로 위치(iloc) 기반으로 매핑.

대상 테이블 (schema.sql 기준, region PK):
  표5-3-5 → region_energy_by_source   표5-4-5 → region_energy_trend
  표5-7-5 → region_energy_by_firm_size
  표5-6-5 → national_complex_energy (국가·일반 산단)
  표5-6-2 → industrial_complex_energy (전체 산단)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import upsert, get_engine

engine = get_engine()
REGIONAL = Path(__file__).resolve().parent.parent / "00.collector" / "data" / "manual" / "regional"


def read_csv(filename: str) -> pd.DataFrame:
    path = REGIONAL / filename
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    # 천 단위 쉼표 제거 후 숫자 변환 (region 열은 제외)
    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col].str.replace(",", ""), errors="coerce")
    # region 문자열 정리 (공백 통일)
    df.iloc[:, 0] = df.iloc[:, 0].str.strip().str.replace(r"\s+", "", regex=True)
    return df


def load(table: str, df: pd.DataFrame, db_cols: list[str]) -> None:
    df.columns = db_cols
    n = upsert(df, table, ["region"], engine=engine)
    print(f"  [{table}] {n}행 upsert 완료")


# ── region_energy_by_source (표5-3-5) ────────────────────────────────────────
# CSV:  지역 | 합계 | [합계비중 SKIP] | 석탄 | 석탄% | 석유 | 석유% |
#       도시가스 | 도시가스% | 기타 | 기타% | 열 | 열% | 전력 | 전력%
df_535 = read_csv("표5-3-5-1_산업부문_지역별_에너지_사용_현황_단위_천toe.csv")
df_535 = df_535.iloc[:, [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]]
load("region_energy_by_source", df_535, [
    "region", "total_ktoe",
    "coal_ktoe", "coal_pct",
    "oil_ktoe", "oil_pct",
    "city_gas_ktoe", "city_gas_pct",
    "other_energy_ktoe", "other_energy_pct",
    "heat_ktoe", "heat_pct",
    "electricity_ktoe", "electricity_pct",
])

# ── region_energy_trend (표5-4-5) ────────────────────────────────────────────
# CSV:  지역 | '20년 | '21년 | '22년 | '23년 | '24년 |
#       '20→'21 | '21→'22 | '22→'23 | '23→'24 | CAGR
df_545 = read_csv("표5-4-5-1_산업부문_지역별_에너지_사용량_변화_단위_천toe.csv")
load("region_energy_trend", df_545, [
    "region",
    "energy_2020", "energy_2021", "energy_2022", "energy_2023", "energy_2024",
    "change_20_21", "change_21_22", "change_22_23", "change_23_24",
    "cagr_5yr_pct",
])

# ── region_energy_by_firm_size (표5-7-5) ─────────────────────────────────────
# CSV:  지역 | 업체수 | 합계 | [합계비중 SKIP] |
#       대기업 | 대기업% | 중견 | 중견% | 중소 | 중소% | 기타 | 기타%
df_575 = read_csv("표5-7-5-1_기업_규모_지역별_에너지_사용_현황_단위_천toe.csv")
df_575 = df_575.iloc[:, [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11]]
load("region_energy_by_firm_size", df_575, [
    "region", "company_count", "total_ktoe",
    "large_ktoe", "large_pct",
    "medium_ktoe", "medium_pct",
    "small_ktoe", "small_pct",
    "other_ktoe", "other_pct",
])

# ── national_complex_energy (표5-6-5, 국가·일반 산업단지) ───────────────────
# CSV:  지역 | 산단수 | 업체수 | 합계 | [합계비중 SKIP] |
#       석탄 | 석탄% | 석유 | 석유% | 도시가스 | 도시가스% |
#       기타 | 기타% | 열 | 열% | 전력 | 전력%
df_565 = read_csv("표5-6-5-1_국가_및_일반_산업단지_지역별_에너지_사용_현황_단위_천toe.csv")
df_565 = df_565.iloc[:, [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]]
load("national_complex_energy", df_565, [
    "region", "complex_count", "company_count", "total_ktoe",
    "coal_ktoe", "coal_pct",
    "oil_ktoe", "oil_pct",
    "city_gas_ktoe", "city_gas_pct",
    "other_energy_ktoe", "other_energy_pct",
    "heat_ktoe", "heat_pct",
    "electricity_ktoe", "electricity_pct",
])

# ── industrial_complex_energy (표5-6-2, 전체 산업단지) ───────────────────────
df_562 = read_csv("표5-6-2-1_산업단지_지역별_에너지_사용_현황_단위_천toe.csv")
df_562 = df_562.iloc[:, [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]]
load("industrial_complex_energy", df_562, [
    "region", "complex_count", "company_count", "total_ktoe",
    "coal_ktoe", "coal_pct",
    "oil_ktoe", "oil_pct",
    "city_gas_ktoe", "city_gas_pct",
    "other_energy_ktoe", "other_energy_pct",
    "heat_ktoe", "heat_pct",
    "electricity_ktoe", "electricity_pct",
])

# ── 검증 ─────────────────────────────────────────────────────────────────────
print("\n완료. DB 행 수 확인:")
from db import query
for t in ["region_energy_by_source", "region_energy_trend", "region_energy_by_firm_size",
          "national_complex_energy", "industrial_complex_energy"]:
    n = query(f"SELECT COUNT(*) FROM {t}", engine=engine).iloc[0, 0]
    print(f"  {t}: {n}행")
