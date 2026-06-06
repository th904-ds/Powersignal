#!/usr/bin/env python3
"""에너지 데이터 수집기 CLI.

사용 예:
  # 데이터셋 상태 확인
  python run.py list

  # 2023-01-01 ~ 2024-12-31 전체 백필 (하루 예산만큼 받고, 다 못 받으면 재실행)
  python run.py backfill --start 2023-01-01 --end 2024-12-31

  # 특정 데이터셋만
  python run.py backfill --start 2024-01-01 --end 2024-12-31 --datasets smp_legacy,dr_economic

  # 매일 증분 (최근 7일 윈도우, 이미 받은 건 자동 skip)
  python run.py daily

  # 수집 결과를 GCS 로 업로드
  python run.py upload
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

from src import storage
from src.collector import Collector
from src.config import load_settings


def _setup_logging():
    from src.config import LOG_DIR
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "collector.log", encoding="utf-8"),
        ],
    )


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _resolve_keys(settings, arg: str | None) -> list[str]:
    if arg:
        return [k.strip() for k in arg.split(",") if k.strip()]
    return [d.key for d in settings.datasets]


def cmd_list(settings, _args):
    print(f"{'KEY':<22}{'PURPOSE':<14}{'MODE':<10}{'ENABLED':<9}{'CONFIGURED'}")
    print("-" * 70)
    for d in settings.datasets:
        print(f"{d.key:<22}{d.purpose:<14}{d.mode:<10}"
              f"{str(d.enabled):<9}{'O' if d.is_configured else 'X (★ 채우기)'}")


def cmd_backfill(settings, args):
    keys = _resolve_keys(settings, args.datasets)
    start, end = _parse_date(args.start), _parse_date(args.end)
    results = Collector(settings).run(keys, start, end)
    _print_summary(results)


def cmd_daily(settings, args):
    keys = _resolve_keys(settings, args.datasets)
    end = date.today()
    start = end - timedelta(days=args.window)
    results = Collector(settings).run(keys, start, end)
    _print_summary(results)


def cmd_upload(settings, _args):
    if not settings.gcs_bucket:
        sys.exit(".env 의 GCS_BUCKET 이 비어있습니다.")
    n = storage.upload_dir_to_gcs(settings.gcs_bucket)
    print(f"업로드 완료: {n}개 파일")


def _print_summary(results):
    print("\n=== 수집 요약 ===")
    for r in results:
        if r["status"] == "ok":
            print(f"  {r['key']:<22} 신규 {r['fetched']:>4} / 건너뜀 {r['skipped']:>4} / {r['rows']}행")
        else:
            print(f"  {r['key']:<22} [{r['status']}]")


def main():
    p = argparse.ArgumentParser(description="에너지 데이터 수집기")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(func=cmd_list)

    pb = sub.add_parser("backfill")
    pb.add_argument("--start", required=True, help="YYYY-MM-DD")
    pb.add_argument("--end", required=True, help="YYYY-MM-DD")
    pb.add_argument("--datasets", help="쉼표구분 키. 생략하면 전체")
    pb.set_defaults(func=cmd_backfill)

    pd_ = sub.add_parser("daily")
    pd_.add_argument("--window", type=int, default=7, help="되돌아볼 일수(기본 7)")
    pd_.add_argument("--datasets")
    pd_.set_defaults(func=cmd_daily)

    sub.add_parser("upload").set_defaults(func=cmd_upload)

    args = p.parse_args()
    _setup_logging()
    settings = load_settings()
    args.func(settings, args)


if __name__ == "__main__":
    main()
