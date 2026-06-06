# 에너지 데이터 수집기 (KPX OpenAPI)

공공데이터포털 KPX API 10종을 로컬 VS Code에서 백필 → parquet 저장 →(선택) GCS 업로드.
모델 학습용 데이터셋 구축이 목적.

## 설계 한 줄 요약
데이터셋 정의는 **`config/datasets.yaml`** 에만 있고, 코드(`src/`)는 안 건드린다.
새 API를 추가하거나 파라미터를 고칠 때 YAML만 수정한다.

## 핵심 제약: 하루 100건
KPX 개발계정 트래픽은 **하루 100건**이다. 그래서:
- 받은 단위는 parquet으로 남고, 재실행 시 **자동으로 건너뜀**(체크포인트).
- 하루 예산(`daily_call_budget: 90`)을 채우면 **깔끔히 멈추고**, 다음 실행 때 이어받는다.
- 즉 몇 년치 백필도 며칠에 걸쳐 `backfill`을 반복 실행하면 채워진다.
- 트래픽을 늘리려면 data.go.kr에서 **운영계정 전환(활용사례 등록)** 이 필요하다.

---

## 1. 설치
```bash
cd energy-collector
python -m venv .venv && source .venv/bin/activate   # 윈도우: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. API 키 넣기
```bash
cp .env.example .env
```
`.env`의 `KPX_SERVICE_KEY`에 **Decoding 키**를 붙여넣는다.
(Encoding 키 — `%2B`, `%3D` 섞인 것 — 를 쓰면 이중 인코딩으로 SERVICE KEY 오류가 난다.)

## 3. 동작 확인 (키가 맞는지부터)
바로 켜져 있는(`enabled: true`) 데이터셋으로 키·파이프라인을 먼저 검증한다.
```bash
python run.py list          # 상태표: ENABLED / CONFIGURED 확인
python run.py backfill --start 2024-01-01 --end 2024-01-01 --datasets smp_dayahead
```
`data/processed/smp_dayahead/<오늘날짜>.parquet`이 생기면 정상.

### 바로 되는 것 (요청주소 확인 완료)
- `smp_dayahead` 계통한계가격 및 수요예측 (snapshot)
- `power_supply_today` 오늘전력수급현황 (snapshot)
- `gen_by_source` 발전원별 발전량 현황 (snapshot)
- `solar_wind_by_region` 지역별 태양광·풍력 (odcloud, 연도별 파일 10개 자동 수집)

### 날짜 파라미터만 채우면 되는 것 (path 는 이미 채움)
아래 6개는 요청주소는 확정됐고, **상세설명의 요청변수에서 날짜/월 파라미터 이름만**
확인해 `date_param`에 넣고 `enabled: true`로 바꾸면 된다.
`monthly_fuel_cost`, `smp_decision_count`, `dr_economic`, `dr_reliability`,
`dr_voluntary`, `dr_plus`.
> 만약 해당 API에 날짜 파라미터가 아예 없다면(전체를 페이지로 다 주는 경우),
> `date_param` 줄을 지우고 `mode: snapshot` 으로 바꾼 뒤 `enabled: true` 하면 된다.

## 4. 응답 구조가 다르면
KPX 표준(XML `item`)과 odcloud(`data[]`)는 자동 처리된다. 특정 API가 빈 결과만
주면 그 API 응답 샘플을 보고 `src/parsers.py`의 추출 규칙을 한 줄 조정하면 된다.
(한 API가 실패해도 나머지 수집은 계속되고, 실패는 로그/요약에 남는다.)

## 5. 백필 실행
```bash
# 전체(설정된 것만), 기간 지정
python run.py backfill --start 2023-01-01 --end 2024-12-31

# 예산 소진 메시지가 뜨면 다음 날(또는 그냥 다시) 같은 명령 재실행 → 이어받음
```

## 6. 매일 증분
```bash
python run.py daily            # 최근 7일 윈도우, 이미 받은 건 skip
```
크론/작업스케줄러에 걸어두면 자동 누적. (지금은 로컬 기준. 나중에 그대로 컨테이너에 넣어
Cloud Run으로 승격 가능 — 코드 변경 없음.)

## 7. GCS 업로드
`.env`에 `GCS_BUCKET` 설정 후:
```bash
pip install google-cloud-storage
gcloud auth application-default login   # 또는 서비스계정 키 경로 지정
python run.py upload
```

---

## 폴더 구조
```
energy-collector/
├── .env                 # 키 (gitignore)
├── config/datasets.yaml # ★ 데이터셋 선언 — 여기만 수정
├── src/
│   ├── config.py        # 설정/키 로드
│   ├── client.py        # HTTP: 재시도·레이트리밋·키·호출카운트
│   ├── parsers.py       # XML/JSON 자동판별 + resultCode 처리
│   ├── storage.py       # parquet 저장·체크포인트·GCS
│   └── collector.py     # 단위생성·예산·페이지네이션 오케스트레이션
├── data/processed/      # <key>/<단위>.parquet
└── run.py               # CLI
```

## 자주 만나는 오류
- `SERVICE KEY IS NOT REGISTERED` → Decoding 키인지 확인. data.go.kr 승인 직후 1~2시간 반영 지연 있음.
- `LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS` → 하루 100건 초과. 다음 날 이어받기.
- 빈 결과만 나옴 → 응답 구조가 표준과 다른 API일 수 있음. 해당 API 응답 샘플을 보면
  `parsers.py`의 item 추출 규칙을 그 API에 맞게 한 줄 조정하면 된다.
"# Powersignal" 
"# Powersignal" 
