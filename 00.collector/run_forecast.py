#!/usr/bin/env python3
"""기상 예보 수집 & DB 적재.

사용법:
    cd Powersignal/00.collector
    python run_forecast.py            # 즉시 수집 + DB upsert
    python run_forecast.py --dry-run  # DB 적재 없이 수집 결과만 출력 (API 테스트용)

단기예보 (getVilageFcst):  D+0 ~ D+3/4  시간별
중기예보 (getMidTa/Land):  D+3  ~ D+7   오전(09:00)/오후(15:00) KST 대표

data.go.kr 에서 아래 두 서비스 신청 후 .env KPX_SERVICE_KEY 를 발급키로 설정:
  - 기상청_단기예보 ((구)동네예보) 조회서비스
  - 기상청_중기예보 조회서비스
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent   # 00.collector/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "02.database"))

from src.config import LOG_DIR
from src.forecast_collector import ForecastCollector

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "forecast.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("run_forecast")


def main() -> None:
    p = argparse.ArgumentParser(description="기상 예보 수집 & DB 적재")
    p.add_argument("--dry-run", action="store_true",
                   help="DB 적재 없이 수집 결과만 출력 (API 연결 테스트용)")
    args = p.parse_args()

    service_key = os.getenv("KPX_SERVICE_KEY", "").strip()
    if not service_key or service_key.startswith("여기에"):
        sys.exit(".env 의 KPX_SERVICE_KEY 가 비어있습니다.")

    log.info("기상 예보 수집 시작")
    df = ForecastCollector(service_key).run()

    if df.empty:
        log.warning("수집 결과 없음")
        return

    n_short = int((df["forecast_type"] == "short").sum())
    n_mid   = int(df["forecast_type"].isin(["mid_am", "mid_pm"]).sum())
    log.info("단기 %d행 (시간별)  중기 %d행 (오전/오후)  합계 %d행",
             n_short, n_mid, len(df))

    kst_min = df["datetime"].min().tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M KST")
    kst_max = df["datetime"].max().tz_convert("Asia/Seoul").strftime("%Y-%m-%d %H:%M KST")
    log.info("예보 범위: %s ~ %s", kst_min, kst_max)

    # parquet 백업 — DB 설정 없어도 데이터 유지
    out_dir = ROOT / "data" / "processed" / "asos_forecast"
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / f"{datetime.now().strftime('%Y%m%d_%H%M')}.parquet"
    df.to_parquet(parquet_path, index=False)
    log.info("parquet 백업: %s", parquet_path.name)

    if args.dry_run:
        print("\n=== 수집 결과 (--dry-run, DB 적재 생략) ===")
        print(df.to_string(index=False))
        return

    # DB upsert
    try:
        from db import upsert
        n = upsert(df, "asos_forecast", ["datetime", "stn_id"])
        log.info("DB upsert 완료: %d행 → asos_forecast", n)
    except Exception as e:
        log.error("DB upsert 실패 (parquet 은 정상 저장됨): %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
