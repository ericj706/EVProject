# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import pandas as pd
import numpy as np

df = pd.read_csv('DataSet/final_candidates_pool.csv')
print("L_j min:", df['L_j'].min())
print("L_j max:", df['L_j'].max())

from pulp import LpProblem, LpMaximize, LpVariable, LpBinary, LpInteger, lpSum, value, LpStatus, PULP_CBC_CMD
print("Imported pulp")
