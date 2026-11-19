"""
Columnas derivadas y variables pre-carrera del dataset final.

Las variables pre-carrera solo usan información conocida antes de la largada:
cada una se calcula sobre las carreras anteriores del piloto o de la escudería,
ordenadas por fecha. El modelo de clasificación no ve el resultado de la carrera
que predice.
"""
import numpy as np
import pandas as pd

# Estados de pilotos que no tomaron la salida de la carrera.
NON_STARTER_STATUSES = (
    "Did not qualify",
    "Did not prequalify",
    "Withdrew",
    "107% Rule",
)

# Puntos del sistema vigente desde 2010 para las posiciones 1 a 10.
POINTS_2010 = dict(zip(range(1, 11), (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)))

# Eras reglamentarias: año de inicio y nombre.
ERAS = (
    (1950, "1950-1965 pioneers"),
    (1966, "1966-1988 3-litre and turbo"),
    (1989, "1989-2005 naturally aspirated V10"),
    (2006, "2006-2013 V8"),
    (2014, "2014-2021 hybrid"),
    (2022, "2022-2024 ground effect"),
)

# Número de carreras anteriores que se promedian para la forma reciente.
RECENT_RACES = 5

# Carreras mínimas para que el perfil de un piloto sea confiable.
MIN_RACES = 20

# Variables pre-carrera que usa el clasificador de podio.
PODIUM_FEATURES = [
    "grid",
    "quali_position",
    "driver_points_before",
    "driver_rank_before",
    "driver_form",
    "driver_circuit_form",
    "constructor_form",
    "driver_races_before",
    "round",
]

# Variables del perfil de cada piloto que usa el clustering.
PROFILE_FEATURES = [
    "win_rate",
    "podium_rate",
    "dnf_rate",
    "points_per_race",
    "mean_grid",
    "mean_positions_gained",
    "seasons",
]


def convert_time_to_ms(value) -> float:
    """
    Convertir un tiempo de texto 'm:ss.mmm' o 'ss.mmm' a milisegundos.

    :param value: Tiempo de texto, ej. '1:26.572'; puede ser nulo.

    :return: Tiempo en milisegundos, o NaN si el valor es nulo.
    """
    if pd.isna(value):
        return np.nan

    minutes, _, seconds = str(value).rpartition(":")
    return round((int(minutes or 0) * 60 + float(seconds)) * 1000)


def is_finished(status: pd.Series) -> pd.Series:
    """
    Indicar si el piloto terminó la carrera. Incluye llegar a vueltas del
    ganador ('+1 Lap', '+2 Laps', ...).

    :param status: Estado de llegada de cada resultado.

    :return: True si el piloto vio la bandera a cuadros.
    """
    return status.eq("Finished") | status.str.match(r"^\+\d+ Laps?$")


def assign_era(year: pd.Series) -> pd.Series:
    """
    Asignar la era reglamentaria de cada temporada.

    :param year: Año de la temporada.

    :return: Nombre de la era.
    """
    starts, names = zip(*ERAS)
    return pd.cut(
        year, bins=[*starts, np.inf], labels=names, right=False
    ).astype(str)


def add_result_columns(results: pd.DataFrame) -> pd.DataFrame:
    """
    Agregar las columnas derivadas del resultado de cada carrera.

    :param results: Resultados con grid, position, position_order y status.

    :return: Copia de results con las columnas nuevas.
    """
    results = results.copy()
    results["finished"] = is_finished(results["status"])
    results["is_win"] = results["position_order"].eq(1)
    results["is_podium"] = results["position_order"].le(3)

    # grid 0 = salida desde el pit lane o posición de salida desconocida.
    results["positions_gained"] = (
        results["grid"] - results["position_order"]
    ).where(results["grid"] > 0)
    results["points_2010"] = results["position"].map(POINTS_2010).fillna(0)
    results["era"] = assign_era(results["year"])
    return results


def add_pre_race_features(
        results: pd.DataFrame, standings: pd.DataFrame) -> pd.DataFrame:
    """
    Agregar las variables pre-carrera de cada piloto y escudería.

    Variables nuevas:
    - driver_races_before: carreras disputadas antes por el piloto.
    - driver_points_before / driver_rank_before: puntos y puesto del piloto
      en el campeonato después de la carrera anterior de la temporada
      (0 puntos y sin puesto en la primera fecha).
    - driver_form: posición final media en sus últimas 5 carreras.
    - driver_circuit_form: posición final media en ese circuito.
    - constructor_form: posición final media de la escudería en sus
      últimas 5 carreras.

    :param results: Una fila por piloto y carrera, con race_id, year, round,
        race_date, circuit_id, driver_id, constructor_id y position_order.
    :param standings: Campeonato de pilotos después de cada carrera, con
        race_id, driver_id, points y position.

    :return: Copia de results, ordenada por fecha, con las variables nuevas.
    """
    results = results.sort_values(["race_date", "race_id", "position_order"])
    results = results.reset_index(drop=True)

    by_driver = results.groupby("driver_id")
    results["driver_races_before"] = by_driver.cumcount()
    results["driver_form"] = by_driver["position_order"].transform(
        lambda s: s.shift(1).rolling(RECENT_RACES, min_periods=1).mean()
    )
    results["driver_circuit_form"] = results.groupby(
        ["driver_id", "circuit_id"]
    )["position_order"].transform(lambda s: s.shift(1).expanding().mean())

    # Campeonato oficial después de la carrera anterior de la misma temporada.
    # Se usa la tabla de posiciones porque los puntos de las carreras sprint
    # no están en results.
    races = results[["race_id", "year", "round"]].drop_duplicates()
    races = races.sort_values(["year", "round"])
    races["previous_race_id"] = (
        races.groupby("year")["race_id"].shift(1).astype("Int64")
    )
    previous = standings[["race_id", "driver_id", "points", "position"]]
    previous = previous.rename(
        columns={
            "race_id": "previous_race_id",
            "points": "driver_points_before",
            "position": "driver_rank_before",
        }
    ).astype({"previous_race_id": "Int64"})
    results = results.merge(
        races[["race_id", "previous_race_id"]], on="race_id", how="left"
    ).merge(previous, on=["previous_race_id", "driver_id"], how="left")
    results["driver_points_before"] = results["driver_points_before"].fillna(0)
    results = results.drop(columns="previous_race_id")

    # La forma de la escudería se calcula por carrera (promedio de sus
    # pilotos) y se desplaza una carrera.
    constructor_races = (
        results.groupby(["constructor_id", "race_id"], sort=False)
        .agg(race_date=("race_date", "first"), mean=("position_order", "mean"))
        .reset_index()
        .sort_values(["race_date", "race_id"])
    )
    constructor_races["constructor_form"] = constructor_races.groupby(
        "constructor_id"
    )["mean"].transform(
        lambda s: s.shift(1).rolling(RECENT_RACES, min_periods=1).mean()
    )

    return results.merge(
        constructor_races[["constructor_id", "race_id", "constructor_form"]],
        on=["constructor_id", "race_id"],
        how="left",
    )


def build_driver_profiles(results: pd.DataFrame) -> pd.DataFrame:
    """
    Resumir la carrera deportiva de cada piloto con al menos MIN_RACES.
    Los puntos usan el sistema de 2010 (points_2010) para comparar épocas.
    La salida desde el pit lane (grid 0) no cuenta para la parrilla media.

    :param results: Dataset final, con una fila por piloto que tomó la
        salida en una carrera.

    :return: Una fila por piloto con races, first_year, last_year y las
        variables de PROFILE_FEATURES.
    """
    grid = results["grid"].where(results["grid"] > 0)
    profiles = (
        results.assign(grid=grid, dnf=~results["finished"])
        .groupby(["driver_id", "driver_ref", "driver_name"])
        .agg(
            races=("race_id", "size"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            win_rate=("is_win", "mean"),
            podium_rate=("is_podium", "mean"),
            dnf_rate=("dnf", "mean"),
            points_per_race=("points_2010", "mean"),
            mean_grid=("grid", "mean"),
            mean_positions_gained=("positions_gained", "mean"),
            seasons=("year", "nunique"),
        )
        .reset_index()
    )

    return profiles[profiles["races"] >= MIN_RACES].reset_index(drop=True)
