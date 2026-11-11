# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import requests
import pandas as pd
import time
import numpy as np
import os

# API 설정
API_KEY = "03b4c55579e52ffdb65114d67337fb08"
HEADERS = {
    "Authorization": f"KakaoAK {API_KEY}",
    "Origin": "http://localhost:8000",
    "KA": "sdk/1.0.0 os/javascript lang/ko-KR origin/http://localhost:8000"
}
URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

# 강남구 Bounding Box (대략적인 위경도 좌표)
LAT_MIN, LAT_MAX = 37.4538, 37.5340
LNG_MIN, LNG_MAX = 127.0160, 127.1145

# 강남구를 2x2 격자 정도로 나누어 빠르게 수집
LAT_STEP = 0.045  # 위도 범위 0.08을 약 2등분
LNG_STEP = 0.055  # 경도 범위 0.098을 약 2등분

# 검색할 키워드 목록
KEYWORDS = [
    "대형마트",
    "백화점",
    "지하철역",
    "공공기관"
]

def fetch_poi_data():
    all_data = []
    
    # 위도, 경도 격자 생성 (한 번의 바운딩 박스로 강남구 전체 커버)
    lat_grids = [LAT_MIN, LAT_MAX]
    lng_grids = [LNG_MIN, LNG_MAX]
    
    total_expected_grids = (len(lat_grids) - 1) * (len(lng_grids) - 1) * len(KEYWORDS)
    current_request = 0

    print(f"총 예상 탐색 격자(키워드 포함): 약 {total_expected_grids}개")
    
    for keyword in KEYWORDS:
        print(f"\n--- '{keyword}' 데이터 수집 시작 ---")
        keyword_data = []
        for i in range(len(lat_grids) - 1):
            for j in range(len(lng_grids) - 1):
                bottom_lat = lat_grids[i]
                top_lat = lat_grids[i+1]
                left_lng = lng_grids[j]
                right_lng = lng_grids[j+1]
                
                # rect 포맷: 좌측x좌표,좌측y좌표,우측x좌표,우측y좌표 (경도,위도,경도,위도)
                rect = f"{left_lng},{bottom_lat},{right_lng},{top_lat}"
                
                page = 1
                is_end = False
                
                while not is_end:
                    params = {
                        "query": keyword,
                        "rect": rect,
                        "page": page,
                        "size": 15
                    }
                    
                    try:
                        response = requests.get(URL, headers=HEADERS, params=params)
                        if response.status_code != 200:
                            print(f"API 에러: {response.status_code} - {response.text}")
                            break
                            
                        data = response.json()
                        documents = data.get('documents', [])
                        meta = data.get('meta', {})
                        
                        for doc in documents:
                            # 어떤 키워드로 검색되어 수집되었는지 태깅
                            doc['search_keyword'] = keyword
                            keyword_data.append(doc)
                            all_data.append(doc)
                            
                        # 다음 페이지 존재 여부 확인 (카카오맵 API 최대 45페이지)
                        is_end = meta.get('is_end', True)
                        if page >= 45: 
                            is_end = True
                        else:
                            page += 1
                        
                        # API 일일 쿼터 및 속도 제한을 고려한 sleep (초당 호출 제한 방지)
                        time.sleep(0.01)  
                        current_request += 1
                        
                        if current_request % 500 == 0:
                            print(f"진행 상황: API {current_request}회 호출 완료...")
                            
                    except Exception as e:
                        print(f"API 요청 중 에러 발생: {e}")
                        time.sleep(2) # 에러 발생 시 조금 더 대기
                        break
        print(f"'{keyword}' 수집 완료 (수집된 건수: {len(keyword_data)}건, 누적 API 호출: {current_request}회)")

    return all_data

if __name__ == "__main__":
    print("강남구 POI 데이터 수집을 시작합니다...")
    poi_data = fetch_poi_data()
    
    if not poi_data:
        print("수집된 데이터가 없습니다. API 키 및 네트워크 상태를 확인해주세요.")
    else:
        # DataFrame 변환
        df = pd.DataFrame(poi_data)
        
        # 중복 제거 (id 기준)
        before_count = len(df)
        df = df.drop_duplicates(subset=['id'], keep='first')
        after_count = len(df)
        
        print(f"\n데이터 수집 완료!")
        print(f"총 수집 건수: {before_count}건 -> 중복 제거 후 최종 건수: {after_count}건")
        
        # 유용한 컬럼들만 정리 (응답에 포함된 주요 데이터)
        columns_to_save = [
            'id', 'place_name', 'category_group_name', 'category_name', 
            'search_keyword', 'address_name', 'road_address_name', 
            'x', 'y', 'phone', 'place_url'
        ]
        
        # 존재하는 컬럼만 선택
        columns_to_save = [col for col in columns_to_save if col in df.columns]
        df = df[columns_to_save]
        
        # CSV로 저장 (인코딩 utf-8-sig로 설정하여 엑셀에서 한글 깨짐 방지)
        save_path = str(RESOURCE_DIR / "gangnam_POI.csv")
        df.to_csv(save_path, index=False, encoding='utf-8-sig')
        print(f"\n저장 완료: {save_path}")
