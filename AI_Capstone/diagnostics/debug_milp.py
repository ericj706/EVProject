# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import os
_original_open = os.open
def _custom_open(path, flags, *args, **kwargs):
    if isinstance(path, str) and path.lower() in ('nul', 'nul:'):
        temp_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sandbox_devnull.tmp")
        return _original_open(temp_file, flags | os.O_CREAT, *args, **kwargs)
    return _original_open(path, flags, *args, **kwargs)
os.open = _custom_open

import pandas as pd
from pulp import LpProblem, LpMaximize, LpVariable, LpBinary, LpInteger, lpSum, value, PULP_CBC_CMD
import math

df_candidates = pd.read_csv('DataSet/final_candidates_pool.csv')
J = len(df_candidates)
print("J=", J)

BUDGET = 2_000_000_000
C_FAST = 20_000_000
C_SLOW = 5_000_000

prob = LpProblem(f"EV_Siting", LpMaximize)
x = [LpVariable(f"x_{j}", cat=LpBinary) for j in range(J)]
n_fast = [LpVariable(f"n_fast_{j}", lowBound=0, cat=LpInteger) for j in range(J)]
n_slow = [LpVariable(f"n_slow_{j}", lowBound=0, cat=LpInteger) for j in range(J)]

PENALTY_WEIGHT = 5.0
prob += lpSum(
    df_candidates.loc[j, 'lambda_day'] * n_fast[j] 
    + df_candidates.loc[j, 'lambda_night'] * n_slow[j] 
    - (df_candidates.loc[j, 'L_j'] * PENALTY_WEIGHT * x[j]) 
    for j in range(J)
), "Obj"

prob += lpSum(C_FAST * n_fast[j] for j in range(J)) <= BUDGET * 0.6, "Fast_Budget"
prob += lpSum(C_SLOW * n_slow[j] for j in range(J)) <= BUDGET * 0.4, "Slow_Budget"
prob += lpSum(C_FAST * n_fast[j] + C_SLOW * n_slow[j] for j in range(J)) <= BUDGET, "Total_Budget"
prob += lpSum(n_fast[j] for j in range(J)) >= 0.10 * lpSum(n_fast[j] + n_slow[j] for j in range(J)), "Min_Fast_Ratio"

for j in range(J):
    P_j = int(df_candidates.loc[j, 'P_j'])
    prob += n_fast[j] + n_slow[j] <= P_j
    prob += n_fast[j] + n_slow[j] <= P_j * x[j]

prob.solve(PULP_CBC_CMD(timeLimit=30, gapRel=0.01, msg=True))

is_installed = [int(value(x[j])) for j in range(J)]
installed_count = sum(1 for val in is_installed if val > 0)
print("installed_count:", installed_count)
print("Objective:", value(prob.objective))

zeros = 0
for j in range(J):
    if is_installed[j] > 0 and value(n_fast[j]) == 0 and value(n_slow[j]) == 0:
        zeros += 1
print("Installed but 0 chargers:", zeros)
