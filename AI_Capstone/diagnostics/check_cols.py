# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import pandas as pd

try:
    df_poi = pd.read_csv('DataSet/gangnam_poi.csv')
    print("POI columns:", df_poi.columns.tolist())
except Exception as e:
    print("POI err:", e)

try:
    df_pk = pd.read_excel('DataSet/gangnam_ev_parking_lots.xlsx')
    print("Parking columns:", df_pk.columns.tolist())
except Exception as e:
    print("PK err:", e)

try:
    import glob
    apt_file = glob.glob('DataSet/분석용_정리데이터/*아파트*.xlsx')[0]
    df_apt = pd.read_excel(apt_file)
    print("APT columns:", df_apt.columns.tolist())
except Exception as e:
    print("APT err:", e)
