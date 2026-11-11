# EVProject

강남구 전기차 충전소의 수요 분석, 입지 최적화, 결과 시각화 프로젝트입니다.
파일은 주요 기능별로 구분했으며, 기존 파일은 삭제하지 않았습니다. `DataSet/` 내부는 이번 정리에서 변경하지 않았습니다.

## 폴더 구조

```text
EVProject/
├─ DataSet/                        기존 데이터 폴더 (그대로 유지)
├─ AI_Capstone/                    데이터 분석 및 최적화 코드
│  ├─ collection/                  POI 수집
│  ├─ preprocessing/               격자·공간 데이터 전처리
│  ├─ modeling/                    수요 지수 모델링
│  ├─ optimization/                후보지 생성 및 입지 최적화
│  ├─ pipeline/                    전체 분석 통합 실행
│  ├─ evaluation/                  기준 방법 비교 및 성능 지표
│  ├─ diagnostics/                 데이터 구조 확인 및 최적화 디버깅
│  ├─ resources/                   기존 분석 폴더에 있던 POI·주차장 데이터
│  ├─ outputs/                     분석 결과 JSON·JS
│  ├─ archive/experiments/         과거 scratch 실험 스크립트
│  ├─ archive/logs/                과거 실행 로그·임시 출력
│  ├─ .vscode/                     기존 IDE 설정
│  └─ project_paths.py             프로젝트 공통 경로 설정
├─ dashboard/                      지도·차트 기반 웹 대시보드
│  ├─ index.html                   화면 진입점
│  ├─ style.css                    화면 스타일
│  ├─ script.js                    지도·차트·상호작용 로직
│  ├─ *.json, *_data.js, data.js    화면에서 사용하는 결과 데이터
│  ├─ heatmap.js                   히트맵 데이터
│  ├─ existing_stations.js         기존 충전소 데이터
│  ├─ index_single_file.html       기존 단일 HTML 배포본
│  ├─ tools/build_standalone.py    CSS·JS를 포함한 단일 HTML 생성
│  └─ archive/                     기존 script.txt·test.json 보관
├─ docs/file_moves.json            파일별 이전 위치 → 현재 위치 목록
└─ run_dashboard.py                대시보드 서버 실행
```

## 기능별 코드 안내

| 기능 | 파일 | 역할 |
| --- | --- | --- |
| 수집 | `collection/collect_gangnam_poi.py` | 관심 지점(POI) 수집 및 CSV 저장 |
| 전처리 | `preprocessing/preprocessing_phase1.py` | 초기 격자·데이터 전처리 방식 |
| 전처리 | `preprocessing/spatial_preprocessing.py` | 공간 격자와 인구·POI·차량 데이터 결합 |
| 전처리 | `preprocessing/update_poi_only.py` | 기존 격자의 POI 정보 갱신 |
| 수요 분석 | `modeling/demand_index_modeling.py` | KDE·PCA 등을 이용한 수요 지수 계산 |
| 최적화 | `optimization/siting_and_optimization.py` | 설치 후보지 생성 및 예산에 따른 최적 입지 계산 |
| 통합 실행 | `pipeline/gangnam_ev_siting_pipeline.py` | 전처리부터 최적화·화면용 데이터 생성까지 수행 |
| 비교 평가 | `evaluation/baseline_comparison.py` | 기준 방법과 비교하고 대시보드 비교 데이터 생성 |
| 지표 확인 | `evaluation/calculate_real_metrics.py` | 코드에 포함된 시나리오 데이터와 후보지로 지표 계산 |
| 점검 | `diagnostics/check_cols.py`, `inspect_data2.py`, `read_excel.py` | 데이터 열·파일 내용 확인 |
| 디버깅 | `diagnostics/debug.py`, `debug2.py`, `debug_milp.py` | 후보지·최적화 문제 점검 |

표의 코드 경로는 `AI_Capstone/` 기준입니다. 통합 파이프라인과 개별 단계 코드는 별도의 구현이므로, 동일한 결과를 보장하는 하나의 실행 체인으로 간주하지 않습니다.

## 실행 방법

Python과 필요한 라이브러리가 설치된 환경에서 프로젝트 루트 기준으로 실행합니다.

```powershell
# 대시보드 서버 시작 (브라우저 자동 열림, 종료: Ctrl+C)
python run_dashboard.py

# 전체 분석 실행
python AI_Capstone/pipeline/gangnam_ev_siting_pipeline.py

# 개별 단계 실행 예시
python AI_Capstone/preprocessing/spatial_preprocessing.py
python AI_Capstone/modeling/demand_index_modeling.py
python AI_Capstone/optimization/siting_and_optimization.py

# 단일 HTML 배포본 재생성
python dashboard/tools/build_standalone.py
```

주요 외부 라이브러리는 pandas, numpy, geopandas, shapely, scikit-learn, pulp, requests, pyproj, geopy, openpyxl입니다. 대시보드 서버와 HTML 빌더는 Python 표준 라이브러리를 사용합니다. 지도·차트 CDN 및 지도 경계 데이터 로딩에는 인터넷 연결이 필요합니다.

## 데이터와 결과 경로

- 유지 관리 대상 분석 스크립트의 기존 `C:\AI_Capstone` 고정 경로는 `project_paths.py`의 프로젝트 상대 경로로 교체했습니다.
- `resources/`는 원래 `AI_Capstone/`에 있던 데이터의 새 위치입니다. `DataSet/` 내부 파일을 이동한 것이 아닙니다.
- 통합 분석에서 생성하는 `data.*`, `heatmap.*`, `existing_stations.*`는 `AI_Capstone/outputs/`로 저장됩니다.
- `dashboard/`의 데이터는 기존 화면용 사본을 유지합니다. 분석 결과를 화면에 반영하려면 검토 후 `outputs/`의 JSON·JS 파일을 `dashboard/`로 복사하고 필요하면 단일 HTML을 다시 생성합니다. 기준 방법 비교 코드는 `dashboard/baseline_data.js`에 직접 저장합니다.
- 기존 `dashboard/index.html`이 참조하던 `heatmap.js`가 누락되어 있어, 기존 분석 결과의 동일 파일을 복사해 보완했습니다.
- 분석 코드는 실행 시 기존 동작대로 `DataSet/`의 전처리 CSV나 후보지 CSV를 생성·갱신할 수 있습니다. 이번 폴더 정리에서는 분석 코드를 실행하지 않았습니다.
- `archive/experiments/`는 과거 실험 원본 보관용입니다. 당시의 고정 경로가 남아 있으며, 실행 전 경로와 입력 데이터 확인이 필요합니다. `archive/logs/`의 임시 파일도 삭제 없이 보관했습니다.
- 초기 전처리 코드의 입력 파일 이름·하위 경로와 각 모델의 데이터 요구사항은 기존 구현을 유지했습니다. 실제 데이터와의 호환성 검증은 별도입니다.

## 확인 범위

파일 이동 목록과 이동 후 파일 존재 여부, 대시보드의 로컬 CSS·JS 참조, JavaScript 구문을 확인했습니다. 현재 환경에는 실행 가능한 Python 인터프리터가 없어 Python 코드 실행과 전체 분석 결과 검증은 수행하지 못했습니다.

전체 파일 이동 이력은 [docs/file_moves.json](docs/file_moves.json)에서 확인할 수 있습니다.
