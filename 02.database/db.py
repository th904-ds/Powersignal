"""
DB 연결 & upsert 유틸리티.

사용법:
    from db import upsert, get_engine

    upsert(df, "smp_dayahead", pk_cols=["datetime", "area_name"])
"""
from __future__ import annotations

import io
import os
import logging
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# 프로젝트 루트 .env 로드 (02.database/의 상위 = 프로젝트 루트)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

log = logging.getLogger("powersignal.db")

# 한글 컬럼명 → DB 영문 컬럼명 매핑 (전 모듈 공통)
RENAME_FOR_DB: dict[str, str] = {
    # 발전원
    "gen_원자력":       "gen_nuclear",
    "gen_LNG":          "gen_lng",
    "gen_유연탄":       "gen_bituminous",
    "gen_무연탄":       "gen_anthracite",
    "gen_신재생·기타":  "gen_renewable",
    "gen_수력":         "gen_hydro",
    "gen_양수":         "gen_pumped",
    "gen_유전":         "gen_oil",
    # 발전원 비율
    "gen_원자력_ratio":      "gen_nuclear_ratio",
    "gen_LNG_ratio":         "gen_lng_ratio",
    "gen_유연탄_ratio":      "gen_bituminous_ratio",
    "gen_무연탄_ratio":      "gen_anthracite_ratio",
    "gen_신재생·기타_ratio": "gen_renewable_ratio",
    "gen_수력_ratio":        "gen_hydro_ratio",
    "gen_양수_ratio":        "gen_pumped_ratio",
    "gen_유전_ratio":        "gen_oil_ratio",
    # 연료비용
    "fuel_cost_LNG":    "fuel_cost_lng",
    "fuel_cost_유연탄": "fuel_cost_bituminous",
    "fuel_cost_무연탄": "fuel_cost_anthracite",
    "fuel_cost_유류":   "fuel_cost_oil",
    "fuel_cost_원자력": "fuel_cost_nuclear",
    # SMP 결정횟수
    "smp_decision_cnt_LNG": "smp_decision_cnt_lng",
    # 기상
    "avg_solar_MJm2": "avg_solar_mjm2",
    # sukub 5분단위 전력수급현황 (한글 컬럼명)
    "기준일시":         "datetime",
    "공급능력(MW)":     "supply_capacity",
    "현재수요(MW)":     "current_demand",
    "최대예측수요(MW)": "forecast_load",
    "공급예비력(MW)":   "supply_reserve_power",
    "공급예비율(%)":    "supply_reserve_rate",
    "운영예비력(MW)":   "operating_reserve_power",
    "운영예비율(%)":    "operating_reserve_rate",
    # 원시 API 필드명
    "areaName": "area_name",
    "areaNm":   "area_name",
    "fuelType": "fuel_type",
    "tradeDay": "trade_date",
}


def get_engine() -> Engine:
    url = os.getenv("PG_URL")
    if not url:
        raise RuntimeError(
            "PG_URL 이 설정되지 않았습니다. "
            "프로젝트 루트 .env 파일에 PG_URL=postgresql://... 를 추가하세요."
        )
    return create_engine(url, pool_pre_ping=True)


def rename_for_db(df: pd.DataFrame) -> pd.DataFrame:
    """한글/원본 컬럼명을 DB 영문 컬럼명으로 일괄 변환."""
    return df.rename(columns={k: v for k, v in RENAME_FOR_DB.items() if k in df.columns})


def upsert(
    df: pd.DataFrame,
    table: str,
    pk_cols: list[str],
    engine: Engine | None = None,
    batch_size: int = 50_000,
) -> int:
    """
    DataFrame을 PostgreSQL 테이블에 upsert (COPY 기반 bulk insert).
    임시 테이블에 COPY로 적재 후 INSERT ... ON CONFLICT DO UPDATE로 반영한다.
    행 단위 파라미터 바인딩 INSERT보다 대용량(수만~수십만 행) 테이블에서 훨씬 빠르다.
    반환값: 처리된 총 행 수.
    """
    if df.empty:
        return 0

    if engine is None:
        engine = get_engine()

    df = rename_for_db(df)

    col_names = list(df.columns)
    non_pk = [c for c in col_names if c not in pk_cols]

    if not non_pk:
        raise ValueError(f"pk_cols 외 업데이트할 컬럼이 없습니다: {col_names}")

    col_sql = ", ".join(f'"{c}"' for c in col_names)
    pk_sql  = ", ".join(f'"{c}"' for c in pk_cols)
    upd_sql = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in non_pk)
    tmp     = f"_tmp_{table}"

    total = 0
    for start in range(0, len(df), batch_size):
        raw_chunk = df.iloc[start : start + batch_size]
        chunk = raw_chunk.where(raw_chunk.notna(), None)

        raw = engine.raw_connection()
        try:
            cur = raw.cursor()
            cur.execute("SET statement_timeout = 0")
            cur.execute(f'DROP TABLE IF EXISTS "{tmp}"')
            cur.execute(f'CREATE TEMP TABLE "{tmp}" (LIKE "{table}" INCLUDING DEFAULTS)')

            buf = io.StringIO()
            chunk.to_csv(buf, index=False, header=False, na_rep="\\N")
            buf.seek(0)
            cur.copy_expert(
                f'COPY "{tmp}" ({col_sql}) FROM STDIN WITH (FORMAT csv, NULL \'\\N\')',
                buf,
            )

            cur.execute(
                f'INSERT INTO "{table}" ({col_sql}) '
                f'SELECT {col_sql} FROM "{tmp}" '
                f'ON CONFLICT ({pk_sql}) DO UPDATE SET {upd_sql}'
            )
            total += cur.rowcount
            raw.commit()
        finally:
            raw.close()

    log.info("upsert %s: %d행 완료", table, total)
    return total


def query(sql_str: str, engine: Engine | None = None) -> pd.DataFrame:
    """간단한 SELECT 쿼리 → DataFrame."""
    if engine is None:
        engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql_str), conn)
