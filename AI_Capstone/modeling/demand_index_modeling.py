# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import pandas as pd
import numpy as np
from sklearn.neighbors import KernelDensity
from sklearn.preprocessing import MinMaxScaler
from sklearn.decomposition import PCA
import os
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# 1. 설정 및 데이터 로드
# ==========================================
DATA_DIR = str(DATASET_DIR)
GRID_PREPROCESSED_PATH = os.path.join(DATA_DIR, "gangnam_grid_preprocessed.csv")
OUT_DEMAND_PATH = os.path.join(DATA_DIR, "gangnam_demand_index.csv")

# 가중치 변수: 강남구 전기차 전환율 (EV Adoption Rate)
EV_ADOPTION_RATE = 0.06

print("=== [Part 2] 잠재 수요 지수 모델링 파이프라인 시작 ===")
if not os.path.exists(GRID_PREPROCESSED_PATH):
    print(f"[오류] 전처리된 격자 데이터를 찾을 수 없습니다: {GRID_PREPROCESSED_PATH}")
    print("먼저 [Part 1] 공간 전처리 스크립트를 실행해 주세요.")
    exit(1)

df = pd.read_csv(GRID_PREPROCESSED_PATH)
print(f"전처리 격자 로드 완료: 총 {len(df)}개 격자")
print("사용 가능한 컬럼:", df.columns.tolist())

# 좌표 어레이 추출
coords = df[['centroid_x', 'centroid_y']].values

# ==========================================
# 2. KDE 공간 평활화 함수 (Bandwidth = 500m)
# ==========================================
def calculate_spatial_kde(coords, values, bandwidth=500.0):
    """
    Scikit-learn의 KernelDensity를 사용하여 공간 평활화를 수행합니다.
    변수 값을 sample_weight로 주어 가중 밀도 평활을 구현합니다.
    """
    sum_val = np.sum(values)
    if sum_val == 0:
        return np.zeros(len(coords))
        
    # 가중 밀도 추정을 위해 가중치가 0인 포인트는 아주 미세한 값을 더해주어 계산 안정성 확보
    weights = np.maximum(values, 1e-9)
    
    # 2D KDE 학습 (Gaussian Kernel, Bandwidth 500m)
    kde = KernelDensity(bandwidth=bandwidth, kernel='gaussian')
    kde.fit(coords, sample_weight=weights)
    
    # 각 포인트에서의 log-density 계산 후 exp하여 절대 밀도값 복원
    # total sum을 곱해 원본 스케일 수준의 평활화 스케일로 스케일링
    smoothed = np.exp(kde.score_samples(coords)) * sum_val
    return smoothed

# 2.1 투트랙 변수 지정 및 KDE 계산
print("\n[투트랙 수요 분리 및 KDE 공간 평활화 시작 (대역폭 500m)]...")

# 급속 (Fast Track) 타겟 변수
print(" - 급속 변수: daytime_pop, poi_count")
df['kde_daytime_pop'] = calculate_spatial_kde(coords, df['daytime_pop'].values, bandwidth=500.0)
df['kde_poi_count'] = calculate_spatial_kde(coords, df['poi_count'].values, bandwidth=500.0)

# 완속 (Slow Track) 타겟 변수
print(" - 완속 변수: nighttime_pop, allocated_ev, apartment_households")
df['kde_nighttime_pop'] = calculate_spatial_kde(coords, df['nighttime_pop'].values, bandwidth=500.0)
df['kde_allocated_ev'] = calculate_spatial_kde(coords, df['allocated_ev'].values, bandwidth=500.0)
df['kde_apartment_households'] = calculate_spatial_kde(coords, df['apartment_households'].values, bandwidth=500.0)

print("KDE 평활화 완료.")

# ==========================================
# 3. Min-Max 정규화 (0~1)
# ==========================================
print("\n[KDE 결과값 Min-Max 정규화 진행 중]...")
scaler = MinMaxScaler()

# 급속 변수 정규화
fast_cols = ['kde_daytime_pop', 'kde_poi_count']
fast_norm = scaler.fit_transform(df[fast_cols])
df_fast_norm = pd.DataFrame(fast_norm, columns=[f'norm_{c}' for c in fast_cols])

# 완속 변수 정규화
slow_cols = ['kde_nighttime_pop', 'kde_allocated_ev', 'kde_apartment_households']
slow_norm = scaler.fit_transform(df[slow_cols])
df_slow_norm = pd.DataFrame(slow_norm, columns=[f'norm_{c}' for c in slow_cols])

# 원본 DataFrame에 병합
df = pd.concat([df, df_fast_norm, df_slow_norm], axis=1)
print("정규화 완료.")

# ==========================================
# 4. PCA 주성분 분석 (제1주성분 PC1 점수 추출)
# ==========================================
print("\n[PCA 주성분 분석을 통한 제1주성분(PC1) 점수 추출 중]...")

# 4.1 급속 PCA (2개 변수)
pca_fast = PCA(n_components=1)
pc1_fast = pca_fast.fit_transform(df_fast_norm)

# PC1 계수(loadings)의 합이 음수일 경우 방향 뒤집기 (해석 용이성 확보: 높은 값이 높은 수요)
if pca_fast.components_[0].sum() < 0:
    pc1_fast = -pc1_fast
df['pc1_fast'] = pc1_fast[:, 0]
print(f" - 급속 PCA 설명 분산비(PC1): {pca_fast.explained_variance_ratio_[0]*100:.2f}%")
print(f" - 급속 PCA 로딩 계수: {pca_fast.components_[0]}")

# 4.2 완속 PCA (3개 변수)
pca_slow = PCA(n_components=1)
pc1_slow = pca_slow.fit_transform(df_slow_norm)

if pca_slow.components_[0].sum() < 0:
    pc1_slow = -pc1_slow
df['pc1_slow'] = pc1_slow[:, 0]
print(f" - 완속 PCA 설명 분산비(PC1): {pca_slow.explained_variance_ratio_[0]*100:.2f}%")
print(f" - 완속 PCA 로딩 계수: {pca_slow.components_[0]}")

# ==========================================
# 5. PC1 점수 0~100 스케일링 & EV Adoption Rate 가중치 적용
# ==========================================
print("\n[수요 점수 최종 계산 및 스케일링 (가중치: 전기차 전환율 0.06) 중]...")

# 5.1 PC1 점수 0~100 Min-Max 스케일링
pc1_scaler = MinMaxScaler(feature_range=(0, 100))
df['pc1_fast_scaled'] = pc1_scaler.fit_transform(df[['pc1_fast']])
df['pc1_slow_scaled'] = pc1_scaler.fit_transform(df[['pc1_slow']])

df['lambda_day'] = df['pc1_fast_scaled'] * 1.0 + df['pc1_slow_scaled'] * 0.2
df['lambda_night'] = df['pc1_slow_scaled'] * 1.0 + df['pc1_fast_scaled'] * 0.2

print("최종 융합 수요 점수 컬럼 생성 완료: 'lambda_day', 'lambda_night'")

# ==========================================
# 6. 최종 모델링 결과 CSV 저장
# ==========================================
print("\n최종 모델링 결과 CSV 저장 중...")
df.to_csv(OUT_DEMAND_PATH, index=False, encoding='utf-8-sig')
print(f"성공: 잠재 수요 모델링 결과물이 저장되었습니다: {OUT_DEMAND_PATH}")

# 6.1 기술통계 요약 출력
print("\n=== 최종 잠재 수요 점수 기술통계 요약 ===")
print(df[['lambda_fast', 'lambda_slow']].describe())
print("===" * 20)
