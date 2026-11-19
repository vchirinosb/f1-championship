"""Pruebas de la ingesta: base de datos construida y lectura de las fuentes."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from f1 import data
from f1.config import CSV_TABLES, DB_TABLES
from f1.db import get_engine

LAP_TIMES_COLUMNS = [
    "race_id", "driver_id", "lap", "position", "time", "milliseconds",
]
PIT_STOPS_COLUMNS = [
    "race_id", "driver_id", "stop", "lap", "time", "duration", "milliseconds",
]


def test_database_has_exactly_the_relational_tables():
    """
    Verificar que la BD tenga las 12 tablas relacionales y ninguna de las tablas
    CSV.
    """
    tables = data.read_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )["name"]
    assert set(tables) == set(DB_TABLES)
    assert not set(tables) & set(CSV_TABLES)


@pytest.mark.parametrize("table", DB_TABLES)
def test_row_counts_match_csv(table):
    """
    Verificar que cada tabla tenga las mismas filas que su CSV.

    :param table: Nombre de la tabla.
    """
    loaded = data.read_sql(f"SELECT COUNT(*) AS n FROM {table}")["n"].iloc[0]
    assert loaded == len(data.read_raw_csv(table))


def test_no_foreign_key_violations():
    """Verificar que ninguna fila apunte a un registro inexistente."""
    assert data.read_sql("PRAGMA foreign_key_check").empty


def test_monza_2019_winner_is_leclerc():
    """Verificar que la vista de ganadores responda correctamente una consulta
    conocida."""
    winner = data.read_sql(
        "SELECT driver_name, constructor_name FROM v_race_winners "
        "WHERE circuit_ref = :circuit AND year = :year",
        {"circuit": "monza", "year": 2019},
    )
    assert winner.to_dict("records") == [
        {"driver_name": "Charles Leclerc", "constructor_name": "Ferrari"}
    ]


def test_read_only_engine_rejects_writes():
    """Verificar que el motor de solo lectura no permita modificar datos."""
    with get_engine().connect() as connection:
        with pytest.raises(OperationalError, match="readonly"):
            connection.execute(text("DELETE FROM status"))
    assert len(data.read_table("status")) == len(data.read_raw_csv("status"))


def test_read_table_rejects_unknown_names():
    """
    Verificar que read_table no acepte nombres que no sean tablas o vistas
    conocidas.
    """
    with pytest.raises(ValueError):
        data.read_table("status; DROP TABLE races")


@pytest.mark.parametrize(
    "reader, columns",
    [
        (data.read_lap_times, LAP_TIMES_COLUMNS),
        (data.read_pit_stops, PIT_STOPS_COLUMNS),
    ],
)
def test_csv_sources_use_snake_case(reader, columns):
    """
    Verificar que los CSV se lean con columnas en snake_case.

    :param reader: Función que lee el CSV.
    :param columns: Columnas esperadas, en orden.
    """
    frame = reader()
    assert list(frame.columns) == columns
    assert len(frame) > 10_000


def test_raw_nulls_are_converted():
    """Verificar que los valores \\N del CSV original se lean como nulos."""
    results = data.read_raw_csv("results")
    assert "fastest_lap_rank" in results.columns
    # Los pilotos no clasificados tienen posición \N en el CSV original
    assert results["position"].isna().any()
    assert not (results.astype(str) == "\\N").any().any()


@pytest.mark.parametrize(
    "camel, snake",
    [
        ("raceId", "race_id"),
        ("fastestLapTime", "fastest_lap_time"),
        ("constructorResultsId", "constructor_results_id"),
        ("fp1_date", "fp1_date"),
        ("rank", "fastest_lap_rank"),
    ],
)
def test_to_snake_case(camel, snake):
    """
    Verificar que los nombres camelCase se conviertan a snake_case.

    :param camel: Nombre original.
    :param snake: Nombre esperado.
    """
    assert data.convert_to_snake_case(camel) == snake
