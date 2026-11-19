"""Configuración del proyecto: rutas de carpetas y URLs de los servicios."""
import os
from pathlib import Path

# Carpetas del repositorio.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
FINAL_DATA_DIR = DATA_DIR / "final"
EVAL_DATA_DIR = DATA_DIR / "eval"
SQL_DIR = PROJECT_ROOT / "sql"
IMAGES_DIR = PROJECT_ROOT / "images"

# Base de datos SQLite.
DB_PATH = DATA_DIR / "f1.db"

# Tablas que se cargan en la BD, en orden de carga, que no dependen de otras.
DB_TABLES = (
    "circuits",
    "constructors",
    "drivers",
    "seasons",
    "status",
    "races",
    "results",
    "sprint_results",
    "qualifying",
    "driver_standings",
    "constructor_standings",
    "constructor_results",
)
# Tablas que se consumen directamente como CSV.
CSV_TABLES = ("lap_times", "pit_stops")

# Servicios locales.
MLFLOW_TRACKING_URI = os.environ.get(
    "MLFLOW_TRACKING_URI", "http://127.0.0.1:9090"
)
API_URL = os.environ.get("F1_API_URL", "http://127.0.0.1:5001")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
