"""KPX OpenAPI HTTP 클라이언트.

책임:
  - serviceKey 자동 주입 (Decoding 키를 params 로 넘겨 requests 가 인코딩하게 함)
  - 일시 오류(5xx/타임아웃) 재시도
  - 호출 간 최소 간격 유지
  - 실제 HTTP 호출 횟수 카운트 (하루 트래픽 예산 관리용)
  - 응답 파싱은 parsers 에 위임
"""
from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import parsers

log = logging.getLogger("collector.client")


class KpxClient:
    def __init__(self, service_key: str, base_url: str, interval_sec: float = 0.5,
                 timeout: int = 30):
        self.service_key = service_key
        self.base_url = base_url.rstrip("/")
        self.interval = interval_sec
        self.timeout = timeout
        self.calls_made = 0          # 이번 실행에서 서버로 나간 HTTP 호출 수
        self._last_call = 0.0

        self.session = requests.Session()
        retry = Retry(
            total=3, backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def get(self, path: str, params: dict, parser: str = "kpx") -> tuple[list[dict], int]:
        """단일 호출. (행 리스트, totalCount) 반환.

        parser: "kpx"(data.go.kr/KPX 표준 XML·JSON) | "odcloud"(api.odcloud.kr).
        NoData(0건)는 ([], total) 로 정상 반환. 키/트래픽 오류는 ApiError 전파.
        """
        # 호출 간격 유지
        wait = self.interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        # path 가 전체 URL이면 그대로, 아니면 base_url 에 붙인다(호스트 다른 API 대응)
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        q = {"serviceKey": self.service_key, **params}

        resp = self.session.get(url, params=q, timeout=self.timeout)
        self.calls_made += 1
        self._last_call = time.monotonic()
        resp.raise_for_status()

        if parser == "odcloud":
            return parsers.parse_odcloud(resp.text)
        try:
            return parsers.parse(resp.text)
        except parsers.NoData:
            return [], 0
