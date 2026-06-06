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
