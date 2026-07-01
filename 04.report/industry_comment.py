"""
'업종 클릭 코멘트' — 업종별 비교 화면에서 막대를 클릭했을 때 보여줄 짧은 AI 코멘트.

화면 정의서 4번 "업종별 비교 화면" / 기능구현 크로스체크 "업종 클릭 코멘트: 해당 업종
AI코멘트 | LLM" 에 해당. AI 리포트(04.report/report_service.py)와 달리 이건 DB 조회가
필요 없다 — 프론트가 이미 계산해서 넘겨주는 부담 지수·등급만 있으면 된다.
"""
from __future__ import annotations

from typing import Literal

from google.genai import types
from pydantic import BaseModel

from branching import INDUSTRY_DISPLAY_NAME
from report_service import _client, _MODEL_ID  # 클라이언트·모델 재사용


class IndustryCommentRequest(BaseModel):
    industry: str
    smp_score: int  # 0~100
    industry_burden_index: float  # C1
    industry_burden_level: Literal["LOW", "MID", "HIGH"]  # C2


class IndustryCommentResponse(BaseModel):
    comment: str


_SYSTEM_PROMPT = """당신은 파워시그널(Powersignal) 서비스의 AI 코멘트 작성자입니다.
업종별 전력비 부담 비교 화면에서, 사용자가 특정 업종 막대를 클릭했을 때 보여줄
아주 짧은 코멘트를 작성합니다.

규칙:
- 1~2문장으로만 작성한다.
- 전달받은 부담 지수·등급·SMP 스코어 숫자를 반드시 근거로 포함한다. 숫자를 지어내지 않는다.
- 마크다운을 쓰지 않는다.
- 업종명과 부담 등급을 자연스럽게 문장에 녹여서, 그 업종이 현재 전력비 부담을 얼마나
  받는 상황인지 설명한다."""


def generate_industry_comment(req: IndustryCommentRequest) -> IndustryCommentResponse:
    industry_name = INDUSTRY_DISPLAY_NAME.get(req.industry, req.industry)

    user_turn = (
        f"업종: {industry_name}\n"
        f"현재 SMP 스코어: {req.smp_score}점 (0~100)\n"
        f"업종별 전력비 부담 지수: {req.industry_burden_index}\n"
        f"업종별 부담 등급: {req.industry_burden_level}\n\n"
        "위 데이터를 근거로 짧은 코멘트를 작성하라."
    )

    response = _client.models.generate_content(
        model=_MODEL_ID,
        contents=user_turn,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=512,
            temperature=0.4,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    return IndustryCommentResponse(comment=(response.text or "").strip())
