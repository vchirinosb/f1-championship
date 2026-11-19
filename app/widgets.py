"""Controles compartidos por varias páginas de la aplicación."""
import pandas as pd
import streamlit as st

import api_client


def fetch(call, *args):
    """
    Llamar a la API; si falla, mostrar el error y detener la página.

    :param call: Función de api_client, ej. api_client.get_races.
    :param args: Argumentos de la función.

    :return: JSON de la respuesta.
    """
    try:
        return call(*args)
    except api_client.ApiError as error:
        st.error(str(error))
        st.stop()


def select_race(year_column, race_column) -> int:
    """
    Mostrar los selectores de temporada y carrera; por defecto, la última
    carrera.

    :param year_column: Columna de Streamlit para elegir la temporada.
    :param race_column: Columna de Streamlit para elegir la carrera.

    :return: Race_id elegido.
    """
    races = pd.DataFrame(fetch(api_client.get_races))
    year = year_column.selectbox(
        "Temporada", sorted(races["year"].unique(), reverse=True)
    )
    season = races[races["year"] == year].set_index("race_id")
    return int(
        race_column.selectbox(
            "Carrera", season.index, index=len(season) - 1,
            format_func=lambda key: f"{season.at[key, 'round']}. "
            f"{season.at[key, 'race_name']} ({season.at[key, 'race_date']})",
        )
    )
