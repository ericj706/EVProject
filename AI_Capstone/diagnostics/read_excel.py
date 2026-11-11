# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import pandas as pd
import sys

try:
    df = pd.read_excel(str(DATASET_DIR / "강남구_동별_친환경차_등록현황.xlsx"))
    print(df.head())
    print(df.columns)
except Exception as e:
    print(e)
