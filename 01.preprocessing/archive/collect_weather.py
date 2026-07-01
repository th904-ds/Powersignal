"""
기상 데이터 수집 — 7개 지역 (2023-2025, 시간단위)

전략:
  - 기존 4개소(서울108·대전133·대구143·부산159):
      이미 수집된 asos_hourly parquet에서 추가 필드 재파싱
  - 신규 3개소(울산152·창원155·여수168):
      ASOS API 월별 청크 직접 수집 (36개월×3개소=108 call)
  - startHh=00 으로 수집해 00:00 구조적 결측 해소
  - 7개소 수집 후 지역별 평균 컬럼 생성

저장: 01.preprocessing/output/weather_hourly.parquet
"""
import sys, os, time, json
sys.stdout.reconfigure(encoding="utf-8")

import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date
from dateutil.relativedelta import relativedelta

BASE = Path("c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal")
ASOS_PROC = BASE / "00.collector/data/processed/asos_hourly"
OUT_DIR   = BASE / "01.preprocessing/output"
OUT_DIR.mkdir(exist_ok=True)

# ── 설정 ──────────────────────────────────────────────────────────────
STATIONS = {
    108: "서울",
    152: "울산",
    143: "대구",
    133: "대전",
    159: "부산",
    155: "창원",
    168: "여수",
}
EXISTING_STNS = {108, 133, 143, 159}
NEW_STNS      = {152, 155, 168}

TRAIN_START = date(2023, 1, 1)
TRAIN_END   = date(2025, 12, 31)

# ASOS API
ASOS_URL = "https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"

# 원본 필드 → 정규 컬럼명
FIELD_MAP = {
    "ta":   "temp_c",        # 기온 (°C)
    "hm":   "humidity_pct",  # 상대습도 (%)
    "ws":   "wind_speed_ms", # 풍속 (m/s)
    "rn":   "precip_mm",     # 강수량 (mm)
    "dsnw": "snow_cm",       # 신적설 (cm)
    "ss":   "sunshine_hr",   # 일조시간 (hr)
    "icsr": "solar_MJm2",    # 일사량 (MJ/m²)
}

# ── 서비스키 로드 ─────────────────────────────────────────────────────
def _load_key() -> str:
    env_path = BASE / "00.collector/.env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("KPX_SERVICE_KEY"):
            return line.split("=", 1)[1].strip()
    raise ValueError(".env 에서 KPX_SERVICE_KEY 를 찾을 수 없음")

SERVICE_KEY = _load_key()

# ── 파트 1: 기존 4개소 재파싱 ─────────────────────────────────────────
def parse_existing() -> pd.DataFrame:
    print("=== Part 1: 기존 4개소 parquet 재파싱 ===")
    files = sorted(f for f in os.listdir(ASOS_PROC) if f.endswith(".parquet"))
    # 2023-2025 파일만
    target = [f for f in files if "2023" <= f[:8] <= "20251231"]
    print(f"  대상 파일: {len(target)}개  ({target[0]} ~ {target[-1]})")

    dfs = []
    for fname in target:
        df = pd.read_parquet(ASOS_PROC / fname)
        # 기존 4개소만
        df = df[df["stnId"].astype(str).isin([str(s) for s in EXISTING_STNS])].copy()
        if df.empty:
            continue

        # datetime
        df["datetime"] = pd.to_datetime(df["tm"])
        # 2023-2025 범위 필터
        df = df[(df["datetime"] >= "2023-01-01") & (df["datetime"] < "2026-01-01")]
        if df.empty:
            continue

        # 필드 추출
        keep = {"datetime", "stnId", "stnNm"} | set(FIELD_MAP.keys())
        cols = [c for c in keep if c in df.columns]
        dfs.append(df[cols])

    result = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    print(f"  파싱 완료: {len(result):,}행  관측소: {sorted(result['stnId'].unique())}")
    return result


# ── 파트 2: 신규 3개소 API 수집 ──────────────────────────────────────
def _fetch_month(stn_id: int, ym: date, session: requests.Session) -> list[dict]:
    """월 단위 ASOS 시간 데이터 수집 (페이지네이션 포함)"""
    start_dt = ym.strftime("%Y%m%d")
    end_dt   = (ym + relativedelta(months=1) - relativedelta(days=1)).strftime("%Y%m%d")

    rows_all = []
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
            "startHh":    "00",
            "endHh":      "23",
            "stnIds":     str(stn_id),
        }
        r = session.get(ASOS_URL, params=params, timeout=20)
        r.raise_for_status()

        body = r.json()
        resp   = body.get("response", body)
        header = resp.get("header", {})
        code   = str(header.get("resultCode", ""))
        if code not in {"00", "0"}:
            msg = header.get("resultMsg", "")
            # NODATA는 정상(해당 기간 데이터 없음)
            if "NODATA" in msg.upper() or "NO_DATA" in msg.upper():
                break
            raise RuntimeError(f"ASOS API 오류: {code} / {msg}")

        b     = resp.get("body", {})
        total = int(b.get("totalCount", 0))
        items = b.get("items", {})
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


def collect_new_stations() -> pd.DataFrame:
    print("\n=== Part 2: 신규 3개소 API 수집 ===")
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    all_rows = []
    months = []
    cur = TRAIN_START.replace(day=1)
    while cur <= TRAIN_END:
        months.append(cur)
        cur += relativedelta(months=1)

    total_calls = len(NEW_STNS) * len(months)
    done = 0

    for stn_id in sorted(NEW_STNS):
        stn_name = STATIONS[stn_id]
        print(f"\n  [{stn_id}] {stn_name} — {len(months)}개월 수집 시작")
        for ym in months:
            try:
                rows = _fetch_month(stn_id, ym, session)
                for r in rows:
                    r["stnId"]  = str(stn_id)
                    r["stnNm"]  = stn_name
                all_rows.extend(rows)
                done += 1
                if done % 12 == 0 or done == total_calls:
                    print(f"    진행: {done}/{total_calls}  ({ym.strftime('%Y-%m')} 완료)")
                time.sleep(0.5)
            except Exception as e:
                print(f"    [경고] {stn_id} {ym.strftime('%Y-%m')} 실패: {e}")
                time.sleep(2)

    if not all_rows:
        print("  수집 결과 없음")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    # datetime 파싱 (tm: "2023-01-01 01:00")
    df["datetime"] = pd.to_datetime(df["tm"], errors="coerce")
    df = df.dropna(subset=["datetime"])
    df = df[(df["datetime"] >= "2023-01-01") & (df["datetime"] < "2026-01-01")]

    keep = {"datetime", "stnId", "stnNm"} | set(FIELD_MAP.keys())
    cols = [c for c in keep if c in df.columns]
    df = df[cols].copy()
    print(f"\n  신규 수집 완료: {len(df):,}행")
    return df


# ── 파트 3: 합치기 + 정규화 + 지역 평균 ──────────────────────────────
def build_weather(df_exist: pd.DataFrame, df_new: pd.DataFrame) -> pd.DataFrame:
    print("\n=== Part 3: 합치기 + 정규화 + 지역 평균 ===")

    df = pd.concat([df_exist, df_new], ignore_index=True)
    df["stnId"] = df["stnId"].astype(str)

    # 수치 변환 (빈 문자열 → NaN)
    for src, tgt in FIELD_MAP.items():
        if src in df.columns:
            df[tgt] = pd.to_numeric(df[src].replace("", np.nan), errors="coerce")
        else:
            df[tgt] = np.nan

    df["region"] = df["stnId"].map({str(k): v for k, v in STATIONS.items()})

    # 관측소별 요약
    print("\n  관측소별 수집 현황 (2023-2025):")
    for stn_id, stn_name in sorted(STATIONS.items()):
        sub = df[df["stnId"] == str(stn_id)]
        n = len(sub)
        t_miss = sub["temp_c"].isnull().mean() * 100
        p_miss = sub["precip_mm"].isnull().mean() * 100
        s_miss = sub["solar_MJm2"].isnull().mean() * 100
        print(f"    [{stn_id}] {stn_name:<5}: {n:,}행  "
              f"기온결측={t_miss:.1f}%  강수결측={p_miss:.1f}%  일사결측={s_miss:.1f}%")

    # datetime 기준 피벗 → 지역 평균
    METRIC_COLS = list(FIELD_MAP.values())
    # 시간-지역 long → pivot → 평균
    df_wide = df.groupby("datetime")[METRIC_COLS].mean()
    df_wide.columns = [f"avg_{c}" for c in df_wide.columns]
    df_wide = df_wide.reset_index()

    # 관측소별 컬럼도 추가 (wide pivot)
    df_stn = df.pivot_table(
        index="datetime",
        columns="region",
        values=METRIC_COLS,
        aggfunc="mean"
    )
    df_stn.columns = [f"{var}_{region}" for var, region in df_stn.columns]
    df_stn = df_stn.reset_index()

    result = df_wide.merge(df_stn, on="datetime", how="left")
    result = result.sort_values("datetime").reset_index(drop=True)

    print(f"\n  최종 shape: {result.shape}")
    print(f"  기간: {result['datetime'].min()} ~ {result['datetime'].max()}")
    print(f"  avg_temp_c 결측: {result['avg_temp_c'].isnull().mean()*100:.2f}%")
    print(f"  avg_precip_mm 결측: {result['avg_precip_mm'].isnull().mean()*100:.2f}%")
    print(f"  avg_solar_MJm2 결측: {result['avg_solar_MJm2'].isnull().mean()*100:.2f}%")

    out_path = OUT_DIR / "weather_hourly.parquet"
    result.to_parquet(out_path, index=False)
    print(f"\n  저장: {out_path}")
    return result


# ── 메인 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    df_exist = parse_existing()
    df_new   = collect_new_stations()
    df_weather = build_weather(df_exist, df_new)

    print("\n=== 컬럼 목록 ===")
    avg_cols = [c for c in df_weather.columns if c.startswith("avg_")]
    stn_cols = [c for c in df_weather.columns if not c.startswith("avg_") and c != "datetime"]
    print(f"  평균 컬럼 ({len(avg_cols)}개): {avg_cols}")
    print(f"  관측소별 컬럼 ({len(stn_cols)}개): {stn_cols[:7]}...")
    print("\n수집 완료.")
