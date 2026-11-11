import pandas as pd
file_path = 'c:/AI_Capstone/서울특별시-강남구-전기차충전소-20250707.xlsx'
df = pd.read_excel(file_path, header=None, nrows=10)
for i, row in df.iterrows():
    print(f"Row {i}:", row.tolist()[:10])
