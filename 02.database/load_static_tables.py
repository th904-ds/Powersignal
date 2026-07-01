"""
solar_wind_by_region (지역별 시간별 태양광·풍력 발전량, 2017~2025 정적) 적재 스크립트.

dr_plus/dr_voluntary는 job_daily_collect가 매일 자동 수집·upsert하므로
여기서는 다루지 않음(과거 하드코딩 스냅샷 로더는 제거됨).

실행: python 02.database/load_static_tables.py
"""

import sys, pathlib, io
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pandas as pd
import numpy as np
from db import get_engine
from sqlalchemy import text

BASE   = pathlib.Path(__file__).resolve().parents[1]
DATA   = BASE / "00.collector" / "data" / "processed"
engine = get_engine()

DATE_FROM = pd.Timestamp("2023-01-01").date()   # 프론트에 필요한 최소 기간


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼: COPY 방식 bulk upsert (빠른 적재)
# ─────────────────────────────────────────────────────────────────────────────

def _bulk_upsert(table: str, df: pd.DataFrame, pk: list[str],
                 chunk_col: str = None, chunk_size: int = 10_000) -> int:
    """
    1) 임시 테이블에 COPY → 2) INSERT … ON CONFLICT DO UPDATE
    chunk_col 지정 시 해당 컬럼 기준으로 청크 분할 (Supabase timeout 회피).
    """
    if df.empty:
        return 0

    # 청크가 없으면 전체를 한 번에
    if chunk_col is None or chunk_col not in df.columns:
        chunks = [df]
    else:
        # chunk_col 고유값 기준으로 묶음
        uniq = sorted(df[chunk_col].unique())
        chunks = [df[df[chunk_col].isin(uniq[i:i+chunk_size])]
                  for i in range(0, len(uniq), chunk_size)]

    cols    = list(df.columns)
    tmp     = f"_tmp_{table}"
    pk_str  = ", ".join(pk)
    col_str = ", ".join(cols)
    upd     = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in pk)
    total   = 0

    for chunk in chunks:
        chunk = chunk.where(chunk.notna(), other=None)
        raw = engine.raw_connection()
        try:
            cur = raw.cursor()
            cur.execute("SET statement_timeout = 0")   # Supabase timeout 비활성화

            cur.execute(f"DROP TABLE IF EXISTS {tmp}")
            cur.execute(f"CREATE TEMP TABLE {tmp} (LIKE {table} INCLUDING DEFAULTS)")

            buf = io.StringIO()
            chunk.to_csv(buf, index=False, header=False, na_rep="\\N")
            buf.seek(0)
            cur.copy_expert(
                f"COPY {tmp} ({col_str}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
                buf
            )

            cur.execute(
                f"INSERT INTO {table} ({col_str}) "
                f"SELECT {col_str} FROM {tmp} "
                f"ON CONFLICT ({pk_str}) DO UPDATE SET {upd}"
            )
            total += cur.rowcount
            raw.commit()
        finally:
            raw.close()

    return total


# ─────────────────────────────────────────────────────────────────────────────
# 1. solar_wind_by_region
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_solar_file(f: pathlib.Path) -> pd.DataFrame | None:
    df = pd.read_parquet(f)
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()

    # 날짜
    for src in ("거래일자", "거래일"):
        if src in df.columns:
            df.rename(columns={src: "trade_date"}, inplace=True); break
    # 시간
    for src in ("거래시간", "시간"):
        if src in df.columns:
            df.rename(columns={src: "trade_hour"}, inplace=True); break
    # 지역
    for src in ("지역", "지역세부구분", "지역명"):
        if src in df.columns:
            df.rename(columns={src: "region"}, inplace=True); break

    if not {"trade_date", "trade_hour", "region"}.issubset(df.columns):
        print(f"    [SKIP] {f.name}: 필수 컬럼 없음")
        return None

    # 날짜 파싱 후 DATE_FROM 이후만
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
    df = df[df["trade_date"] >= DATE_FROM]
    if df.empty:
        print(f"    [SKIP] {f.name}: {DATE_FROM} 이전 데이터만 존재")
        return None

    df["trade_hour"] = pd.to_numeric(df["trade_hour"], errors="coerce")
    df = df[df["trade_hour"].between(1, 24)]

    # long 형식 (연료원 컬럼 있음)
    if "연료원" in df.columns:
        gen_col = next(
            (c for c in ("전력거래량(MWh)", "전력거래량", "발전량(MWh)", "발전량") if c in df.columns),
            None
        )
        if gen_col is None:
            print(f"    [SKIP] {f.name}: 발전량 컬럼 없음")
            return None
        df[gen_col] = pd.to_numeric(df[gen_col], errors="coerce").fillna(0)
        df["연료원"] = df["연료원"].astype(str).str.strip()
        pivot = (
            df.groupby(["trade_date", "trade_hour", "region", "연료원"])[gen_col]
            .sum().unstack(fill_value=0).reset_index()
        )
        pivot.columns.name = None
        pivot["solar_mwh"] = pd.to_numeric(pivot.get("태양광", 0), errors="coerce").fillna(0)
        pivot["wind_mwh"]  = pd.to_numeric(pivot.get("풍력",  0), errors="coerce").fillna(0)
        result = pivot[["trade_date", "trade_hour", "region", "solar_mwh", "wind_mwh"]]

    # wide 형식 (태양광/풍력 각각 컬럼)
    else:
        solar_col = next((c for c in df.columns if "태양광" in c), None)
        wind_col  = next((c for c in df.columns if "풍력"  in c), None)
        if solar_col is None and wind_col is None:
            print(f"    [SKIP] {f.name}: 연료원 구분 불가 (단일 발전량)")
            return None
        df["solar_mwh"] = pd.to_numeric(df.get(solar_col, 0), errors="coerce").fillna(0)
        df["wind_mwh"]  = pd.to_numeric(df.get(wind_col,  0), errors="coerce").fillna(0)
        result = df[["trade_date", "trade_hour", "region", "solar_mwh", "wind_mwh"]].copy()

    result["trade_hour"] = result["trade_hour"].astype(int)
    result = result.drop_duplicates(["trade_date", "trade_hour", "region"])
    return result.reset_index(drop=True)


def load_solar_wind():
    solar_dir  = DATA / "solar_wind_by_region"
    skip_stems = {"2021", "2017", "2020"}   # 2023_0228이 같은 기간 커버, 2021은 연료원 불명

    total = 0
    for f in sorted(solar_dir.glob("*.parquet")):
        if f.stem in skip_stems:
            print(f"  [SKIP] {f.name}")
            continue
        print(f"  처리: {f.name} ...", end=" ", flush=True)
        chunk = _normalize_solar_file(f)
        if chunk is None:
            continue
        # trade_date 기준 30일 단위 청크로 분할 → timeout 방지
        n = _bulk_upsert("solar_wind_by_region", chunk,
                         ["trade_date", "trade_hour", "region"],
                         chunk_col="trade_date", chunk_size=30)
        print(f"{len(chunk):,}행 적재")
        total += len(chunk)

    print(f"[solar_wind_by_region] 총 {total:,}행 완료")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("solar_wind_by_region 적재 시작")
    print("=" * 60)

    load_solar_wind()

    print("\n" + "=" * 60)
    print("최종 확인:")
    with engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM solar_wind_by_region")).scalar()
        print(f"  solar_wind_by_region  {cnt:>8,}행")
    print("=" * 60)
