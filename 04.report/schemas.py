"""
POST /api/v1/report/generate 요청·응답 스키마.

'요구사항 정의 - AI 리포트' 4번 섹션 API 스펙 기준. 문서 스펙 대비 다음 2가지를 변경:

1. dr_bid_rate_similar(E10, 유사 조건 과거 낙찰률) 제거
   — 기능구현 크로스체크에서 이미 "기능 구현 불가"로 확정된 값이라 DB에 컬럼 자체가 없음.
2. user_id 필드 추가
   — 원문 스펙에는 캐싱 키로 쓸 사용자 식별자가 빠져 있어서, reports 캐시 테이블의
     PK(user_id, report_date, case_type)를 채우려면 필요. 프론트가 로그인 유저 조회 시
     같이 넘겨주면 됨.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GenMix(BaseModel):
    lng: float
    nuclear: float
    coal: float
    renewable: float


class ReportRequest(BaseModel):
    # 캐싱 키 (원문 스펙에 없던 추가 필드)
    user_id: UUID

    # 유저 데이터 (U1~U7, DB에서 조회해서 프론트가 전달)
    industry: str
    region: str
    contract_power: int
    dr_registered: bool
    aggregator: Optional[str] = None
    production_per_hour: int = 0
    expected_reduction_kw: int = 0

    # 날짜 (캘린더 선택값) — "today" 또는 "YYYY-MM-DD"
    date: str

    # 에너지 시장 데이터 (DB fetch 후 프론트가 전달)
    smp_current: float
    smp_monthly_avg_diff: float
    smp_forecast_24h: list[float]
    smp_score_24h: list[int]
    reserve_power_current: float
    reserve_rate_current: float
    reserve_power_forecast_24h: list[float]
    dr_score_current: int
    dr_score_24h: list[int]
    expected_revenue_per_1000kw_24h: list[float]
    gen_mix: GenMix
    temperature: float

    # 프론트 계산값 (C1~C4)
    industry_burden_index: float
    industry_burden_level: Literal["LOW", "MID", "HIGH"]
    expected_dr_revenue: float
    estimated_production_loss: float


class ReportResponse(BaseModel):
    report_text: str
    generated_at: datetime
    case_type: Literal["today", "future"]
    disclaimer: Optional[str] = None
