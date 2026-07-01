"""
reports 테이블 캐시 read/write.

같은 유저가 같은 (report_date, case_type) 조합을 다시 요청하면 LLM을 재호출하지 않고
캐시된 리포트를 그대로 반환한다. Case A(오늘)는 스케줄러가 매일 아침 미리 채워둘 수도
있고, 온디맨드 요청 시 첫 호출에서 채워질 수도 있다 (소규모 유저 기준 배치 사전생성은
불필요 — 첫 요청 시 생성 후 캐싱으로 충분).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "02.database"))
from db import get_engine  # noqa: E402

from schemas import ReportResponse  # noqa: E402


def get_cached_report(
    user_id: UUID, report_date: date, case_type: str, engine: Engine | None = None
) -> ReportResponse | None:
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT report_text, disclaimer, generated_at
                FROM reports
                WHERE user_id = :user_id
                  AND report_date = :report_date
                  AND case_type = :case_type
                """
            ),
            {"user_id": str(user_id), "report_date": report_date, "case_type": case_type},
        ).fetchone()

    if row is None:
        return None

    return ReportResponse(
        report_text=row.report_text,
        generated_at=row.generated_at,
        case_type=case_type,
        disclaimer=row.disclaimer,
    )


def save_report(
    user_id: UUID,
    report_date: date,
    case_type: str,
    result: ReportResponse,
    model_version: str,
    engine: Engine | None = None,
) -> None:
    if engine is None:
        engine = get_engine()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO reports (user_id, report_date, case_type, report_text, disclaimer, model_version, generated_at)
                VALUES (:user_id, :report_date, :case_type, :report_text, :disclaimer, :model_version, :generated_at)
                ON CONFLICT (user_id, report_date, case_type)
                DO UPDATE SET
                    report_text = EXCLUDED.report_text,
                    disclaimer = EXCLUDED.disclaimer,
                    model_version = EXCLUDED.model_version,
                    generated_at = EXCLUDED.generated_at
                """
            ),
            {
                "user_id": str(user_id),
                "report_date": report_date,
                "case_type": case_type,
                "report_text": result.report_text,
                "disclaimer": result.disclaimer,
                "model_version": model_version,
                "generated_at": result.generated_at,
            },
        )
