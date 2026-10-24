from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
DATA_DIR = REPO_ROOT / "data"
RAW_NISAR_DIR = DATA_DIR / "raw" / "nisar"
CENSUS_DIR = DATA_DIR / "raw" / "census"
PROCESSED_DIR = DATA_DIR / "processed"
WORLD_CACHE = PROCESSED_DIR / "world-big-bend.npz"
