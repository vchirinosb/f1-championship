"""Página Inicio: descripción del proyecto y cifras del dataset."""

import streamlit as st

import api_client
import widgets

REPOSITORY = "https://github.com/vchirinosb/f1-championship"

st.title("Campeonato Mundial de Fórmula 1 (1950-2024)")
st.markdown(
    "Análisis del dataset *Formula 1 World Championship* de Kaggle: "
    "resultados de todas las carreras desde 1950, dos modelos de machine "
    "learning registrados en MLflow y un asistente que responde preguntas "
    "en español con un LLM local."
)

counts = widgets.fetch(api_client.get_health)["counts"]
if counts is None:
    st.warning("La base de datos no está disponible.")
    st.stop()

columns = st.columns(4)
columns[0].metric("Temporadas", counts["seasons"])
columns[1].metric("Carreras", counts["races"])
columns[2].metric("Pilotos", counts["drivers"])
columns[3].metric("Escuderías", counts["constructors"])

st.subheader("Qué se puede hacer")
st.markdown(
    "- **Explorar**: elegir una temporada y una carrera para ver el podio, "
    "la clasificación completa y cuántas posiciones ganó cada piloto.\n"
    "- **Predicciones**: estimar la probabilidad de podio de un piloto "
    "antes de la carrera y ver a qué grupo de pilotos pertenece según el "
    "clustering.\n"
    "- **Asistente**: preguntar en español, ej. *¿Quién ganó en Monza "
    "en 2019?*, y ver la consulta SQL que se usó para responder."
)
st.markdown(f"[Repositorio en GitHub]({REPOSITORY}) · "
            f"[Wiki del proyecto]({REPOSITORY}/wiki)")
