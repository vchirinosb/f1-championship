"""Página Explorar: resultados de una carrera elegida por año."""

import pandas as pd
import streamlit as st

import api_client
import widgets

MEDALS = ["🥇", "🥈", "🥉"]

st.title("Explorar resultados")

left, right = st.columns([1, 3])
race_id = widgets.select_race(left, right)
body = widgets.fetch(api_client.get_race_results, race_id)
race = body["race"]
results = pd.DataFrame(body["results"])

st.subheader(f"{race['race_name']} {race['year']}")
st.caption(f"{race['circuit_name']} · {race['race_date']} · "
           f"ronda {race['round']}")

for column, medal, row in zip(st.columns(3), MEDALS,
                              results.head(3).itertuples()):
    column.metric(f"{medal} {row.position_order}.º", row.driver_name)
    column.caption(row.constructor_name)

st.dataframe(
    results[["position_order", "driver_name", "constructor_name", "grid",
             "points", "laps", "time", "status"]],
    hide_index=True,
    column_config={
        "position_order": "Pos.",
        "driver_name": "Piloto",
        "constructor_name": "Escudería",
        "grid": "Salida",
        "points": "Puntos",
        "laps": "Vueltas",
        "time": "Tiempo",
        "status": "Estado",
    },
)

st.subheader("Posición de salida y posición final")
st.caption(
    "Cada punto es un piloto. Los que quedan por debajo de la diagonal "
    "ganaron posiciones durante la carrera. No se incluyen los que "
    "salieron desde el pit lane (salida 0)."
)
started = results[results["grid"] > 0]
st.scatter_chart(started, x="grid", y="position_order",
                 x_label="Posición de salida", y_label="Posición final")
