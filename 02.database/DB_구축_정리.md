# 2. DB 구축

| 항목 | 내용 |
|---|---|
| Status | In progress |
| 담당자 | 김태희 (인공지능대학 데이터사이언스학과) |
| 최종 업데이트 | 2026-06-24 |

---

## 작업 단계 요약

| 단계 | 작업 | 결과 |
|---|---|---|
| 1 | DB 선택 | PostgreSQL 선정 (구조화 데이터 + 팀 호환성) |
| 2 | 로컬 환경 구성 | Docker로 PostgreSQL 17 컨테이너 설치 |
| 3 | 스키마 설계 | 원본·피처·정적·예측 테이블 설계 (현재 총 26개) |
| 4 | Python 연동 모듈 작성 | `02.database/db.py` — upsert, rename, query |
| 5 | 기존 데이터 초기 적재 | `load_initial.py` — parquet → DB (420,000+행) |
| 6 | 수집 파이프라인 자동 연동 | `storage.py` 수정 — 수집 즉시 DB upsert |
| 7 | 전처리 파이프라인 자동 연동 | `run_preprocess.py` 수정 — 전처리 완료 시 DB upsert |
| 8 | 자동화 스케줄러 구성 | `scheduler.py` — APScheduler 5개 job 등록 |
| 9 | 클라우드 마이그레이션 | Supabase (cloud PostgreSQL 17) 으로 이전 |
| 10 | 예비력 데이터 추가 수집 | sukub 5분단위 수급 CSV 수동 수집 → model_features 통합 |
| 11 | 지역·DR 데이터 DB 적재 | `solar_wind_by_region`, `dr_plus`, `dr_voluntary` 테이블 신규 생성·적재 |
| 12 | predictions 스키마 확장 | 앙상블 컬럼(smp_pred_base/residual/final/score) + DR·예비력 예측 컬럼 추가 |
| 13 | 정적 참조 테이블 생성 | `industry_weights` 테이블 생성 및 6행 적재 (`load_industry_weights.py`) |
| 14 | 팀원 공유 준비 | `DB_GUIDE.md` 업데이트 |

---

## 1. DB 정보

| 항목 | 값 |
|---|---|
| DB 종류 | PostgreSQL 17 (Supabase cloud) |
| 프로젝트 ID | eszcdtumysqpifsprxrs |
| 리전 | ap-northeast-2 (서울) |
| 호스트 | aws-1-ap-northeast-2.pooler.supabase.com |
| 포트 | 5432 (Session pooler) |
| DB명 | postgres |
| 유저 | postgres.eszcdtumysqpifsprxrs |
| 연결 문자열 | **비밀번호 포함 — GPT나 Git 배포 금지** |

**Python 연결 (팀원용)**

```python
import os
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()  # 프로젝트 루트 .env 파일에 PG_URL 설정
engine = create_engine(os.environ["PG_URL"])
```

**필요 패키지**

```bash
pip install sqlalchemy psycopg2-binary python-dotenv pandas
```

---

## 2. 테이블 구조 (총 26개)

### 파이프라인 자동 적재 테이블

| 테이블 | 용도 | PK | 업데이트 주기 | 기간 | 행수 |
|---|---|---|---|---|---|
| `smp_dayahead` | SMP 실적 + 수요예측 | (datetime, area_name) | 매일 06:30 | 2020-01 ~ 현재 | 112,800행 |
| `gen_by_source_hist` | 발전원별 발전량 이력 | datetime | 매일 06:30 | 2022-01 ~ 약 4주 전 | 36,888행 |
| `monthly_fuel_cost` | 연료원별 월간 단가 | (month, fuel_type) | 매월 3일 | 2021-11 ~ 현재 | 280행 |
| `smp_decision_count` | 연료원별 SMP 결정횟수 | (trade_date, fuel_type, area_name) | 매일 06:30 | 2001-04 ~ 현재 | 28,449행 |
| `asos_hourly` | 기상관측 시간자료 (서울·대전·대구·부산) | (datetime, stn_id) | 매일 07:00 | 2020-01 ~ 현재 | 216,200행 |
| `sukub_raw` | 5분단위 수급 원시 (수동 CSV) | datetime | 수동 임포트 | — | 0행 (model_features에 통합됨) |
| `dr_plus` | 플러스DR 입낙찰·이행량 (지역별·시간별) | (trade_date, region, trade_hour) | 수집 시 | 2023-01 ~ 현재 | 54,657행 |
| `dr_voluntary` | 자발적DR 입낙찰 현황 (AI 리포트용) | (trade_date, rn) | 수집 시 | 2023-01 ~ 현재 | 23,097행 |

### 전처리 완료 피처 테이블

| 테이블 | 용도 | PK | 업데이트 주기 | 기간 | 행수 |
|---|---|---|---|---|---|
| **`model_features`** | **전처리 완료 ML 피처** | (datetime, model_id) | 매일 08:00 | 2023-01-01 ~ 2025-12-31 | **52,608행** (model1·model2 각 26,304행) |

### 프론트 RAW·정적 데이터 테이블

| 테이블 | 용도 | PK | 행수 | 비고 |
|---|---|---|---|---|
| `solar_wind_by_region` | 지역별 시간별 태양광·풍력 발전량 | (trade_date, trade_hour, region) | 1,368,912행 | 2017-01~2025-12, 19개 지역 |
| `dr_plus` | 플러스DR 지역 맥락 (위와 동일) | — | 54,657행 | 14개 지역, 10~18시 |
| `industry_weights` | 업종별 집중도 가중치 (정적) | industry_code | 6행 | `load_industry_weights.py`로 적재 완료 |

### 모델링 팀 작성 테이블

| 테이블 | 용도 | PK | 상태 |
|---|---|---|---|
| `predictions` | 모델 예측 결과 | (datetime, area_name, model_id) | 모델링 팀이 채움 (score_weighted_revenue_per_1000kw 컬럼 포함) |
| `model_registry` | 모델 버전·성능 기록 | (model_id, version) | 재학습 시 기록 |
| `model_artifacts` | 모델 산출물 바이너리 저장 | (model_id, version, artifact_type) | 모델링 팀이 채움 (신규) |
| `model_explain_values` | 모델 단위 SHAP 값 | id | 모델링 팀이 채움 (신규) |
| `prediction_explain_values` | 예측 단위 SHAP 값 | id | 모델링 팀이 채움 (신규) |

---

## 3. model_features 테이블 컬럼 구조

모델링 팀이 직접 사용하는 핵심 테이블. `model_id`로 두 모델 구분. **총 100컬럼.**

| 컬럼 그룹 | 주요 컬럼 | 비고 |
|---|---|---|
| 타겟 | `smp` | 예측 대상 (원/kWh) |
| 수요예측 | `jlfd`, `slfd`, `mlfd` | 단기·중기·장기 부하예측 (MW) |
| 발전량 | `gen_nuclear`, `gen_lng`, `gen_bituminous`, `gen_anthracite`, `gen_renewable`, `gen_hydro`, `gen_pumped`, `gen_oil`, `gen_total` | 일합산 MWh (24h 동일값) |
| 발전비율 | `gen_nuclear_ratio` ~ `gen_oil_ratio` (8개) | gen_* / gen_total |
| 연료비용 | `fuel_cost_lng`, `fuel_cost_bituminous`, `fuel_cost_oil` | 월별 단가 (월 내 동일값) |
| NBTP | `nbtp_accepted`, `nbtp_bid` | 수요자원 낙찰·입찰 기준가격 (월 내 동일값) |
| SMP 결정 | `smp_decision_cnt_lng` | LNG가 SMP 결정한 시간수 (일별) |
| 전력수급 | `facility_capacity`, `supply_capacity`, `supply_reserve_power`, `supply_reserve_rate`, `current_demand`, `forecast_load`, `operating_reserve_power`, `operating_reserve_rate` | 5분단위 sukub → 시간 집계 |
| 기상 | `avg_temp_c`, `avg_humidity_pct`, `avg_wind_speed_ms`, `avg_precip_mm`, `avg_snow_cm`, `avg_sunshine_hr`, `avg_solar_mjm2`, `avg_temp_c_sq` | 4개 관측소 평균 |
| 시간 피처 | `hour_of_day`, `weekday`, `month_num`, `is_weekend`, `hour_sin`, `hour_cos`, `month_sin`, `month_cos` | 순환 인코딩 포함 |
| 공휴일 | `is_holiday`, `is_before_holiday`, `is_after_holiday` | 한국 공휴일 기준 |
| 수요 lag | `jlfd_lag24/168`, `slfd_lag24/168`, `mlfd_lag24/168`, `*_diff_24`, `*_pct_change_24` (12개) | 24h·168h |
| 예비력 lag | `operating_reserve_rate_lag24/168`, `operating_reserve_power_lag24/168`, `supply_capacity_lag24/168`, `current_demand_lag24/168`, `forecast_load_lag24/168` (10개) | |
| 예비력 rolling | `operating_reserve_rate_roll_mean/min/std_24_lag24`, `operating_reserve_rate_roll_mean/min/std_168_lag24` (6개) | |
| 예비력 비율 | `operating_reserve_power_to_demand_lag24` | |
| SMP lag | `smp_lag1`, `smp_lag24`, `smp_lag48`, `smp_lag72`, `smp_lag168`, `smp_lag336` | **model1만 값 있음** (model2는 NULL) |
| SMP rolling | `smp_roll_mean_24/168`, `smp_roll_std_24/168`, `smp_roll_max/min_24/168` (8개) | **model1만 값 있음** |

> `model_id = 'model1'` : SMP 자기회귀 피처 포함
> `model_id = 'model2'` : 시장 변수만 (SMP lag 컬럼은 NULL)

---

## 4. predictions 테이블 컬럼 구조

요구사항 기준 앙상블 구조로 설계. 모델링 팀(상현)이 채움.

| 컬럼 | 설명 | 비고 |
|---|---|---|
| `datetime` | 예측 대상 시각 | PK |
| `area_name` | `'육지'` / `'제주'` | PK |
| `model_id` | `'model1'` / `'model2'` | PK |
| `smp_pred_base` | 모델1 1차 예측값 | |
| `smp_pred_residual` | 모델2 잔차 보정값 | |
| `smp_pred_final` | base + residual (화면 표시용 최종값) | **프론트가 이 값 사용** |
| `smp_score` | smp_pred_final 기준 0~100 정규화 | |
| `reserve_power_pred` | 예비력 예측 (MW) | 신뢰성 DR 판정용, 구현 완료 |
| `dr_score` | 경제성 DR 낙찰 가능성 0~100 | |
| `score_weighted_revenue_per_1000kw` | 1,000kW당 기대수익 | pssr_p75 × SMP × dr_score/100 |
| `predicted_smp` | (구버전 호환용) | 신규는 smp_pred_final 사용 |

### 4-1. SHAP 설명값 테이블 (신규, 모델링 팀이 씀)

| 테이블 | 용도 | PK |
|---|---|---|
| `model_artifacts` | 모델 산출물(pkl 등) 바이너리 저장 | (model_id, version, artifact_type) |
| `model_explain_values` | 모델 단위 SHAP 값 (학습/평가 시점) | id |
| `prediction_explain_values` | 예측 단위 SHAP 값 (스코어 근거 패널용) | id |

---

## 5. 데이터 저장 방식 — Upsert

새 데이터가 들어올 때마다 **ON CONFLICT DO UPDATE** 방식으로 처리.

- 중복 데이터 자동 덮어쓰기 (idempotent)
- 수집 실패 후 재실행해도 중복 없음
- 대용량 적재 시 COPY 방식 bulk upsert 사용 (30일 단위 청크, statement_timeout=0)

**컬럼명 변환 규칙 (한글 parquet → 영문 DB)**

| parquet 원본 | DB 컬럼명 |
|---|---|
| `gen_원자력` | `gen_nuclear` |
| `gen_LNG` | `gen_lng` |
| `gen_유연탄` | `gen_bituminous` |
| `gen_신재생·기타` | `gen_renewable` |
| `fuel_cost_LNG` | `fuel_cost_lng` |
| `avg_solar_MJm2` | `avg_solar_mjm2` |
| `공급능력(MW)` | `supply_capacity` |
| `현재수요(MW)` | `current_demand` |
| `최대예측수요(MW)` | `forecast_load` |
| `운영예비력(MW)` | `operating_reserve_power` |
| `운영예비율(%)` | `operating_reserve_rate` |

---

## 6. 자동화 스케줄러

`scheduler.py`를 실행하면 APScheduler가 아래 스케줄로 수집→전처리→DB 적재를 자동 반복.

```bash
cd Powersignal
python scheduler.py
# 종료: Ctrl+C
```

| Job ID | 실행 시각 | 작업 내용 |
|---|---|---|
| `realtime_5min` | 매 5분 (0~23시) | gen_by_source, power_supply_today 수집 → DB upsert |
| `daily_collect` | 매일 06:30 | smp_dayahead, gen_by_source_hist, smp_decision_count, DR 데이터 수집 → DB upsert |
| `daily_asos` | 매일 07:00 | asos_hourly 수집 → DB upsert |
| `daily_preprocess` | 매일 08:00 | run_preprocess.py → model_features DB upsert |
| `monthly_fuel` | 매월 3일 09:00 | monthly_fuel_cost 수집 → DB upsert |

스케줄러는 `python scheduler.py` 창이 열려있는 동안만 작동. DB(Supabase)는 클라우드이므로 팀원은 항상 접속 가능.

---

## 7. 파이프라인 자동 DB 연동 구조

```
[수집] 00.collector/run.py
  └→ storage.py (save() 호출)
       ├→ parquet 저장 (00.collector/data/processed/)
       └→ _try_upsert_to_db() → Supabase upsert

[전처리] 01.preprocessing/run_preprocess.py
  └→ step8_filter_save() 완료 후
       └→ _write_model_features_to_db() → Supabase model_features upsert

[정적 테이블 적재]
  02.database/load_static_tables.py   → solar_wind_by_region (2017-2025 정적, 재적재 시에만 실행)
  02.database/load_regional_csv.py    → region_energy_by_source 등 지역별 5개 테이블
  02.database/load_industrial_csv.py  → industry_energy_by_source 등 업종별 3개 테이블

  ※ dr_plus, dr_voluntary는 job_daily_collect가 매일 자동 수집·upsert (별도 적재 스크립트 불필요)
```

---

## 8. 팀원 공유 파일

| 파일 | 내용 |
|---|---|
| `02.database/DB_GUIDE.md` | 테이블 구조, 쿼리 예시, Python 연결 방법 (개발자용 상세) |
| `02.database/DB_구축_정리.md` | 이 파일 (팀 공유용 노션 정리본) |
| `02.database/schema.sql` | 테이블 DDL 전체 (참고용) |
| `02.database/load_static_tables.py` | solar_wind_by_region 적재 스크립트 (2017-2025 정적, 재적재용) |
| Supabase 연결 비밀번호 | 연결 문자열 형식에 포함 — **GPT·Git 배포 금지** |

---

## 초기 적재 행수 (2026-06-24 기준)

| 테이블 | 행수 | 기간 |
|---|---|---|
| smp_dayahead | 112,800행 | 2020-01 ~ 2026-06 |
| gen_by_source_hist | 36,888행 | 2022-01 ~ 2026-05 |
| monthly_fuel_cost | 280행 | 2021-11 ~ 2026-06 |
| smp_decision_count | 28,449행 | 2001-04 ~ 2026-05 |
| asos_hourly | 216,200행 | 2020-01 ~ 2026-06 |
| model_features (model1) | 26,304행 | 2023-01 ~ 2025-12 |
| model_features (model2) | 26,304행 | 2023-01 ~ 2025-12 |
| solar_wind_by_region | 1,368,912행 | 2017-01 ~ 2025-12 |
| dr_plus | 54,657행 | 2023-01 ~ 2026-06 |
| dr_voluntary | 23,097행 | 2023-01 ~ 2026-06 |
