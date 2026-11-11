# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import pandas as pd
import numpy as np
import requests
import os
import re

try:
    from pyproj import Transformer
except ImportError:
    print("오류: pyproj 라이브러리가 설치되어 있지 않습니다.")
    print("명령 프롬프트(터미널)에서 아래 명령어를 실행하여 설치해 주세요:")
    print("pip install pyproj")
    exit()

# ==========================================
# 설정 및 파일 경로 (사용자 환경에 맞게 수정)
# ==========================================
KAKAO_API_KEY = '03b4c55579e52ffdb65114d67337fb08' # 카카오 REST API 키 입력
DATA_DIR = str(DATASET_DIR)

PATH_APT = os.path.join(DATA_DIR, 'standard_apt_final.csv')
PATH_EV_DONG = os.path.join(DATA_DIR, '민영,공영 라벨 데이터셋', '강남구_동별_친환경차_등록현황.xlsx')
PATH_POI = os.path.join(DATA_DIR, 'gangnam_POI.csv') # 저장된 POI 파일 경로
PATH_CHARGER_LABEL = os.path.join(DATA_DIR, '민영,공영 라벨 데이터셋', '라벨링_강남구_전기차충전소_위치_공영민영.csv') # 예시 경로

# EPSG:4326 (WGS84) -> EPSG:5179 (Korea 2000) 변환기
transformer_to_5179 = Transformer.from_crs("epsg:4326", "epsg:5179", always_xy=True)

# 강남구 Bounding Box (대략적인 위경도)
GANGNAM_MIN_LON, GANGNAM_MIN_LAT = 127.016, 37.457 # 서쪽, 남쪽 끝
GANGNAM_MAX_LON, GANGNAM_MAX_LAT = 127.124, 37.536 # 동쪽, 북쪽 끝

# ==========================================
# 1. 강남구 100m x 100m 격자 생성 (수학적 계산)
# ==========================================
def create_gangnam_grid(grid_size=100):
    print("1. 강남구 100m 격자를 생성합니다 (Geopandas 제외, 순수 수학적 계산)...")
    
    # Bounding Box를 5179 좌표계로 변환
    min_x, min_y = transformer_to_5179.transform(GANGNAM_MIN_LON, GANGNAM_MIN_LAT)
    max_x, max_y = transformer_to_5179.transform(GANGNAM_MAX_LON, GANGNAM_MAX_LAT)
    
    cols = np.arange(min_x, max_x, grid_size)
    rows = np.arange(min_y, max_y, grid_size)
    
    grids = []
    grid_idx = 0
    for x in cols:
        for y in rows:
            centroid_x = x + (grid_size / 2)
            centroid_y = y + (grid_size / 2)
            grids.append({
                'grid_id': f'G{grid_idx:05d}',
                'min_x': x, 'min_y': y,
                'max_x': x + grid_size, 'max_y': y + grid_size,
                'centroid_x': centroid_x,
                'centroid_y': centroid_y
            })
            grid_idx += 1
            
    grid_df = pd.DataFrame(grids)
    print(f"완료: 총 {len(grid_df)}개의 100m 격자가 생성되었습니다.")
    return grid_df, min_x, min_y, max_x, max_y, grid_size

# 특정 좌표가 어느 격자에 속하는지 찾는 수식 함수 (O(1) 속도)
def find_grid_id(x, y, grid_df, min_x, min_y, max_x, max_y, grid_size):
    if pd.isna(x) or pd.isna(y): return None
    if x < min_x or x >= max_x or y < min_y or y >= max_y: return None
    
    col_idx = int((x - min_x) // grid_size)
    row_idx = int((y - min_y) // grid_size)
    num_rows = int(np.ceil((max_y - min_y) / grid_size))
    idx = col_idx * num_rows + row_idx
    
    if 0 <= idx < len(grid_df):
        return grid_df.at[idx, 'grid_id']
    return None

# 가장 가까운 격자 찾기
def find_nearest_grid_id(x, y, grid_df):
    if pd.isna(x) or pd.isna(y): return None
    # 유클리디안 거리 제곱 기준 최소값
    distances = (grid_df['centroid_x'] - x)**2 + (grid_df['centroid_y'] - y)**2
    return grid_df.loc[distances.idxmin(), 'grid_id']

# ==========================================
# 2. 카카오 API를 활용한 주소 지오코딩 헬퍼 함수
# ==========================================
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

geolocator = Nominatim(user_agent="capstone_ev_project")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

def geocode_address(address, api_key=None):
    try:
        location = geocode(address)
        if location:
            return location.latitude, location.longitude
    except Exception:
        pass
    return None, None

# ==========================================
# 3. 행정동 단위 전기차 대수 -> 격자별 Spatial Disaggregation
# ==========================================
def spatial_disaggregation(grid_df, min_x, min_y, max_x, max_y, grid_size):
    print("\n2. 전기차 등록대수 Spatial Disaggregation을 시작합니다...")
    apt_df = pd.read_csv(PATH_APT)
    try:
        ev_dong_df = pd.read_excel(PATH_EV_DONG)
    except:
        ev_dong_df = pd.DataFrame()
    
    print(" - 아파트 주소 지오코딩 진행 중...")
    for idx, row in apt_df.iterrows():
        if pd.isna(row.get('latitude')) or pd.isna(row.get('longitude')):
            lat, lng = geocode_address(row['address'], KAKAO_API_KEY)
            apt_df.at[idx, 'latitude'] = lat
            apt_df.at[idx, 'longitude'] = lng
            
    apt_df = apt_df.dropna(subset=['latitude', 'longitude']).copy()
    
    def extract_dong(addr):
        match = re.search(r'([가-힣]+동)', str(addr))
        return match.group(1) if match else '기타'
        
    apt_df['dong'] = apt_df['address'].apply(extract_dong)
    
    dong_total = apt_df.groupby('dong')['parking_spaces'].sum().reset_index()
    dong_total.columns = ['dong', 'total_spaces_in_dong']
    
    apt_df = pd.merge(apt_df, dong_total, on='dong', how='left')
    apt_df['weight'] = apt_df['parking_spaces'] / apt_df['total_spaces_in_dong']
    
    if not ev_dong_df.empty:
        col_dong = '동이름' if '동이름' in ev_dong_df.columns else ev_dong_df.columns[0]
        col_ev = '전기차수' if '전기차수' in ev_dong_df.columns else ev_dong_df.columns[1]
        
        apt_df = pd.merge(apt_df, ev_dong_df, left_on='dong', right_on=col_dong, how='left')
        apt_df['allocated_ev'] = apt_df[col_ev] * apt_df['weight']
    else:
        apt_df['allocated_ev'] = 0
        
    # 좌표 변환 (WGS84 -> 5179)
    apt_df['x_5179'], apt_df['y_5179'] = transformer_to_5179.transform(apt_df['longitude'].values, apt_df['latitude'].values)
    
    # 격자 매핑
    apt_df['grid_id'] = apt_df.apply(lambda row: find_grid_id(row['x_5179'], row['y_5179'], grid_df, min_x, min_y, max_x, max_y, grid_size) or find_nearest_grid_id(row['x_5179'], row['y_5179'], grid_df), axis=1)
    
    grid_ev = apt_df.groupby('grid_id')['allocated_ev'].sum().reset_index()
    grid_df = pd.merge(grid_df, grid_ev, on='grid_id', how='left').fillna({'allocated_ev': 0})
    
    print("완료: 세대수 비율 기반 격자별 전기차 대수 할당 완료.")
    return grid_df

# ==========================================
# 4. POI 데이터 격자 매칭
# ==========================================
def match_poi_to_grid(grid_df):
    print("\n3. POI 데이터를 격자에 매칭합니다...")
    if not os.path.exists(PATH_POI):
        print(f"POI 파일을 찾을 수 없습니다: {PATH_POI}")
        return grid_df
        
    poi_df = pd.read_csv(PATH_POI)
    
    target_categories = ['대형마트', '백화점', '지하철역', '공공기관', 'MT1', 'SW8', 'PO3']
    if 'category_group_name' in poi_df.columns:
        poi_filtered = poi_df[poi_df['category_group_name'].isin(target_categories) | 
                              poi_df['category_group_code'].isin(target_categories)].copy()
    else:
        poi_filtered = poi_df.copy()
        
    lng_col = 'x' if 'x' in poi_filtered.columns else 'longitude'
    lat_col = 'y' if 'y' in poi_filtered.columns else 'latitude'
    
    if lng_col not in poi_filtered.columns or lat_col not in poi_filtered.columns:
        return grid_df
        
    poi_filtered['x_5179'], poi_filtered['y_5179'] = transformer_to_5179.transform(poi_filtered[lng_col].values, poi_filtered[lat_col].values)
    poi_filtered['grid_id'] = poi_filtered.apply(lambda row: find_nearest_grid_id(row['x_5179'], row['y_5179'], grid_df), axis=1)
    
    poi_counts = poi_filtered.groupby('grid_id').size().reset_index(name='poi_count')
    grid_df = pd.merge(grid_df, poi_counts, on='grid_id', how='left').fillna({'poi_count': 0})
    
    print("완료: POI 격자 매칭 및 집계 완료.")
    return grid_df

# ==========================================
# 5. 민영/공영 라벨 데이터 매칭
# ==========================================
def match_charger_labels(grid_df):
    print("\n4. 민영/공영 충전소 데이터를 격자에 매칭합니다...")
    if not os.path.exists(PATH_CHARGER_LABEL):
        print(f"라벨 데이터셋을 찾을 수 없습니다: {PATH_CHARGER_LABEL}")
        return grid_df
        
    try:
        charger_df = pd.read_csv(PATH_CHARGER_LABEL)
    except:
        charger_df = pd.read_excel(PATH_CHARGER_LABEL)
        
    lng_col = 'longitude' if 'longitude' in charger_df.columns else ('경도' if '경도' in charger_df.columns else 'x')
    lat_col = 'latitude' if 'latitude' in charger_df.columns else ('위도' if '위도' in charger_df.columns else 'y')
    
    if lng_col in charger_df.columns and lat_col in charger_df.columns:
        charger_df['x_5179'], charger_df['y_5179'] = transformer_to_5179.transform(charger_df[lng_col].values, charger_df[lat_col].values)
        charger_df['grid_id'] = charger_df.apply(lambda row: find_nearest_grid_id(row['x_5179'], row['y_5179'], grid_df), axis=1)
        
        label_col = '구분' if '구분' in charger_df.columns else ('설치기관' if '설치기관' in charger_df.columns else None)
        if label_col and label_col in charger_df.columns:
            counts = charger_df.groupby(['grid_id', label_col]).size().unstack(fill_value=0).reset_index()
            grid_df = pd.merge(grid_df, counts, on='grid_id', how='left').fillna(0)
    
    print("완료: 민영/공영 충전소 격자 매칭 완료.")
    return grid_df

# ==========================================
# 메인 실행부
# ==========================================
if __name__ == "__main__":
    print("=== [Phase 1] 데이터 전처리 및 공간 격자 구축 시작 ===")
    
    grid_df, min_x, min_y, max_x, max_y, grid_size = create_gangnam_grid()
    grid_df = spatial_disaggregation(grid_df, min_x, min_y, max_x, max_y, grid_size)
    grid_df = match_poi_to_grid(grid_df)
    grid_df = match_charger_labels(grid_df)
    
    # 최종 데이터를 CSV 형태로 저장 (Geopandas가 없으므로 GeoJSON 대신 CSV 활용)
    out_path = os.path.join(DATA_DIR, 'gangnam_grid_preprocessed.csv')
    grid_df.to_csv(out_path, index=False, encoding='utf-8-sig')
    
    print(f"\n=== 모든 전처리 완료! 결과물이 CSV로 저장되었습니다: {out_path} ===")
