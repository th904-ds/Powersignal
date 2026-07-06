"""
04.report/api.py에 CORS 설정을 추가한 예시입니다.

사용법:
1. 기존 api.py를 백업합니다.
2. 이 파일 내용을 api.py에 반영하거나, 파일명을 api.py로 바꿉니다.
3. allow_origins에 실제 프론트 도메인을 넣습니다.
4. 로컬 실행:
   cd 04.report
   uvicorn api:app --reload --port 8001
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db_report_cache import get_cached_report, save_report
from industry_comment import (
    IndustryCommentRequest,
    IndustryCommentResponse,
    generate_industry_comment,
)
from report_service import _MODEL_ID, _resolve_date, generate_report
from schemas import ReportRequest, ReportResponse
from score_explain import ScoreExplainRequest, ScoreExplainResponse, generate_score_explain

app = FastAPI(title="Powersignal AI Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://b759b329-69f8-4634-9e8b-feaf697799b2.lovableproject.com",
        "https://getpowersignal.lovable.app",
        "https://www.getpowersignal.space",
        "https://getpowersignal.space",
        "http://localhost:8080",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/v1/report/generate", response_model=ReportResponse)
def create_report(req: ReportRequest) -> ReportResponse:
    report_date, case_type = _resolve_date(req.date)

    cached = get_cached_report(req.user_id, report_date, case_type)
    if cached is not None:
        return cached

    result = generate_report(req)
    save_report(req.user_id, report_date, case_type, result, model_version=_MODEL_ID)
    return result


@app.post("/api/v1/industry/comment", response_model=IndustryCommentResponse)
def create_industry_comment(req: IndustryCommentRequest) -> IndustryCommentResponse:
    return generate_industry_comment(req)


@app.post("/api/v1/score/explain", response_model=ScoreExplainResponse)
def create_score_explain(req: ScoreExplainRequest) -> ScoreExplainResponse:
    return generate_score_explain(req)