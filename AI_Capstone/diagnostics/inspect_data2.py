# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import csv
import glob
from openpyxl import load_workbook
import os

folder = str(DATASET_DIR)
for f in os.listdir(folder):
    path = os.path.join(folder, f)
    if os.path.isfile(path):
        print("="*50)
        print(f)
        try:
            if path.endswith(".csv"):
                with open(path, "r", encoding="utf-8") as file:
                    reader = csv.reader(file)
                    print(next(reader))
            elif path.endswith(".xlsx"):
                wb = load_workbook(filename=path, read_only=True, data_only=True)
                ws = wb.active
                for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
                    print(row)
        except Exception as e:
            try:
                # try cp949 for csv
                if path.endswith(".csv"):
                    with open(path, "r", encoding="cp949") as file:
                        reader = csv.reader(file)
                        print(next(reader))
            except Exception as e2:
                print("Error:", e2)
