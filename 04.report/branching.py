"""
유저 조건별 프롬프트 분기 로직.

임계값 판정은 여기서 파이썬으로 확정하고, LLM에는 "이미 판정된 결론"을
지시문으로 넘긴다 — LLM이 300kW, 6,500MW 같은 경계값 비교를 직접 하게
두지 않는다.
"""
from __future__ import annotations

INDUSTRY_DISPLAY_NAME: dict[str, str] = {
    "steel_metal": "철강·금속",
    "chemical": "화학·석유화학",
    "electronics": "전자·반도체",
    "food": "식품·음료",
    "machinery": "기계·자동차",
    "other": "기타 제조업",
}

CONTRACT_POWER_THRESHOLD_KW = 300
RESERVE_POWER_THRESHOLD_MW = 6500


def industry_directive(industry: str) -> str:
    name = INDUSTRY_DISPLAY_NAME.get(industry, industry)
    return f"사용자의 업종은 '{name}'이다. 업종 부담 관련 서술에는 이 업종명을 사용한다."


def contract_power_directive(contract_power: int) -> str:
    if contract_power >= CONTRACT_POWER_THRESHOLD_KW:
        return (
            f"사용자의 계약전력은 {contract_power}kW로 {CONTRACT_POWER_THRESHOLD_KW}kW 이상이므로 "
            "DR 시장 참여 자격이 있다. 전달된 예상 수익(expected_dr_revenue)을 근거로 경제성 DR 참여를 권고한다."
        )
    return (
        f"사용자의 계약전력은 {contract_power}kW로 {CONTRACT_POWER_THRESHOLD_KW}kW 미만이다. "
        "경제성 DR 참여 권고 항목에서는 예상 수익을 계산해 제시하지 말고, "
        "'현재 계약전력 기준 DR 시장 참여 자격 미달' 이라는 취지의 안내 문구로 대체한다."
    )


def dr_registration_directive(dr_registered: bool, aggregator: str | None) -> str:
    if dr_registered:
        agg = aggregator or "등록된 수요관리사업자"
        return (
            f"사용자는 DR 시장에 이미 등록되어 있다 (수요관리사업자: {agg}). "
            "DR 관련 서술은 '현재 DR 스코어 OO점, 이 시간대 입찰 시 예상 수익 OO만원' 같은 "
            "낙찰 가능성·예상 수익 중심으로 작성한다."
        )
    return (
        "사용자는 아직 DR 시장에 등록되어 있지 않다. "
        "DR 관련 서술은 낙찰 가능성을 단정적으로 말하기보다, "
        "'DR 등록 시 기본정산금 수령 등 잠재적 이익을 고려해 볼 만하다'는 취지로, "
        "등록 절차를 고려해볼 것을 권유하는 톤으로 작성한다."
    )


def revenue_vs_loss_directive(
    expected_dr_revenue: float,
    estimated_production_loss: float,
    production_per_hour: int,
    expected_reduction_kw: int,
) -> str:
    # production_per_hour=0 여부와 expected_reduction_kw=0 여부는 서로 독립적인 조건이라,
    # 둘 다 0이어도 "1,000kW 기준값" 안내는 빠지면 안 된다.
    note = (
        "DR 참여 시 예상 절감량이 입력되지 않아 1,000kW 기준값으로 계산된 수익이다. "
        if expected_reduction_kw == 0
        else ""
    )

    if production_per_hour == 0:
        return (
            f"{note}시간당 생산 단가 정보가 입력되지 않았다. 생산 손실과의 비교는 하지 말고, "
            "예상 DR 수익 금액만 제시한다."
        )

    if expected_dr_revenue > estimated_production_loss:
        return (
            f"{note}예상 DR 수익({expected_dr_revenue}만원)이 예상 생산 손실({estimated_production_loss}만원)보다 크다. "
            "'DR 참여 시 수익이 생산 손실을 초과하므로 참여를 권고한다'는 취지로 서술한다."
        )
    return (
        f"{note}예상 DR 수익({expected_dr_revenue}만원)이 예상 생산 손실({estimated_production_loss}만원)보다 작거나 같다. "
        "'현재 생산 단가 기준으로는 DR 수익성이 낮으므로 입찰 보류를 검토해볼 만하다'는 취지로 서술한다."
    )


def reserve_power_directive(
    reserve_power_current: float, reserve_power_forecast_24h: list[float]
) -> str:
    """
    Case A(오늘)는 현재값, Case B(미래)는 24시간 예측 배열의 최솟값을 기준으로 판정한다.
    현재값만 보면, 하루 중 일부 시간대만 임계값 아래로 떨어지는 경우를 놓친다.
    """
    forecast_min = min(reserve_power_forecast_24h) if reserve_power_forecast_24h else reserve_power_current

    if forecast_min < RESERVE_POWER_THRESHOLD_MW:
        low_hour = reserve_power_forecast_24h.index(forecast_min)
        return (
            f"현재 계통 예비력은 {reserve_power_current}MW이지만, 24시간 예측 배열 중 최저치는 "
            f"{forecast_min}MW(약 {low_hour}시경)로 임계값({RESERVE_POWER_THRESHOLD_MW}MW) 미만으로 떨어지는 시간대가 있다. "
            "그 시간대를 중심으로 신뢰성 DR 발령 가능성이 있다는 점을 명확히 언급한다."
        )
    return (
        f"현재 계통 예비력({reserve_power_current}MW)과 24시간 예측 최저치({forecast_min}MW) 모두 "
        f"임계값({RESERVE_POWER_THRESHOLD_MW}MW) 이상으로 여유가 있다. "
        "신뢰성 DR 발령 가능성은 낮다는 점을 언급한다."
    )


def build_branching_directives(
    *,
    industry: str,
    contract_power: int,
    dr_registered: bool,
    aggregator: str | None,
    production_per_hour: int,
    expected_reduction_kw: int,
    expected_dr_revenue: float,
    estimated_production_loss: float,
    reserve_power_current: float,
    reserve_power_forecast_24h: list[float],
) -> list[str]:
    """요청 하나에 대한 전체 분기 지시문 리스트를 만든다."""
    return [
        industry_directive(industry),
        contract_power_directive(contract_power),
        dr_registration_directive(dr_registered, aggregator),
        revenue_vs_loss_directive(
            expected_dr_revenue, estimated_production_loss,
            production_per_hour, expected_reduction_kw,
        ),
        reserve_power_directive(reserve_power_current, reserve_power_forecast_24h),
    ]
