import pandas as pd
import os
import openpyxl 
import csv

path = 'c:/AI_Capstone'
files = [
    '강남구_동별_친환경차_등록현황.xlsx',
    '서울특별시-강남구-전기차충전소-20250707.xlsx',
    'gangnam_ev_parking_lots.csv',
    '강남구도시관리공단_공영주차장 전기차 충전시설 설치 현황_20251203.csv',
    '전기차 충전소 설치현황_20260319.xlsx'
]

for f in files:
    file_path = os.path.join(path, f)
    try:
        if f.endswith('.csv'):
            try:
                df = pd.read_csv(file_path, encoding='utf-8', nrows=2)
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding='cp949', nrows=2)
            print(f'\n--- {f} ---')
            print(df.columns.tolist())
        else:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            sheet = wb.active
            rows = sheet.iter_rows(min_row=1, max_row=3, values_only=True)
            row_list = list(rows)
            print(f'\n--- {f} ---')
            if row_list:
                print('Columns:', row_list[0])
                if len(row_list) > 1:
                    print('Row 1:', row_list[1])
            wb.close()
    except Exception as e:
        print(f'Error reading {f}: {e}')
