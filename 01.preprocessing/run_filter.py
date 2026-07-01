"""
run_filter.py
-------------
필터링 단계 실행 스크립트

실행 방법 (01.preprocessing/ 디렉토리에서):
    python run_filter.py

출력 위치: ../00.collector/data/features/
    base_merged.parquet      — 공통 원시 변수
    model1_filtered.parquet  — Model 1 기반 (lag/rolling 추가 전)
    model2_filtered.parquet  — Model 2 기반 (SMP 이력 lag/rolling 제외 기반)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from filter_features import build_base, filter_and_save

if __name__ == "__main__":
    base = build_base()
    print(f"\n  base shape: {base.shape}")
    print(f"  기간: {base['datetime'].min()} ~ {base['datetime'].max()}")
    filter_and_save(base)
    print("\n[완료] 필터링 완료")
