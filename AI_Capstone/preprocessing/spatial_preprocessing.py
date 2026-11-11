# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point, box
import os
import glob
import re
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# 1. 설정 및 경로 정의
# ==========================================
DATA_DIR = str(DATASET_DIR)
OUT_GRID_PATH = os.path.join(DATA_DIR, "gangnam_grid_preprocessed.csv")

# 1.1 입력 파일 경로 자동 매핑
RAW_DATA_DIR = os.path.join(DATA_DIR, "분석용_정리데이터")
POP_DIR = os.path.join(RAW_DATA_DIR, "2602_유동인구데이터")
POI_PATH = str(RESOURCE_DIR / "gangnam_POI.csv")

# Excel 파일들 glob 패턴으로 탐색
apt_files = glob.glob(os.path.join(RAW_DATA_DIR, "*아파트*.xlsx"))
ev_files = glob.glob(os.path.join(RAW_DATA_DIR, "*친환경차*.xlsx"))

APT_PATH = apt_files[0] if apt_files else None
EV_PATH = ev_files[0] if ev_files else None

print("=== [Part 1] 공간 데이터 전처리 파이프라인 시작 ===")
print(f"아파트 파일 경로: {APT_PATH}")
print(f"친환경차 등록현황 경로: {EV_PATH}")
print(f"POI 파일 경로: {POI_PATH}")
print(f"유동인구 데이터 디렉토리: {POP_DIR}")

# ==========================================
# 2. 강남구 행정경계 로드 및 100m Grid 생성
# ==========================================
# 2.1 강남구 행정동 경계 SHP 로드 (없을 경우 Bounding Box로 synthetic 생성)
shp_files = glob.glob(os.path.join(DATA_DIR, "*.shp")) + glob.glob(os.path.join(RAW_DATA_DIR, "*.shp"))
gangnam_boundary = None

if shp_files:
    print(f"\n강남구 shapefile을 불러옵니다: {shp_files[0]}")
    try:
        gangnam_gdf = gpd.read_file(shp_files[0])
        # EPSG:5179 변환
        if gangnam_gdf.crs != "EPSG:5179":
            gangnam_gdf = gangnam_gdf.to_crs("EPSG:5179")
        # 강남구만 필터링 (행정구역 코드 혹은 이름 기준)
        # 구 이름 컬럼 탐색 및 필터링
        gu_cols = [c for c in gangnam_gdf.columns if any(x in str(c).lower() for x in ['sig_kor_nm', 'sgg_nm', '구명', '시군구'])]
        if gu_cols:
            gangnam_gdf = gangnam_gdf[gangnam_gdf[gu_cols[0]].str.contains('강남구', na=False)]
        gangnam_boundary = gangnam_gdf.geometry.unary_union
    except Exception as e:
        print(f"Shapefile 로드 오류: {e}. Bounding Box Fallback을 적용합니다.")

if gangnam_boundary is None:
    print("\n[알림] 강남구 shapefile이 존재하지 않거나 로드에 실패했습니다.")
    print("강남구 행정경계 바운딩 박스를 기준으로 Synthetic 경계를 구성합니다 (CRS: EPSG:5179).")
    # 대략적인 강남구 바운딩 박스 (EPSG:5179)
    # preprocessing_phase1.py의 GANGNAM_MIN_LON, LAT 기반 수학적 좌표 범위
    min_x, min_y = 957194.5502129612, 1939865.7618353504
    max_x, max_y = 967194.5502129612, 1948865.7618353504
    gangnam_boundary = box(min_x, min_y, max_x, max_y)

# 2.2 100m 격자망 생성
print("\n강남구 경계 내 100m x 100m 폴리곤 격자를 생성 중...")
bounds = gangnam_boundary.bounds  # (minx, miny, maxx, maxy)
grid_size = 100

x_coords = np.arange(bounds[0], bounds[2] + grid_size, grid_size)
y_coords = np.arange(bounds[1], bounds[3] + grid_size, grid_size)

grid_cells = []
for x in x_coords:
    for y in y_coords:
        # 100m 격자박스 생성
        grid_cells.append(box(x, y, x + grid_size, y + grid_size))

grid_gdf = gpd.GeoDataFrame(geometry=grid_cells, crs="EPSG:5179")

# 강남구 경계 내 격자만 필터링 (Spatial Join)
grid_gdf = grid_gdf[grid_gdf.intersects(gangnam_boundary)].copy().reset_index(drop=True)
grid_gdf['grid_id'] = [f"G{i:05d}" for i in range(len(grid_gdf))]

# 중심점 좌표 추출
centroids = grid_gdf.geometry.centroid
grid_gdf['centroid_x'] = centroids.x
grid_gdf['centroid_y'] = centroids.y

print(f"성공: 총 {len(grid_gdf)}개의 100m 격자가 생성되었습니다.")

# ==========================================
# 3. 생활인구 데이터 (주/야간) 전처리 및 매핑
# ==========================================
print("\n생활인구 데이터 집계 및 공간 조인 시작...")
pop_files = glob.glob(os.path.join(POP_DIR, "*.csv"))

if pop_files:
    print(f"총 {len(pop_files)}개의 생활인구 CSV 파일을 발견했습니다. 최적화된 처리를 시작합니다.")
    pop_daily_list = []
    
    for f_idx, pop_file in enumerate(sorted(pop_files)):
        try:
            # 1. 인코딩 및 컬럼 자동 식별을 위해 2행 로드
            temp_df = pd.read_csv(pop_file, nrows=2, encoding='cp949')
            encoding = 'cp949'
        except Exception:
            temp_df = pd.read_csv(pop_file, nrows=2, encoding='utf-8')
            encoding = 'utf-8'
            
        cols = temp_df.columns.tolist()
        
        # 컬럼 이름 복원 (위치 기반/키워드 매칭)
        col_hour = [c for c in cols if '시간' in str(c) or '시간' in str(c).encode('utf-8', errors='ignore').decode('cp949', errors='ignore') or 'time' in str(c).lower() or c == cols[1]][0]
        col_dong = [c for c in cols if '동코드' in str(c) or 'dong' in str(c).lower() or c == cols[2]][0]
        col_grid = [c for c in cols if '격자' in str(c) or 'grid' in str(c).lower() or c == cols[3]][0]
        col_pop = [c for c in cols if '합계' in str(c) or 'pop' in str(c).lower() or c == cols[4]][0]
        
        # 2. 강남구 행정동 코드(11680)만 필터링하여 경량화 로드
        # usecols로 필요한 컬럼만 추출하여 메모리 절약
        df = pd.read_csv(pop_file, encoding=encoding, usecols=[col_hour, col_dong, col_grid, col_pop])
        df = df[df[col_dong].astype(str).str.startswith('11680')].copy()
        
        if df.empty:
            continue
            
        # Convert population column to numeric, replacing privacy masks (*) with 0.0
        df[col_pop] = pd.to_numeric(df[col_pop], errors='coerce').fillna(0.0)
            
        # 주/야간 분류 (주간: 09:00 ~ 18:00, 야간: 그 외)
        df['is_daytime'] = (df[col_hour] >= 9) & (df[col_hour] < 18)
        
        # 격자별 주/야간 평균 생활인구 산출
        # 일별 파일 내에서 각 격자의 주간/야간 시간대 평균 스냅샷 인구를 계산
        grid_pop = df.groupby([col_grid, 'is_daytime'])[col_pop].mean().unstack(fill_value=0)
        
        # Unstack 결과 컬럼 이름 처리
        grid_pop.columns = ['nighttime_pop', 'daytime_pop']
        pop_daily_list.append(grid_pop.reset_index())
        
        if (f_idx + 1) % 5 == 0 or (f_idx + 1) == len(pop_files):
            print(f" - 진행 상황: {f_idx + 1}/{len(pop_files)} 파일 전처리 완료...")
            
    # 전체 기간 동안의 평균 구하기
    all_pop = pd.concat(pop_daily_list, ignore_index=True)
    mean_pop = all_pop.groupby(col_grid)[['daytime_pop', 'nighttime_pop']].mean().reset_index()
    
    # 250M 격자 중심점 좌표 복원
    # 다사XXXXYYYY -> X_center = 900000 + XXXX * 10 + 125, Y_center = 1900000 + YYYY * 10 + 125 (250m 격자의 정중앙)
    def parse_grid_coords(grid_code):
        match = re.search(r'(\d{8})', str(grid_code))
        if match:
            digits = match.group(1)
            x = 900000 + int(digits[:4]) * 10 + 125
            y = 1900000 + int(digits[4:]) * 10 + 125
            return x, y
        return None, None
        
    coords = mean_pop[col_grid].apply(parse_grid_coords)
    mean_pop['x_5179'] = [c[0] for c in coords]
    mean_pop['y_5179'] = [c[1] for c in coords]
    
    # NaN 좌표 필터링 및 Point GeoDataFrame 생성
    mean_pop = mean_pop.dropna(subset=['x_5179', 'y_5179']).copy()
    pop_gdf = gpd.GeoDataFrame(
        mean_pop, 
        geometry=gpd.points_from_xy(mean_pop['x_5179'], mean_pop['y_5179']),
        crs="EPSG:5179"
    )
    
    # 100m grid에 Spatial Join (각 100m 격자 안에 떨어지는 250m 격자 중심의 인구값 합산 혹은 평균)
    # 100m 격자가 250m보다 조밀하므로, 100m 격자별로 가장 가까운(혹은 포함하는) 250m 생활인구를 할당
    joined = gpd.sjoin(grid_gdf, pop_gdf[['daytime_pop', 'nighttime_pop', 'geometry']], how='left', predicate='contains')
    # 혹시 sjoin으로 안 잡힌 외곽 격자는 가장 가까운 곳 매핑하기 위해 nearest join 적용
    nan_grids = joined[joined['daytime_pop'].isna()]
    if not nan_grids.empty:
        non_nan_grids = pop_gdf[['daytime_pop', 'nighttime_pop', 'geometry']]
        # 가까운 point 매핑
        nearest_joined = gpd.sjoin_nearest(nan_grids.drop(columns=['daytime_pop', 'nighttime_pop', 'index_right']), non_nan_grids, how='left', max_distance=300)
        joined.update(nearest_joined)
        
    # grid_id 기준으로 groupby 및 평균
    pop_result = joined.groupby('grid_id')[['daytime_pop', 'nighttime_pop']].mean().reset_index().fillna(0)
    grid_gdf = pd.merge(grid_gdf, pop_result, on='grid_id', how='left').fillna({'daytime_pop': 0, 'nighttime_pop': 0})
    print("완료: 생활인구 공간 조인 및 100m 격자 매핑 완료.")
else:
    print("[경고] 생활인구 폴더가 비어있거나 찾을 수 없습니다. 인구수를 0으로 초기화합니다.")
    grid_gdf['daytime_pop'] = 0.0
    grid_gdf['nighttime_pop'] = 0.0

# ==========================================
# 4. POI 데이터 전처리 및 매핑
# ==========================================
print("\nPOI 데이터 집계 및 공간 조인 시작...")
if os.path.exists(POI_PATH):
    poi_df = pd.read_csv(POI_PATH)
    
    # target 카테고리 필터링 (대형마트, 백화점, 지하철역, 공공기관 등 상업/업무 주요 POI)
    target = ['대형마트', '백화점', '지하철역', '공공기관', 'MT1', 'SW8', 'PO3']
    
    # 카테고리 그룹명이나 키워드에 포함된 경우
    poi_filtered = poi_df[
        poi_df['category_group_name'].isin(target) |
        poi_df['search_keyword'].isin(target) |
        poi_df['category_name'].str.contains('|'.join(target[:-3]), na=False)
    ].copy()
    
    # EPSG:4326 Point 생성 및 EPSG:5179 변환
    poi_gdf = gpd.GeoDataFrame(
        poi_filtered,
        geometry=gpd.points_from_xy(poi_filtered['x'], poi_filtered['y']),
        crs="EPSG:4326"
    ).to_crs("EPSG:5179")
    
    # 100m 격자에 포함되는 POI 카운팅
    poi_joined = gpd.sjoin(poi_gdf, grid_gdf[['grid_id', 'geometry']], how='inner', predicate='within')
    poi_counts = poi_joined.groupby('grid_id').size().reset_index(name='poi_count')
    
    grid_gdf = pd.merge(grid_gdf, poi_counts, on='grid_id', how='left').fillna({'poi_count': 0})
    print(f"완료: 총 {len(poi_gdf)}개 주요 POI 중 강남구 격자 내 {int(grid_gdf['poi_count'].sum())}개 매핑 및 카운트 완료.")
else:
    print("[경고] POI 파일을 찾을 수 없습니다. POI 개수를 0으로 초기화합니다.")
    grid_gdf['poi_count'] = 0

# ==========================================
# 5. 전기차 등록대수 및 아파트 세대수 데이터 전처리 및 매핑
# ==========================================
print("\n전기차 등록대수 및 아파트 세대수 비례 Spatial Disaggregation 시작...")
if APT_PATH and EV_PATH:
    df_apt = pd.read_excel(APT_PATH)
    df_ev = pd.read_excel(EV_PATH)
    
    # 아파트 강남구 필터링
    addr_col = [c for c in df_apt.columns if '도로명' in c or '주소' in c or 'kapt' in c][0]
    df_apt = df_apt[df_apt[addr_col].astype(str).str.contains("강남구")].copy()
    
    # Dong명 매핑 및 정규화
    def clean_dong(addr):
        match = re.search(r'([가-힣]+동)', str(addr))
        if match:
            dong = match.group(1)
            # 행정동 명칭 법정동 명칭 조정을 위한 정규화
            # '세곡동', '자곡동', '율현동' -> '세곡동' (세곡동 행정동으로 통합)
            if dong in ['자곡동', '율현동']:
                return '세곡동'
            # 숫자가 포함된 행정동의 경우 숫자를 제외한 법정동 명으로 병합
            dong_base = re.sub(r'\d', '', dong)
            return dong_base
        return '기타'
        
    df_apt['legal_dong'] = df_apt[addr_col].apply(clean_dong)
    
    # EV 데이터 동명 정규화
    ev_dong_col = df_ev.columns[0]
    ev_val_col = df_ev.columns[3]  # 전기차수
    df_ev['legal_dong'] = df_ev[ev_dong_col].apply(clean_dong)
    
    # EV 데이터 법정동별 합산 (행정동 단위 데이터를 법정동 단위로 롤업)
    ev_dong_sum = df_ev.groupby('legal_dong')[ev_val_col].sum().reset_index()
    ev_dong_sum.columns = ['legal_dong', 'total_ev']
    
    # 아파트 세대수 및 주차대수 추출
    households_col = [c for c in df_apt.columns if '세대수' in c or '세대' in c or 'ü' in c][0]
    parking_col = [c for c in df_apt.columns if '주차' in c or '대수' in c or c == df_apt.columns[6]][0]
    
    # NaN 값 0 처리
    df_apt[households_col] = pd.to_numeric(df_apt[households_col], errors='coerce').fillna(0)
    df_apt[parking_col] = pd.to_numeric(df_apt[parking_col], errors='coerce').fillna(0)
    
    # 법정동별 총 주차대수 집계
    dong_parking_total = df_apt.groupby('legal_dong')[parking_col].sum().reset_index()
    dong_parking_total.columns = ['legal_dong', 'total_parking_in_dong']
    
    # 아파트 데이터 병합 및 세대수/주차수 비례 가중치 계산
    df_apt = pd.merge(df_apt, dong_parking_total, on='legal_dong', how='left')
    df_apt = pd.merge(df_apt, ev_dong_sum, on='legal_dong', how='left').fillna({'total_ev': 0})
    
    # 가중치 (주차대수 기준, 분모가 0일 경우 세대수 기준 대체)
    df_apt['parking_weight'] = np.where(
        df_apt['total_parking_in_dong'] > 0,
        df_apt[parking_col] / df_apt['total_parking_in_dong'],
        0
    )
    
    # 가중치에 따라 전기차 등록 대수 할당
    df_apt['allocated_ev'] = df_apt['total_ev'] * df_apt['parking_weight']
    
    # 좌표 컬럼 추출
    x_col = [c for c in df_apt.columns if '좌표X' in c or 'X' in c or '경도' in c][0]
    y_col = [c for c in df_apt.columns if '좌표Y' in c or 'Y' in c or '위도' in c][0]
    
    df_apt = df_apt.dropna(subset=[x_col, y_col]).copy()
    
    # 아파트 Points GeoDataFrame 생성 (EPSG:4326 -> 5179)
    apt_gdf = gpd.GeoDataFrame(
        df_apt,
        geometry=gpd.points_from_xy(df_apt[x_col], df_apt[y_col]),
        crs="EPSG:4326"
    ).to_crs("EPSG:5179")
    
    # 격자 안에 포함되는 아파트의 전기차 및 세대수 합산
    apt_joined = gpd.sjoin(apt_gdf, grid_gdf[['grid_id', 'geometry']], how='inner', predicate='within')
    
    apt_aggregated = apt_joined.groupby('grid_id').agg({
        'allocated_ev': 'sum',
        households_col: 'sum'
    }).reset_index()
    
    apt_aggregated.columns = ['grid_id', 'allocated_ev', 'apartment_households']
    
    grid_gdf = pd.merge(grid_gdf, apt_aggregated, on='grid_id', how='left').fillna({
        'allocated_ev': 0.0,
        'apartment_households': 0.0
    })
    
    print(f"완료: 아파트 전기차 분할 및 강남구 격자 내 할당 완료. 총 할당 EV: {grid_gdf['allocated_ev'].sum():.1f}대")
else:
    print("[경고] 아파트 또는 EV 등록 데이터가 누락되었습니다. 관련 수치를 0으로 초기화합니다.")
    grid_gdf['allocated_ev'] = 0.0
    grid_gdf['apartment_households'] = 0.0

# ==========================================
# 6. 최종 출력물 GeoDataFrame 확인 및 CSV 저장
# ==========================================
# GeoDataFrame을 pandas DataFrame으로 변환(geometry 컬럼 제외 혹은 유지)하여 CSV로 저장
print("\n최종 GeoDataFrame 확인 및 CSV 저장 중...")
df_out = pd.DataFrame(grid_gdf.drop(columns=['geometry']))
df_out.to_csv(OUT_GRID_PATH, index=False, encoding='utf-8-sig')

print(f"\n전처리 성공적으로 완료! 결과 파일이 다음 경로에 저장되었습니다: {OUT_GRID_PATH}")
print(df_out.head(5))
print("===" * 20)
