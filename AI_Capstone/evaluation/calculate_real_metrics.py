# Resolve shared paths independently of the current working directory.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import PROJECT_ROOT, DATASET_DIR, RESOURCE_DIR, OUTPUT_DIR, DASHBOARD_DIR

import os
os.chdir(PROJECT_ROOT)

import json
import math
import pandas as pd

# Inlined JSON data from dashboard/data.json
json_str = """{
  "budget_10b": [
    {
      "id": "G01061",
      "name": "기타 논현1동주민센터 (상업시설)",
      "type": "fast_heavy",
      "coords": [
        37.51158,
        127.02866
      ],
      "limit": 10,
      "fast": 5,
      "slow": 4,
      "total": 9,
      "demand": "통합 수요: 49점",
      "shap_scores": {
        "com": 53.913619719496076,
        "ev": 44.72707503443483,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G01137",
      "name": "기타 역삼세무서 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.49807,
        127.02988
      ],
      "limit": 10,
      "fast": 1,
      "slow": 6,
      "total": 7,
      "demand": "통합 수요: 77점",
      "shap_scores": {
        "com": 91.02895380042848,
        "ev": 64.67024891009798,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G01141",
      "name": "기타 국기원 (상업시설)",
      "type": "fast_heavy",
      "coords": [
        37.50167,
        127.02985
      ],
      "limit": 10,
      "fast": 5,
      "slow": 5,
      "total": 10,
      "demand": "통합 수요: 62점",
      "shap_scores": {
        "com": 72.52906466980126,
        "ev": 52.290308015936034,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G01231",
      "name": "기타 한국과학기술회관 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.50078,
        127.03099
      ],
      "limit": 10,
      "fast": 1,
      "slow": 6,
      "total": 7,
      "demand": "통합 수요: 77점",
      "shap_scores": {
        "com": 93.20826417257166,
        "ev": 62.76395991911672,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G02052",
      "name": "기타 스타필드 더샵스앳센터필드점 (상업시설)",
      "type": "fast_heavy",
      "coords": [
        37.50262,
        127.04116
      ],
      "limit": 10,
      "fast": 5,
      "slow": 5,
      "total": 10,
      "demand": "통합 수요: 56점",
      "shap_scores": {
        "com": 62.89856566446268,
        "ev": 49.5723218645677,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G02500",
      "name": "기타 역삼2동주민센터 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.49633,
        127.04686
      ],
      "limit": 10,
      "fast": 3,
      "slow": 7,
      "total": 10,
      "demand": "통합 수요: 67점",
      "shap_scores": {
        "com": 61.962013063110604,
        "ev": 73.36259554661706,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G02525",
      "name": "기타 강남세무서 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.51887,
        127.04672
      ],
      "limit": 10,
      "fast": 1,
      "slow": 5,
      "total": 6,
      "demand": "통합 수요: 49점",
      "shap_scores": {
        "com": 47.6893096667494,
        "ev": 52.018786338250464,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G02594",
      "name": "기타 이마트 역삼점 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.49904,
        127.04797
      ],
      "limit": 10,
      "fast": 1,
      "slow": 7,
      "total": 8,
      "demand": "통합 수요: 63점",
      "shap_scores": {
        "com": 56.49350921054739,
        "ev": 69.90048063005835,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G02614",
      "name": "기타 강남구청 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.51707,
        127.04786
      ],
      "limit": 10,
      "fast": 1,
      "slow": 5,
      "total": 6,
      "demand": "통합 수요: 47점",
      "shap_scores": {
        "com": 43.33461146361497,
        "ev": 52.62350122081791,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G03047",
      "name": "기타 롯데백화점 강남점 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.49726,
        127.05364
      ],
      "limit": 10,
      "fast": 1,
      "slow": 5,
      "total": 6,
      "demand": "통합 수요: 52점",
      "shap_scores": {
        "com": 52.43759564511519,
        "ev": 53.16118190300499,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G03414",
      "name": "기타 대치4동주민센터 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.49998,
        127.05815
      ],
      "limit": 10,
      "fast": 1,
      "slow": 6,
      "total": 7,
      "demand": "통합 수요: 58점",
      "shap_scores": {
        "com": 55.561826414635625,
        "ev": 61.46947190069611,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G03515",
      "name": "기타 현대백화점 무역센터점 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.509,
        127.05923
      ],
      "limit": 10,
      "fast": 1,
      "slow": 5,
      "total": 6,
      "demand": "통합 수요: 78점",
      "shap_scores": {
        "com": 105.26514589713042,
        "ev": 51.99670839921967,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G04954",
      "name": "기타 수서경찰서 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.49374,
        127.07742
      ],
      "limit": 10,
      "fast": 1,
      "slow": 5,
      "total": 6,
      "demand": "통합 수요: 48점",
      "shap_scores": {
        "com": 46.74159927168354,
        "ev": 49.613032250860314,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G05045",
      "name": "기타 서울강남우체국 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.49374,
        127.07855
      ],
      "limit": 10,
      "fast": 1,
      "slow": 4,
      "total": 5,
      "demand": "통합 수요: 41점",
      "shap_scores": {
        "com": 42.92135592813473,
        "ev": 40.28370896180451,
        "infra": 0.0,
        "land": -0.0
      }
    },
    {
      "id": "G07040",
      "name": "기타 이마트 수서점 (상업시설)",
      "type": "slow_heavy",
      "coords": [
        37.48752,
        127.10347
      ],
      "limit": 10,
      "fast": 2,
      "slow": 5,
      "total": 7,
      "demand": "통합 수요: 57점",
      "shap_scores": {
        "com": 58.77706654403476,
        "ev": 57.140347953913185,
        "infra": 0.0,
        "land": -0.0
      }
    }
  ]
}"""

dashboard_data = json.loads(json_str)

# Load candidate pool
df = pd.read_csv("DataSet/final_candidates_pool.csv")

# The default budget scenario is budget_10b
selected_nodes = dashboard_data.get("budget_10b", [])
selected_ids = {node["id"] for node in selected_nodes}

print(f"Number of selected locations: {len(selected_nodes)}")

# Recalculate sum_lambda_day_score
sum_lambda_day_score = df['lambda_day'].sum()
DAILY_FAST_SESSIONS = 8000
MU_FAST = 1.5

def calculate_waiting_time(c, lam, mu=1.5):
    if c <= 0: return float('inf')
    rho = lam / (c * mu)
    if rho >= 1.0: return float('inf')
    sum_terms = sum((c * rho)**k / math.factorial(k) for k in range(math.ceil(c)))
    last_term = ((c * rho)**c) / (math.factorial(c) * (1.0 - rho))
    p0 = 1.0 / (sum_terms + last_term)
    pc = last_term * p0
    wq_hours = pc / (c * mu * (1.0 - rho))
    return wq_hours * 60.0

# Calculate waiting times for selected nodes
wait_times = []
for node in selected_nodes:
    node_id = node["id"]
    row = df[df["grid_id"] == node_id].iloc[0]
    c = node["fast"]
    daily_demand = DAILY_FAST_SESSIONS * (row["lambda_day"] / sum_lambda_day_score)
    hourly_lambda = daily_demand / 24.0
    wq = calculate_waiting_time(c, hourly_lambda, MU_FAST)
    wait_times.append(wq)
    print(f"Node: {node['name']}, Grid ID: {node_id}, Fast Chargers: {c}, Hourly Lambda: {hourly_lambda:.3f}, Wait Time: {wq:.2f} mins")

avg_wait_time = sum(wait_times) / len(wait_times)
print(f"\\nActual average wait time of selected nodes: {avg_wait_time:.2f} minutes")

# Check demand coverage
# Let's see how much of unmet_lambda_day/night is covered
# Coverage = sum(min(unmet_lambda, 10 * n_fast/slow)) / sum(unmet_lambda)
total_unmet_day = df["unmet_lambda_day"].sum()
total_unmet_night = df["unmet_lambda_night"].sum()

covered_day = 0.0
covered_night = 0.0
for node in selected_nodes:
    node_id = node["id"]
    row = df[df["grid_id"] == node_id].iloc[0]
    c = node["fast"]
    s = node["slow"]
    
    cov_day_j = min(row["unmet_lambda_day"], 10.0 * c)
    cov_night_j = min(row["unmet_lambda_night"], 10.0 * s)
    
    covered_day += cov_day_j
    covered_night += cov_night_j

coverage_day_pct = (covered_day / total_unmet_day) * 100 if total_unmet_day > 0 else 0
coverage_night_pct = (covered_night / total_unmet_night) * 100 if total_unmet_night > 0 else 0
avg_coverage_pct = (coverage_day_pct + coverage_night_pct) / 2

print(f"Total Unmet Day: {total_unmet_day:.2f}, Covered Day: {covered_day:.2f} ({coverage_day_pct:.2f}%)")
print(f"Total Unmet Night: {total_unmet_night:.2f}, Covered Night: {covered_night:.2f} ({coverage_night_pct:.2f}%)")
print(f"Average Demand Coverage: {avg_coverage_pct:.2f}%")
