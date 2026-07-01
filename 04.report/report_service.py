"""
AI 리포트 생성 핵심 로직: 프롬프트 조립 → Gemini 호출 → 응답 조립.

분기 판정(300kW, 6,500MW 등 임계값 비교)은 branching.py가 파이썬으로 미리 끝내고,
그 결론을 "지시문" 문자열로 LLM에 넘긴다. LLM은 판정하지 않고 문장만 만든다.

참고: Gemini의 명시적 캐싱(client.caches.create)은 별도 객체 생성 + 최소 토큰 수
요건이 있어서, 지금 시스템 프롬프트 크기(수백~1천 토큰대)로는 캐싱 이득을 보기
어렵다. 그래서 캐싱 없이 매 호출마다 system_instruction을 그대로 보낸다
(Gemini Flash 가격 자체가 낮아서 이 정도 규모에선 비용 영향이 크지 않음).
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from branching import build_branching_directives
from schemas import ReportRequest, ReportResponse

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_MODEL_ID = "gemini-2.5-flash"

# 1번 섹션 "모든 리포트 하단 고정 문구" — LLM이 생성하지 않고 서버가 항상 이어붙인다.
FIXED_FOOTER = (
    "\n\n본 리포트는 공공데이터 기반 AI 분석 결과이며, 실제 전력시장 상황과 다를 수 있습니다. "
    "참고용으로 활용하세요."
)

# 6-3번 섹션 "안내 문구" — Case B(미래 날짜)에서만 disclaimer 필드에 채워진다.
FUTURE_DISCLAIMER = "기상 예보 기반 AI 예측입니다. 실제와 다를 수 있습니다."

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _load_system_prompt(case_type: str) -> str:
    base = (_PROMPTS_DIR / "system_base.md").read_text(encoding="utf-8")
    template_file = "case_a_template.md" if case_type == "today" else "case_b_template.md"
    template = (_PROMPTS_DIR / template_file).read_text(encoding="utf-8")
    return f"{base}\n\n{template}"


def _hourly(values: list[float]) -> dict[str, float]:
    """24개짜리 배열을 {'0시': 값, ..., '23시': 값} 형태로 바꾼다.

    배열을 그냥 리스트로 주면 LLM이 인덱스-시간 매핑을 스스로 추측해야 해서
    (예: index 0이 0시인지 1시인지) 시간대 언급이 틀릴 수 있다. 키에 시간을
    직접 박아두면 그 여지가 없어진다.
    """
    return {f"{i}시": v for i, v in enumerate(values)}


def _build_user_turn(req: ReportRequest, directives: list[str]) -> str:
    data_payload = {
        "region": req.region,
        "date": req.date,
        "smp_current": req.smp_current,
        "smp_monthly_avg_diff": req.smp_monthly_avg_diff,
        "smp_forecast_by_hour": _hourly(req.smp_forecast_24h),
        "smp_score_by_hour": _hourly(req.smp_score_24h),
        "reserve_power_current": req.reserve_power_current,
        "reserve_rate_current": req.reserve_rate_current,
        "reserve_power_forecast_by_hour": _hourly(req.reserve_power_forecast_24h),
        "dr_score_current": req.dr_score_current,
        "dr_score_by_hour": _hourly(req.dr_score_24h),
        "expected_revenue_per_1000kw_by_hour": _hourly(req.expected_revenue_per_1000kw_24h),
        "gen_mix": req.gen_mix.model_dump(),
        "temperature": req.temperature,
        "industry_burden_index": req.industry_burden_index,
        "industry_burden_level": req.industry_burden_level,
        "expected_dr_revenue": req.expected_dr_revenue,
        "estimated_production_loss": req.estimated_production_loss,
    }

    directive_text = "\n".join(f"- {d}" for d in directives)

    return (
        "아래 데이터를 근거로 리포트 본문을 작성하라.\n\n"
        "## 데이터 (JSON)\n"
        f"{json.dumps(data_payload, ensure_ascii=False, indent=2)}\n\n"
        "## 분기 지시\n"
        f"{directive_text}\n\n"
        "위 데이터와 지시를 모두 반영한 리포트 본문만 출력하라. "
        "다른 설명이나 머리말 없이 본문 텍스트로 바로 시작하라."
    )


def _resolve_date(date_param: str) -> tuple[date, str]:
    if date_param == "today":
        return date.today(), "today"
    return date.fromisoformat(date_param), "future"


def generate_report(req: ReportRequest) -> ReportResponse:
    report_date, case_type = _resolve_date(req.date)

    directives = build_branching_directives(
        industry=req.industry,
        contract_power=req.contract_power,
        dr_registered=req.dr_registered,
        aggregator=req.aggregator,
        production_per_hour=req.production_per_hour,
        expected_reduction_kw=req.expected_reduction_kw,
        expected_dr_revenue=req.expected_dr_revenue,
        estimated_production_loss=req.estimated_production_loss,
        reserve_power_current=req.reserve_power_current,
        reserve_power_forecast_24h=req.reserve_power_forecast_24h,
    )

    system_instruction = _load_system_prompt(case_type)
    user_turn = _build_user_turn(req, directives)

    response = _client.models.generate_content(
        model=_MODEL_ID,
        contents=user_turn,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=4096,
            temperature=0.4,
            # 정형화된 리포트 작성 작업이라 깊은 추론이 필요 없음 — thinking을 꺼서
            # max_output_tokens 예산이 전부 실제 리포트 텍스트로 가게 한다.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    report_text = (response.text or "").strip() + FIXED_FOOTER

    return ReportResponse(
        report_text=report_text,
        generated_at=datetime.now(timezone.utc),
        case_type=case_type,
        disclaimer=FUTURE_DISCLAIMER if case_type == "future" else None,
    )
