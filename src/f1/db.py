"""Conexión de solo lectura a la base de datos SQLite mediante SQLAlchemy."""
from functools import cache

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from f1.config import DB_PATH


@cache
def get_engine() -> Engine:
    """
    Devolver el motor de solo lectura de la base de datos.

    :return: motor de SQLAlchemy conectado a data/f1.db.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No existe la base de datos {DB_PATH}. Constrúyala con: "
            "../bin/python scripts/build_database.py"
        )
    # uri=true hace que sqlite3 abra la ruta como URI y respete mode=ro
    return create_engine(f"sqlite:///file:{DB_PATH}?mode=ro&uri=true")


def query(sql: str, **params) -> pd.DataFrame:
    """
    Ejecutar una consulta parametrizada en la base de datos.

    :param sql: Consulta con parámetros ':nombre'.
    :param params: Valores de los parámetros.

    :return: Filas devueltas.
    """
    with get_engine().connect() as connection:
        return pd.read_sql(text(sql), connection, params=params)
