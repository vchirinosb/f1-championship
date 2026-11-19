"""Pruebas de las columnas derivadas y de las variables pre-carrera."""
import numpy as np
import pandas as pd
import pytest

from f1 import data, features

PRE_RACE_COLUMNS = [
    "driver_races_before",
    "driver_points_before",
    "driver_rank_before",
    "driver_form",
    "driver_circuit_form",
    "constructor_form",
]


@pytest.fixture(scope="module")
def results():
    """
    Leer de la base de datos los resultados reales de 2015 a 2024.

    :return: Una fila por piloto y carrera.
    """
    return data.read_sql(
        "SELECT race_id, year, round, race_date, circuit_id, driver_id, "
        "constructor_id, grid, position, position_order, points, status "
        "FROM v_race_results WHERE year >= 2015"
    )


@pytest.fixture(scope="module")
def standings():
    """
    Leer el campeonato de pilotos después de cada carrera, de 2015 a 2024.

    :return: Una fila por piloto y carrera.
    """
    return data.read_sql(
        "SELECT ds.race_id, ds.driver_id, ds.points, ds.position "
        "FROM driver_standings AS ds "
        "JOIN races AS ra ON ra.race_id = ds.race_id WHERE ra.year >= 2015"
    )


@pytest.mark.parametrize(
    "text, ms",
    [("1:26.572", 86572), ("23.606", 23606), ("1:00.000", 60000)],
)
def test_time_to_ms(text, ms):
    """
    Verificar que los tiempos de texto se conviertan a milisegundos.

    :param text: Tiempo de texto.
    :param ms: Milisegundos esperados.
    """
    assert features.convert_time_to_ms(text) == ms


def test_time_to_ms_keeps_nulls():
    """Verificar que un tiempo nulo siga siendo nulo."""
    assert np.isnan(features.convert_time_to_ms(None))


def test_result_columns():
    """Verificar que las columnas derivadas sigan las reglas documentadas."""
    results = pd.DataFrame(
        {
            "year": [1955, 2023, 2023],
            "grid": [0, 5, 1],
            "position": [1.0, 3.0, np.nan],
            "position_order": [1, 3, 20],
            "status": ["Finished", "+1 Lap", "Engine"],
        }
    )
    added = features.add_result_columns(results)
    assert added["finished"].tolist() == [True, True, False]
    assert added["is_podium"].tolist() == [True, True, False]
    assert added["points_2010"].tolist() == [25, 15, 0]
    assert added["positions_gained"].isna().tolist() == [True, False, False]
    assert added["era"].str[:4].tolist() == ["1950", "2022", "2022"]


def test_pre_race_features_have_no_leakage(results, standings):
    """
    Verificar que cambiar el resultado de una carrera no cambie sus variables.

    :param results: Resultados reales de 2015 a 2024.
    :param standings: Campeonato después de cada carrera.
    """
    race_id = results.loc[results["year"] == 2021, "race_id"].max()
    altered = results.copy()
    in_race = altered["race_id"] == race_id
    # Se invierte el orden de llegada y se reparten otros puntos
    altered.loc[in_race, "position_order"] = (
        altered.loc[in_race, "position_order"].max()
        + 1
        - altered.loc[in_race, "position_order"]
    )
    altered.loc[in_race, "points"] = 100.0
    altered_standings = standings.copy()
    altered_standings.loc[
        altered_standings["race_id"] == race_id, ["points", "position"]
    ] = [1000.0, 99]

    def compute_race_features(frame, table):
        rows = features.add_pre_race_features(frame, table)
        rows = rows[rows["race_id"] == race_id]
        return rows.sort_values("driver_id")[PRE_RACE_COLUMNS].reset_index(
            drop=True
        )

    pd.testing.assert_frame_equal(
        compute_race_features(results, standings),
        compute_race_features(altered, altered_standings),
    )


def test_pre_race_features_values(results, standings):
    """
    Verificar que las variables coincidan con valores calculados a mano.

    :param results: Resultados reales de 2015 a 2024.
    :param standings: Campeonato después de cada carrera.
    """
    rows = features.add_pre_race_features(results, standings)
    driver = rows[rows["driver_id"] == 1]  # Lewis Hamilton
    previous = driver["position_order"].shift(1)
    expected = previous.rolling(features.RECENT_RACES, min_periods=1).mean()
    np.testing.assert_allclose(driver["driver_form"], expected)
    assert driver["driver_races_before"].tolist() == list(range(len(driver)))
    # En la primera carrera de cada temporada no hay puntos previos
    first_rounds = driver.groupby("year").head(1)
    assert (first_rounds["driver_points_before"] == 0).all()
    assert first_rounds["driver_rank_before"].isna().all()
    # Antes de Abu Dhabi 2021 Verstappen y Hamilton estaban empatados con
    # 369.5 puntos, que incluyen los de las carreras sprint
    final_race = rows[rows["year"] == 2021]["round"].max()
    leaders = rows[
        (rows["year"] == 2021) & (rows["round"] == final_race)
        & rows["driver_id"].isin([1, 830])  # Hamilton y Verstappen
    ]
    assert leaders["driver_points_before"].tolist() == [369.5, 369.5]


def test_driver_profiles():
    """
    Verificar que el perfil filtre a los pilotos con pocas carreras y calcule
    las tasas.
    """
    results = pd.DataFrame(
        {
            "driver_id": [1] * 20 + [2] * 3,
            "driver_ref": ["a"] * 20 + ["b"] * 3,
            "driver_name": ["A"] * 20 + ["B"] * 3,
            "race_id": range(23),
            "year": [2020] * 10 + [2021] * 10 + [2021] * 3,
            "grid": [0] + [2] * 19 + [5] * 3,
            "is_win": [True] * 5 + [False] * 18,
            "is_podium": [True] * 10 + [False] * 13,
            "finished": [False] * 4 + [True] * 19,
            "points_2010": [25.0] * 5 + [0.0] * 18,
            "positions_gained": [np.nan] + [1.0] * 22,
        }
    )
    profiles = features.build_driver_profiles(results)
    assert profiles["driver_ref"].tolist() == ["a"]

    row = profiles.iloc[0]
    assert (row["races"], row["seasons"]) == (20, 2)
    assert (row["win_rate"], row["podium_rate"]) == (0.25, 0.5)
    assert row["dnf_rate"] == 0.2
    assert row["points_per_race"] == 6.25
    assert (row["mean_grid"], row["mean_positions_gained"]) == (2.0, 1.0)
