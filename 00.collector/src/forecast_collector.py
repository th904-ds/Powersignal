"""기상청 단기·중기 예보 수집 → asos_forecast 테이블.

단기예보 (getVilageFcst):        D+0 ~ D+3/4, 1시간 단위
중기예보 (getMidTa/getMidLandFcst): D+3 ~ D+7, 오전 09:00·오후 15:00 (KST 대표시각)

PK: (datetime, stn_id) — 매일 갱신 시 최신 예보로 덮어씀

API 등록 필요 (data.go.kr):
  - 기상청_단기예보 ((구)동네예보) 조회서비스  →  VilageFcstInfoService_2.0
  - 기상청_중기예보 조회서비스                →  MidFcstInfoService
  동일한 서비스키(.env KPX_SERVICE_KEY)로 신청 가능.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

log = logging.getLogger("forecast_collector")

KST = timezone(timedelta(hours=9))

# 단기예보 발표 시각 (KST 기준 하루 8회)
_SHORT_BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)

# ── 관측소 설정 ──────────────────────────────────────────────────────────────
# asos_hourly와 동일한 7개 관측소
# nx, ny     : 동네예보 Lambert 격자 좌표 (기상청 좌표변환 공식 적용값)
# mid_ta     : getMidTa 구역코드   (세부 기온 예보, 관측소 인근 시 단위)
# mid_land   : getMidLandFcst 구역코드 (광역 육상 예보, 시·도 단위)
STATIONS: dict[str, dict] = {
    "108": {"name": "서울", "nx": 60,  "ny": 127, "mid_ta": "11B10101", "mid_land": "11B00000"},
    "133": {"name": "대전", "nx": 67,  "ny": 100, "mid_ta": "11C20401", "mid_land": "11C20000"},
    "143": {"name": "대구", "nx": 89,  "ny": 90,  "mid_ta": "11H10701", "mid_land": "11H10000"},
    "159": {"name": "부산", "nx": 98,  "ny": 76,  "mid_ta": "11H20201", "mid_land": "11H20000"},
    "152": {"name": "울산", "nx": 102, "ny": 84,  "mid_ta": "11H20101", "mid_land": "11H20000"},
    "155": {"name": "창원", "nx": 91,  "ny": 77,  "mid_ta": "11H20301", "mid_land": "11H20000"},
    "168": {"name": "여수", "nx": 73,  "ny": 66,  "mid_ta": "11F20501", "mid_land": "11F20000"},
}

SHORT_URL    = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
MID_TA_URL   = "https://apis.data.go.kr/1360000/MidFcstInfoService/getMidTa"
MID_LAND_URL = "https://apis.data.go.kr/1360000/MidFcstInfoService/getMidLandFcst"

# 중기예보 wf 텍스트 → sky_code (1맑음 2구름조금 3구름많음 4흐림)
_WF_SKY: dict[str, int] = {
    "맑음": 1,
    "구름조금": 2,
    "구름많음": 3, "구름많고 비": 3, "구름많고 눈": 3, "구름많고 비/눈": 3,
    "흐림": 4, "흐리고 비": 4, "흐리고 눈": 4, "흐리고 비/눈": 4, "흐리고 소나기": 4,
}

# 수집 대상 단기예보 카테고리
_CAT_KEEP = {"TMP", "REH", "WSD", "POP", "SKY"}


class ForecastCollector:
    def __init__(self, service_key: str, interval_sec: float = 0.5,
                 timeout: tuple[float, float] = (10, 60), max_retries: int = 3):
        self.service_key = service_key
        self.interval_sec = interval_sec
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"

    # ── 공통 HTTP ────────────────────────────────────────────────────────────
    def _get(self, url: str, extra: dict) -> dict:
        """공공데이터 API 호출. 일시적 지연/네트워크 오류는 재시도한다."""
        last_error: Exception | None = None
        endpoint = url.split("/")[-1]

        for attempt in range(1, self.max_retries + 1):
            try:
                r = self.session.get(
                    url,
                    params={"serviceKey": self.service_key, "dataType": "json",
                            "numOfRows": 9999, **extra},
                    timeout=self.timeout,
                )
                r.raise_for_status()
                time.sleep(self.interval_sec)

                payload = r.json()
                body   = payload.get("response", payload)
                header = body.get("header", {})
                code   = str(header.get("resultCode", ""))
                msg    = header.get("resultMsg", "")
                if code not in {"00", "0"}:
                    if any(k in msg.upper() for k in ("NODATA", "NO_DATA")):
                        return {}
                    raise RuntimeError(f"API {endpoint} 오류 {code}: {msg}")
                return body.get("body", {})

            except RuntimeError:
                # 인증키 오류 등 API가 명시적으로 반환한 오류는 재시도해도 해결되지 않는 경우가 많다.
                raise
            except (requests.exceptions.RequestException, ValueError) as e:
                last_error = e
                if attempt >= self.max_retries:
                    break
                wait = min(2 ** attempt, 10)
                log.warning("%s 호출 실패(%d/%d): %s — %d초 후 재시도",
                            endpoint, attempt, self.max_retries, e, wait)
                time.sleep(wait)

        raise last_error if last_error is not None else RuntimeError(f"API {endpoint} 호출 실패")

    def _items(self, body: dict) -> list[dict]:
        it = body.get("items") or {}
        if isinstance(it, dict):
            it = it.get("item", [])
        if isinstance(it, dict):
            it = [it]
        return it or []

    # ── 단기예보 ─────────────────────────────────────────────────────────────
    def collect_short(self, now: datetime) -> pd.DataFrame:
        """최근 발표 기준 단기예보 전 관측소 수집 (1시간 단위)."""
        eligible = [h for h in _SHORT_BASE_HOURS if h <= now.hour]
        if eligible:
            base_hour     = max(eligible)
            base_date_kst = now.date()
        else:
            # 00:00~01:59 KST → 어제 23:00 발표분
            base_hour     = 23
            base_date_kst = now.date() - timedelta(days=1)

        base_date = base_date_kst.strftime("%Y%m%d")
        base_time = f"{base_hour:02d}00"
        issued_at = datetime(base_date_kst.year, base_date_kst.month, base_date_kst.day,
                             base_hour, tzinfo=KST)

        log.info("단기예보 base=%s %s (7개 관측소)", base_date, base_time)
        rows: list[dict] = []
        for stn_id, info in STATIONS.items():
            try:
                body = self._get(SHORT_URL, {
                    "base_date": base_date,
                    "base_time": base_time,
                    "nx": info["nx"],
                    "ny": info["ny"],
                })
            except (requests.exceptions.RequestException, ValueError) as e:
                log.warning("단기예보 수집 실패: stn_id=%s name=%s error=%s",
                            stn_id, info.get("name"), e)
                continue
            rows.extend(self._parse_vilagefcst(self._items(body), stn_id, issued_at))

        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def _parse_vilagefcst(self, items: list[dict], stn_id: str,
                           issued_at: datetime) -> list[dict]:
        """category별 행을 (fcstDate+fcstTime) 기준으로 피벗."""
        slots: dict[str, dict] = defaultdict(dict)
        for it in items:
            cat = it.get("category", "")
            if cat in _CAT_KEEP:
                slots[it["fcstDate"] + it["fcstTime"]][cat] = it.get("fcstValue", "")

        result = []
        for key in sorted(slots):
            # fcstDate(8자) + fcstTime(4자, HHMM) → KST datetime
            kst_dt = datetime.strptime(key, "%Y%m%d%H%M").replace(tzinfo=KST)
            cats = slots[key]
            result.append({
                "datetime":      kst_dt,
                "stn_id":        stn_id,
                "issued_at":     issued_at,
                "forecast_type": "short",
                "temp_c":        _f(cats.get("TMP")),
                "humidity_pct":  _f(cats.get("REH")),
                "wind_speed_ms": _f(cats.get("WSD")),
                "pop":           _f(cats.get("POP")),
                "sky_code":      _i(cats.get("SKY")),
            })
        return result

    # ── 중기예보 ─────────────────────────────────────────────────────────────
    def collect_mid(self, now: datetime) -> pd.DataFrame:
        """중기예보 D+3 ~ D+7, 오전(09:00 KST) / 오후(15:00 KST) 2포인트."""
        if now.hour >= 18:
            mid_hour  = 18
            base      = now
        elif now.hour >= 6:
            mid_hour  = 6
            base      = now
        else:
            # 00:00~05:59 KST → 어제 18:00 발표분
            mid_hour  = 18
            base      = now - timedelta(days=1)

        tmFc      = base.strftime("%Y%m%d") + f"{mid_hour:02d}00"
        issued_at = datetime(base.year, base.month, base.day, mid_hour, tzinfo=KST)
        today     = base.date()

        log.info("중기예보 tmFc=%s (D+3~D+7)", tmFc)

        # 동일 구역코드는 한 번만 호출 (부산·울산·창원이 mid_land를 공유)
        ta_cache:   dict[str, dict] = {}
        land_cache: dict[str, dict] = {}
        for info in STATIONS.values():
            if info["mid_ta"] not in ta_cache:
                try:
                    body = self._get(MID_TA_URL, {"regId": info["mid_ta"], "tmFc": tmFc})
                    items = self._items(body)
                    ta_cache[info["mid_ta"]] = items[0] if items else {}
                except (requests.exceptions.RequestException, ValueError) as e:
                    log.warning("중기 기온예보 수집 실패: regId=%s error=%s", info["mid_ta"], e)
                    ta_cache[info["mid_ta"]] = {}
            if info["mid_land"] not in land_cache:
                try:
                    body = self._get(MID_LAND_URL, {"regId": info["mid_land"], "tmFc": tmFc})
                    items = self._items(body)
                    land_cache[info["mid_land"]] = items[0] if items else {}
                except (requests.exceptions.RequestException, ValueError) as e:
                    log.warning("중기 육상예보 수집 실패: regId=%s error=%s", info["mid_land"], e)
                    land_cache[info["mid_land"]] = {}

        rows: list[dict] = []
        for stn_id, info in STATIONS.items():
            ta   = ta_cache.get(info["mid_ta"],   {})
            land = land_cache.get(info["mid_land"], {})
            for d in range(3, 8):   # D+3 ~ D+7
                target = today + timedelta(days=d)
                # 오전: 최저기온·오전강수확률 대표 → 09:00 KST
                # 오후: 최고기온·오후강수확률 대표 → 15:00 KST
                for period, hour, temp_key, pop_key, wf_key in (
                    ("mid_am", 9,  f"taMin{d}", f"rnSt{d}Am", f"wf{d}Am"),
                    ("mid_pm", 15, f"taMax{d}", f"rnSt{d}Pm", f"wf{d}Pm"),
                ):
                    rows.append({
                        "datetime":      datetime(target.year, target.month, target.day,
                                                  hour, tzinfo=KST),
                        "stn_id":        stn_id,
                        "issued_at":     issued_at,
                        "forecast_type": period,
                        "temp_c":        _f(ta.get(temp_key)),
                        "humidity_pct":  None,   # 중기예보 미제공
                        "wind_speed_ms": None,   # 중기예보 미제공
                        "pop":           _f(land.get(pop_key)),
                        "sky_code":      _wf(land.get(wf_key, "")),
                    })

        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ── 통합 실행 ─────────────────────────────────────────────────────────────
    def run(self, now: Optional[datetime] = None) -> pd.DataFrame:
        """단기 + 중기 예보 수집 후 UTC TIMESTAMPTZ 기준 정렬 DataFrame 반환."""
        if now is None:
            now = datetime.now(KST)

        short_df = self.collect_short(now)
        mid_df   = self.collect_mid(now)

        df = pd.concat([short_df, mid_df], ignore_index=True)
        if df.empty:
            return df

        df["datetime"]  = pd.to_datetime(df["datetime"],  utc=True)
        df["issued_at"] = pd.to_datetime(df["issued_at"], utc=True)

        # DB primary key is (datetime, stn_id). Short-range forecast and
        # medium-range forecast can overlap around D+3 09:00/15:00.
        # PostgreSQL ON CONFLICT cannot update the same target row twice
        # within one INSERT statement, so keep exactly one row per key.
        # Prefer short forecast because it is hourly and more granular.
        forecast_priority = {"short": 0, "mid_am": 1, "mid_pm": 1}
        df["_forecast_priority"] = df["forecast_type"].map(forecast_priority).fillna(9)
        before = len(df)
        df = (
            df.sort_values(["datetime", "stn_id", "_forecast_priority", "issued_at"])
              .drop_duplicates(subset=["datetime", "stn_id"], keep="first")
              .drop(columns=["_forecast_priority"])
              .reset_index(drop=True)
        )
        removed = before - len(df)
        if removed:
            log.info("중복 예보 행 제거: %d행 ((datetime, stn_id) 기준, short 우선)", removed)

        return df.sort_values(["datetime", "stn_id"]).reset_index(drop=True)


# ── helpers ──────────────────────────────────────────────────────────────────
def _f(v) -> Optional[float]:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _i(v) -> Optional[int]:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _wf(text: str) -> Optional[int]:
    return _WF_SKY.get((text or "").strip())
