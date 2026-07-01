"""
POST /api/v1/report/generate

실행: uvicorn api:app --reload --port 8001  (04.report/ 디렉토리에서)
"""
from __future__ import annotations

from fastapi import FastAPI

from db_report_cache import get_cached_report, save_report
from industry_comment import IndustryCommentRequest, IndustryCommentResponse, generate_industry_comment
from report_service import _MODEL_ID, _resolve_date, generate_report
from schemas import ReportRequest, ReportResponse
from score_explain import ScoreExplainRequest, ScoreExplainResponse, generate_score_explain

app = FastAPI(title="Powersignal AI Report API")


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
