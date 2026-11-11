"""Shared project locations for analysis scripts."""
from pathlib import Path

ANALYSIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ANALYSIS_DIR.parent
DATASET_DIR = PROJECT_ROOT / "DataSet"
RESOURCE_DIR = ANALYSIS_DIR / "resources"
OUTPUT_DIR = ANALYSIS_DIR / "outputs"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
