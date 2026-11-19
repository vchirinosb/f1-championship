"""
Lectura de las dos fuentes de datos del proyecto con Pandas.

- Base de datos: las 12 tablas relacionales y las vistas v_race_results y
  v_race_winners.
- CSV: lap_times y pit_stops, que se leen directamente desde data/raw/.
"""
import re

import pandas as pd
from sqlalchemy import text

from f1.config import CSV_TABLES, DB_TABLES, RAW_DATA_DIR
from f1.db import get_engine

DB_VIEWS = ("v_race_results", "v_race_winners")
COLUMN_RENAMES = {"rank": "fastest_lap_rank"}


def convert_to_snake_case(name: str) -> str:
    """
    Convertir un nombre de columna de camelCase a snake_case.

    :param name: Nombre original, ej. 'fastestLapTime'.

    :return: Nombre en snake_case, ej. 'fastest_lap_time'.
    """
    snake = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()
    return COLUMN_RENAMES.get(snake, snake)


def read_raw_csv(table: str) -> pd.DataFrame:
    """
    Leer un CSV original de data/raw/.

    Las columnas quedan en snake_case y los valores \\N se leen como nulos.

    :param table: Nombre del archivo sin extensión, ej. 'results'.

    :return: Contenido del CSV.
    """
    if table not in DB_TABLES + CSV_TABLES:
        raise ValueError(f"'{table}' no es un archivo del dataset")
    path = RAW_DATA_DIR / f"{table}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Los 14 CSV originales del dataset deben "
            "estar en data/raw/."
        )
    # keep_default_na=False evita que textos como "NA" se lean como nulos
    data = pd.read_csv(path, na_values=["\\N", ""], keep_default_na=False)
    return data.rename(columns=convert_to_snake_case)


def read_lap_times() -> pd.DataFrame:
    """
    Leer los tiempos de cada vuelta de cada piloto (desde 1996).

    :return: Contenido de lap_times.csv.
    """
    return read_raw_csv("lap_times")


def read_pit_stops() -> pd.DataFrame:
    """
    Leer las paradas en boxes (desde 2011).

    :return: Contenido de pit_stops.csv.
    """
    return read_raw_csv("pit_stops")


def read_table(name: str) -> pd.DataFrame:
    """
    Leer completa una tabla o vista de la base de datos.

    :param name: Nombre de la tabla o vista, ej. 'v_race_winners'.

    :return: Todas las filas de la tabla o vista.
    """
    if name not in DB_TABLES + DB_VIEWS:
        raise ValueError(
            f"'{name}' no es una tabla ni una vista de la base de datos"
        )
    return read_sql(f"SELECT * FROM {name}")


def read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    """
    Ejecutar una consulta SQL en modo solo lectura.

    :param query: Consulta SQL, ej. 'SELECT * FROM races WHERE year = :year'.
    :param params: Valores de los marcadores, ej. {'year': 2019}.

    :return: Resultado de la consulta.
    """
    with get_engine().connect() as connection:
        return pd.read_sql(text(query), connection, params=params)
