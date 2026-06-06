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
from pathlib import Path

import pandas as pd

from .config import PROCESSED_DIR

log = logging.getLogger("collector.storage")


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
    return path


# ------------------------------------------------------------------- GCS
def upload_dir_to_gcs(bucket_name: str, prefix: str = "energy-collector") -> int:
    """processed 전체를 GCS 로 미러링 업로드. 업로드한 파일 수 반환."""
    from google.cloud import storage  # 필요할 때만 import

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    count = 0
    for path in PROCESSED_DIR.rglob("*.parquet"):
        rel = path.relative_to(PROCESSED_DIR)
        blob = bucket.blob(f"{prefix}/{rel.as_posix()}")
        blob.upload_from_filename(str(path))
        count += 1
    log.info("GCS 업로드 완료: %d개 파일 -> gs://%s/%s", count, bucket_name, prefix)
    return count
