"""
'스코어 근거 패널' — DR 기회 화면에서 24h 히트맵 셀을 클릭했을 때, "왜 이 시간의 SMP/
계통 예비력이 이런 수치인지"를 SHAP 기여도 기반으로 설명한다.

기능구현 크로스체크 "[3. DR 기회 화면] 스코어 근거 패널: SMP 수준 | LLM + SHAP,
계통 예비력 | LLM + SHAP" 에 해당. (원래 3카드였던 "과거 낙찰률"은 요구사항 정의-AI
리포트에서 유사 낙찰률 자체가 기능 구현 불가로 확정돼서 이 패널에서도 제외한다.)

AI 리포트(report_service.py)와 달리, 여기서는 프론트가 원본 SHAP 값을 넘겨주는 게 아니라
이 서비스가 prediction_explain_values 테이블을 직접 조회한다 — SHAP 데이터는 모델링
결과물이라 웹 프론트가 그 의미를 해석할 필요 없이 "그 시간을 지정"만 하면 되기 때문이다.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from google.genai import types
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "02.database"))
from db import get_engine  # noqa: E402

from report_service import _client, _MODEL_ID  # noqa: E402

TOP_N_FEATURES = 5
PREDICTION_MODEL_ID = "smp_combined"

# feature_name이 영문 코드라 LLM이 오독하지 않도록 자주 나오는 패턴을 미리 설명해둔다.
_FEATURE_GLOSSARY = """자주 나오는 피처명 해석 가이드:
- *_lag24, *_lag168 등: N시간 전의 값
- hour_of_day, hour_sin, hour_cos: 시간대(0~23시) 관련 피처
- month_sin, month_cos: 월 관련 계절성 피처
- avg_temp_c, temp_proxy_*: 기온 관련
- supply_reserve_power, operating_reserve_power: 계통 예비력(MW)
- supply_reserve_rate, operating_reserve_rate: 공급/운영 예비율(%)
- smp_lag*, smp_roll_mean/std/max/min_*: SMP 과거값 및 이동통계
- forecast_load, demand_proxy: 전력 수요 예측
- facility_capacity, supply_capacity: 설비/공급 능력"""


class ScoreExplainRequest(BaseModel):
    area_name: str = "육지"
    target_datetime: datetime


class ScoreExplainResponse(BaseModel):
    smp_reason: str
    reserve_reason: str


def _get_top_shap_features(
    area_name: str, target_datetime: datetime, component: str, engine: Engine | None = None
) -> list[dict]:
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT feature_name, feature_value, effect_value, base_value
                FROM prediction_explain_values
                WHERE prediction_datetime = :dt
                  AND area_name = :area_name
                  AND prediction_model_id = :pred_model_id
                  AND component = :component
                ORDER BY abs_effect_value DESC
                LIMIT :top_n
                """
            ),
            {
                "dt": target_datetime,
                "area_name": area_name,
                "pred_model_id": PREDICTION_MODEL_ID,
                "component": component,
                "top_n": TOP_N_FEATURES,
            },
        ).fetchall()

    return [
        {
            "feature_name": r.feature_name,
            "feature_value": r.feature_value,
            "effect_value": r.effect_value,
            "base_value": r.base_value,
        }
        for r in rows
    ]


def _build_explain_prompt(subject: str, features: list[dict]) -> str:
    feature_lines = "\n".join(
        f"- {f['feature_name']} (값={f['feature_value']}, 기여도={f['effect_value']:+.2f})"
        for f in features
    )
    return (
        f"아래는 '{subject}' 예측값에 가장 큰 영향을 준 상위 {len(features)}개 요인이다 "
        "(SHAP 기여도 — 양수면 값을 높이는 방향, 음수면 낮추는 방향으로 작용).\n\n"
        f"{feature_lines}\n\n"
        f"{_FEATURE_GLOSSARY}\n\n"
        "위 요인들을 근거로, 이 값이 왜 이렇게 나왔는지 2문장 이내로 쉽게 설명하라. "
        "피처명을 그대로 노출하지 말고 자연어로 풀어서 설명하고, 마크다운은 쓰지 마라."
    )


def _explain(subject: str, features: list[dict]) -> str:
    if not features:
        return f"{subject}에 대한 근거 데이터가 아직 없습니다."

    response = _client.models.generate_content(
        model=_MODEL_ID,
        contents=_build_explain_prompt(subject, features),
        config=types.GenerateContentConfig(
            max_output_tokens=512,
            temperature=0.4,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return (response.text or "").strip()


def generate_score_explain(req: ScoreExplainRequest) -> ScoreExplainResponse:
    smp_features = _get_top_shap_features(req.area_name, req.target_datetime, "smp_final")
    reserve_features = _get_top_shap_features(req.area_name, req.target_datetime, "reserve_base")

    return ScoreExplainResponse(
        smp_reason=_explain("SMP(전력 도매가격)", smp_features),
        reserve_reason=_explain("계통 예비력", reserve_features),
    )
