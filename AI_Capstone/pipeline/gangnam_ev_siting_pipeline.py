# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import os
import tempfile

# Windows sandbox 'nul' permission bypass monkeypatch
_original_open = os.open
def _custom_open(path, flags, *args, **kwargs):
    if isinstance(path, str) and path.lower() in ('nul', 'nul:'):
        temp_file = os.path.join(tempfile.gettempdir(), "sandbox_devnull.tmp")
        return _original_open(temp_file, flags | os.O_CREAT, *args, **kwargs)
    return _original_open(path, flags, *args, **kwargs)
os.open = _custom_open

import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point, box
import os
import glob
import re
import math
import warnings
from sklearn.neighbors import KernelDensity
from sklearn.preprocessing import MinMaxScaler
from sklearn.decomposition import PCA
from pulp import LpProblem, LpMaximize, LpVariable, LpBinary, LpInteger, lpSum, value, LpStatus, PULP_CBC_CMD


warnings.filterwarnings('ignore')

# ==========================================
# [설정 및 환경 정의]
# ==========================================
DATA_DIR = str(DATASET_DIR)
RAW_DATA_DIR = os.path.join(DATA_DIR, "분석용_정리데이터")
POP_DIR = os.path.join(RAW_DATA_DIR, "2602_유동인구데이터")
POI_PATH = str(RESOURCE_DIR / "gangnam_POI.csv")

# Excel 파일들 glob 패턴으로 자동 검색
apt_files = glob.glob(os.path.join(RAW_DATA_DIR, "*아파트*.xlsx"))
ev_parking_files = glob.glob(os.path.join(DATA_DIR, "gangnam_ev_parking_lots.xlsx")) or glob.glob(str(RESOURCE_DIR / "gangnam_ev_parking_lots.xlsx"))
land_price_files = glob.glob(os.path.join(RAW_DATA_DIR, "*공시지가*.xlsx"))
ev_files = glob.glob(os.path.join(RAW_DATA_DIR, "*친환경차*.xlsx"))

APT_PATH = apt_files[0] if apt_files else None
PARKING_PATH = ev_parking_files[0] if ev_parking_files else None
PRICE_PATH = land_price_files[0] if land_price_files else None
EV_PATH = ev_files[0] if ev_files else None

# 출력 파일 경로
OUT_GRID_PATH = os.path.join(DATA_DIR, "gangnam_grid_preprocessed.csv")
OUT_DEMAND_PATH = os.path.join(DATA_DIR, "gangnam_demand_index.csv")
OUT_CANDIDATE_PATH = os.path.join(DATA_DIR, "final_candidates_pool.csv")

# 모델 전역 상수 설정
EV_ADOPTION_RATE = 0.06        # 전기차 전환율 가중치
TOTAL_BUDGET = 2_000_000_000   # 총예산 20억
C_FAST = 20_000_000            # 급속 충전기 단가 2천만원
C_SLOW = 5_000_000             # 완속 충전기 단가 5백만원
L_WEIGHT = 20_000_000          # 지가 페널티 가중 단가 (2천만원)
DAILY_FAST_SESSIONS = 8000     # 강남구 일평균 급속 충전 건수
MU_FAST = 1.5                  # 급속 충전기당 시간당 처리 능력 (1.5대/시간)

print("="*80)
print("     [MASTER PIPELINE] 강남구 전기차 충전소 최적 입지 선정 시스템 (1단계 - 5단계)")
print("="*80)

# ==========================================
# [1단계 & 2단계] 공간 전처리 및 격자 매핑 파이프라인
# ==========================================
print("\n>>> [1~2단계] 공간 데이터 전처리 및 잠재 수요 점수 도출 시작")

# 1. 강남구 행정경계 로드 및 100m Grid 생성
shp_files = glob.glob(os.path.join(DATA_DIR, "*.shp")) + glob.glob(os.path.join(RAW_DATA_DIR, "*.shp"))
gangnam_boundary = None

if shp_files:
    print(f" - 강남구 shapefile 로드 중: {os.path.basename(shp_files[0])}")
    try:
        gangnam_gdf = gpd.read_file(shp_files[0])
        if gangnam_gdf.crs != "EPSG:5179":
            gangnam_gdf = gangnam_gdf.to_crs("EPSG:5179")
        gu_cols = [c for c in gangnam_gdf.columns if any(x in str(c).lower() for x in ['sig_kor_nm', 'sgg_nm', '구명', '시군구'])]
        if gu_cols:
            gangnam_gdf = gangnam_gdf[gangnam_gdf[gu_cols[0]].str.contains('강남구', na=False)]
        gangnam_boundary = gangnam_gdf.geometry.unary_union
    except Exception as e:
        print(f" - Shapefile 로드 실패: {e}. Bounding Box로 대체합니다.")

if gangnam_boundary is None:
    print(" - [알림] 강남구 행정경계 바운딩 박스를 기준으로 격자망을 구축합니다.")
    min_x, min_y = 957194.5502129612, 1939865.7618353504
    max_x, max_y = 967194.5502129612, 1948865.7618353504
    gangnam_boundary = box(min_x, min_y, max_x, max_y)

# 100m 격자망 생성
bounds = gangnam_boundary.bounds
grid_size = 100
x_coords = np.arange(bounds[0], bounds[2] + grid_size, grid_size)
y_coords = np.arange(bounds[1], bounds[3] + grid_size, grid_size)

grid_cells = []
for x in x_coords:
    for y in y_coords:
        grid_cells.append(box(x, y, x + grid_size, y + grid_size))

grid_gdf = gpd.GeoDataFrame(geometry=grid_cells, crs="EPSG:5179")
grid_gdf = grid_gdf[grid_gdf.intersects(gangnam_boundary)].copy().reset_index(drop=True)
grid_gdf['grid_id'] = [f"G{i:05d}" for i in range(len(grid_gdf))]

# 격자 경계 좌표 및 Centroid 계산
centroids = grid_gdf.geometry.centroid
grid_gdf['centroid_x'] = centroids.x
grid_gdf['centroid_y'] = centroids.y
grid_gdf['min_x'] = grid_gdf.geometry.bounds['minx']
grid_gdf['min_y'] = grid_gdf.geometry.bounds['miny']
grid_gdf['max_x'] = grid_gdf.geometry.bounds['maxx']
grid_gdf['max_y'] = grid_gdf.geometry.bounds['maxy']
print(f" - 완료: 총 {len(grid_gdf)}개의 100m 격자 생성 완료.")

# 2. 생활인구 데이터 (주/야간 스냅샷 평균) 처리
pop_files = glob.glob(os.path.join(POP_DIR, "*.csv"))
if pop_files:
    print(f" - 생활인구 CSV 집계 중 (총 {len(pop_files)}개 파일)...")
    pop_daily_list = []
    
    for f_idx, pop_file in enumerate(sorted(pop_files)):
        try:
            temp_df = pd.read_csv(pop_file, nrows=2, encoding='cp949')
            encoding = 'cp949'
        except Exception:
            temp_df = pd.read_csv(pop_file, nrows=2, encoding='utf-8')
            encoding = 'utf-8'
            
        cols = temp_df.columns.tolist()
        col_hour = [c for c in cols if '시간' in str(c) or '시간' in str(c).encode('utf-8', errors='ignore').decode('cp949', errors='ignore') or 'time' in str(c).lower() or c == cols[1]][0]
        col_dong = [c for c in cols if '동코드' in str(c) or 'dong' in str(c).lower() or c == cols[2]][0]
        col_grid = [c for c in cols if '격자' in str(c) or 'grid' in str(c).lower() or c == cols[3]][0]
        col_pop = [c for c in cols if '합계' in str(c) or 'pop' in str(c).lower() or c == cols[4]][0]
        
        df = pd.read_csv(pop_file, encoding=encoding, usecols=[col_hour, col_dong, col_grid, col_pop])
        df = df[df[col_dong].astype(str).str.startswith('11680')].copy()
        
        if df.empty:
            continue
            
        # 결측 및 마스킹된 데이터(*) 0으로 전처리
        df[col_pop] = pd.to_numeric(df[col_pop], errors='coerce').fillna(0.0)
        df['is_daytime'] = (df[col_hour] >= 9) & (df[col_hour] < 18)
        
        grid_pop = df.groupby([col_grid, 'is_daytime'])[col_pop].mean().unstack(fill_value=0)
        grid_pop.columns = ['nighttime_pop', 'daytime_pop']
        pop_daily_list.append(grid_pop.reset_index())
        
    all_pop = pd.concat(pop_daily_list, ignore_index=True)
    mean_pop = all_pop.groupby(col_grid)[['daytime_pop', 'nighttime_pop']].mean().reset_index()
    
    # 250M 격자 다사XXXXYYYY 좌표 변환
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
    mean_pop = mean_pop.dropna(subset=['x_5179', 'y_5179']).copy()
    
    pop_gdf = gpd.GeoDataFrame(
        mean_pop, 
        geometry=gpd.points_from_xy(mean_pop['x_5179'], mean_pop['y_5179']),
        crs="EPSG:5179"
    )
    
    # 격자 공간 조인
    joined = gpd.sjoin(grid_gdf, pop_gdf[['daytime_pop', 'nighttime_pop', 'geometry']], how='left', predicate='contains')
    nan_grids = joined[joined['daytime_pop'].isna()]
    if not nan_grids.empty:
        non_nan_grids = pop_gdf[['daytime_pop', 'nighttime_pop', 'geometry']]
        nearest_joined = gpd.sjoin_nearest(nan_grids.drop(columns=['daytime_pop', 'nighttime_pop', 'index_right']), non_nan_grids, how='left', max_distance=300)
        joined.update(nearest_joined)
        
    pop_result = joined.groupby('grid_id')[['daytime_pop', 'nighttime_pop']].mean().reset_index().fillna(0)
    grid_gdf = pd.merge(grid_gdf, pop_result, on='grid_id', how='left').fillna({'daytime_pop': 0, 'nighttime_pop': 0})
    print(" - 완료: 생활인구 공간 조인 완료.")
else:
    grid_gdf['daytime_pop'] = 0.0
    grid_gdf['nighttime_pop'] = 0.0

# 3. POI 데이터 전처리
if os.path.exists(POI_PATH):
    poi_df = pd.read_csv(POI_PATH)
    target = ['대형마트', '백화점', '지하철역', '공공기관', 'MT1', 'SW8', 'PO3']
    poi_filtered = poi_df[
        poi_df['category_group_name'].isin(target) |
        poi_df['search_keyword'].isin(target) |
        poi_df['category_name'].str.contains('|'.join(target[:-3]), na=False)
    ].copy()
    
    poi_gdf = gpd.GeoDataFrame(
        poi_filtered,
        geometry=gpd.points_from_xy(poi_filtered['x'], poi_filtered['y']),
        crs="EPSG:4326"
    ).to_crs("EPSG:5179")
    
    poi_joined = gpd.sjoin(poi_gdf, grid_gdf[['grid_id', 'geometry']], how='inner', predicate='within')
    poi_counts = poi_joined.groupby('grid_id').size().reset_index(name='poi_count')
    grid_gdf = pd.merge(grid_gdf, poi_counts, on='grid_id', how='left').fillna({'poi_count': 0})
    
    # 대표 상업시설 이름 추출
    if 'place_name' in poi_joined.columns:
        poi_names = poi_joined.groupby('grid_id')['place_name'].first().reset_index(name='rep_poi_name')
    else:
        poi_names = poi_joined.groupby('grid_id')['category_name'].first().reset_index(name='rep_poi_name')
    grid_gdf = pd.merge(grid_gdf, poi_names, on='grid_id', how='left')
    
    print(" - 완료: POI 카운트 공간 매핑 완료.")
else:
    grid_gdf['poi_count'] = 0

# 4. 아파트 및 전기차 등록대수 Disaggregation
if APT_PATH and EV_PATH:
    df_apt = pd.read_excel(APT_PATH)
    df_ev = pd.read_excel(EV_PATH)
    
    addr_col = [c for c in df_apt.columns if '도로명' in c or '주소' in c or 'kapt' in c][0]
    df_apt = df_apt[df_apt[addr_col].astype(str).str.contains("강남구")].copy()
    
    def clean_dong(addr):
        match = re.search(r'([가-힣]+동)', str(addr))
        if match:
            dong = match.group(1)
            if dong in ['자곡동', '율현동']: return '세곡동'
            return re.sub(r'\d', '', dong)
        return '기타'
        
    df_apt['legal_dong'] = df_apt[addr_col].apply(clean_dong)
    
    ev_dong_col = df_ev.columns[0]
    ev_val_col = df_ev.columns[3]
    df_ev['legal_dong'] = df_ev[ev_dong_col].apply(clean_dong)
    ev_dong_sum = df_ev.groupby('legal_dong')[ev_val_col].sum().reset_index(name='total_ev')
    
    households_col = [c for c in df_apt.columns if '세대수' in c or '세대' in c or 'ü' in c][0]
    parking_col = [c for c in df_apt.columns if '주차' in c or '대수' in c or c == df_apt.columns[6]][0]
    
    df_apt[households_col] = pd.to_numeric(df_apt[households_col], errors='coerce').fillna(0)
    df_apt[parking_col] = pd.to_numeric(df_apt[parking_col], errors='coerce').fillna(0)
    
    dong_parking_total = df_apt.groupby('legal_dong')[parking_col].sum().reset_index(name='total_parking_in_dong')
    df_apt = pd.merge(df_apt, dong_parking_total, on='legal_dong', how='left')
    df_apt = pd.merge(df_apt, ev_dong_sum, on='legal_dong', how='left').fillna({'total_ev': 0})
    
    df_apt['parking_weight'] = np.where(df_apt['total_parking_in_dong'] > 0, df_apt[parking_col] / df_apt['total_parking_in_dong'], 0)
    df_apt['allocated_ev'] = df_apt['total_ev'] * df_apt['parking_weight']
    
    x_col = [c for c in df_apt.columns if '좌표X' in c or 'X' in c or '경도' in c][0]
    y_col = [c for c in df_apt.columns if '좌표Y' in c or 'Y' in c or '위도' in c][0]
    df_apt = df_apt.dropna(subset=[x_col, y_col])
    
    apt_gdf = gpd.GeoDataFrame(df_apt, geometry=gpd.points_from_xy(df_apt[x_col], df_apt[y_col]), crs="EPSG:4326").to_crs("EPSG:5179")
    apt_joined = gpd.sjoin(apt_gdf, grid_gdf[['grid_id', 'geometry']], how='inner', predicate='within')
    
    apt_aggregated = apt_joined.groupby('grid_id').agg({'allocated_ev': 'sum', households_col: 'sum'}).reset_index()
    apt_aggregated.columns = ['grid_id', 'allocated_ev', 'apartment_households']
    
    grid_gdf = pd.merge(grid_gdf, apt_aggregated, on='grid_id', how='left').fillna({'allocated_ev': 0.0, 'apartment_households': 0.0})
    print(" - 완료: 세대수/주차수 비례 전기차 등록대수 Spatial Disaggregation 완료.")
else:
    grid_gdf['allocated_ev'] = 0.0
    grid_gdf['apartment_households'] = 0.0

# 5. 전처리 임시 결과 CSV로 보관
df_preprocessed = pd.DataFrame(grid_gdf.drop(columns=['geometry']))
df_preprocessed.to_csv(OUT_GRID_PATH, index=False, encoding='utf-8-sig')

# ==========================================
# [2단계 모델링] KDE 공간 평활화 & PCA 기반 잠재 수요 지수 산출
# ==========================================
print("\n>>> [2단계] KDE 공간 평활화 및 PCA 잠재 수요 모델링 시작")
coords = df_preprocessed[['centroid_x', 'centroid_y']].values

def calculate_spatial_kde(coords, values, bandwidth=150.0):
    sum_val = np.sum(values)
    if sum_val == 0: return np.zeros(len(coords))
    weights = np.maximum(values, 1e-9)
    kde = KernelDensity(bandwidth=bandwidth, kernel='gaussian')
    kde.fit(coords, sample_weight=weights)
    return np.exp(kde.score_samples(coords)) * sum_val

# KDE 공간 평활화 가동 (Bandwidth = 500m)
print(" - Gaussian KDE 공간 평활화 수행 중...")
df_preprocessed['kde_daytime_pop'] = calculate_spatial_kde(coords, df_preprocessed['daytime_pop'].values)
df_preprocessed['kde_poi_count'] = calculate_spatial_kde(coords, df_preprocessed['poi_count'].values)
df_preprocessed['kde_nighttime_pop'] = calculate_spatial_kde(coords, df_preprocessed['nighttime_pop'].values)
df_preprocessed['kde_allocated_ev'] = calculate_spatial_kde(coords, df_preprocessed['allocated_ev'].values)
df_preprocessed['kde_apartment_households'] = calculate_spatial_kde(coords, df_preprocessed['apartment_households'].values)

# Min-Max Scaling (0~1)
scaler = MinMaxScaler()
fast_norm = scaler.fit_transform(df_preprocessed[['kde_daytime_pop', 'kde_poi_count']])
df_fast_norm = pd.DataFrame(fast_norm, columns=['norm_kde_daytime_pop', 'norm_kde_poi_count'])

slow_norm = scaler.fit_transform(df_preprocessed[['kde_nighttime_pop', 'kde_allocated_ev', 'kde_apartment_households']])
df_slow_norm = pd.DataFrame(slow_norm, columns=['norm_kde_nighttime_pop', 'norm_kde_allocated_ev', 'norm_kde_apartment_households'])

df_model = pd.concat([df_preprocessed, df_fast_norm, df_slow_norm], axis=1)

# PCA 수행 (PC1 점수 추출)
print(" - PCA(주성분 분석) 수행 및 설명력 검출 중...")
pca_fast = PCA(n_components=1)
pc1_fast = pca_fast.fit_transform(df_fast_norm)
if pca_fast.components_[0].sum() < 0: pc1_fast = -pc1_fast
df_model['pc1_fast'] = pc1_fast[:, 0]

pca_slow = PCA(n_components=1)
pc1_slow = pca_slow.fit_transform(df_slow_norm)
if pca_slow.components_[0].sum() < 0: pc1_slow = -pc1_slow
df_model['pc1_slow'] = pc1_slow[:, 0]

# 스케일링(0~100) 및 전기차 전환율 가중치 곱 계산
pc_scaler = MinMaxScaler(feature_range=(0, 100))
df_model['pc1_fast_scaled'] = pc_scaler.fit_transform(df_model[['pc1_fast']])
df_model['pc1_slow_scaled'] = pc_scaler.fit_transform(df_model[['pc1_slow']])

df_model['lambda_day'] = df_model['pc1_fast_scaled'] * 1.0 + df_model['pc1_slow_scaled'] * 0.2
df_model['lambda_night'] = df_model['pc1_slow_scaled'] * 1.0 + df_model['pc1_fast_scaled'] * 0.2

# 수요 예측 결과물 보관
df_model.to_csv(OUT_DEMAND_PATH, index=False, encoding='utf-8-sig')
print(" - 완료: 격자별 통합 수요 점수 lambda_day, lambda_night 도출 완료 (1.0:0.2 교차 가중치).")

# ==========================================
# [3단계] 투트랙(Two-Track) 후보지(Set J) 분류 및 제약 조건 구축
# ==========================================
print("\n>>> [3단계] 투트랙 최적화 후보지(Set J) 분류 및 제약 용량(P_j) 설정 시작")

# 격자 경계 box geometry 생성
grid_cells = [box(row['centroid_x'] - 50, row['centroid_y'] - 50, row['centroid_x'] + 50, row['centroid_y'] + 50) for _, row in df_model.iterrows()]
grid_gdf = gpd.GeoDataFrame(df_model, geometry=grid_cells, crs="EPSG:5179")

# 1. [공식 주차장 데이터] 기반 공간 조인 및 주차면수 집계 (Track 1-A용)
total_parking_per_grid = pd.Series(0.0, index=df_model['grid_id'])
if PARKING_PATH and os.path.exists(PARKING_PATH):
    df_pk = pd.read_excel(PARKING_PATH)
    lat_col = [c for c in df_pk.columns if '위도' in c or 'lat' in c.lower()][0]
    lng_col = [c for c in df_pk.columns if '경도' in c or 'lng' in c.lower()][0]
    pk_col = [c for c in df_pk.columns if '주차면수' in c or '면수' in c or c == df_pk.columns[6]][0]
    
    df_pk[pk_col] = pd.to_numeric(df_pk[pk_col], errors='coerce').fillna(0)
    pk_gdf = gpd.GeoDataFrame(df_pk, geometry=gpd.points_from_xy(df_pk[lng_col], df_pk[lat_col]), crs="EPSG:4326").to_crs("EPSG:5179")
    pk_joined = gpd.sjoin(pk_gdf, grid_gdf[['grid_id', 'geometry']], how='inner', predicate='within')
    pk_sum = pk_joined.groupby('grid_id')[pk_col].sum()
    total_parking_per_grid = total_parking_per_grid.add(pk_sum, fill_value=0)
    
    # 대표 주차장명 추출
    name_col = [c for c in df_pk.columns if '주차장명' in c or '명' in c][0]
    pk_names = pk_joined.groupby('grid_id')[name_col].first()
    df_model['rep_parking_name'] = df_model['grid_id'].map(pk_names)
df_model['total_parking_spaces'] = df_model['grid_id'].map(total_parking_per_grid).fillna(0)

# 2. POI 정보 & 학교 버퍼 50m 공간 매핑
df_model['track_type'] = 'None'
df_model['P_j'] = 0

if os.path.exists(POI_PATH):
    poi_df = pd.read_csv(POI_PATH)
    poi_gdf = gpd.GeoDataFrame(poi_df, geometry=gpd.points_from_xy(poi_df['x'], poi_df['y']), crs="EPSG:4326").to_crs("EPSG:5179")
    poi_joined = gpd.sjoin(poi_gdf, grid_gdf[['grid_id', 'geometry']], how='inner', predicate='within')
    
    # 격자별 카테고리 정보 추출 (하천/강/계곡 녹지 범위에 추가)
    grid_poi_cats = poi_joined.groupby('grid_id').apply(lambda g: {
        'PK6': any(g['category_group_name'].astype(str).str.contains('주차장') | g['category_name'].astype(str).str.contains('주차장')),
        'PO3': any(g['category_group_name'].astype(str).str.contains('공공기관') | g['category_name'].astype(str).str.contains('공공기관')),
        'MT1': any(g['category_group_name'].astype(str).str.contains('대형마트|백화점') | g['category_name'].astype(str).str.contains('대형마트|백화점')),
        'SC4': any(g['category_group_name'].astype(str).str.contains('학교') | g['category_name'].astype(str).str.contains('학교|초등학교|중학교|고등학교')),
        'park_count': g['category_name'].astype(str).str.contains('공원|산|숲|녹지|하천|강|계곡').sum(),
        'total_count': len(g)
    }).to_dict()
    
    # 대표 상업시설 이름 추출 (Track1-B 등에 표기 목적)
    if 'place_name' in poi_joined.columns:
        poi_names = poi_joined.groupby('grid_id')['place_name'].first()
    else:
        poi_names = poi_joined.groupby('grid_id')['category_name'].first()
    df_model['rep_poi_name'] = df_model['grid_id'].map(poi_names)
    
    # [학교 SC4 반경 50m 내 격자 검사]
    school_gdf = poi_gdf[
        poi_gdf['category_group_name'].astype(str).str.contains('SC4') | 
        poi_gdf['category_name'].astype(str).str.contains('학교|초등학교|중학교|고등학교')
    ].copy()
    
    if not school_gdf.empty:
        # 학교 위치 버퍼 50m 연산 및 병합
        school_buffer = school_gdf.geometry.buffer(50).unary_union
        # intersects() 연산을 통해 학교 반경 50m 이내 격자 감지
        is_near_school_series = grid_gdf.geometry.intersects(school_buffer)
        grid_gdf['is_near_school'] = is_near_school_series
    else:
        grid_gdf['is_near_school'] = False
        
    df_model['is_near_school'] = grid_gdf['is_near_school'].values
    
    for idx, row in df_model.iterrows():
        gid = row['grid_id']
        cats = grid_poi_cats.get(gid, {'PK6': False, 'PO3': False, 'MT1': False, 'SC4': False, 'park_count': 0, 'total_count': 0})
        
        # 영구 제외 조건 (학교 SC4 반경 50m 이내이거나 녹지/하천 비율이 50% 이상)
        is_school_50m = row['is_near_school']
        is_green_dominated = (cats['total_count'] > 0) and (cats['park_count'] / cats['total_count'] >= 0.5)
        
        if is_school_50m or is_green_dominated:
            df_model.at[idx, 'track_type'] = 'None'
            df_model.at[idx, 'P_j'] = 0
            continue
            
        # 1. 공식 주차장 기반 (Track 1-A)
        official_spaces = row['total_parking_spaces']
        if official_spaces > 0:
            df_model.at[idx, 'track_type'] = 'Track1-A'
            p_val = int(math.floor(official_spaces * 0.1))
            df_model.at[idx, 'P_j'] = max(p_val, 1) # 후보지로서 기능할 수 있게 최소 1 보장
            
        # 2. 대형 POI 시설 기반 (Track 1-B)
        elif cats['PO3'] or cats['MT1']:
            df_model.at[idx, 'track_type'] = 'Track1-B'
            df_model.at[idx, 'P_j'] = 10
            
        # 3. 가로변 신규 설치 (Track 2)
        else:
            is_commercial = (row['daytime_pop'] > 50.0) or (cats['total_count'] > cats['park_count'])
            if is_commercial:
                df_model.at[idx, 'track_type'] = 'Track2'
                df_model.at[idx, 'P_j'] = 2

# 후보지만 필터링 (Track1-A, Track1-B, Track2 포함)
df_candidates = df_model[df_model['track_type'].isin(['Track1-A', 'Track1-B', 'Track2'])].copy().reset_index(drop=True)

# 3. 공시지가 매핑을 통한 지가 페널티 (L_j) 생성
if PRICE_PATH and os.path.exists(PRICE_PATH):
    df_price = pd.read_excel(PRICE_PATH)
    dong_col = df_price.columns[0]
    price_col = df_price.columns[2]
    
    def get_legal_dong(addr):
        match = re.search(r'([가-힣]+동)', str(addr))
        if match:
            dong = match.group(1)
            if dong in ['자곡동', '율현동']: return '세곡동'
            return re.sub(r'\d', '', dong)
        return '기타'
        
    df_price['legal_dong'] = df_price[dong_col].apply(get_legal_dong)
    df_price[price_col] = pd.to_numeric(df_price[price_col], errors='coerce').fillna(0)
    dong_mean_price = df_price.groupby('legal_dong')[price_col].mean().to_dict()
    
    # 가까운 아파트 매핑을 통한 법정동 매핑
    if APT_PATH and os.path.exists(APT_PATH):
        df_apt_ref = pd.read_excel(APT_PATH)
        addr_col_ref = [c for c in df_apt_ref.columns if '도로명' in c or '주소' in c or 'kapt' in c][0]
        df_apt_ref = df_apt_ref[df_apt_ref[addr_col_ref].astype(str).str.contains("강남구")].copy()
        df_apt_ref['legal_dong'] = df_apt_ref[addr_col_ref].apply(get_legal_dong)
        
        # 강남구 아파트 좌표계 컬럼 감지 보강
        x_col_ref = [c for c in df_apt_ref.columns if '좌표X' in c or 'X' in c or '경도' in c][0]
        y_col_ref = [c for c in df_apt_ref.columns if '좌표Y' in c or 'Y' in c or '위도' in c][0]
        
        apt_ref_gdf = gpd.GeoDataFrame(
            df_apt_ref, 
            geometry=gpd.points_from_xy(df_apt_ref[x_col_ref], df_apt_ref[y_col_ref]), 
            crs="EPSG:4326"
        ).to_crs("EPSG:5179")
        cand_gdf = gpd.GeoDataFrame(df_candidates, geometry=gpd.points_from_xy(df_candidates['centroid_x'], df_candidates['centroid_y']), crs="EPSG:5179")
        
        nearest_apt = gpd.sjoin_nearest(cand_gdf, apt_ref_gdf[['legal_dong', 'geometry']], how='left', max_distance=3000)
        nearest_apt = nearest_apt.drop_duplicates(subset=['grid_id'])
        df_candidates['legal_dong'] = df_candidates['grid_id'].map(nearest_apt.set_index('grid_id')['legal_dong']).fillna('역삼동')
    else:
        df_candidates['legal_dong'] = '역삼동'
        
    df_candidates['raw_land_price'] = df_candidates['legal_dong'].map(dong_mean_price).fillna(np.mean(list(dong_mean_price.values())))
    df_candidates['L_j'] = scaler.fit_transform(df_candidates[['raw_land_price']])
else:
    df_candidates['L_j'] = 0.5

# --- [Phase 3.5] 기존 충전소 매핑 및 순 미충족 수요 (Net Unmet Demand) 산출 ---
INFRA_DATA_PATH = os.path.join(str(DATASET_DIR), "분석용_정리데이터", "라벨링_강남구_전기차충전소_위치_공영민영.xlsx")
if os.path.exists(INFRA_DATA_PATH):
    df_infra = pd.read_excel(INFRA_DATA_PATH)
    lat_col = [c for c in df_infra.columns if '위도' in c or 'lat' in c.lower() or 'Y' in c.upper()][0]
    lon_col = [c for c in df_infra.columns if '경도' in c or 'lon' in c.lower() or 'lng' in c.lower() or 'X' in c.upper()][0]
    
    infra_gdf = gpd.GeoDataFrame(
        df_infra,
        geometry=gpd.points_from_xy(df_infra[lon_col], df_infra[lat_col]),
        crs="EPSG:4326"
    ).to_crs("EPSG:5179")
    
    cand_gdf = gpd.GeoDataFrame(df_candidates, geometry=gpd.points_from_xy(df_candidates['centroid_x'], df_candidates['centroid_y']), crs="EPSG:5179")
    
    infra_joined = gpd.sjoin(infra_gdf, cand_gdf[['grid_id', 'geometry']], how='inner', predicate='within')
    infra_counts = infra_joined.groupby('grid_id').size().reset_index(name='existing_stations_count')
    df_candidates = pd.merge(df_candidates, infra_counts, on='grid_id', how='left').fillna({'existing_stations_count': 0})
else:
    df_candidates['existing_stations_count'] = 0

# unmet_lambda 계산 (기존 충전소 1개소당 10점의 수요 방어 가정)
df_candidates['unmet_lambda_day'] = np.maximum(0, df_candidates['lambda_day'] - (df_candidates['existing_stations_count'] * 10))
df_candidates['unmet_lambda_night'] = np.maximum(0, df_candidates['lambda_night'] - (df_candidates['existing_stations_count'] * 10))

df_candidates.to_csv(OUT_CANDIDATE_PATH, index=False, encoding='utf-8-sig')

# JSON 대시보드 덤프용 WGS84 좌표 변환 (EPSG:5179 -> EPSG:4326)
cand_gdf_5179 = gpd.GeoDataFrame(df_candidates, geometry=gpd.points_from_xy(df_candidates['centroid_x'], df_candidates['centroid_y']), crs="EPSG:5179")
cand_gdf_4326 = cand_gdf_5179.to_crs("EPSG:4326")
df_candidates['lon_wgs84'] = cand_gdf_4326.geometry.x
df_candidates['lat_wgs84'] = cand_gdf_4326.geometry.y

try:
    df_candidates[['lat_wgs84', 'lon_wgs84']].rename(columns={'lat_wgs84': 'lat', 'lon_wgs84': 'lon'}).to_json(str(OUTPUT_DIR / "existing_stations.json"), orient='records')
except PermissionError as e:
    print(f" - [경고] existing_stations.json 쓰기 권한이 거부되었습니다 ({e}). 이 단계를 건너뜁니다.")

existing_js_path = str(OUTPUT_DIR / "existing_stations.js")
with open(existing_js_path, 'w', encoding='utf-8') as f:
    f.write('window.existingStationsDataRaw = ')
    df_candidates[['lat_wgs84', 'lon_wgs84']].rename(columns={'lat_wgs84': 'lat', 'lon_wgs84': 'lon'}).to_json(f, orient='records')
    f.write(';\n')
print(f" - 완료: 투트랙 분류 완료 (Track 1-A: {sum(df_candidates['track_type']=='Track1-A')}개, Track 1-B: {sum(df_candidates['track_type']=='Track1-B')}개, Track 2: {sum(df_candidates['track_type']=='Track2')}개)")

# ==========================================
# [4단계] MILP 수리적 최적화 및 다중 예산 시나리오 JSON 연동
# ==========================================
import json
print("\n>>> [4단계] PuLP 기반 예산 시나리오(10억 고정) 최적화 구동")

BUDGET_SCENARIOS = [1_000_000_000]
final_dashboard_data = {}
J = len(df_candidates)

# 수요 도착률 산출 (큐잉 검증용)
sum_lambda_day_score = df_candidates['lambda_day'].sum()
df_candidates['daily_demand'] = DAILY_FAST_SESSIONS * (df_candidates['lambda_day'] / sum_lambda_day_score)
df_candidates['hourly_lambda'] = df_candidates['daily_demand'] / 24.0

def calculate_waiting_time(c, lam, mu=1.5):
    if c <= 0: return float('inf')
    rho = lam / (c * mu)
    if rho >= 1.0: return float('inf')
    sum_terms = sum((c * rho)**k / math.factorial(k) for k in range(c))
    last_term = ((c * rho)**c) / (math.factorial(c) * (1.0 - rho))
    p0 = 1.0 / (sum_terms + last_term)
    pc = last_term * p0
    wq_hours = pc / (c * mu * (1.0 - rho))
    return wq_hours * 60.0

for BUDGET in BUDGET_SCENARIOS:
    budget_key = f"budget_{BUDGET // 100_000_000}b"
    print(f"\n--- 시나리오: 총 예산 {BUDGET // 100_000_000}억 ---")
    
    prob = LpProblem(f"EV_Siting_{budget_key}", LpMaximize)
    
    x = [LpVariable(f"x_{j}", cat=LpBinary) for j in range(J)]
    n_fast = [LpVariable(f"n_fast_{j}", lowBound=0, cat=LpInteger) for j in range(J)]
    n_slow = [LpVariable(f"n_slow_{j}", lowBound=0, cat=LpInteger) for j in range(J)]
    cov_day = [LpVariable(f"cov_day_{j}", lowBound=0) for j in range(J)]
    cov_night = [LpVariable(f"cov_night_{j}", lowBound=0) for j in range(J)]

    ALPHA = 10.0     # 수요 커버량 가중치 (기기 1대당 10점 처리 * 10배 = 최대 100점 획득 가능)
    BETA = 50.0     # 지가 페널티 가중치 (0~1 스케일을 수요 점수 스케일로 변환)
    DELTA = 1 / 1_000_000  # 예산 페널티 가중치 (100만 원당 1점 감점)
    
    prob += lpSum(
        ALPHA * (cov_day[j] + cov_night[j])
        - BETA * (df_candidates.loc[j, 'L_j'] * x[j])
        - DELTA * (C_FAST * n_fast[j] + C_SLOW * n_slow[j])
        for j in range(J)
    ), "Obj"

    prob += lpSum(C_FAST * n_fast[j] for j in range(J)) <= BUDGET * 0.7, "Fast_Budget"
    prob += lpSum(C_SLOW * n_slow[j] for j in range(J)) <= BUDGET * 0.3, "Slow_Budget"
    
    # 예산 제약식에서 단위(Dimension)가 맞지 않는 지가 지수(L_j) 항목을 순수 기기 예산(원)으로 통일 (사용자 피드백 수용)
    prob += lpSum(C_FAST * n_fast[j] + C_SLOW * n_slow[j] for j in range(J)) <= BUDGET, "Total_Budget"
    prob += lpSum(n_fast[j] for j in range(J)) >= 0.10 * lpSum(n_fast[j] + n_slow[j] for j in range(J)), "Min_Fast_Ratio"
    
    # [피드백 반영] 너무 자잘하게 많은 곳에 설치되는 현상(스팸)을 막고, 
    # 수요가 가장 집중된 소수의 핵심 거점만 선별하기 위해 최대 거점 개수를 강력하게 제한합니다.
    MAX_LOCATIONS = 15
    prob += lpSum(x[j] for j in range(J)) <= MAX_LOCATIONS, "Max_Locations_Limit"

    for j in range(J):
        P_j = int(df_candidates.loc[j, 'P_j'])
        prob += n_fast[j] + n_slow[j] <= P_j
        prob += n_fast[j] + n_slow[j] <= P_j * x[j]
        
        # [신규 추가] COV(Coverage) 상한선 제약식: 점수 무한 복사 폭주 방지
        # 1. 수요 한계: 실제 동네에 존재하는 미충족 수요량을 초과하여 점수를 얻을 수 없음
        prob += cov_day[j] <= df_candidates.loc[j, 'unmet_lambda_day'] * x[j]
        prob += cov_night[j] <= df_candidates.loc[j, 'unmet_lambda_night'] * x[j]
        
        # 2. 물리적 한계: 설치된 기계의 처리 용량(급속 1대당 20점, 완속 1대당 10점 산정)을 초과하여 점수를 얻을 수 없음
        prob += cov_day[j] <= 20.0 * n_fast[j]
        prob += cov_night[j] <= 10.0 * n_slow[j]

        # COV 모델 도입으로 인해 인공지능이 스스로 수요에 맞게 대수를 맞추게 되므로, 
        # 이전의 억지스러운 수학적 상/하한선 제약식은 완전히 걷어냄.
        # 단, 하이브리드 인프라의 상징성을 위해 최소 1대씩은 교차 설치하도록 최소한의 방어선만 남김
        if P_j >= 2:
            prob += n_fast[j] >= 1 * x[j]
            prob += n_slow[j] >= 1 * x[j]

    # 시간 제한 30초, gap 1%
    # PuLP solver 실행 시 윈도우 환경에서 'nul' 권한 에러를 막기 위해 msg=True 로 설정
    prob.solve(PULP_CBC_CMD(timeLimit=30, gapRel=0.01, msg=True))
    
    fast_alloc = [int(value(n_fast[j])) for j in range(J)]
    slow_alloc = [int(value(n_slow[j])) for j in range(J)]
    is_installed = [int(value(x[j])) for j in range(J)]
    
    scenario_locations = []
    
    for j in range(J):
        if is_installed[j] > 0 and (fast_alloc[j] > 0 or slow_alloc[j] > 0):
            c = fast_alloc[j]
            s = slow_alloc[j]
            lam = df_candidates.loc[j, 'hourly_lambda']
            limit = int(df_candidates.loc[j, 'P_j'])
            
            # 피드백: Wq > 15m 일 경우 증설 (가능하다면)
            wq = calculate_waiting_time(c, lam, MU_FAST)
            while wq > 15.0 and (c + s < limit):
                c += 1
                wq = calculate_waiting_time(c, lam, MU_FAST)
                
            track_val = str(df_candidates.loc[j, 'track_type'])
            
            # 정확한 명칭 할당 (주차장명, 시설명 우선)
            exact_name = ""
            if track_val == 'Track1-A':
                exact_name = df_candidates.loc[j, 'rep_parking_name'] if 'rep_parking_name' in df_candidates.columns and pd.notna(df_candidates.loc[j, 'rep_parking_name']) else "공영주차장"
                t_name = f"{exact_name} (주차장)"
            elif track_val == 'Track1-B':
                exact_name = df_candidates.loc[j, 'rep_poi_name'] if 'rep_poi_name' in df_candidates.columns and pd.notna(df_candidates.loc[j, 'rep_poi_name']) else "대형상업/공공시설"
                t_name = f"{exact_name} (상업시설)"
            else:
                t_name = "신규 노상/가로변 (상업/업무밀집)"
                
            loc_data = {
                "id": df_candidates.loc[j, 'grid_id'],
                "name": f"{df_candidates.loc[j, 'legal_dong']} {t_name}",
                "type": "fast_heavy" if c >= s else "slow_heavy",
                "coords": [round(df_candidates.loc[j, 'lat_wgs84'], 5), round(df_candidates.loc[j, 'lon_wgs84'], 5)],
                "limit": limit,
                "fast": c,
                "slow": s,
                "total": c + s,
                "demand": f"통합 수요: {int((df_candidates.loc[j, 'lambda_day'] + df_candidates.loc[j, 'lambda_night'])*0.5)}점",
                "shap_scores": {
                    "com": float(df_candidates.loc[j, 'lambda_day']),
                    "ev": float(df_candidates.loc[j, 'lambda_night']),
                    "infra": float(0.0),
                    "land": float(-df_candidates.loc[j, 'L_j'] * 20.0)
                }
            }
            scenario_locations.append(loc_data)
            
    final_dashboard_data[budget_key] = scenario_locations
    print(f"  * 도출된 최적 입지 수: {len(scenario_locations)}개소")

try:
    json_out_path = str(OUTPUT_DIR / "data.json")
    with open(json_out_path, 'w', encoding='utf-8') as f:
        json.dump(final_dashboard_data, f, ensure_ascii=False, indent=2)
except PermissionError as e:
    print(f" - [경고] data.json 쓰기 권한이 거부되었습니다 ({e}). 이 단계를 건너뜁니다.")

data_js_path = str(OUTPUT_DIR / "data.js")
with open(data_js_path, 'w', encoding='utf-8') as f:
    f.write('window.dashboardDataRaw = ')
    json.dump(final_dashboard_data, f, ensure_ascii=False, indent=2)
    f.write(';\n')

# 히트맵 덤프용 WGS84 좌표 변환 (EPSG:5179 -> EPSG:4326)
model_gdf_5179 = gpd.GeoDataFrame(df_model, geometry=gpd.points_from_xy(df_model['centroid_x'], df_model['centroid_y']), crs="EPSG:5179")
model_gdf_4326 = model_gdf_5179.to_crs("EPSG:4326")
df_model['lon_wgs84'] = model_gdf_4326.geometry.x
df_model['lat_wgs84'] = model_gdf_4326.geometry.y

heatmap_data = {
    "day": df_model[['lat_wgs84', 'lon_wgs84', 'norm_kde_daytime_pop', 'norm_kde_poi_count', 'norm_kde_nighttime_pop', 'norm_kde_allocated_ev']].rename(
        columns={'lat_wgs84':'lat', 'lon_wgs84':'lon', 'norm_kde_daytime_pop':'weight'}
    ).to_dict(orient='records'),
    "night": df_model[['lat_wgs84', 'lon_wgs84', 'norm_kde_nighttime_pop', 'norm_kde_poi_count', 'norm_kde_daytime_pop', 'norm_kde_allocated_ev']].rename(
        columns={'lat_wgs84':'lat', 'lon_wgs84':'lon', 'norm_kde_nighttime_pop':'weight'}
    ).to_dict(orient='records')
}
try:
    heatmap_out_path = str(OUTPUT_DIR / "heatmap.json")
    with open(heatmap_out_path, 'w', encoding='utf-8') as f:
        json.dump(heatmap_data, f, ensure_ascii=False)
except PermissionError as e:
    print(f" - [경고] heatmap.json 쓰기 권한이 거부되었습니다 ({e}). 이 단계를 건너뜁니다.")

heatmap_js_path = str(OUTPUT_DIR / "heatmap.js")
with open(heatmap_js_path, 'w', encoding='utf-8') as f:
    f.write('window.heatmapDataRaw = ')
    json.dump(heatmap_data, f, ensure_ascii=False)
    f.write(';\n')

# 기존 충전소 마커 데이터 (실제 데이터셋 기반 추출)
existing_stations_list = []
INFRA_DATA_PATH = os.path.join(str(DATASET_DIR), "분석용_정리데이터", "라벨링_강남구_전기차충전소_위치_공영민영.xlsx")
if os.path.exists(INFRA_DATA_PATH):
    try:
        df_infra = pd.read_excel(INFRA_DATA_PATH)
        # 컬럼명 유연하게 처리 (위도/경도 또는 Y/X 형태)
        lat_col = [c for c in df_infra.columns if '위도' in c or 'lat' in c.lower() or 'Y' in c.upper()][0]
        lon_col = [c for c in df_infra.columns if '경도' in c or 'lon' in c.lower() or 'lng' in c.lower() or 'X' in c.upper()][0]
        
        for _, row in df_infra.iterrows():
            if pd.notna(row[lat_col]) and pd.notna(row[lon_col]):
                existing_stations_list.append({
                    "lat": float(row[lat_col]), 
                    "lon": float(row[lon_col])
                })
        print(f"  * 실제 기존 충전소 데이터 {len(existing_stations_list)}개 로드 완료")
    except Exception as e:
        print(f"  * 기존 충전소 데이터 로드 실패: {e}")
else:
    print("  * 기존 충전소 데이터 파일을 찾을 수 없습니다. 빈 마커 배열을 생성합니다.")

existing_js_path = str(OUTPUT_DIR / "existing_stations.js")
with open(existing_js_path, 'w', encoding='utf-8') as f:
    f.write('window.existingStationsDataRaw = ')
    json.dump(existing_stations_list, f, ensure_ascii=False)
    f.write(';\n')

print("\n" + "="*80)
print(f">>> 다중 시나리오 분석 완료 및 대시보드 연동용 JSON/JS 생성 완료: {json_out_path}")
print(f"    - 히트맵 데이터 생성 완료: {heatmap_out_path}")
print(f"    - 기존 충전소 마커 생성 완료: {existing_js_path}")
print("="*80)
