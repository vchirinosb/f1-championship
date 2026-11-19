"""
Construye la base de datos SQLite data/f1.db con los CSV de data/raw/.

Pasos:
1. Crea las tablas con sql/schema.sql en un archivo temporal.
2. Carga las 12 tablas relacionales (lap_times y pit_stops quedan como CSV).
   Las claves foráneas están activas: una fila que apunte a un registro
   inexistente detiene la carga.
3. Crea las vistas de sql/views.sql.
4. Solo si todo es correcto reemplaza data/f1.db; si algo falla, la BD
   anterior no se toca.
"""
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from f1.config import DB_PATH, DB_TABLES, PROJECT_ROOT, SQL_DIR
from f1.data import read_raw_csv


def load_tables(connection: sqlite3.Connection) -> dict[str, int]:
    """
    Cargar cada CSV en su tabla de la base de datos.

    :param connection: Conexión a la base de datos en construcción.

    :return: Filas cargadas por tabla.
    """
    rows = {}
    for table in DB_TABLES:
        try:
            rows[table] = read_raw_csv(table).to_sql(
                table, connection, if_exists="append", index=False
            )
        except Exception as error:
            raise SystemExit(
                f"No se pudo cargar {table}.csv: {error.__cause__ or error}"
            ) from error
    return rows


def build_database() -> dict[str, int]:
    """
    Construir data/f1.db a partir de los CSV de data/raw/.

    :return: Filas cargadas por tabla.
    """
    temp_path = DB_PATH.with_name(DB_PATH.name + ".tmp")
    temp_path.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(temp_path)) as connection:
            # Con las claves foráneas activas, una fila que apunte a un
            # registro inexistente falla al insertarse.
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript((SQL_DIR / "schema.sql").read_text())
            rows = load_tables(connection)
            connection.executescript((SQL_DIR / "views.sql").read_text())
            connection.commit()
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise

    os.replace(temp_path, DB_PATH)
    return rows


def print_summary(rows: dict[str, int]) -> None:
    """
    Mostrar el tamaño de la base de datos y las filas cargadas por tabla.

    :param rows: Filas cargadas por tabla, devueltas por build_database.
    """
    size_mb = DB_PATH.stat().st_size / 1024 / 1024
    print(
        f"Base de datos creada: {DB_PATH.relative_to(PROJECT_ROOT)} "
        f"({size_mb:.1f} MB)\n"
    )
    print(f"{'Tabla':24} {'Filas':>8}")
    for table, count in rows.items():
        print(f"{table:24} {count:>8,}")
    print(f"\n{len(rows)} tablas cargadas; claves foráneas verificadas.")


if __name__ == "__main__":
    print_summary(build_database())
