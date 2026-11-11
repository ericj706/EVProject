# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import pandas as pd
import os
from pyproj import Transformer

DATA_DIR = str(DATASET_DIR)
GRID_PATH = os.path.join(DATA_DIR, 'gangnam_grid_preprocessed.csv')
POI_PATH = str(RESOURCE_DIR / "gangnam_POI.csv")

print("기존 전처리된 격자 데이터를 불러옵니다...")
df = pd.read_csv(GRID_PATH)

print("수집된 POI 데이터를 불러옵니다...")
poi = pd.read_csv(POI_PATH)

target = ['대형마트', '백화점', '지하철역', '공공기관', 'MT1', 'SW8', 'PO3']
if 'category_group_name' in poi.columns:
    poi = poi[poi['category_group_name'].isin(target)].copy()

t = Transformer.from_crs('epsg:4326', 'epsg:5179', always_xy=True)

# 좌표 컬럼 (x, y)를 5179로 변환
poi['x_5179'], poi['y_5179'] = t.transform(poi['x'].values, poi['y'].values)

print("격자와 POI를 매칭합니다 (가장 가까운 거리 기준)...")
# 벡터화 연산을 통해 가장 가까운 격자 찾기
grid_centroids_x = df['centroid_x'].values
grid_centroids_y = df['centroid_y'].values
grid_ids = df['grid_id'].values

poi_grid_ids = []
for idx, row in poi.iterrows():
    dist_sq = (grid_centroids_x - row['x_5179'])**2 + (grid_centroids_y - row['y_5179'])**2
    poi_grid_ids.append(grid_ids[dist_sq.argmin()])

poi['grid_id'] = poi_grid_ids

print("격자별 POI 개수를 집계합니다...")
pc = poi.groupby('grid_id').size().reset_index(name='poi_count')

if 'poi_count' in df.columns:
    df = df.drop(columns=['poi_count'])

df = pd.merge(df, pc, on='grid_id', how='left').fillna({'poi_count': 0})

df.to_csv(GRID_PATH, index=False, encoding='utf-8-sig')
print(f"완료! {GRID_PATH} 에 POI 데이터가 성공적으로 업데이트되었습니다.")
