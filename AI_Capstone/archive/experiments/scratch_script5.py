import pandas as pd
df = pd.read_excel('DataSet/분석용_정리데이터/라벨링_강남구_전기차충전소_위치_공영민영.xlsx')
print(df.columns.tolist())
print(df.head(2).to_dict(orient='records'))
