"""
asos_hourly 백필 스크립트

  Phase 1 - 신규 3개소 (152·155·168): 2020-01-01 ~ 오늘 (전체 기간)
  Phase 2 - 기존 4개소 (108·133·143·159): 2026-06 (20일 gap 보충)

  asos_hourly 테이블 컬럼:
      datetime TIMESTAMPTZ, stn_id VARCHAR, temp_c, humidity_pct,
      wind_speed_ms, dew_point_c (모두 DOUBLE PRECISION)

실행:
    cd Powersignal
    python backfill_asos.py
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dateutil.relativedelta import relativedelta

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path("c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal")
sys.path.insert(0, str(BASE / "02.database"))

from dotenv import load_dotenv
load_dotenv(BASE / "00.collector/.env")

from db import upsert  # noqa: E402

logging.basicConfig(level=logging.WARNING)   # db.py INFO 로그 억제
log = logging.getLogger("backfill_asos")

ASOS_URL = "https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"

# asos_hourly 테이블에 들어가는 4개 필드
FIELD_MAP = {
    "ta": "temp_c",
    "hm": "humidity_pct",
    "ws": "wind_speed_ms",
    "td": "dew_point_c",
}

NEW_STNS      = [152, 155, 168]    # Phase 1: 전체 기간 백필
EXISTING_STNS = [108, 133, 143, 159]  # Phase 2: gap 보충 (June 2026)


def _load_key() -> str:
    for line in (BASE / "00.collector/.env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("KPX_SERVICE_KEY") and "=" in line:
            return line.split("=", 1)[1].strip()
    raise ValueError("KPX_SERVICE_KEY not found in .env")


SERVICE_KEY = _load_key()


def _fetch_month(stn_id: int, ym: date, session: requests.Session) -> list[dict]:
    """월 단위 ASOS 시간 데이터 수집 (페이지네이션 포함)."""
    start_dt = ym.strftime("%Y%m%d")
    month_end = ym + relativedelta(months=1) - relativedelta(days=1)
    yesterday = date.today() - timedelta(days=1)
    end_dt   = min(month_end, yesterday).strftime("%Y%m%d")
    if end_dt < start_dt:
        return []  # 아직 수집 가능한 날짜가 없는 미래 월

    rows_all: list[dict] = []
    page = 1
    while True:
        params = {
            "serviceKey": SERVICE_KEY,
            "pageNo":     page,
            "numOfRows":  999,
            "dataType":   "json",
            "dataCd":     "ASOS",
            "dateCd":     "HR",
            "startDt":    start_dt,
            "endDt":      end_dt,
            "startHh":    "01",
            "endHh":      "23",
            "stnIds":     str(stn_id),
        }
        r = session.get(ASOS_URL, params=params, timeout=20)
        r.raise_for_status()

        body   = r.json()
        resp   = body.get("response", body)
        header = resp.get("header", {})
        code   = str(header.get("resultCode", ""))
        if code not in {"00", "0"}:
            msg = header.get("resultMsg", "")
            if "NODATA" in msg.upper() or "NO_DATA" in msg.upper():
                break
            raise RuntimeError(f"ASOS API 오류 [{stn_id} {ym}]: {code} / {msg}")

        b     = resp.get("body", {})
        total = int(b.get("totalCount", 0))
        items = b.get("items") or {}
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        if not items:
            break

        rows_all.extend(items)
        if total <= 0 or len(rows_all) >= total:
            break
        page += 1
        time.sleep(0.3)

    return rows_all


def _to_df(rows: list[dict], stn_id: int) -> pd.DataFrame:
    """원시 API rows → asos_hourly 형식 DataFrame (datetime UTC-aware)."""
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # KST 문자열 → UTC TIMESTAMPTZ
    df["datetime"] = (
        pd.to_datetime(df["tm"], errors="coerce")
          .dt.tz_localize("Asia/Seoul", ambiguous="NaT", nonexistent="NaT")
          .dt.tz_convert("UTC")
    )
    df = df.dropna(subset=["datetime"])

    df["stn_id"] = str(stn_id)

    for src, tgt in FIELD_MAP.items():
        if src in df.columns:
            df[tgt] = pd.to_numeric(
                df[src].replace("", np.nan), errors="coerce"
            )
        else:
            df[tgt] = np.nan

    out_cols = ["datetime", "stn_id"] + list(FIELD_MAP.values())
    return df[out_cols].copy()


def _month_range(start: date, end_inclusive: date) -> list[date]:
    months: list[date] = []
    cur = start.replace(day=1)
    while cur <= end_inclusive.replace(day=1):
        months.append(cur)
        cur += relativedelta(months=1)
    return months


def collect_and_upsert(
    stns: list[int],
    months: list[date],
    session: requests.Session,
    engine,
    label: str,
) -> None:
    total = len(stns) * len(months)
    done  = 0
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  관측소: {stns}  / {len(months)}개월 ({months[0]} ~ {months[-1]})")
    print(f"  예상 API 호출: {total}회")
    print(f"{'='*60}")

    for stn_id in stns:
        for ym in months:
            try:
                rows = _fetch_month(stn_id, ym, session)
                df   = _to_df(rows, stn_id)
                done += 1

                if not df.empty:
                    n = upsert(df, "asos_hourly", ["datetime", "stn_id"], engine=engine)
                else:
                    n = 0

                if done % 12 == 0 or done == total or n > 0:
                    print(
                        f"  [{done:>4}/{total}] stn={stn_id} {ym.strftime('%Y-%m')}: "
                        f"{n:>4}행 upsert  (raw={len(rows)})"
                    )
                time.sleep(0.5)

            except Exception as e:
                done += 1
                print(f"  [경고] stn={stn_id} {ym.strftime('%Y-%m')} 실패: {e}")
                time.sleep(2)


def main() -> None:
    from sqlalchemy import create_engine as _ce
    pg_url = os.getenv("PG_URL")
    if not pg_url:
        sys.exit("PG_URL 이 .env 에 없습니다.")
    # pool_size=1, max_overflow=0 → 동시 연결 1개로 Supabase 풀 초과 방지
    engine = _ce(pg_url, pool_size=1, max_overflow=0, pool_pre_ping=True)

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    today = date.today()
    print(f"backfill_asos.py 시작  (오늘: {today})")

    # Phase 1: 신규 3개소 전체 기간
    phase1_months = _month_range(date(2020, 1, 1), today)
    collect_and_upsert(NEW_STNS, phase1_months, session, engine, "Phase 1: 신규 3개소 (152·155·168) 2020-01 ~ 현재")

    # Phase 2: 기존 4개소 — 2026-06 gap 보충
    phase2_months = _month_range(date(2026, 6, 1), today)
    collect_and_upsert(EXISTING_STNS, phase2_months, session, engine, "Phase 2: 기존 4개소 (108·133·143·159) gap 보충")

    engine.dispose()
    print("\n✓ 백필 완료")


if __name__ == "__main__":
    main()
