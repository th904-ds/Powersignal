"""수집 오케스트레이션.

흐름:
  데이터셋 -> 수집 '단위' 목록 생성(날짜/월/스냅샷/odcloud 파일) -> 이미 받은 단위 건너뜀
  -> 남은 단위를 호출 예산 안에서 수집 -> parquet 저장.

호출 예산(daily_call_budget)을 넘으면 BudgetExceeded 로 깔끔히 멈춘다.
다음 실행 때 체크포인트 덕분에 받은 곳 다음부터 이어받는다.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from . import storage
from .client import KpxClient
from .config import Dataset, Settings

log = logging.getLogger("collector")

# api_type 별 (페이지번호 파라미터명, 페이지크기 파라미터명)
PAGING = {
    "kpx": ("pageNo", "numOfRows"),
    "odcloud": ("page", "perPage"),
}


class BudgetExceeded(Exception):
    pass


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _monthrange(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield date(y, m, 1)
        m += 1
        if m > 12:
            y, m = y + 1, 1


def _shift_months(d: date, n: int) -> date:
    """d 에서 n개월 뒤로(음수면 과거로) 이동. 일자는 1일 고정."""
    idx = (d.year * 12 + (d.month - 1)) - n
    return date(idx // 12, idx % 12 + 1, 1)


def _drop_implausible_dates(rows: list[dict], col: str) -> list[dict]:
    """date_sanity_col 의 연도가 비정상(2000 미만 또는 현재+1년 초과)인 행 제거.

    원본에 섞인 센티넬/플레이스홀더(예: 신뢰성DR 의 tradeDay 99990813, 30000330)를 거른다.
    정상적인 근미래(예: 자발적DR 의 다음날 입찰)는 현재+1년 이내라 보존된다.
    """
    max_year = date.today().year + 1
    kept = []
    for r in rows:
        v = str(r.get(col, "")).strip()
        if len(v) >= 4 and v[:4].isdigit() and 2000 <= int(v[:4]) <= max_year:
            kept.append(r)
    dropped = len(rows) - len(kept)
    if dropped:
        log.info("비정상 날짜(%s) %d행 제거", col, dropped)
    return kept


class Collector:
    def __init__(self, settings: Settings):
        self.s = settings
        self.client = KpxClient(
            service_key=settings.service_key,
            base_url=settings.base_url,
            interval_sec=settings.request_interval_sec,
        )

    # ----------------------------------------------------------- 단위 생성
    def _units(self, ds: Dataset, start: date, end: date):
        """(unit_label, fetch_target) 튜플들을 생성.

        fetch_target 의미:
          - odcloud : 그 파일의 전체 URL(문자열)
          - daily/monthly : date 객체
          - snapshot : None
        """
        if ds.api_type == "odcloud":
            for label, url in ds.resources.items():
                yield (str(label), url)
            return

        if ds.mode == "snapshot":
            yield (date.today().strftime("%Y%m%d"), None)
        elif ds.mode == "daily":
            for d in _daterange(start, end):
                yield (d.strftime(ds.date_format), d)
        elif ds.mode == "monthly":
            eff_end = _shift_months(end.replace(day=1), ds.settle_lag_months)
            for m in _monthrange(start.replace(day=1), eff_end):
                yield (m.strftime(ds.date_format), m)
        else:
            raise ValueError(f"알 수 없는 mode: {ds.mode}")

    # ----------------------------------------------------------- 호출
    def _budget_left(self) -> bool:
        return self.client.calls_made < self.s.daily_call_budget

    def _fetch_paginated(self, ds: Dataset, path: str, base_params: dict) -> list[dict]:
        page_name, size_name = PAGING.get(ds.api_type, PAGING["kpx"])
        parser = "odcloud" if ds.api_type == "odcloud" else "kpx"
        rows_all: list[dict] = []
        page = 1
        n = self.s.num_of_rows
        while True:
            if not self._budget_left():
                raise BudgetExceeded
            q = {size_name: n, **base_params, **ds.extra_params, page_name: page}
            rows, total = self.client.get(path, q, parser=parser)
            rows_all.extend(rows)
            done = (
                not ds.paginate
                or not rows
                or len(rows) < n
                or (total >= 0 and len(rows_all) >= total)
            )
            if done:
                break
            page += 1
        return rows_all

    def _fetch_unit(self, ds: Dataset, target) -> list[dict]:
        # odcloud: target 이 그 파일의 전체 URL
        if ds.api_type == "odcloud":
            return self._fetch_paginated(ds, target, {})

        base = {}
        if ds.date_param and target is not None:
            base[ds.date_param] = target.strftime(ds.date_format)
            if ds.end_date_param:
                base[ds.end_date_param] = target.strftime(ds.date_format)

        if ds.area_param and ds.areas:
            rows: list[dict] = []
            for area in ds.areas:
                part = self._fetch_paginated(ds, ds.path, {**base, ds.area_param: area})
                for r in part:
                    r.setdefault(ds.area_param, area)
                rows.extend(part)
            return rows
        return self._fetch_paginated(ds, ds.path, base)

    # ----------------------------------------------------------- 공개 API
    def collect(self, ds: Dataset, start: date, end: date) -> dict:
        if not ds.enabled:
            log.info("건너뜀(비활성) %s", ds.key)
            return {"key": ds.key, "status": "disabled"}
        if not ds.is_configured:
            log.warning("건너뜀(미설정 ★) %s — datasets.yaml 에서 path/date_param 채우세요", ds.key)
            return {"key": ds.key, "status": "unconfigured"}

        fetched = skipped = total_rows = 0
        saved_paths: list = []
        for unit, target in self._units(ds, start, end):
            if storage.is_collected(ds.key, unit):
                skipped += 1
                continue
            if not self._budget_left():
                log.warning("호출 예산(%d) 소진 — %s 는 다음 실행에서 이어받기",
                            self.s.daily_call_budget, ds.key)
                break
            rows = self._fetch_unit(ds, target)
            if ds.date_sanity_col:
                rows = _drop_implausible_dates(rows, ds.date_sanity_col)
            path = storage.save(ds.key, unit, rows,
                                meta={"purpose": ds.purpose, "dataset": ds.key})
            saved_paths.append(path)
            fetched += 1
            total_rows += len(rows)
        return {"key": ds.key, "status": "ok", "fetched": fetched,
                "skipped": skipped, "rows": total_rows, "saved_paths": saved_paths}

    def run(self, keys: list[str], start: date, end: date) -> list[dict]:
        import requests
        from .parsers import ApiError

        results = []
        for key in keys:
            ds = self.s.dataset(key)
            try:
                results.append(self.collect(ds, start, end))
            except BudgetExceeded:
                results.append({"key": key, "status": "budget_exceeded"})
                log.warning("일일 호출 예산 소진으로 전체 중단. 내일/다음 실행 때 이어집니다.")
                break
            except (ApiError, requests.RequestException) as e:
                # 한 데이터셋이 실패해도(파라미터 누락/일시 오류 등) 나머지는 계속
                log.error("%s 수집 실패: %s", key, e)
                results.append({"key": key, "status": f"error: {str(e)[:60]}"})
                continue
        log.info("이번 실행 총 HTTP 호출: %d / 예산 %d",
                 self.client.calls_made, self.s.daily_call_budget)
        return results
