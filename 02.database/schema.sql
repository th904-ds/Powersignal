-- =============================================================
-- Powersignal DB 스키마
-- 실행: psql -U postgres -d powersignal -f schema.sql
-- =============================================================

-- ─────────────────────────────────────────────────────────────
-- 1. 원시 데이터 테이블 (collector가 씀)
-- ─────────────────────────────────────────────────────────────

-- SMP + 수요예측 (시간별, snapshot — 매일 전체 이력 갱신)
CREATE TABLE IF NOT EXISTS smp_dayahead (
    datetime    TIMESTAMPTZ NOT NULL,
    area_name   VARCHAR(10) NOT NULL,   -- '육지' | '제주'
    smp         DOUBLE PRECISION,
    jlfd        DOUBLE PRECISION,
    slfd        DOUBLE PRECISION,
    mlfd        DOUBLE PRECISION,
    PRIMARY KEY (datetime, area_name)
);

-- 발전원별 발전량 이력 (시간별, 일합산 wide 형태)
CREATE TABLE IF NOT EXISTS gen_by_source_hist (
    datetime            TIMESTAMPTZ PRIMARY KEY,
    gen_nuclear         DOUBLE PRECISION,
    gen_lng             DOUBLE PRECISION,
    gen_bituminous      DOUBLE PRECISION,   -- 유연탄
    gen_anthracite      DOUBLE PRECISION,   -- 무연탄
    gen_renewable       DOUBLE PRECISION,   -- 신재생·기타
    gen_hydro           DOUBLE PRECISION,   -- 수력
    gen_pumped          DOUBLE PRECISION,   -- 양수
    gen_oil             DOUBLE PRECISION,   -- 유전
    gen_total           DOUBLE PRECISION,
    gen_nuclear_ratio   DOUBLE PRECISION,
    gen_lng_ratio       DOUBLE PRECISION,
    gen_bituminous_ratio    DOUBLE PRECISION,
    gen_anthracite_ratio    DOUBLE PRECISION,
    gen_renewable_ratio     DOUBLE PRECISION,
    gen_hydro_ratio         DOUBLE PRECISION,
    gen_pumped_ratio        DOUBLE PRECISION,
    gen_oil_ratio           DOUBLE PRECISION
);

-- 월간 연료비용 (월별)
CREATE TABLE IF NOT EXISTS monthly_fuel_cost (
    month       DATE        NOT NULL,   -- 해당 월 1일
    fuel_type   VARCHAR(20) NOT NULL,
    cost        DOUBLE PRECISION,
    PRIMARY KEY (month, fuel_type)
);

-- 연료원별 SMP 결정횟수 (일별)
CREATE TABLE IF NOT EXISTS smp_decision_count (
    trade_date  DATE        NOT NULL,
    fuel_type   VARCHAR(20) NOT NULL,
    area_name   VARCHAR(10) NOT NULL,
    cnt         INTEGER,
    PRIMARY KEY (trade_date, fuel_type, area_name)
);

-- 종관기상관측 시간자료 ASOS (시간별, 4개 관측소)
CREATE TABLE IF NOT EXISTS asos_hourly (
    datetime        TIMESTAMPTZ NOT NULL,
    stn_id          VARCHAR(10) NOT NULL,   -- 108·133·143·159
    temp_c          DOUBLE PRECISION,
    humidity_pct    DOUBLE PRECISION,
    wind_speed_ms   DOUBLE PRECISION,
    dew_point_c     DOUBLE PRECISION,
    PRIMARY KEY (datetime, stn_id)
);

-- 기상 예보 (단기+중기, 매일 아침 갱신)
-- forecast_type: 'short'(단기 1시간) | 'mid_am'(중기 오전 09:00 KST) | 'mid_pm'(중기 오후 15:00 KST)
-- humidity_pct, wind_speed_ms: 단기만 제공, 중기는 NULL
-- asos_hourly(실측)와 UNION 시 dew_point_c = NULL 로 채워 사용
CREATE TABLE IF NOT EXISTS asos_forecast (
    datetime        TIMESTAMPTZ NOT NULL,
    stn_id          VARCHAR(10) NOT NULL,   -- 108·133·143·152·155·159·168
    issued_at       TIMESTAMPTZ,            -- 예보 발표 기준시각 (메타)
    forecast_type   VARCHAR(10) NOT NULL,   -- 'short' | 'mid_am' | 'mid_pm'
    temp_c          DOUBLE PRECISION,
    humidity_pct    DOUBLE PRECISION,
    wind_speed_ms   DOUBLE PRECISION,
    pop             DOUBLE PRECISION,       -- 강수확률 (%)
    sky_code        DOUBLE PRECISION,      -- 1맑음 2구름조금 3구름많음 4흐림
    PRIMARY KEY (datetime, stn_id)
);

CREATE INDEX IF NOT EXISTS idx_asos_forecast_dt ON asos_forecast (datetime DESC);
CREATE INDEX IF NOT EXISTS idx_asos_forecast_stn ON asos_forecast (stn_id);

-- ─────────────────────────────────────────────────────────────
-- 2. 전처리 완료 피처 테이블 (preprocessor가 씀, 모델이 읽음)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS model_features (
    datetime    TIMESTAMPTZ NOT NULL,
    model_id    VARCHAR(10) NOT NULL,   -- 'model1' | 'model2'

    -- 타겟
    smp         DOUBLE PRECISION,

    -- 수요예측 원본
    jlfd        DOUBLE PRECISION,
    slfd        DOUBLE PRECISION,
    mlfd        DOUBLE PRECISION,

    -- 발전량 (일합산)
    gen_nuclear     DOUBLE PRECISION,
    gen_lng         DOUBLE PRECISION,
    gen_bituminous  DOUBLE PRECISION,
    gen_anthracite  DOUBLE PRECISION,
    gen_renewable   DOUBLE PRECISION,
    gen_hydro       DOUBLE PRECISION,
    gen_pumped      DOUBLE PRECISION,
    gen_oil         DOUBLE PRECISION,
    gen_total       DOUBLE PRECISION,

    -- 발전원 비율
    gen_nuclear_ratio   DOUBLE PRECISION,
    gen_lng_ratio       DOUBLE PRECISION,
    gen_bituminous_ratio    DOUBLE PRECISION,
    gen_anthracite_ratio    DOUBLE PRECISION,
    gen_renewable_ratio     DOUBLE PRECISION,
    gen_hydro_ratio         DOUBLE PRECISION,
    gen_pumped_ratio        DOUBLE PRECISION,
    gen_oil_ratio           DOUBLE PRECISION,

    -- 연료비용 (월별 전파, 무연탄·원자력은 상수라 제외됨)
    fuel_cost_lng           DOUBLE PRECISION,
    fuel_cost_bituminous    DOUBLE PRECISION,
    fuel_cost_oil           DOUBLE PRECISION,

    -- NBTP (월별 전파)
    nbtp_accepted           DOUBLE PRECISION,   -- 낙찰NBTP (원/kWh)
    nbtp_bid                DOUBLE PRECISION,   -- 입찰NBTP (원/kWh, 2022.12~)

    -- SMP 결정횟수 (일별 전파)
    smp_decision_cnt_lng    DOUBLE PRECISION,

    -- 전력수급 (시간별, sukub 5분→1시간 집계)
    facility_capacity           DOUBLE PRECISION,
    supply_capacity             DOUBLE PRECISION,   -- 공급능력 min
    current_demand              DOUBLE PRECISION,   -- 현재수요 max
    forecast_load               DOUBLE PRECISION,   -- 최대예측수요 max
    supply_reserve_power        DOUBLE PRECISION,   -- 공급예비력 min
    supply_reserve_rate         DOUBLE PRECISION,   -- 공급예비율 min
    operating_reserve_power     DOUBLE PRECISION,   -- 운영예비력 min
    operating_reserve_rate      DOUBLE PRECISION,   -- 운영예비율 min

    -- 기상 (4개 관측소 avg, stepW 처리 완료)
    avg_temp_c          DOUBLE PRECISION,
    avg_humidity_pct    DOUBLE PRECISION,
    avg_wind_speed_ms   DOUBLE PRECISION,
    avg_precip_mm       DOUBLE PRECISION,
    avg_snow_cm         DOUBLE PRECISION,
    avg_sunshine_hr     DOUBLE PRECISION,
    avg_solar_mjm2      DOUBLE PRECISION,
    avg_temp_c_sq       DOUBLE PRECISION,

    -- 시간 피처 (step4)
    hour_of_day SMALLINT,
    weekday     SMALLINT,
    month_num   SMALLINT,
    is_weekend  SMALLINT,
    hour_sin    DOUBLE PRECISION,
    hour_cos    DOUBLE PRECISION,
    month_sin   DOUBLE PRECISION,
    month_cos   DOUBLE PRECISION,

    -- 공휴일 피처 (step5)
    is_holiday          SMALLINT,
    is_before_holiday   SMALLINT,
    is_after_holiday    SMALLINT,

    -- 수요예측 lag/차분 (step6, 공통)
    jlfd_lag24          DOUBLE PRECISION,
    jlfd_lag168         DOUBLE PRECISION,
    slfd_lag24          DOUBLE PRECISION,
    slfd_lag168         DOUBLE PRECISION,
    mlfd_lag24          DOUBLE PRECISION,
    mlfd_lag168         DOUBLE PRECISION,
    jlfd_diff_24        DOUBLE PRECISION,
    slfd_diff_24        DOUBLE PRECISION,
    mlfd_diff_24        DOUBLE PRECISION,
    jlfd_pct_change_24  DOUBLE PRECISION,
    slfd_pct_change_24  DOUBLE PRECISION,
    mlfd_pct_change_24  DOUBLE PRECISION,

    -- 예비력 lag 피처 (stepRESERVE)
    operating_reserve_rate_lag24            DOUBLE PRECISION,
    operating_reserve_rate_lag168           DOUBLE PRECISION,
    operating_reserve_power_lag24           DOUBLE PRECISION,
    operating_reserve_power_lag168          DOUBLE PRECISION,
    supply_capacity_lag24                   DOUBLE PRECISION,
    supply_capacity_lag168                  DOUBLE PRECISION,
    current_demand_lag24                    DOUBLE PRECISION,
    current_demand_lag168                   DOUBLE PRECISION,
    forecast_load_lag24                     DOUBLE PRECISION,
    forecast_load_lag168                    DOUBLE PRECISION,

    -- 운영예비율 rolling 피처 (stepRESERVE)
    operating_reserve_rate_roll_mean_24_lag24   DOUBLE PRECISION,
    operating_reserve_rate_roll_min_24_lag24    DOUBLE PRECISION,
    operating_reserve_rate_roll_std_24_lag24    DOUBLE PRECISION,
    operating_reserve_rate_roll_mean_168_lag24  DOUBLE PRECISION,
    operating_reserve_rate_roll_min_168_lag24   DOUBLE PRECISION,
    operating_reserve_rate_roll_std_168_lag24   DOUBLE PRECISION,

    -- 예비력 비율 파생 피처 (stepRESERVE)
    operating_reserve_power_to_demand_lag24     DOUBLE PRECISION,

    -- SMP 자기회귀 피처 (step7, model1 전용 — model2는 NULL)
    smp_lag1            DOUBLE PRECISION,
    smp_lag24           DOUBLE PRECISION,
    smp_lag48           DOUBLE PRECISION,
    smp_lag72           DOUBLE PRECISION,
    smp_lag168          DOUBLE PRECISION,
    smp_lag336          DOUBLE PRECISION,
    smp_roll_mean_24    DOUBLE PRECISION,
    smp_roll_mean_168   DOUBLE PRECISION,
    smp_roll_std_24     DOUBLE PRECISION,
    smp_roll_std_168    DOUBLE PRECISION,
    smp_roll_max_24     DOUBLE PRECISION,
    smp_roll_max_168    DOUBLE PRECISION,
    smp_roll_min_24     DOUBLE PRECISION,
    smp_roll_min_168    DOUBLE PRECISION,

    updated_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (datetime, model_id)
);

-- ─────────────────────────────────────────────────────────────
-- 3. 모델 예측 결과 (모델링 팀이 씀, 웹 팀이 읽음)
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS predictions (
    datetime            TIMESTAMPTZ NOT NULL,
    area_name           VARCHAR(10) NOT NULL DEFAULT '육지',
    model_id            VARCHAR(10) NOT NULL,
    smp_pred_base       DOUBLE PRECISION,        -- 모델1 1차 예측값
    smp_pred_residual   DOUBLE PRECISION,        -- 모델2 잔차 보정값
    smp_pred_final      DOUBLE PRECISION,        -- base + residual (화면 표시용)
    smp_score           DOUBLE PRECISION,        -- 0~100 정규화
    reserve_power_pred  DOUBLE PRECISION,        -- 예비력 예측 (신뢰성 DR 판정용, 검토중)
    dr_score            DOUBLE PRECISION,        -- 경제성 DR 낙찰 가능성 0~100
    model_version       VARCHAR(20),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (datetime, area_name, model_id)
);

-- 모델 버전 & 성능 기록 (모델링 팀이 씀)
CREATE TABLE IF NOT EXISTS model_registry (
    model_id        VARCHAR(10)  NOT NULL,
    version         VARCHAR(20)  NOT NULL,
    trained_at      TIMESTAMPTZ,
    train_start     DATE,
    train_end       DATE,
    rmse            DOUBLE PRECISION,
    mae             DOUBLE PRECISION,
    r2              DOUBLE PRECISION,
    model_path      TEXT,               -- .pkl 파일 경로
    feature_count   INTEGER,
    is_active       BOOLEAN DEFAULT FALSE,
    note            TEXT,
    PRIMARY KEY (model_id, version)
);

-- ─────────────────────────────────────────────────────────────
-- 4. 정적·참조 테이블 (프론트에서 직접 읽는 RAW/정적 데이터)
-- ─────────────────────────────────────────────────────────────

-- 지역별 시간별 태양광·풍력 발전량 (KPX odcloud, 연도별 파일 통합)
CREATE TABLE IF NOT EXISTS solar_wind_by_region (
    trade_date  DATE        NOT NULL,
    trade_hour  SMALLINT    NOT NULL,   -- 1~24
    region      VARCHAR(30) NOT NULL,
    solar_mwh   DOUBLE PRECISION,
    wind_mwh    DOUBLE PRECISION,
    PRIMARY KEY (trade_date, trade_hour, region)
);

-- 플러스DR 입낙찰 및 이행량 (KPX, 지역별·시간별, 10~18시)
CREATE TABLE IF NOT EXISTS dr_plus (
    trade_date      DATE        NOT NULL,
    region          VARCHAR(20) NOT NULL,
    trade_hour      SMALLINT    NOT NULL,   -- 10~18
    bid_mw          DOUBLE PRECISION,       -- 입찰량(MW)
    awarded_mw      DOUBLE PRECISION,       -- 낙찰량(MW)
    reduction_rate  DOUBLE PRECISION,       -- 이행률(%)
    PRIMARY KEY (trade_date, region, trade_hour)
);

-- 자발적DR 입낙찰 현황 (KPX, AI 리포트 학습용)
CREATE TABLE IF NOT EXISTS dr_voluntary (
    trade_date  DATE        NOT NULL,
    trade_hour  SMALLINT    NOT NULL,   -- tradeTm (시간)
    rn          SMALLINT    NOT NULL,   -- 행 순번 (tradeDay 내 고유)
    sra         DOUBLE PRECISION,       -- 수요감축량 입찰
    ssr         DOUBLE PRECISION,       -- 수요감축량 낙찰
    PRIMARY KEY (trade_date, rn)
);

-- 경제성DR 거래실적 (KPX, snapshot 전체이력)
CREATE TABLE IF NOT EXISTS dr_economic (
    trade_date  DATE             NOT NULL,
    rn          SMALLINT         NOT NULL,   -- API 행번호
    dr_type     VARCHAR(20),                 -- drType ('경제성DR')
    qty         DOUBLE PRECISION,            -- 입찰량
    pssr        DOUBLE PRECISION,            -- 입낙찰 관련값
    rdu         DOUBLE PRECISION,            -- 감축량(MWh)
    rdu_time    DOUBLE PRECISION,            -- 감축시간(h)
    rdu_rate    DOUBLE PRECISION,            -- 감축률(%)
    PRIMARY KEY (trade_date, rn)
);

-- 신뢰성DR 거래실적 (KPX, snapshot 전체이력, 센티넬 행 수집 시 제거)
CREATE TABLE IF NOT EXISTS dr_reliability (
    trade_date  DATE             NOT NULL,
    rn          SMALLINT         NOT NULL,   -- API 행번호
    dr_type     VARCHAR(20),                 -- drType ('신뢰성 DR')
    rdu_req     DOUBLE PRECISION,            -- 감축요청(MWh)
    rdu         DOUBLE PRECISION,            -- 감축량(MWh)
    rdu_time    DOUBLE PRECISION,            -- 감축시간(h)
    rdu_rate    DOUBLE PRECISION,            -- 감축률(%)
    PRIMARY KEY (trade_date, rn)
);

-- 업종별 집중도 지수 (정적, 팀 직접 정의)
CREATE TABLE IF NOT EXISTS industry_weights (
    industry_code   VARCHAR(20) PRIMARY KEY,  -- 예: 'semiconductor'
    industry_name   VARCHAR(40) NOT NULL,     -- 예: '반도체/전자'
    weight          DOUBLE PRECISION NOT NULL, -- 집중도 가중치
    description     TEXT
);

-- ─────────────────────────────────────────────────────────────
-- 5. 인덱스 (조회 성능)
-- ─────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_smp_dayahead_dt       ON smp_dayahead          (datetime DESC);
CREATE INDEX IF NOT EXISTS idx_gen_hist_dt            ON gen_by_source_hist    (datetime DESC);
CREATE INDEX IF NOT EXISTS idx_asos_dt               ON asos_hourly           (datetime DESC);
CREATE INDEX IF NOT EXISTS idx_model_features_dt     ON model_features        (datetime DESC);
CREATE INDEX IF NOT EXISTS idx_model_features_mid    ON model_features        (model_id);
CREATE INDEX IF NOT EXISTS idx_predictions_dt        ON predictions           (datetime DESC);
CREATE INDEX IF NOT EXISTS idx_smp_dec_date          ON smp_decision_count    (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_solar_wind_dt         ON solar_wind_by_region  (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_solar_wind_region     ON solar_wind_by_region  (region);
CREATE INDEX IF NOT EXISTS idx_dr_plus_dt            ON dr_plus               (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_dr_plus_region        ON dr_plus               (region);
CREATE INDEX IF NOT EXISTS idx_dr_voluntary_dt       ON dr_voluntary          (trade_date DESC);

-- ─────────────────────────────────────────────────────────────
-- 6. 정적 산업 에너지 통계 (한국에너지공단 산업부문 에너지사용 통계, 기준연도 2024)
-- ─────────────────────────────────────────────────────────────

-- 지역별 에너지원별 산업부문 소비 현황 (단위: 천toe)
CREATE TABLE IF NOT EXISTS region_energy_by_source (
    region              VARCHAR(20) PRIMARY KEY,
    total_ktoe          DOUBLE PRECISION,
    coal_ktoe           DOUBLE PRECISION,
    coal_pct            DOUBLE PRECISION,
    oil_ktoe            DOUBLE PRECISION,
    oil_pct             DOUBLE PRECISION,
    city_gas_ktoe       DOUBLE PRECISION,
    city_gas_pct        DOUBLE PRECISION,
    other_energy_ktoe   DOUBLE PRECISION,
    other_energy_pct    DOUBLE PRECISION,
    heat_ktoe           DOUBLE PRECISION,
    heat_pct            DOUBLE PRECISION,
    electricity_ktoe    DOUBLE PRECISION,
    electricity_pct     DOUBLE PRECISION
);

-- 지역별 산업부문 에너지소비 5개년 추이 (단위: 천toe)
CREATE TABLE IF NOT EXISTS region_energy_trend (
    region          VARCHAR(20) PRIMARY KEY,
    energy_2020     DOUBLE PRECISION,
    energy_2021     DOUBLE PRECISION,
    energy_2022     DOUBLE PRECISION,
    energy_2023     DOUBLE PRECISION,
    energy_2024     DOUBLE PRECISION,
    change_20_21    DOUBLE PRECISION,
    change_21_22    DOUBLE PRECISION,
    change_22_23    DOUBLE PRECISION,
    change_23_24    DOUBLE PRECISION,
    cagr_5yr_pct    DOUBLE PRECISION
);

-- 지역별 기업규모별 산업부문 에너지소비 (단위: 천toe)
CREATE TABLE IF NOT EXISTS region_energy_by_firm_size (
    region          VARCHAR(20) PRIMARY KEY,
    company_count   INTEGER,
    total_ktoe      DOUBLE PRECISION,
    large_ktoe      DOUBLE PRECISION,
    large_pct       DOUBLE PRECISION,
    medium_ktoe     DOUBLE PRECISION,
    medium_pct      DOUBLE PRECISION,
    small_ktoe      DOUBLE PRECISION,
    small_pct       DOUBLE PRECISION,
    other_ktoe      DOUBLE PRECISION,
    other_pct       DOUBLE PRECISION
);

-- 지역별 국가·일반 산업단지 에너지소비 현황 (단위: 천toe)
CREATE TABLE IF NOT EXISTS national_complex_energy (
    region                  VARCHAR(20) PRIMARY KEY,
    complex_count           INTEGER,
    company_count           INTEGER,
    total_ktoe              DOUBLE PRECISION,
    coal_ktoe               DOUBLE PRECISION,
    coal_pct                DOUBLE PRECISION,
    oil_ktoe                DOUBLE PRECISION,
    oil_pct                 DOUBLE PRECISION,
    city_gas_ktoe           DOUBLE PRECISION,
    city_gas_pct            DOUBLE PRECISION,
    other_energy_ktoe       DOUBLE PRECISION,
    other_energy_pct        DOUBLE PRECISION,
    heat_ktoe               DOUBLE PRECISION,
    heat_pct                DOUBLE PRECISION,
    electricity_ktoe        DOUBLE PRECISION,
    electricity_pct         DOUBLE PRECISION
);

-- 업종별 에너지원별 산업부문 소비 현황 (단위: 천toe)
CREATE TABLE IF NOT EXISTS industry_energy_by_source (
    industry                VARCHAR(50) PRIMARY KEY,
    total_ktoe              DOUBLE PRECISION,
    coal_ktoe               DOUBLE PRECISION,
    coal_pct                DOUBLE PRECISION,
    oil_ktoe                DOUBLE PRECISION,
    oil_pct                 DOUBLE PRECISION,
    city_gas_ktoe           DOUBLE PRECISION,
    city_gas_pct            DOUBLE PRECISION,
    other_energy_ktoe       DOUBLE PRECISION,
    other_energy_pct        DOUBLE PRECISION,
    heat_ktoe               DOUBLE PRECISION,
    heat_pct                DOUBLE PRECISION,
    electricity_ktoe        DOUBLE PRECISION,
    electricity_pct         DOUBLE PRECISION
);

-- 업종별 산업부문 에너지소비 5개년 추이 (단위: 천toe)
CREATE TABLE IF NOT EXISTS industry_energy_trend (
    industry                VARCHAR(50) PRIMARY KEY,
    energy_2020             DOUBLE PRECISION,
    energy_2021             DOUBLE PRECISION,
    energy_2022             DOUBLE PRECISION,
    energy_2023             DOUBLE PRECISION,
    energy_2024             DOUBLE PRECISION,
    change_20_21            DOUBLE PRECISION,
    change_21_22            DOUBLE PRECISION,
    change_22_23            DOUBLE PRECISION,
    change_23_24            DOUBLE PRECISION,
    cagr_5yr_pct            DOUBLE PRECISION
);

-- 업종별 기업규모별 산업부문 에너지소비 (단위: 천toe)
CREATE TABLE IF NOT EXISTS industry_energy_by_firm_size (
    industry                VARCHAR(50) PRIMARY KEY,
    company_count           INTEGER,
    total_ktoe              DOUBLE PRECISION,
    large_ktoe              DOUBLE PRECISION,
    large_pct               DOUBLE PRECISION,
    medium_ktoe             DOUBLE PRECISION,
    medium_pct              DOUBLE PRECISION,
    small_ktoe              DOUBLE PRECISION,
    small_pct               DOUBLE PRECISION,
    other_ktoe              DOUBLE PRECISION,
    other_pct               DOUBLE PRECISION
);

-- 지역별 전체 산업단지 에너지소비 현황 (단위: 천toe, 국가+일반+도시첨단 포함)
CREATE TABLE IF NOT EXISTS industrial_complex_energy (
    region                  VARCHAR(20) PRIMARY KEY,
    complex_count           INTEGER,
    company_count           INTEGER,
    total_ktoe              DOUBLE PRECISION,
    coal_ktoe               DOUBLE PRECISION,
    coal_pct                DOUBLE PRECISION,
    oil_ktoe                DOUBLE PRECISION,
    oil_pct                 DOUBLE PRECISION,
    city_gas_ktoe           DOUBLE PRECISION,
    city_gas_pct            DOUBLE PRECISION,
    other_energy_ktoe       DOUBLE PRECISION,
    other_energy_pct        DOUBLE PRECISION,
    heat_ktoe               DOUBLE PRECISION,
    heat_pct                DOUBLE PRECISION,
    electricity_ktoe        DOUBLE PRECISION,
    electricity_pct         DOUBLE PRECISION
);
