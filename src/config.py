"""설정 로드: .env 의 키와 datasets.yaml 을 읽어들인다."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LOG_DIR = ROOT / "logs"
CONFIG_PATH = ROOT / "config" / "datasets.yaml"


@dataclass
class Dataset:
    key: str
    name: str
    purpose: str
    path: str = ""                    # base_url 뒤에 붙는 경로, 또는 전체 URL
    mode: str = "snapshot"            # snapshot | daily | monthly
    api_type: str = "kpx"            # kpx | odcloud
    enabled: bool = True
    paginate: bool = True
    date_param: str | None = None
    date_format: str = "%Y%m%d"
    area_param: str | None = None
    areas: list = field(default_factory=list)
    settle_lag_months: int = 0
    resources: dict = field(default_factory=dict)   # odcloud 전용: {라벨: 전체URL}
    extra_params: dict = field(default_factory=dict)  # 매 요청에 붙는 고정값(예: dataType)
    ref: str | None = None

    @property
    def is_configured(self) -> bool:
        """★ 플레이스홀더가 안 채워졌으면 미설정으로 간주."""
        if self.api_type == "odcloud":
            return bool(self.resources)
        if not self.path or "★" in self.path:
            return False
        if self.date_param and "★" in self.date_param:
            return False
        return True


@dataclass
class Settings:
    service_key: str
    gcs_bucket: str | None
    base_url: str
    num_of_rows: int
    daily_call_budget: int
    request_interval_sec: float
    datasets: list[Dataset]

    def dataset(self, key: str) -> Dataset:
        for d in self.datasets:
            if d.key == key:
                return d
        raise KeyError(f"알 수 없는 데이터셋: {key}")


def load_settings() -> Settings:
    service_key = os.getenv("KPX_SERVICE_KEY", "").strip()
    if not service_key or service_key.startswith("여기에"):
        raise RuntimeError(
            ".env 의 KPX_SERVICE_KEY 가 비어있습니다. "
            ".env.example 을 .env 로 복사하고 Decoding 키를 넣으세요."
        )

    with open(CONFIG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    defaults = raw.get("defaults", {})
    datasets = [Dataset(**d) for d in raw.get("datasets", [])]

    for d in (DATA_DIR, RAW_DIR, PROCESSED_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)

    return Settings(
        service_key=service_key,
        gcs_bucket=os.getenv("GCS_BUCKET") or None,
        base_url=defaults.get("base_url", "https://apis.data.go.kr/B552115"),
        num_of_rows=int(defaults.get("num_of_rows", 9999)),
        daily_call_budget=int(defaults.get("daily_call_budget", 90)),
        request_interval_sec=float(defaults.get("request_interval_sec", 0.5)),
        datasets=datasets,
    )
