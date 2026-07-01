"""저장 계층.

설계 원칙:
  - 원본(raw)은 거의 안 만들고, 파싱된 결과를 parquet 으로 저장한다.
    (KPX 응답은 행 구조가 단순해 parquet 만으로 재현 가능. raw 가 필요하면
     save_raw 를 켜면 됨.)
  - 파일 경로는 (데이터셋, 날짜단위) 단위로 멱등하게 떨군다.
      data/processed/<key>/<unit>.parquet
    덕분에 재실행해도 덮어쓰기만 되고, is_collected 로 건너뛸 수 있다.
    => 하루 100콜 제약 아래서 며칠에 걸쳐 백필을 이어받는 핵심 장치.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

from .config import PROCESSED_DIR

# 02.database/db.py 임포트 (PG_URL 없으면 조용히 비활성화)
_DB_AVAILABLE = False
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "02.database"))
    from db import upsert as _db_upsert, get_engine as _get_engine  # noqa: F401
    _DB_AVAILABLE = True
except Exception:
    pass

# 데이터셋별 DB 테이블명 & PK 컬럼 매핑
_DB_CONFIG: dict[str, tuple[str, list[str]]] = {
    "smp_dayahead":       ("smp_dayahead",        ["datetime", "area_name"]),
    "gen_by_source_hist": ("gen_by_source_hist",  ["datetime"]),
    "monthly_fuel_cost":  ("monthly_fuel_cost",   ["month", "fuel_type"]),
    "smp_decision_count": ("smp_decision_count",  ["trade_date", "fuel_type", "area_name"]),
    "asos_hourly":        ("asos_hourly",          ["datetime", "stn_id"]),
    "dr_plus":            ("dr_plus",              ["trade_date", "region", "trade_hour"]),
    "dr_voluntary":       ("dr_voluntary",         ["trade_date", "rn"]),
    "dr_economic":        ("dr_economic",          ["trade_date", "rn"]),
    "dr_reliability":     ("dr_reliability",       ["trade_date", "rn"]),
}

log = logging.getLogger("collector.storage")


# ── DR 변환 함수 (parquet raw → DB 스키마) ───────────────────────────────────

def _transform_dr_plus(df: pd.DataFrame) -> pd.DataFrame:
    """wide format (sli/slia/rduRate × hour 10~18, 1행/날짜·지역)
       → long format (1행/날짜·지역·시간대)."""
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()
    df["trade_date"] = pd.to_datetime(
        df["tradeDay"].astype(str), format="%Y%m%d", errors="coerce"
    ).dt.date
    df = df.dropna(subset=["trade_date"])
    records = []
    for _, row in df.iterrows():
        for h in range(10, 19):
            records.append({
                "trade_date":     row["trade_date"],
                "region":         row["areaNm"],
                "trade_hour":     h,
                "bid_mw":         pd.to_numeric(row.get(f"sli{h}"),     errors="coerce"),
                "awarded_mw":     pd.to_numeric(row.get(f"slia{h}"),    errors="coerce"),
                "reduction_rate": pd.to_numeric(row.get(f"rduRate{h}"), errors="coerce"),
            })
    return pd.DataFrame(records)


def _transform_dr_voluntary(df: pd.DataFrame) -> pd.DataFrame:
    """camelCase API 컬럼 → DB 스키마."""
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()
    df["trade_date"] = pd.to_datetime(
        df["tradeDay"].astype(str), format="%Y%m%d", errors="coerce"
    ).dt.date
    df["trade_hour"] = pd.to_numeric(df["tradeTm"], errors="coerce")
    df["sra"] = pd.to_numeric(df["sra"], errors="coerce")
    df["ssr"] = pd.to_numeric(df["ssr"], errors="coerce")
    df = df.dropna(subset=["trade_date"])
    return df[["trade_date", "trade_hour", "rn", "sra", "ssr"]]


def _transform_dr_economic(df: pd.DataFrame) -> pd.DataFrame:
    """경제성DR: camelCase → snake_case, 날짜 파싱."""
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()
    df["trade_date"] = pd.to_datetime(
        df["tradeDay"].astype(str), format="%Y%m%d", errors="coerce"
    ).dt.date
    df = df.dropna(subset=["trade_date"])
    df = df.rename(columns={
        "drType":   "dr_type",
        "rduTime":  "rdu_time",
        "rduRate":  "rdu_rate",
    })
    for col in ["qty", "pssr", "rdu", "rdu_time", "rdu_rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["trade_date", "rn", "dr_type", "qty", "pssr", "rdu", "rdu_time", "rdu_rate"]]


def _transform_dr_reliability(df: pd.DataFrame) -> pd.DataFrame:
    """신뢰성DR: 센티넬 행 제거(9999xxxx·3000xxxx) + 컬럼 정규화."""
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()
    # 센티넬 행 제거 (date_sanity_col 로직과 동일)
    df = df[df["tradeDay"].astype(str).str.match(r"^(19|20)\d{6}$")]
    df["trade_date"] = pd.to_datetime(
        df["tradeDay"].astype(str), format="%Y%m%d", errors="coerce"
    ).dt.date
    df = df.dropna(subset=["trade_date"])
    df = df.rename(columns={
        "drType":   "dr_type",
        "rduReq":   "rdu_req",
        "rduTime":  "rdu_time",
        "rduRate":  "rdu_rate",
    })
    for col in ["rdu_req", "rdu", "rdu_time", "rdu_rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["trade_date", "rn", "dr_type", "rdu_req", "rdu", "rdu_time", "rdu_rate"]]


def _transform_smp_dayahead(df: pd.DataFrame) -> pd.DataFrame:
    """date(YYYYMMDD str) + hour(1~24) → datetime TIMESTAMPTZ, 불필요 컬럼 제거."""
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()
    base = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
    h = pd.to_numeric(df["hour"], errors="coerce")
    df["datetime"] = (base + pd.to_timedelta(h, unit="h")).dt.tz_localize("Asia/Seoul")
    df = df.dropna(subset=["datetime"])
    # areaName → area_name 은 db.py rename_for_db 에서 처리됨
    area_col = "areaName" if "areaName" in df.columns else "area_name"
    for col in ["smp", "jlfd", "slfd", "mlfd"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["datetime", area_col, "smp", "jlfd", "slfd", "mlfd"]]


_GEN_FUEL_MAP = {
    "원자력":      "gen_nuclear",
    "LNG":         "gen_lng",
    "유연탄":      "gen_bituminous",
    "무연탄":      "gen_anthracite",
    "신재생·기타": "gen_renewable",
    "수력":        "gen_hydro",
    "양수":        "gen_pumped",
    "유전":        "gen_oil",
}


def _transform_gen_by_source_hist(df: pd.DataFrame) -> pd.DataFrame:
    """long (fuelTpCd×date×hour) → wide (datetime PK, gen_* cols)."""
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()
    base = pd.to_datetime(df["tradeYmd"].astype(str), format="%Y%m%d", errors="coerce")
    h = pd.to_numeric(df["tradeNo"], errors="coerce")
    df["datetime"] = (base + pd.to_timedelta(h, unit="h")).dt.tz_localize("Asia/Seoul")
    df["amgo"] = pd.to_numeric(df["amgo"], errors="coerce")
    df["col"] = df["fuelTpCd"].map(_GEN_FUEL_MAP)
    df = df.dropna(subset=["datetime", "col"])

    pivot = (
        df.pivot_table(index="datetime", columns="col", values="amgo", aggfunc="sum")
        .reset_index()
    )
    pivot.columns.name = None

    gen_cols = list(_GEN_FUEL_MAP.values())
    for col in gen_cols:
        if col not in pivot.columns:
            pivot[col] = float("nan")
    pivot["gen_total"] = pivot[gen_cols].sum(axis=1, min_count=1)
    for col in gen_cols:
        pivot[f"{col}_ratio"] = pivot[col] / pivot["gen_total"]

    return pivot.sort_values("datetime").reset_index(drop=True)


def _transform_smp_decision_count(df: pd.DataFrame) -> pd.DataFrame:
    """trade_date 문자열 → DATE, rn 컬럼 제거. fuel_type/area_name 은 rename_for_db 처리."""
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()
    date_col = "tradeDay" if "tradeDay" in df.columns else "trade_date"
    df["trade_date"] = pd.to_datetime(
        df[date_col].astype(str), format="%Y%m%d", errors="coerce"
    ).dt.date
    df["cnt"] = pd.to_numeric(df["cnt"], errors="coerce")
    df = df.dropna(subset=["trade_date"])
    # fuel_type / area_name: rename_for_db handles fuelType→fuel_type, areaNm→area_name
    fuel_col = "fuelType" if "fuelType" in df.columns else "fuel_type"
    area_col = "areaNm" if "areaNm" in df.columns else "area_name"
    return df[[fuel_col, area_col, "cnt", "trade_date"]]


def _transform_monthly_fuel_cost(df: pd.DataFrame) -> pd.DataFrame:
    """day('YYYYMM') → month(DATE 1일), untpc → cost, 불필요 컬럼 제거."""
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()
    df["month"] = pd.to_datetime(
        df["day"].astype(str) + "01", format="%Y%m%d", errors="coerce"
    ).dt.date
    df["cost"] = pd.to_numeric(df["untpc"], errors="coerce")
    df = df.dropna(subset=["month"])
    fuel_col = "fuelType" if "fuelType" in df.columns else "fuel_type"
    return df[[fuel_col, "month", "cost"]]


def _transform_asos_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """ASOS 원시 필드 → DB 스키마 (datetime, stn_id, temp_c, humidity_pct, wind_speed_ms, dew_point_c)."""
    df = df[[c for c in df.columns if not c.startswith("_")]].copy()
    df["datetime"] = pd.to_datetime(df["tm"], format="%Y-%m-%d %H:%M", errors="coerce") \
        .dt.tz_localize("Asia/Seoul")
    df["stn_id"] = df["stnId"].astype(str)
    for src, dst in [("ta", "temp_c"), ("hm", "humidity_pct"),
                     ("ws", "wind_speed_ms"), ("td", "dew_point_c")]:
        df[dst] = pd.to_numeric(df[src], errors="coerce")
    df = df.dropna(subset=["datetime", "stn_id"])
    return df[["datetime", "stn_id", "temp_c", "humidity_pct", "wind_speed_ms", "dew_point_c"]]


_DB_TRANSFORMS = {
    "smp_dayahead":         _transform_smp_dayahead,
    "gen_by_source_hist":   _transform_gen_by_source_hist,
    "smp_decision_count":   _transform_smp_decision_count,
    "monthly_fuel_cost":    _transform_monthly_fuel_cost,
    "asos_hourly":          _transform_asos_hourly,
    "dr_plus":              _transform_dr_plus,
    "dr_voluntary":         _transform_dr_voluntary,
    "dr_economic":          _transform_dr_economic,
    "dr_reliability":       _transform_dr_reliability,
}


def _dir(key: str) -> Path:
    p = PROCESSED_DIR / key
    p.mkdir(parents=True, exist_ok=True)
    return p


def parquet_path(key: str, unit: str) -> Path:
    return _dir(key) / f"{unit}.parquet"


def is_collected(key: str, unit: str) -> bool:
    """이미 받아서 저장된 단위인지(=건너뛸지) 판단."""
    return parquet_path(key, unit).exists()


def save(key: str, unit: str, rows: list[dict], meta: dict | None = None) -> Path:
    """행 리스트를 parquet 으로 저장. 0건이어도 빈 마커 파일을 남겨 재요청 방지."""
    df = pd.DataFrame(rows)
    # 어느 단위/언제 받았는지 추적용 컬럼
    df["_unit"] = unit
    df["_collected_at"] = pd.Timestamp.utcnow().isoformat()
    for k, v in (meta or {}).items():
        df[f"_{k}"] = v

    path = parquet_path(key, unit)
    df.to_parquet(path, index=False)
    log.info("저장 %s [%s] %d행 -> %s", key, unit, len(rows), path.name)

    # DB upsert (PG_URL 설정된 경우에만, 실패해도 수집 결과에 영향 없음)
    _try_upsert_to_db(key, df)

    return path


def _try_upsert_to_db(key: str, df: pd.DataFrame) -> None:
    """수집된 DataFrame을 PostgreSQL에 upsert. 설정 없거나 오류 시 조용히 스킵."""
    if not _DB_AVAILABLE or key not in _DB_CONFIG:
        return

    # 메타 컬럼 제거
    clean = df[[c for c in df.columns if not c.startswith("_")]].copy()
    if clean.empty:
        return

    # 데이터셋별 변환 함수 적용 (dr_plus wide→long 등)
    if key in _DB_TRANSFORMS:
        try:
            clean = _DB_TRANSFORMS[key](clean)
        except Exception as e:
            log.warning("DB transform 실패 (%s): %s — DB upsert 스킵", key, e)
            return
        if clean.empty:
            return

    table, pk_cols = _DB_CONFIG[key]
    try:
        _db_upsert(clean, table, pk_cols)
        log.info("DB upsert %s -> %s: %d행", key, table, len(clean))
    except Exception as e:
        log.warning("DB upsert 실패 (parquet은 정상 저장됨): %s", e)


# ------------------------------------------------------------------- GCS
def _gcs_bucket(bucket_name: str):
    import os

    from google.cloud import storage  # 필요할 때만 import

    # ADC(gcloud) 인증만으로는 프로젝트가 안 잡힐 수 있어 명시적으로 넘긴다.
    project = os.getenv("GCS_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        # google.auth 의 "No project ID could be determined" 경고도 함께 잠재운다.
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
    return storage.Client(project=project).bucket(bucket_name)


def _local_crc32c(path: Path) -> str:
    """GCS 의 blob.crc32c 와 동일 포맷(base64)으로 로컬 파일 체크섬 계산."""
    import base64

    import google_crc32c

    h = google_crc32c.Checksum()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode()


def _upload_one(bucket, path: Path, prefix: str, skip_unchanged: bool) -> bool:
    """파일 1개 업로드. 실제로 올렸으면 True, 변경없어 건너뛰면 False."""
    rel = path.relative_to(PROCESSED_DIR)
    blob_name = f"{prefix}/{rel.as_posix()}"
    if skip_unchanged:
        existing = bucket.get_blob(blob_name)  # 없으면 None, 있으면 crc32c 포함 메타 로드
        if existing is not None and existing.crc32c == _local_crc32c(path):
            return False
    bucket.blob(blob_name).upload_from_filename(str(path))
    return True


def upload_files(bucket_name: str, paths, prefix: str = "energy-collector",
                 skip_unchanged: bool = True) -> int:
    """지정한 parquet 파일들만 GCS 로 업로드(수집 직후 자동 업로드용). 올린 파일 수 반환."""
    bucket = _gcs_bucket(bucket_name)
    uploaded = 0
    for p in paths:
        if _upload_one(bucket, Path(p), prefix, skip_unchanged):
            uploaded += 1
    log.info("GCS 자동 업로드: 신규/변경 %d개 -> gs://%s/%s", uploaded, bucket_name, prefix)
    return uploaded


def upload_dir_to_gcs(bucket_name: str, prefix: str = "energy-collector",
                      skip_unchanged: bool = True) -> int:
    """processed 전체를 GCS 로 미러링 업로드. 변경된 파일만 올린다. 올린 파일 수 반환."""
    bucket = _gcs_bucket(bucket_name)
    uploaded = skipped = 0
    for path in sorted(PROCESSED_DIR.rglob("*.parquet")):
        if _upload_one(bucket, path, prefix, skip_unchanged):
            uploaded += 1
        else:
            skipped += 1
    log.info("GCS 업로드 완료: 신규/변경 %d개, 동일 %d개 -> gs://%s/%s",
             uploaded, skipped, bucket_name, prefix)
    return uploaded
