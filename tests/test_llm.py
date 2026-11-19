"""Pruebas del asistente LLM: herramientas, SQL seguro y errores de Ollama."""
import hashlib

import httpx
import pandas as pd
import pytest
from sqlalchemy.exc import OperationalError

from f1 import llm
from f1.config import DB_PATH
from f1.db import get_engine


def compute_db_hash() -> str:
    """
    Calcular el hash del archivo de la base de datos.

    :return: Hash MD5 del contenido de data/f1.db.
    """
    return hashlib.md5(DB_PATH.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "race", ["GP de Italia", "Gran Premio de Italia", "Monza", "monza"]
)
def test_race_winner_italy_2019(race):
    """
    Verificar que el GP de Italia y Monza 2019 devuelvan a Leclerc.

    :param race: Nombre de la carrera o del circuito.
    """
    answer = llm.get_race_winner(race, 2019)
    assert [row["driver_name"] for row in answer.data] == ["Charles Leclerc"]
    assert "Charles Leclerc (Ferrari)" in answer.text
    assert answer.strategy == "tool:race_winner"


def test_race_winner_two_races_same_circuit():
    """Verificar que se devuelvan las dos carreras de Silverstone 2020."""
    answer = llm.get_race_winner("Silverstone", 2020)
    assert [row["driver_name"] for row in answer.data] == [
        "Lewis Hamilton",
        "Max Verstappen",
    ]


def test_race_winner_without_data():
    """Verificar que una carrera que no existe no invente un ganador."""
    answer = llm.get_race_winner("Monza", 1940)
    assert answer.data == []
    assert answer.text.startswith("No hay datos")


def test_unknown_race_is_not_matched():
    """
    Verificar que un nombre parecido solo en parte no se confunda con otra
    carrera.
    """
    assert llm.resolve_race("GP de la Luna") is None
    assert llm.resolve_race("Italian GP") == (
        "race_name", "Italian Grand Prix"
    )


def test_season_champion():
    """Verificar que el campeón de 2008 sea Hamilton."""
    answer = llm.get_season_champion(2008)
    assert answer.data[0]["driver_name"] == "Lewis Hamilton"


@pytest.mark.parametrize(
    "name, ref",
    [
        ("Checo Pérez", "perez"),
        ("Hamilton", "hamilton"),
        ("Schumacher", "michael_schumacher"),
        ("Ralf Schumacher", "ralf_schumacher"),
        ("Kimi Raikkonen", "raikkonen"),
        ("Juan Pérez", None),
    ],
)
def test_resolve_driver(name, ref):
    """
    Verificar que los pilotos se reconozcan por apellido, apodo o sin tildes, y
    que un nombre que solo comparte el apellido no se confunda con otro piloto.

    :param name: Nombre escrito por el usuario.
    :param ref: Driver_ref esperado.
    """
    assert llm.resolve_driver(name) == ref


def test_driver_stats():
    """
    Verificar que las estadísticas de Hamilton coincidan con la base de datos.
    """
    row = llm.get_driver_stats("Lewis Hamilton").data[0]
    assert (row["wins"], row["titles"]) == (105, 7)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE results",
        "DELETE FROM results",
        "UPDATE drivers SET surname = 'x'",
        "SELECT 1; DELETE FROM results",
        "PRAGMA writable_schema = 1",
    ],
)
def test_unsafe_sql_is_rejected(sql):
    """
    Verificar que se rechace el SQL que modifica datos o tiene varias
    sentencias.

    :param sql: Consulta peligrosa.
    """
    before = compute_db_hash()
    with pytest.raises(llm.UnsafeSQLError):
        llm.run_sql(sql)
    assert compute_db_hash() == before


def test_write_inside_with_fails():
    """
    Verificar que un DELETE dentro de un WITH, que pasa la validación, sea un
    error de sintaxis al envolverlo en SELECT * FROM (...) y la base no cambie.
    """
    before = compute_db_hash()
    with pytest.raises(pd.errors.DatabaseError, match="syntax error"):
        llm.run_sql("WITH x AS (SELECT 1) DELETE FROM status")
    assert compute_db_hash() == before


def test_database_connection_is_read_only():
    """
    Verificar que la conexión rechace una escritura aunque llegara a
    ejecutarse.
    """
    before = compute_db_hash()
    with get_engine().connect() as connection:
        with pytest.raises(OperationalError, match="readonly"):
            connection.exec_driver_sql("DELETE FROM status")
    assert compute_db_hash() == before


def test_sql_has_row_limit():
    """Verificar que las consultas devuelvan como máximo MAX_ROWS filas."""
    rows = llm.run_sql("SELECT * FROM v_race_results;")
    assert len(rows) == llm.MAX_ROWS


def test_sql_timeout(monkeypatch):
    """
    Verificar que se interrumpa una consulta que tarda demasiado.

    :param monkeypatch: Utilidad de pytest para cambiar valores.
    """
    monkeypatch.setattr(llm, "SQL_TIMEOUT_SECONDS", 0)
    with pytest.raises(TimeoutError):
        llm.run_sql(
            "SELECT COUNT(*) FROM v_race_results AS a, v_race_results AS b"
        )


def test_empty_question():
    """Verificar que una pregunta vacía se rechace sin llamar al modelo."""
    with pytest.raises(ValueError):
        llm.ask("   ")


def test_ollama_unavailable(monkeypatch):
    """
    Verificar que, sin Ollama, el error explique cómo iniciarlo.

    :param monkeypatch: Utilidad de pytest para cambiar valores.
    """
    # Nadie escucha en el puerto 9: equivale a tener Ollama detenido.
    monkeypatch.setattr(llm, "OLLAMA_HOST", "http://127.0.0.1:9")
    with pytest.raises(llm.LLMUnavailableError, match="ollama serve"):
        llm.ask("¿Quién ganó en Monza en 2019?")


def test_model_not_downloaded(monkeypatch):
    """
    Verificar que, si falta el modelo, el error explique cómo descargarlo.

    :param monkeypatch: Utilidad de pytest para cambiar valores.
    """
    try:
        httpx.get(llm.OLLAMA_HOST, timeout=2)
    except httpx.HTTPError:
        pytest.skip("Ollama no está en ejecución")

    monkeypatch.setattr(llm, "OLLAMA_MODEL", "modelo-inexistente:1b")
    with pytest.raises(llm.LLMUnavailableError, match="ollama pull"):
        llm.ask("¿Quién ganó en Monza en 2019?")
