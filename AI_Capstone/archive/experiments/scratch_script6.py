import pandas as pd
import json
import os
import sys

# Windows에서 기본 인코딩 문제 회피
sys.stdout.reconfigure(encoding='utf-8')

infra_path = os.path.join("DataSet", "분석용_정리데이터", "라벨링_강남구_전기차충전소_위치_공영민영.xlsx")
df = pd.read_excel(infra_path)

out_data = {
    "columns": df.columns.tolist(),
    "first_row": df.head(1).to_dict(orient='records')
}

with open("scratch_out6.json", "w", encoding="utf-8") as f:
    json.dump(out_data, f, ensure_ascii=False, indent=2)
print("Done")
