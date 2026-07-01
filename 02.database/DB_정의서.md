DB 테이블 정의서
Supabase PostgreSQL  |  기준일: 2026-06-28

────────────────────────────────────────────────────────────
1. 전체 테이블 목록
────────────────────────────────────────────────────────────

  [원시 수집 데이터]
   1. smp_dayahead                             112,800행      2020-01-01  ~  2026-06-09
   2. gen_by_source_hist                       36,888행       2022-01-01  ~  2026-05-13
   3. monthly_fuel_cost                        280행          2021-11-01  ~  2026-06-01
   4. smp_decision_count                       28,449행       2001-04-02  ~  2026-05-29
   5. asos_hourly                              387,818행      2019-12-31  ~  2026-06-26
   6. asos_forecast                            630행          2026-06-27  ~  2026-07-04
   7. solar_wind_by_region                     1,359,384행    2017-01-01  ~  2025-12-31
   8. dr_plus                                  56,466행       2023-01-02  ~  2026-06-29
   9. dr_voluntary                             46,606행       2023-01-02  ~  2026-06-29
  10. dr_economic                              3,220행        2014-11-28  ~  2026-06-28
  11. dr_reliability                           780행          2014-12-05  ~  2026-05-26

  [모델링]
  12. model_features                           52,608행       2023-01-01  ~  2025-12-31
  13. model_registry                           5행          
  14. predictions                              168행          2026-01-01  ~  2026-01-07

  [정적 참조 데이터]
  15. industry_weights                         6행          
  16. industry_energy_by_source                13행         
  17. industry_energy_trend                    13행         
  18. industry_energy_by_firm_size             13행         
  19. region_energy_by_source                  18행         
  20. region_energy_trend                      18행         
  21. region_energy_by_firm_size               18행         
  22. industrial_complex_energy                18행         
  23. national_complex_energy                  18행         

────────────────────────────────────────────────────────────
2. 테이블별 컬럼 상세
────────────────────────────────────────────────────────────

  ▶ 원시 수집 데이터

  ────────────────────────────────────────
  smp_dayahead
  SMP + 수요예측 (시간별, 육지/제주)
  행수: 112,800  범위: 2020-01-01  ~  2026-06-09
  PK  : datetime, area_name

    datetime   TIMESTAMPTZ   NOT NULL  시간 (UTC)
    area_name  VARCHAR       NOT NULL  '육지' | '제주'
    smp        FLOAT                   계통한계가격 (원/kWh)
    jlfd       FLOAT                   전일 수요예측 (MW)
    slfd       FLOAT                   단기 수요예측 (MW)
    mlfd       FLOAT                   중기 수요예측 (MW)

  ────────────────────────────────────────
  gen_by_source_hist
  발전원별 발전량 이력 (시간별)
  행수: 36,888  범위: 2022-01-01  ~  2026-05-13
  PK  : datetime

    datetime              TIMESTAMPTZ   NOT NULL  시간 (UTC)
    gen_nuclear           FLOAT                   원자력 발전량 (MWh)
    gen_lng               FLOAT                   LNG 발전량 (MWh)
    gen_bituminous        FLOAT                   유연탄 발전량 (MWh)
    gen_anthracite        FLOAT                   무연탄 발전량 (MWh)
    gen_renewable         FLOAT                   신재생·기타 발전량 (MWh)
    gen_hydro             FLOAT                   수력 발전량 (MWh)
    gen_pumped            FLOAT                   양수 발전량 (MWh)
    gen_oil               FLOAT                   유류 발전량 (MWh)
    gen_total             FLOAT                   총 발전량 (MWh)
    gen_nuclear_ratio     FLOAT                   원자력 비율
    gen_lng_ratio         FLOAT                   LNG 비율
    gen_bituminous_ratio  FLOAT                   유연탄 비율
    gen_anthracite_ratio  FLOAT                   무연탄 비율
    gen_renewable_ratio   FLOAT                   신재생 비율
    gen_hydro_ratio       FLOAT                   수력 비율
    gen_pumped_ratio      FLOAT                   양수 비율
    gen_oil_ratio         FLOAT                   유류 비율

  ────────────────────────────────────────
  monthly_fuel_cost
  월간 연료비용 (연료원별)
  행수: 280  범위: 2021-11-01  ~  2026-06-01
  PK  : month, fuel_type

    month      DATE          NOT NULL  해당 월 1일
    fuel_type  VARCHAR       NOT NULL  연료 종류 (LNG·무연탄·원자력·유류·유연탄)
    cost       FLOAT                   연료비 (원/kWh 환산)

  ────────────────────────────────────────
  smp_decision_count
  연료원별 SMP 결정횟수 (일별)
  행수: 28,449  범위: 2001-04-02  ~  2026-05-29
  PK  : trade_date, fuel_type, area_name

    trade_date  DATE          NOT NULL  거래일
    fuel_type   VARCHAR       NOT NULL  연료 종류
    area_name   VARCHAR       NOT NULL  '육지' | '제주'
    cnt         INTEGER                 SMP 결정 횟수

  ────────────────────────────────────────
  asos_hourly
  종관기상관측 ASOS 시간자료 (7개 관측소)
  행수: 387,818  범위: 2019-12-31  ~  2026-06-26
  PK  : datetime, stn_id

    datetime       TIMESTAMPTZ   NOT NULL  관측 시각 (UTC)
    stn_id         VARCHAR       NOT NULL  관측소 ID (108·133·143·152·155·159·168)
    temp_c         FLOAT                   기온 (°C)
    humidity_pct   FLOAT                   상대습도 (%)
    wind_speed_ms  FLOAT                   풍속 (m/s)
    dew_point_c    FLOAT                   이슬점 (°C)

  ────────────────────────────────────────
  asos_forecast
  ASOS 단기·중기 기상예보 (7개 관측소)
  행수: 630  범위: 2026-06-27  ~  2026-07-04
  PK  : datetime, stn_id

    datetime       TIMESTAMPTZ   NOT NULL  예보 시각 (UTC)
    stn_id         VARCHAR       NOT NULL  관측소 ID
    issued_at      TIMESTAMPTZ             예보 발표 시각
    forecast_type  VARCHAR       NOT NULL  short · mid_am · mid_pm
    temp_c         FLOAT                   기온 예보 (°C)
    humidity_pct   FLOAT                   습도 예보 (%)
    wind_speed_ms  FLOAT                   풍속 예보 (m/s)
    pop            FLOAT                   강수확률 (%)
    sky_code       FLOAT                   하늘상태 코드

  ────────────────────────────────────────
  solar_wind_by_region
  지역별 시간별 태양광·풍력 발전량 (2017~2025, 18개 지역)
  행수: 1,359,384  범위: 2017-01-01  ~  2025-12-31
  PK  : trade_date, trade_hour, region

    trade_date  DATE          NOT NULL  날짜
    trade_hour  SMALLINT      NOT NULL  시간대 (1~24)
    region      VARCHAR       NOT NULL  지역명 (시도 17개 + 육지 합계)
    solar_mwh   FLOAT                   태양광 발전량 (MWh)
    wind_mwh    FLOAT                   풍력 발전량 (MWh)

  ────────────────────────────────────────
  dr_plus
  플러스DR 입낙찰·이행 (지역별·시간별, 10~18시)
  행수: 56,466  범위: 2023-01-02  ~  2026-06-29
  PK  : trade_date, region, trade_hour

    trade_date      DATE          NOT NULL  거래일
    region          VARCHAR       NOT NULL  지역명 (14개 권역)
    trade_hour      SMALLINT      NOT NULL  시간대 (10~18)
    bid_mw          FLOAT                   입찰량 (MW)
    awarded_mw      FLOAT                   낙찰량 (MW)
    reduction_rate  FLOAT                   이행률 (%)

  ────────────────────────────────────────
  dr_voluntary
  자발적DR 입낙찰 현황 (시간별)
  행수: 46,606  범위: 2023-01-02  ~  2026-06-29
  PK  : trade_date, rn

    trade_date  DATE          NOT NULL  거래일
    trade_hour  SMALLINT      NOT NULL  시간대 (1~24)
    rn          SMALLINT      NOT NULL  API 행 번호
    sra         FLOAT                   수요감축량 입찰 (MW)
    ssr         FLOAT                   수요감축량 낙찰 (MW)

  ────────────────────────────────────────
  dr_economic
  경제성DR 거래실적 (전체 이력)
  행수: 3,220  범위: 2014-11-28  ~  2026-06-28
  PK  : trade_date, rn

    trade_date  DATE          NOT NULL  거래일
    rn          SMALLINT      NOT NULL  API 행 번호
    dr_type     VARCHAR                 '경제성DR'
    qty         FLOAT                   입찰량
    pssr        FLOAT                   입낙찰 관련값
    rdu         FLOAT                   감축량 (MWh)
    rdu_time    FLOAT                   감축시간 (h)
    rdu_rate    FLOAT                   감축률 (%)

  ────────────────────────────────────────
  dr_reliability
  신뢰성DR 거래실적 (전체 이력)
  행수: 780  범위: 2014-12-05  ~  2026-05-26
  PK  : trade_date, rn

    trade_date  DATE          NOT NULL  거래일
    rn          SMALLINT      NOT NULL  API 행 번호
    dr_type     VARCHAR                 '신뢰성 DR'
    rdu_req     FLOAT                   감축요청량 (MWh)
    rdu         FLOAT                   감축량 (MWh)
    rdu_time    FLOAT                   감축시간 (h)
    rdu_rate    FLOAT                   감축률 (%)


  ▶ 모델링

  ────────────────────────────────────────
  model_features
  모델 학습·추론용 피처 테이블 (2023~2025)
  행수: 52,608  범위: 2023-01-01  ~  2025-12-31
  PK  : datetime, model_id

    datetime                                    TIMESTAMPTZ   NOT NULL  시간 (UTC)
    model_id                                    VARCHAR       NOT NULL  모델 ID
    smp                                         FLOAT                   ← smp_dayahead
    jlfd                                        FLOAT                   전일 수요예측 ← smp_dayahead
    slfd                                        FLOAT                   단기 수요예측 ← smp_dayahead
    mlfd                                        FLOAT                   중기 수요예측 ← smp_dayahead
    gen_nuclear                                 FLOAT                   ← gen_by_source_hist
    gen_lng                                     FLOAT                   ← gen_by_source_hist
    gen_bituminous                              FLOAT                   ← gen_by_source_hist
    gen_anthracite                              FLOAT                   ← gen_by_source_hist
    gen_renewable                               FLOAT                   ← gen_by_source_hist
    gen_hydro                                   FLOAT                   ← gen_by_source_hist
    gen_pumped                                  FLOAT                   ← gen_by_source_hist
    gen_oil                                     FLOAT                   ← gen_by_source_hist
    gen_total                                   FLOAT                   ← gen_by_source_hist
    gen_nuclear_ratio                           FLOAT                   ← gen_by_source_hist
    gen_lng_ratio                               FLOAT                   ← gen_by_source_hist
    gen_bituminous_ratio                        FLOAT                   ← gen_by_source_hist
    gen_anthracite_ratio                        FLOAT                   ← gen_by_source_hist
    gen_renewable_ratio                         FLOAT                   ← gen_by_source_hist
    gen_hydro_ratio                             FLOAT                   ← gen_by_source_hist
    gen_pumped_ratio                            FLOAT                   ← gen_by_source_hist
    gen_oil_ratio                               FLOAT                   ← gen_by_source_hist
    fuel_cost_lng                               FLOAT                   ← monthly_fuel_cost
    fuel_cost_bituminous                        FLOAT                   ← monthly_fuel_cost
    fuel_cost_oil                               FLOAT                   ← monthly_fuel_cost
    smp_decision_cnt_lng                        FLOAT                   ← smp_decision_count
    facility_capacity                           FLOAT                   설비용량 (MW) ← 전력수급 parquet
    supply_capacity                             FLOAT                   공급능력 (MW) ← 전력수급 parquet
    supply_reserve_power                        FLOAT                   공급예비력 (MW) ← 전력수급 parquet
    supply_reserve_rate                         FLOAT                   공급예비율 (%) ← 전력수급 parquet
    avg_temp_c                                  FLOAT                   평균기온 (°C) ← asos_hourly
    avg_humidity_pct                            FLOAT                   평균습도 (%) ← asos_hourly
    avg_wind_speed_ms                           FLOAT                   평균풍속 (m/s) ← asos_hourly
    avg_precip_mm                               FLOAT                   강수량 (mm) ← asos_hourly
    avg_snow_cm                                 FLOAT                   적설량 (cm) ← asos_hourly
    avg_sunshine_hr                             FLOAT                   일조시간 (h) ← asos_hourly
    avg_solar_mjm2                              FLOAT                   일사량 (MJ/m²) ← asos_hourly
    avg_temp_c_sq                               FLOAT                   기온 제곱 (비선형 피처)
    hour_of_day                                 SMALLINT                시간 (0~23)
    weekday                                     SMALLINT                요일 (0=월 ~ 6=일)
    month_num                                   SMALLINT                월 (1~12)
    is_weekend                                  SMALLINT                주말 여부
    hour_sin                                    FLOAT                   시간 sin 인코딩
    hour_cos                                    FLOAT                   시간 cos 인코딩
    month_sin                                   FLOAT                   월 sin 인코딩
    month_cos                                   FLOAT                   월 cos 인코딩
    is_holiday                                  SMALLINT                공휴일 여부
    is_before_holiday                           SMALLINT                공휴일 전날
    is_after_holiday                            SMALLINT                공휴일 다음날
    jlfd_lag24                                  FLOAT                   전일 수요예측 lag24h
    jlfd_lag168                                 FLOAT                   전일 수요예측 lag168h (1주)
    slfd_lag24                                  FLOAT                   단기 수요예측 lag24h
    slfd_lag168                                 FLOAT                   단기 수요예측 lag168h
    mlfd_lag24                                  FLOAT                   중기 수요예측 lag24h
    mlfd_lag168                                 FLOAT                   중기 수요예측 lag168h
    jlfd_diff_24                                FLOAT                   전일 수요예측 24h 차분
    slfd_diff_24                                FLOAT                   단기 수요예측 24h 차분
    mlfd_diff_24                                FLOAT                   중기 수요예측 24h 차분
    jlfd_pct_change_24                          FLOAT                   전일 수요예측 24h 변화율
    slfd_pct_change_24                          FLOAT                   단기 수요예측 24h 변화율
    mlfd_pct_change_24                          FLOAT                   중기 수요예측 24h 변화율
    smp_lag1                                    FLOAT                   SMP lag1h
    smp_lag24                                   FLOAT                   SMP lag24h
    smp_lag48                                   FLOAT                   SMP lag48h
    smp_lag72                                   FLOAT                   SMP lag72h
    smp_lag168                                  FLOAT                   SMP lag168h (1주)
    smp_lag336                                  FLOAT                   SMP lag336h (2주)
    smp_roll_mean_24                            FLOAT                   SMP 24h 이동평균
    smp_roll_mean_168                           FLOAT                   SMP 168h 이동평균
    smp_roll_std_24                             FLOAT                   SMP 24h 이동표준편차
    smp_roll_std_168                            FLOAT                   SMP 168h 이동표준편차
    smp_roll_max_24                             FLOAT                   SMP 24h 최대
    smp_roll_max_168                            FLOAT                   SMP 168h 최대
    smp_roll_min_24                             FLOAT                   SMP 24h 최소
    smp_roll_min_168                            FLOAT                   SMP 168h 최소
    updated_at                                  TIMESTAMPTZ             피처 생성 시각
    current_demand                              FLOAT                   현재 수요 (MW) ← 전력수급 parquet
    forecast_load                               FLOAT                   예측 부하 (MW) ← 전력수급 parquet
    operating_reserve_power                     FLOAT                   운영예비력 (MW) ← 전력수급 parquet
    operating_reserve_rate                      FLOAT                   운영예비율 (%) ← 전력수급 parquet
    operating_reserve_rate_lag24                FLOAT                   운영예비율 lag24h
    operating_reserve_rate_lag168               FLOAT                   운영예비율 lag168h
    operating_reserve_power_lag24               FLOAT                   운영예비력 lag24h
    operating_reserve_power_lag168              FLOAT                   운영예비력 lag168h
    supply_capacity_lag24                       FLOAT                   공급능력 lag24h
    supply_capacity_lag168                      FLOAT                   공급능력 lag168h
    current_demand_lag24                        FLOAT                   현재수요 lag24h
    current_demand_lag168                       FLOAT                   현재수요 lag168h
    forecast_load_lag24                         FLOAT                   예측부하 lag24h
    forecast_load_lag168                        FLOAT                   예측부하 lag168h
    operating_reserve_rate_roll_mean_24_lag24   FLOAT                   운영예비율 24h 평균 (lag24)
    operating_reserve_rate_roll_min_24_lag24    FLOAT                   운영예비율 24h 최소 (lag24)
    operating_reserve_rate_roll_std_24_lag24    FLOAT                   운영예비율 24h 표준편차 (lag24)
    operating_reserve_rate_roll_mean_168_lag24  FLOAT                   운영예비율 168h 평균 (lag24)
    operating_reserve_rate_roll_min_168_lag24   FLOAT                   운영예비율 168h 최소 (lag24)
    operating_reserve_rate_roll_std_168_lag24   FLOAT                   운영예비율 168h 표준편차 (lag24)
    operating_reserve_power_to_demand_lag24     FLOAT                   예비력/수요 비율 (lag24)
    nbtp_accepted                               FLOAT                   NBTP 낙찰량 ← 전력수급 parquet
    nbtp_bid                                    FLOAT                   NBTP 입찰량 ← 전력수급 parquet

  ────────────────────────────────────────
  model_registry
  모델 버전 및 성능 기록
  행수: 5
  PK  : model_id, version

    model_id       VARCHAR       NOT NULL  모델 ID
    version        VARCHAR       NOT NULL  버전
    trained_at     TIMESTAMPTZ             학습 완료 시각
    train_start    DATE                    학습 시작일
    train_end      DATE                    학습 종료일
    rmse           FLOAT                   RMSE
    mae            FLOAT                   MAE
    r2             FLOAT                   R²
    model_path     TEXT                    .joblib 파일 경로
    feature_count  INTEGER                 피처 수
    is_active      BOOLEAN                 현재 사용 중 여부
    note           TEXT                    역할·의존관계 메타 (JSON)

  ────────────────────────────────────────
  predictions
  SMP·DR 예측 결과
  행수: 168  범위: 2026-01-01  ~  2026-01-07
  PK  : datetime, area_name, model_id

    datetime            TIMESTAMPTZ   NOT NULL  예측 시각 (UTC)
    area_name           VARCHAR       NOT NULL  '육지' | '제주'
    model_id            VARCHAR       NOT NULL  모델 ID
    model_version       VARCHAR                 모델 버전
    created_at          TIMESTAMPTZ             예측 생성 시각
    smp_pred_base       FLOAT                   모델1 1차 SMP 예측 (원/kWh)
    smp_pred_residual   FLOAT                   모델2 잔차 보정값
    smp_pred_final      FLOAT                   최종 SMP 예측 = base + residual
    smp_score           FLOAT                   SMP 정규화 점수 (0~100)
    reserve_power_pred  FLOAT                   예비력 예측 (MW)
    dr_score            FLOAT                   경제성DR 낙찰 가능성 (0~100)


  ▶ 정적 참조 데이터

  ────────────────────────────────────────
  industry_weights
  업종별 집중도 가중치 (웹팀 정의)
  행수: 6
  PK  : industry_code

    industry_code  VARCHAR       NOT NULL  업종 코드 (예: semiconductor)
    industry_name  VARCHAR       NOT NULL  업종명 (예: 반도체/전자)
    weight         FLOAT         NOT NULL  집중도 가중치
    description    TEXT                    설명

  ────────────────────────────────────────
  industry_energy_by_source
  업종별 에너지원별 소비 현황 (2024 기준, 천toe)
  행수: 13
  PK  : industry

    industry           VARCHAR       NOT NULL  
    total_ktoe         FLOAT                   
    coal_ktoe          FLOAT                   
    coal_pct           FLOAT                   
    oil_ktoe           FLOAT                   
    oil_pct            FLOAT                   
    city_gas_ktoe      FLOAT                   
    city_gas_pct       FLOAT                   
    other_energy_ktoe  FLOAT                   
    other_energy_pct   FLOAT                   
    heat_ktoe          FLOAT                   
    heat_pct           FLOAT                   
    electricity_ktoe   FLOAT                   
    electricity_pct    FLOAT                   

  ────────────────────────────────────────
  industry_energy_trend
  업종별 에너지소비 5개년 추이 (2020~2024)
  행수: 13
  PK  : industry

    industry      VARCHAR       NOT NULL  
    energy_2020   FLOAT                   
    energy_2021   FLOAT                   
    energy_2022   FLOAT                   
    energy_2023   FLOAT                   
    energy_2024   FLOAT                   
    change_20_21  FLOAT                   
    change_21_22  FLOAT                   
    change_22_23  FLOAT                   
    change_23_24  FLOAT                   
    cagr_5yr_pct  FLOAT                   

  ────────────────────────────────────────
  industry_energy_by_firm_size
  업종별 기업규모별 에너지소비 (2024 기준)
  행수: 13
  PK  : industry

    industry       VARCHAR       NOT NULL  
    company_count  INTEGER                 
    total_ktoe     FLOAT                   
    large_ktoe     FLOAT                   
    large_pct      FLOAT                   
    medium_ktoe    FLOAT                   
    medium_pct     FLOAT                   
    small_ktoe     FLOAT                   
    small_pct      FLOAT                   
    other_ktoe     FLOAT                   
    other_pct      FLOAT                   

  ────────────────────────────────────────
  region_energy_by_source
  지역별 에너지원별 소비 현황 (2024 기준, 천toe)
  행수: 18
  PK  : region

    region             VARCHAR       NOT NULL  
    total_ktoe         FLOAT                   
    coal_ktoe          FLOAT                   
    coal_pct           FLOAT                   
    oil_ktoe           FLOAT                   
    oil_pct            FLOAT                   
    city_gas_ktoe      FLOAT                   
    city_gas_pct       FLOAT                   
    other_energy_ktoe  FLOAT                   
    other_energy_pct   FLOAT                   
    heat_ktoe          FLOAT                   
    heat_pct           FLOAT                   
    electricity_ktoe   FLOAT                   
    electricity_pct    FLOAT                   

  ────────────────────────────────────────
  region_energy_trend
  지역별 에너지소비 5개년 추이 (2020~2024)
  행수: 18
  PK  : region

    region        VARCHAR       NOT NULL  
    energy_2020   FLOAT                   
    energy_2021   FLOAT                   
    energy_2022   FLOAT                   
    energy_2023   FLOAT                   
    energy_2024   FLOAT                   
    change_20_21  FLOAT                   
    change_21_22  FLOAT                   
    change_22_23  FLOAT                   
    change_23_24  FLOAT                   
    cagr_5yr_pct  FLOAT                   

  ────────────────────────────────────────
  region_energy_by_firm_size
  지역별 기업규모별 에너지소비 (2024 기준)
  행수: 18
  PK  : region

    region         VARCHAR       NOT NULL  
    company_count  INTEGER                 
    total_ktoe     FLOAT                   
    large_ktoe     FLOAT                   
    large_pct      FLOAT                   
    medium_ktoe    FLOAT                   
    medium_pct     FLOAT                   
    small_ktoe     FLOAT                   
    small_pct      FLOAT                   
    other_ktoe     FLOAT                   
    other_pct      FLOAT                   

  ────────────────────────────────────────
  industrial_complex_energy
  지역별 전체 산업단지 에너지소비 (국가+일반+도시첨단)
  행수: 18
  PK  : region

    region             VARCHAR       NOT NULL  
    complex_count      INTEGER                 
    company_count      INTEGER                 
    total_ktoe         FLOAT                   
    coal_ktoe          FLOAT                   
    coal_pct           FLOAT                   
    oil_ktoe           FLOAT                   
    oil_pct            FLOAT                   
    city_gas_ktoe      FLOAT                   
    city_gas_pct       FLOAT                   
    other_energy_ktoe  FLOAT                   
    other_energy_pct   FLOAT                   
    heat_ktoe          FLOAT                   
    heat_pct           FLOAT                   
    electricity_ktoe   FLOAT                   
    electricity_pct    FLOAT                   

  ────────────────────────────────────────
  national_complex_energy
  지역별 국가·일반 산업단지 에너지소비
  행수: 18
  PK  : region

    region             VARCHAR       NOT NULL  
    complex_count      INTEGER                 
    company_count      INTEGER                 
    total_ktoe         FLOAT                   
    coal_ktoe          FLOAT                   
    coal_pct           FLOAT                   
    oil_ktoe           FLOAT                   
    oil_pct            FLOAT                   
    city_gas_ktoe      FLOAT                   
    city_gas_pct       FLOAT                   
    other_energy_ktoe  FLOAT                   
    other_energy_pct   FLOAT                   
    heat_ktoe          FLOAT                   
    heat_pct           FLOAT                   
    electricity_ktoe   FLOAT                   
    electricity_pct    FLOAT                   
