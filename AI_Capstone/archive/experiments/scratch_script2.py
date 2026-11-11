import pandas as pd
import os

def check_file(f):
    file_path = f'c:/AI_Capstone/{f}'
    print(f'=== {f} ===')
    if f.endswith('.csv'):
        try:
            df = pd.read_csv(file_path, nrows=5, encoding='utf-8')
        except:
            df = pd.read_csv(file_path, nrows=5, encoding='cp949')
    else:
        df = pd.read_excel(file_path, nrows=5)
    print(df.columns.tolist())
    print()

with open('c:/AI_Capstone/scratch_columns.txt', 'w', encoding='utf-8') as out:
    import sys
    sys.stdout = out
    for file in [
        '강남구_동별_친환경차_등록현황.xlsx',
        'gangnam_ev_parking_lots.csv',
        '강남구도시관리공단_공영주차장 전기차 충전시설 설치 현황_20251203.csv',
        '강남구 공동주택 아파트 정보.csv.xlsx'
    ]: check_file(file)
