"""
Powersignal 자동 수집 & 전처리 스케줄러.

실행:
    cd Powersignal
    python scheduler.py

종료: Ctrl+C

업데이트 주기 설계 (datasets.yaml 기준):
    ┌─────────────────────────────┬──────────┬──────────────────────────────┐
    │ 데이터셋                     │ 수집 주기│ 스케줄                       │
    ├─────────────────────────────┼──────────┼──────────────────────────────┤
    │ gen_by_source (현재 발전량)  │ 5분      │ 매 5분 (09:00~23:00)        │
    │ power_supply_today (수급현황)│ 5분      │ 매 5분 (09:00~23:00)        │
    ├─────────────────────────────┼──────────┼──────────────────────────────┤
    │ smp_dayahead (SMP+수요예측) │ 매일     │ 매일 06:30 (전일분 확정 후)  │
    │ gen_by_source_hist (발전이력)│ 매일     │ 매일 06:30                  │
    │ smp_decision_count          │ 매일     │ 매일 06:30                  │
    │ dr_voluntary                │ 매일     │ 매일 06:30                  │
    │ dr_plus                     │ 매일     │ 매일 06:30                  │
    │ dr_economic                 │ 매일     │ 매일 06:30                  │
    │ dr_reliability              │ 매일     │ 매일 06:30                  │
    │ asos_hourly (기상 실측)      │ 매일     │ 매일 07:00 (전일분 ASOS 확정)│
    │ asos_forecast (기상 예보)    │ 매일     │ 매일 07:05 (중기 06:00 발표후)│
    ├─────────────────────────────┼──────────┼──────────────────────────────┤
    │ monthly_fuel_cost           │ 매월     │ 매월 3일 09:00 (전월분 확정) │
    ├─────────────────────────────┼──────────┼──────────────────────────────┤
    │ 전처리 파이프라인            │ 매일     │ 매일 08:00 (수집 완료 후)    │
    └─────────────────────────────┴──────────┴──────────────────────────────┘
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

ROOT = Path(__file__).resolve().parent
PY   = sys.executable  # 현재 가상환경 python

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT / "00.collector" / "logs" / "scheduler.log",
                            encoding="utf-8"),
    ],
)
log = logging.getLogger("scheduler")


def _run(cmd: list[str], cwd: Path | None = None, label: str = "") -> bool:
    """subprocess 실행 후 성공 여부 반환."""
    label = label or " ".join(cmd[-2:])
    log.info("[시작] %s", label)
    result = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=False)
    if result.returncode == 0:
        log.info("[완료] %s", label)
        return True
    else:
        log.error("[실패] %s (exit=%d)", label, result.returncode)
        return False


# ─────────────────────────────────────────────────────────────────────
# Job 정의
# ─────────────────────────────────────────────────────────────────────

def job_5min_realtime():
    """5분: 실시간 발전현황 & 전력수급현황 수집."""
    _run(
        [PY, "run.py", "daily", "--window", "1",
         "--datasets", "gen_by_source,power_supply_today", "--no-upload"],
        cwd=ROOT / "00.collector",
        label="5분 실시간 수집 (gen_by_source, power_supply_today)",
    )


def job_daily_collect():
    """매일 06:30: snapshot 데이터셋 전체 갱신."""
    datasets = ",".join([
        "smp_dayahead",
        "gen_by_source_hist",
        "smp_decision_count",
        "dr_voluntary",
        "dr_plus",
        "dr_economic",
        "dr_reliability",
    ])
    _run(
        [PY, "run.py", "daily", "--window", "3",
         "--datasets", datasets, "--no-upload"],
        cwd=ROOT / "00.collector",
        label="일별 수집 (SMP·발전이력·DR)",
    )


def job_daily_asos():
    """매일 07:00: ASOS 기상 전일분 수집 (전일 데이터 확정 후)."""
    _run(
        [PY, "run.py", "daily", "--window", "2",
         "--datasets", "asos_hourly", "--no-upload"],
        cwd=ROOT / "00.collector",
        label="일별 수집 (asos_hourly)",
    )


def job_forecast():
    """매일 07:05: 기상 예보 수집 (단기 D+0~D+3/4, 중기 D+3~D+7)."""
    _run(
        [PY, "run_forecast.py"],
        cwd=ROOT / "00.collector",
        label="기상 예보 수집 (단기+중기 +7일)",
    )


def job_daily_preprocess():
    """매일 08:00: 수집 완료 후 전처리 & model_features DB 갱신."""
    # 1단계: filter_features (base_merged.parquet 생성)
    ok = _run(
        [PY, "run_filter.py"],
        cwd=ROOT / "01.preprocessing",
        label="전처리 1단계 (filter_features)",
    )
    if not ok:
        return

    # 2단계: preprocess (model1_train, model2_train 생성 + DB upsert)
    _run(
        [PY, "run_preprocess.py"],
        cwd=ROOT / "01.preprocessing",
        label="전처리 2단계 (preprocess → DB)",
    )


def job_monthly_fuel_cost():
    """매월 3일 09:00: 전월 연료비용 수집."""
    _run(
        [PY, "run.py", "daily", "--window", "40",
         "--datasets", "monthly_fuel_cost", "--no-upload"],
        cwd=ROOT / "00.collector",
        label="월별 수집 (monthly_fuel_cost)",
    )


# ─────────────────────────────────────────────────────────────────────
# 스케줄 등록
# ─────────────────────────────────────────────────────────────────────

sched = BlockingScheduler(timezone="Asia/Seoul")

# 5분 실시간 (전력시장 운영 시간대 집중)
sched.add_job(
    job_5min_realtime,
    CronTrigger(minute="*/5", hour="0-23"),
    id="realtime_5min",
    max_instances=1,
    coalesce=True,
)

# 매일 수집
sched.add_job(
    job_daily_collect,
    CronTrigger(hour=6, minute=30),
    id="daily_collect",
    max_instances=1,
)

sched.add_job(
    job_daily_asos,
    CronTrigger(hour=7, minute=0),
    id="daily_asos",
    max_instances=1,
)

sched.add_job(
    job_forecast,
    CronTrigger(hour=7, minute=5),
    id="forecast_weather",
    max_instances=1,
)

sched.add_job(
    job_daily_preprocess,
    CronTrigger(hour=8, minute=0),
    id="daily_preprocess",
    max_instances=1,
)

# 매월
sched.add_job(
    job_monthly_fuel_cost,
    CronTrigger(day=3, hour=9, minute=0),
    id="monthly_fuel",
    max_instances=1,
)


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("Powersignal 스케줄러 시작")
    log.info("=" * 60)
    log.info("등록된 Job:")
    for job in sched.get_jobs():
        log.info("  %-20s  %s", job.id, job.trigger)
    log.info("종료: Ctrl+C")
    log.info("=" * 60)

    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("스케줄러 종료")
