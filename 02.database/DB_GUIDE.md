# Powersignal DB 가이드 — 팀원용

> **DB**: Supabase (cloud PostgreSQL 17) — 담당자 PC 꺼져도 항상 접속 가능  
> **담당**: 김태희 (데이터 파이프라인)  
> **최종 업데이트**: 2026-06-27

---

## 0. 연결 방법

### 연결 문자열
```
⚠️ 비밀번호 포함 — GPT·git 배포 금지. .env 파일로만 관리할 것.
PG_URL=postgresql://postgres.eszcdtumysqpifsprxrs:7543superbase@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres
```

### .env 파일 설정 (프로젝트 루트에 생성)
```
PG_URL=postgresql://postgres.eszcdtumysqpifsprxrs:7543superbase@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres
```

### 연결 테스트
```python
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.environ["PG_URL"])
with engine.connect() as conn:
    print(conn.execute(text("SELECT 1")).scalar())  # 1 출력되면 성공
```

### 필요 패키지
```bash
pip install sqlalchemy psycopg2-binary python-dotenv pandas
```

---

## 1. 테이블 전체 목록

**총 23개 테이블.** 작성 주체별로 구분.

### 파이프라인 자동 적재 (수집·전처리)

| 테이블 | 용도 | 행수 (2026-06 기준) | 기간 | 업데이트 |
|---|---|---|---|---|
| `smp_dayahead` | SMP 실적 + 수요예측 원본 (육지/제주) | 112,800행 | 2020-01 ~ 현재 | 매일 06:30 |
| `gen_by_source_hist` | 발전원별 발전량 이력 (시간별 일합산) | 36,888행 | 2022-01 ~ 약 4주 전 | 매일 06:30 |
| `monthly_fuel_cost` | 연료원별 월간 단가 | 280행 | 2021-11 ~ 현재 | 매월 3일 |
| `smp_decision_count` | 연료원별 SMP 결정횟수 (일별) | 28,449행 | 2001-04 ~ 현재 | 매일 06:30 |
| `asos_hourly` | 기상관측 시간자료 (서울·대전·대구·부산) | 216,200행 | 2020-01 ~ 현재 | 매일 07:00 |
| `sukub_raw` | 5분단위 전국 전력수급현황 원시 | 0행 (수동 CSV → model_features 통합) | — | 수동 |
| `dr_plus` | 플러스DR 입낙찰·이행량 (지역별·10~18시) | 54,657행 | 2023-01 ~ 현재 | 수집 시 |
| `dr_voluntary` | 자발적DR 입낙찰 (AI 리포트 학습용) | 23,097행 | 2023-01 ~ 현재 | 수집 시 |

### 전처리 완료 (ML 피처)

| 테이블 | 용도 | 행수 | 기간 | 업데이트 |
|---|---|---|---|---|
| **`model_features`** | **전처리 완료 ML 피처 (모델 직접 사용)** | **52,608행** (model1·model2 각 26,304) | **2023-01-01 ~ 2025-12-31** | 매일 08:00 |

### 프론트 RAW 데이터

| 테이블 | 용도 | 행수 | 기간 |
|---|---|---|---|
| `solar_wind_by_region` | 지역별 시간별 태양광·풍력 발전량 | 1,368,912행 | 2017-01 ~ 2025-12 |

### 정적 참조 테이블

| 테이블 | 용도 | 상태 |
|---|---|---|
| `industry_weights` | 업종별 집중도 가중치 (6개 업종 고정값) | 6행, `load_industry_weights.py`로 적재 완료 |

### 모델링 팀 작성

| 테이블 | 용도 | 상태 |
|---|---|---|
| `predictions` | 모델 예측 결과 | 0행 (모델링 팀이 채움) |
| `model_registry` | 모델 버전·성능 기록 | 0행 (모델링 팀이 채움) |

### 한국에너지공단 정적 통계 (지역별, 5개)

> **출처**: 한국에너지공단 「산업부문 에너지사용 및 온실가스배출량 통계」 (2024년 기준)  
> **적재 스크립트**: `02.database/load_regional_csv.py`  
> **원본 CSV**: `00.collector/data/manual/regional/` 폴더

| 테이블 | 원본 표 | 용도 | PK | 행수 |
|---|---|---|---|---|
| `region_energy_by_source` | 표5-3-5 | 지역별 에너지원별 사용 현황 (석탄·석유·도시가스·기타·열·전력) | `region` | 18행 |
| `region_energy_trend` | 표5-4-5 | 지역별 에너지 사용량 연도별 변화 (2020~2024, 증감·CAGR) | `region` | 18행 |
| `region_energy_by_firm_size` | 표5-7-5 | 지역별 기업 규모별 사용량 (대기업·중견·중소·기타) | `region` | 18행 |
| `national_complex_energy` | 표5-6-5 | 국가·일반 산업단지 지역별 사용 현황 (산단수·업체수·에너지원별) | `region` | 18행 |
| `industrial_complex_energy` | 표5-6-2 | 전체 산업단지 지역별 사용 현황 (산단수·업체수·에너지원별) | `region` | 18행 |

**지역 목록 (18개)**: 산업부문전체, 서울, 부산, 대구, 인천, 광주, 대전, 울산, 세종, 경기, 강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주

### 한국에너지공단 정적 통계 (업종별, 3개)

> **출처**: 한국에너지공단 「산업부문 에너지사용 및 온실가스배출량 통계」 (2024년 기준)  
> **적재 스크립트**: `02.database/load_industrial_csv.py`  
> **원본 CSV**: `00.collector/data/manual/industrial/` 폴더

| 테이블 | 원본 표 | 용도 | PK | 행수 |
|---|---|---|---|---|
| `industry_energy_by_source` | 표5-3-3 | 업종별 에너지원별 사용 현황 (석탄·석유·도시가스·기타·열·전력) | `industry` | 13행 |
| `industry_energy_trend` | 표5-4-3 | 업종별 에너지 사용량 연도별 변화 (2020~2024, 증감·CAGR) | `industry` | 13행 |
| `industry_energy_by_firm_size` | 표5-7-3 | 업종별 기업 규모별 사용량 (대기업·중견·중소·기타) | `industry` | 13행 |

**업종 목록 (13개)**: 산업부문 전체, 광업, 제조업, 음식료업, 섬유제품업, 펄프·종이, 정유, 화학, 비금속 광물제품, 제1차 금속산업, 전자장비 제조업, 자동차 제조업, 그 외 기타제조업

> **NOTE**: `광업·정유` 일부 에너지원은 해당없음(`?`)으로 DB에 `NULL` 저장됨.

---

## 2. model_features — 핵심 테이블 상세

모델 학습·추론에 바로 사용하는 전처리 완료 피처. **총 100컬럼**.

> `model_id = 'model1'` : SMP 자기회귀 피처 포함 (26,304행)  
> `model_id = 'model2'` : 시장 변수만, SMP lag 컬럼은 NULL (26,304행)

### 컬럼 그룹 요약

| 그룹 | 컬럼 | 비고 |
|---|---|---|
| **PK** | `datetime`, `model_id` | |
| **타겟** | `smp` | 예측 대상 (원/kWh) |
| **수요예측** | `jlfd`, `slfd`, `mlfd` | 단기·중기·장기 부하예측 (MW) |
| **발전량** | `gen_nuclear`, `gen_lng`, `gen_bituminous`, `gen_anthracite`, `gen_renewable`, `gen_hydro`, `gen_pumped`, `gen_oil`, `gen_total` | 일합산 MWh (24h 동일값) |
| **발전비율** | `gen_nuclear_ratio` ~ `gen_oil_ratio` (8개) | gen_*/gen_total |
| **연료비용** | `fuel_cost_lng`, `fuel_cost_bituminous`, `fuel_cost_oil` | 월별 단가 (월 내 동일값) |
| **NBTP** | `nbtp_accepted`, `nbtp_bid` | 낙찰·입찰 NBTP (원/kWh, 월 내 동일값) |
| **SMP 결정** | `smp_decision_cnt_lng` | LNG가 SMP 결정한 시간수 (일별) |
| **전력수급** | `facility_capacity`, `supply_capacity`, `supply_reserve_power`, `supply_reserve_rate`, `current_demand`, `forecast_load`, `operating_reserve_power`, `operating_reserve_rate` | 5분→1시간 집계 (sukub) |
| **기상** | `avg_temp_c`, `avg_humidity_pct`, `avg_wind_speed_ms`, `avg_precip_mm`, `avg_snow_cm`, `avg_sunshine_hr`, `avg_solar_mjm2`, `avg_temp_c_sq` | 4관측소 평균 |
| **시간 피처** | `hour_of_day`, `weekday`, `month_num`, `is_weekend`, `hour_sin`, `hour_cos`, `month_sin`, `month_cos` | 순환 인코딩 포함 |
| **공휴일** | `is_holiday`, `is_before_holiday`, `is_after_holiday` | 한국 공휴일 기준 |
| **수요 lag** | `jlfd_lag24`, `jlfd_lag168`, `slfd_lag24`, `slfd_lag168`, `mlfd_lag24`, `mlfd_lag168`, `*_diff_24`, `*_pct_change_24` (12개) | 24h·168h 래그 |
| **예비력 lag** | `operating_reserve_rate_lag24/168`, `operating_reserve_power_lag24/168`, `supply_capacity_lag24/168`, `current_demand_lag24/168`, `forecast_load_lag24/168` (10개) | |
| **예비력 rolling** | `operating_reserve_rate_roll_mean/min/std_24_lag24`, `operating_reserve_rate_roll_mean/min/std_168_lag24` (6개) | |
| **예비력 비율** | `operating_reserve_power_to_demand_lag24` | |
| **SMP lag** | `smp_lag1`, `smp_lag24`, `smp_lag48`, `smp_lag72`, `smp_lag168`, `smp_lag336` | **model1만 값 있음** |
| **SMP rolling** | `smp_roll_mean_24/168`, `smp_roll_std_24/168`, `smp_roll_max/min_24/168` (8개) | **model1만 값 있음** |

### 조회 예시

```sql
-- 훈련 데이터 전체 (model1)
SELECT * FROM model_features
WHERE model_id = 'model1'
  AND datetime BETWEEN '2023-01-01' AND '2025-12-31'
ORDER BY datetime;

-- 최신 24시간
SELECT * FROM model_features
WHERE model_id = 'model1'
ORDER BY datetime DESC
LIMIT 24;
```

```python
# pandas로 학습 데이터 로드
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()
engine = create_engine(os.environ["PG_URL"])

df = pd.read_sql(
    text("SELECT * FROM model_features WHERE model_id='model1' ORDER BY datetime"),
    engine, parse_dates=["datetime"]
).set_index("datetime")
```

---

## 3. 한국에너지공단 정적 통계 테이블 상세

### 컬럼 구조

#### region_energy_by_source / industry_energy_by_source (표5-3-5 / 표5-3-3) — 에너지원별 사용 현황

| 컬럼 | 설명 | 단위 |
|---|---|---|
| `region` / `industry` | PK (지역명 / 업종명) | — |
| `total_ktoe` | 총 에너지 사용량 | 천toe |
| `coal_ktoe` / `coal_pct` | 석탄류 사용량 / 비중 | 천toe / % |
| `oil_ktoe` / `oil_pct` | 석유류 사용량 / 비중 | 천toe / % |
| `city_gas_ktoe` / `city_gas_pct` | 도시가스 사용량 / 비중 | 천toe / % |
| `other_energy_ktoe` / `other_energy_pct` | 기타에너지(신재생 등) / 비중 | 천toe / % |
| `heat_ktoe` / `heat_pct` | 열에너지 사용량 / 비중 | 천toe / % |
| `electricity_ktoe` / `electricity_pct` | 전력 사용량 / 비중 | 천toe / % |

#### region_energy_trend / industry_energy_trend (표5-4-5 / 표5-4-3) — 연도별 에너지 사용량 변화

| 컬럼 | 설명 | 단위 |
|---|---|---|
| `region` / `industry` | PK | — |
| `energy_2020` ~ `energy_2024` | 연도별 에너지 사용량 | 천toe |
| `change_20_21` ~ `change_23_24` | 전년 대비 증감 | 천toe |
| `cagr_5yr_pct` | 5년 연평균 증감율 | % |

#### region_energy_by_firm_size / industry_energy_by_firm_size (표5-7-5 / 표5-7-3) — 기업 규모별 사용 현황

| 컬럼 | 설명 | 단위 |
|---|---|---|
| `region` / `industry` | PK | — |
| `company_count` | 에너지 다소비 사업장 수 | 개 |
| `total_ktoe` | 총 사용량 | 천toe |
| `large_ktoe` / `large_pct` | 대기업 사용량 / 비중 | 천toe / % |
| `medium_ktoe` / `medium_pct` | 중견기업 사용량 / 비중 | 천toe / % |
| `small_ktoe` / `small_pct` | 중소기업 사용량 / 비중 | 천toe / % |
| `other_ktoe` / `other_pct` | 기타 사용량 / 비중 | 천toe / % |

#### national_complex_energy / industrial_complex_energy (표5-6-5 / 표5-6-2) — 산업단지 지역별 현황

| 컬럼 | 설명 | 단위 |
|---|---|---|
| `region` | PK | — |
| `complex_count` | 입주 산업단지 수 | 개 |
| `company_count` | 입주 업체 수 | 개 |
| `total_ktoe` | 총 에너지 사용량 | 천toe |
| `coal_ktoe` ~ `electricity_pct` | 에너지원별 사용량·비중 (region_energy_by_source와 동일 구조) | 천toe / % |

> `national_complex_energy`(표5-6-5) = 국가·일반 산업단지만 / `industrial_complex_energy`(표5-6-2) = 전체 산업단지 (농공단지 포함)

### 조회 예시

```sql
-- 지역별 전력 사용량 상위 5곳
SELECT region, electricity_ktoe
FROM region_energy_by_source
ORDER BY electricity_ktoe DESC
LIMIT 5;

-- 업종별 2024년 에너지 사용량 (석탄류 비중 포함)
SELECT industry, total_ktoe, coal_pct
FROM industry_energy_by_source
ORDER BY total_ktoe DESC;

-- 산업단지 밀집 상위 지역 (국가·일반 산단)
SELECT region, complex_count, company_count, total_ktoe
FROM national_complex_energy
ORDER BY total_ktoe DESC;
```

```python
# 지역별 연도 추이 분석 예시
df_trend = pd.read_sql(
    text("SELECT * FROM region_energy_trend ORDER BY energy_2024 DESC"),
    engine
)
```

---

## 4. predictions — 모델링 팀 작성

요구사항 기준 컬럼 구조:

| 컬럼 | 설명 |
|---|---|
| `datetime` | 예측 대상 시각 (TIMESTAMPTZ) |
| `area_name` | `'육지'` / `'제주'` |
| `model_id` | `'model1'` / `'model2'` |
| `smp_pred_base` | 모델1 1차 예측값 |
| `smp_pred_residual` | 모델2 잔차 보정값 |
| `smp_pred_final` | base + residual (화면 표시용 최종값) |
| `smp_score` | 0~100 정규화 스코어 |
| `reserve_power_pred` | 예비력 예측 (신뢰성 DR 판정용, 검토중) |
| `dr_score` | 경제성 DR 낙찰 가능성 0~100 |
| `predicted_smp` | (구버전 호환용, 신규는 smp_pred_final 사용) |

```python
# predictions 저장 예시
pred_df = pd.DataFrame({
    "datetime": [...],
    "area_name": "육지",
    "model_id": "model1",
    "smp_pred_base": [...],
    "smp_pred_residual": [...],
    "smp_pred_final": [...],
    "smp_score": [...],
    "dr_score": [...],
    "model_version": "v1.0",
})
pred_df.to_sql("predictions", engine, if_exists="append", index=False, method="multi")
```

---

## 5. 프론트 팀 — 조회 테이블 가이드

### 실시간 RAW 데이터

```sql
-- 현재 SMP (육지/제주 최신값)
SELECT area_name, smp, jlfd, slfd, mlfd
FROM smp_dayahead
WHERE datetime = (SELECT MAX(datetime) FROM smp_dayahead);

-- 계통 예비력 현재값
SELECT datetime, supply_reserve_power, supply_reserve_rate,
       operating_reserve_power, operating_reserve_rate, current_demand
FROM model_features
WHERE model_id = 'model1'
ORDER BY datetime DESC LIMIT 1;

-- 향후 24시간 수요예측
SELECT datetime, jlfd, slfd, mlfd
FROM smp_dayahead
WHERE area_name = '육지'
  AND datetime >= NOW()
ORDER BY datetime LIMIT 24;
```

### 지역별 태양광·풍력 (solar_wind_by_region)

```sql
-- 특정 날짜 지역별 태양광 발전량
SELECT trade_date, trade_hour, region, solar_mwh, wind_mwh
FROM solar_wind_by_region
WHERE trade_date = '2025-01-15'
ORDER BY region, trade_hour;

-- 최근 7일 지역별 태양광 일합산
SELECT trade_date, region, SUM(solar_mwh) AS total_solar
FROM solar_wind_by_region
WHERE trade_date >= CURRENT_DATE - 7
GROUP BY trade_date, region
ORDER BY trade_date, region;
```

**지역명 목록 (19개):**
강원도, 경기도, 경상남도, 경상북도, 광주시, 대구시, 대전시, 부산시, 서울시, 세종시, 울산시, 인천시, 전라남도, 전라북도, 제주, 제주도, 충청남도, 충청북도, 육지

### 플러스 DR (dr_plus)

```sql
-- 지역별 플러스DR 최근 낙찰 현황
SELECT trade_date, region, trade_hour, bid_mw, awarded_mw, reduction_rate
FROM dr_plus
WHERE trade_date >= CURRENT_DATE - 30
ORDER BY trade_date DESC, region, trade_hour;
```

**지역명 목록 (14개):**
강원, 경기, 경기북부, 경남, 경북, 광주/전남, 대구, 대전/충남, 부산/울산, 서울, 인천, 전북, 제주, 충북

---

## 6. 파이프라인 자동화 구조

```
[수집] 00.collector/run.py
  └→ storage.py (save() 호출)
       ├→ parquet 저장 (00.collector/data/processed/)
       └→ _try_upsert_to_db() → Supabase upsert

[전처리] 01.preprocessing/run_preprocess.py
  └→ step8_filter_save() 완료 후
       └→ _write_model_features_to_db() → Supabase model_features upsert

[정적 테이블 적재]
  02.database/load_regional_csv.py    → region_energy_by_source, region_energy_trend,
                                         region_energy_by_firm_size, national_complex_energy,
                                         industrial_complex_energy
  02.database/load_industrial_csv.py  → industry_energy_by_source, industry_energy_trend,
                                         industry_energy_by_firm_size
```

### 스케줄러 (scheduler.py)

| Job ID | 실행 시각 | 작업 |
|---|---|---|
| `daily_collect` | 매일 06:30 | smp_dayahead, gen_by_source_hist, smp_decision_count, DR 데이터 수집 → DB |
| `daily_asos` | 매일 07:00 | asos_hourly 수집 → DB |
| `daily_preprocess` | 매일 08:00 | run_preprocess.py → model_features DB upsert |
| `monthly_fuel` | 매월 3일 09:00 | monthly_fuel_cost 수집 → DB |

---

## 7. 컬럼명 변환 규칙 (parquet 한글 → DB 영문)

| parquet 원본 | DB 컬럼명 |
|---|---|
| `gen_원자력` | `gen_nuclear` |
| `gen_LNG` | `gen_lng` |
| `gen_유연탄` | `gen_bituminous` |
| `gen_무연탄` | `gen_anthracite` |
| `gen_신재생·기타` | `gen_renewable` |
| `gen_수력` | `gen_hydro` |
| `gen_양수` | `gen_pumped` |
| `gen_유전` | `gen_oil` |
| `fuel_cost_LNG` | `fuel_cost_lng` |
| `fuel_cost_유연탄` | `fuel_cost_bituminous` |
| `fuel_cost_유류` | `fuel_cost_oil` |
| `smp_decision_cnt_LNG` | `smp_decision_cnt_lng` |
| `avg_solar_MJm2` | `avg_solar_mjm2` |
| `기준일시` | `datetime` |
| `공급능력(MW)` | `supply_capacity` |
| `현재수요(MW)` | `current_demand` |
| `최대예측수요(MW)` | `forecast_load` |
| `운영예비력(MW)` | `operating_reserve_power` |
| `운영예비율(%)` | `operating_reserve_rate` |

---

## 8. model_registry 기록 방법

```sql
INSERT INTO model_registry
    (model_id, version, trained_at, train_start, train_end, rmse, mae, r2, model_path, is_active)
VALUES
    ('model1', 'v1.0', NOW(), '2023-01-01', '2025-12-31',
     12.5, 9.3, 0.91, '02.model/models/model1_v1.pkl', TRUE);
```
