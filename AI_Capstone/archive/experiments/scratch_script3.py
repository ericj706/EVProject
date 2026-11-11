import pandas as pd
import os

with open('c:/AI_Capstone/scratch_columns2.txt', 'w', encoding='utf-8') as out:
    import sys
    sys.stdout = out

    file_path = 'c:/AI_Capstone/서울특별시-강남구-전기차충전소-20250707.xlsx'
    df = pd.read_excel(file_path, header=1, nrows=5)
    print("=== 서울특별시-강남구-전기차충전소-20250707.xlsx ===")
    print(df.columns.tolist())

    file_path2 = 'c:/AI_Capstone/서울시 개별 공시지가 260210.csv'
    df2 = pd.read_csv(file_path2, nrows=5, encoding='cp949')
    print("=== 서울시 개별 공시지가 260210.csv ===")
    print(df2.columns.tolist())
    print(df2.head(2))

    pop_dir = 'c:/AI_Capstone/2602_유동인구데이터'
    print("=== 2602_유동인구데이터 ===")
    if os.path.exists(pop_dir):
        files = os.listdir(pop_dir)
        print(f"Files: {files}")
        if files:
            pop_file = os.path.join(pop_dir, files[0])
            try:
                df3 = pd.read_csv(pop_file, nrows=5, encoding='cp949')
                print(f"Columns of {files[0]}: {df3.columns.tolist()}")
            except Exception as e:
                print(e)
