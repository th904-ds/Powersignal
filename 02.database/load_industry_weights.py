"""
industry_weights 적재 스크립트 (웹팀 요청).

공식: 업종별 가중치 = 업종 electricity_ktoe / 제조업전체 electricity_ktoe
출처: industry_energy_by_source (표5-3-3 업종별 에너지원별 산업부문 소비 현황)
분모: '제조업' 행의 electricity_ktoe (광업 제외 순수 제조업 합계)

실행: python 02.database/load_industry_weights.py
"""

import sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pandas as pd
from db import upsert, get_engine, query

engine = get_engine()

# industry_code -> (industry_energy_by_source.industry 값, 표시용 한글명)
CODE_MAP = {
    "steel_metal": "제1차 금속산업",
    "chemical":    "화학",
    "electronics": "전자장비 제조업",
    "food":        "음식료업",
    "machinery":   "자동차 제조업",
    "other":       "그 외 기타제조업",
}
DENOM_INDUSTRY = "제조업"

src = query("SELECT industry, electricity_ktoe FROM industry_energy_by_source", engine=engine)
src_map = dict(zip(src["industry"], src["electricity_ktoe"]))

denom = src_map[DENOM_INDUSTRY]
print(f"분모 ('{DENOM_INDUSTRY}' electricity_ktoe) = {denom}")

rows = []
for code, industry_name in CODE_MAP.items():
    val = src_map[industry_name]
    weight = val / denom
    rows.append({
        "industry_code": code,
        "industry_name": industry_name,
        "weight": weight,
        "description": (
            f"표5-3-3 electricity_ktoe 기준: {industry_name} {val} / "
            f"제조업 {denom} = {weight:.4f}"
        ),
    })
    print(f"  {code:12s} {industry_name:10s} {val:>10,.1f} / {denom:,.1f} = {weight:.4f}")

df = pd.DataFrame(rows)
n = upsert(df, "industry_weights", ["industry_code"], engine=engine)
print(f"\n[industry_weights] {n}행 upsert 완료")

print("\n검증:")
result = query("SELECT * FROM industry_weights ORDER BY industry_code", engine=engine)
print(result.to_string(index=False))
