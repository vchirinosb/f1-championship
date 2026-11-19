"""Página Predicciones: probabilidad de podio y tipo de piloto.

Se elige un piloto de una carrera del dataset, o se ingresan a mano las
variables del modelo de podio. El resultado de Predecir se muestra solo
hasta el siguiente cambio en la página: cambiar de pestaña no vuelve a
ejecutarla, pero elegir otro piloto sí, y el resultado desaparece.
"""

import pandas as pd
import streamlit as st

import api_client
import widgets

DATASET, MANUAL = "Piloto y carrera del dataset", "Valores manuales"

# Variables del modelo de podio: (descripción, ¿obligatoria?, mínimo).
# El tipo del mínimo define el campo del formulario manual: 0 o 1 acepta
# solo enteros (posiciones, conteos); 0.0 o 1.0 acepta decimales (puntos,
# promedios).
FEATURES = {
    "grid": ("Posición de salida (0 = pit lane)", True, 0),
    "quali_position": ("Posición en la clasificación", False, 1),
    "driver_points_before": ("Puntos en el campeonato antes de la carrera",
                             True, 0.0),
    "driver_rank_before": ("Puesto en el campeonato antes de la carrera",
                           False, 1),
    "driver_form": ("Posición media en sus últimas 5 carreras", False, 1.0),
    "driver_circuit_form": ("Posición media en este circuito", False, 1.0),
    "constructor_form": ("Posición media de la escudería en sus últimas 5 "
                         "carreras", False, 1.0),
    "driver_races_before": ("Carreras disputadas antes", True, 0),
    "round": ("Ronda de la temporada", True, 1),
}

GROUPS = {
    "CHAMPION": "Campeones: ganan con frecuencia y salen casi siempre "
                "adelante.",
    "WINNER": "Ganadores ocasionales: algunas victorias y podios "
              "frecuentes en equipos competitivos.",
    "MIDFIELD": "Mitad de la parrilla: pocos podios, pero terminan la "
                "mayoría de las carreras.",
    "BACKMARKER": "Fondo de la parrilla: salen atrás y abandonan con "
                  "frecuencia.",
}

PROFILE = {
    "win_rate": "Tasa de victorias",
    "podium_rate": "Tasa de podios",
    "dnf_rate": "Tasa de abandonos",
    "points_per_race": "Puntos por carrera (sistema 2010)",
    "mean_grid": "Posición de salida media",
    "mean_positions_gained": "Posiciones ganadas por carrera",
    "seasons": "Temporadas",
}


def show_podium(payload: dict) -> None:
    """Predecir el podio y mostrar la probabilidad y las variables usadas.

    :param payload: cuerpo para /predict/podium.
    """
    try:
        result = api_client.predict_podium(payload)
    except api_client.ApiError as error:
        st.error(str(error))
        return
    left, right = st.columns(2)
    left.metric("Probabilidad de podio", f"{result['probability']:.1%}")
    right.metric("Predicción",
                 "Podio" if result["podium"] else "Sin podio")
    st.caption(f"Se predice podio si la probabilidad es al menos "
               f"{result['threshold']:.0%}. Modelo f1-podium-classifier "
               f"v{result['model_version']}.")
    actual = result["result"]
    if actual:
        verdict = "acertó" if actual["is_podium"] == result["podium"] else \
            "falló"
        st.info(f"Resultado real: {actual['driver_name']} "
                f"({actual['constructor_name']}) terminó "
                f"{actual['position_order']}.º en el {actual['race_name']} "
                f"{actual['year']}; el modelo {verdict}.")
    with st.expander("Variables usadas"):
        st.dataframe(
            pd.DataFrame({
                "feature": [FEATURES[name][0] for name in result["features"]],
                "value": list(result["features"].values()),
            }),
            hide_index=True,
            column_config={"feature": "Variable", "value": "Valor"},
        )


def show_cluster(driver_ref: str | None) -> None:
    """Mostrar el grupo del piloto y su perfil frente al del grupo.

    :param driver_ref: piloto elegido, o None con valores manuales.
    """
    if driver_ref is None:
        st.info("El tipo de piloto requiere elegir un piloto del dataset.")
        return
    try:
        result = api_client.get_driver_cluster(driver_ref)
    except api_client.ApiError as error:
        st.warning(str(error))
        return
    st.metric("Grupo", result["group"])
    st.markdown(GROUPS[result["group"]])
    profile = result["profile"]
    st.caption(f"{result['driver_name']}: {profile['races']} carreras entre "
               f"{profile['first_year']} y {profile['last_year']}. El grupo "
               f"tiene {result['group_size']} pilotos. Modelo "
               f"f1-driver-clustering v{result['model_version']}.")
    st.dataframe(
        pd.DataFrame({
            "variable": PROFILE.values(),
            "driver": [profile[key] for key in PROFILE],
            "group": [result["group_mean"][key] for key in PROFILE],
        }),
        hide_index=True,
        column_config={"variable": "Variable", "driver": "Piloto",
                       "group": "Promedio del grupo"},
    )


def select_dataset_driver() -> tuple[dict, str]:
    """Mostrar la selección de temporada, carrera y piloto.

    :return: cuerpo para /predict/podium y driver_ref.
    """
    columns = st.columns([1, 2, 2])
    race_id = widgets.select_race(columns[0], columns[1])
    results = pd.DataFrame(
        widgets.fetch(api_client.get_race_results, race_id)["results"]
    )
    drivers = results.set_index("driver_id")
    driver_id = int(columns[2].selectbox(
        "Piloto", drivers.index,
        format_func=lambda key: f"{drivers.at[key, 'driver_name']} "
        f"({drivers.at[key, 'constructor_name']})",
    ))
    return ({"race_id": race_id, "driver_id": driver_id},
            drivers.at[driver_id, "driver_ref"])


def enter_manual_values() -> tuple[dict, None]:
    """Mostrar el formulario con las variables del modelo de podio.

    :return: cuerpo para /predict/podium y None (sin piloto, no hay tipo
        de piloto).
    """
    st.caption("Los campos opcionales pueden quedar vacíos, ej. el "
               "puesto en el campeonato en la primera carrera del año.")
    columns = st.columns(3)
    payload = {}
    for index, (name, (label, required, minimum)) in enumerate(
        FEATURES.items()
    ):
        payload[name] = columns[index % 3].number_input(
            label if required else f"{label} (opcional)",
            min_value=minimum, value=minimum if required else None,
            step=type(minimum)(1),
        )
    return payload, None


st.title("Predicciones")
if api_client.is_unavailable("mlflow"):
    st.warning("Los modelos no están cargados: inicie MLflow y reinicie la "
               "API para obtener predicciones.")

mode = st.radio("Datos de entrada", [DATASET, MANUAL], horizontal=True)
payload, driver_ref = (select_dataset_driver() if mode == DATASET
                       else enter_manual_values())

if st.button("Predecir", type="primary"):
    podium_tab, cluster_tab = st.tabs(["Podio", "Tipo de piloto"])
    with podium_tab:
        show_podium(payload)
    with cluster_tab:
        show_cluster(driver_ref)
