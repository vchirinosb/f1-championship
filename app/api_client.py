"""Cliente HTTP de la API Flask para la aplicación Streamlit."""
import os

import requests
import streamlit as st

API_URL = os.environ.get("F1_API_URL", "http://127.0.0.1:5001")

# Segundos de espera; el asistente puede tardar más si el modelo de Ollama
# todavía no está cargado en memoria.
TIMEOUT_SECONDS = 10
ASK_TIMEOUT_SECONDS = 120


class ApiError(Exception):
    """La API no respondió o devolvió un error."""
    pass


def _call_api(method: str, path: str, timeout: int = TIMEOUT_SECONDS, **kwargs):
    """
    Llamar a la API y devolver el JSON de la respuesta.

    :param method: 'GET' o 'POST'.
    :param path: Ruta de la API, ej. '/races'.
    :param timeout: Segundos de espera.
    :param kwargs: Argumentos de requests, ej. params o json.

    :return: Cuerpo JSON de la respuesta.
    """
    try:
        response = requests.request(
            method, f"{API_URL}{path}", timeout=timeout, **kwargs
        )
    except requests.ConnectionError as error:
        raise ApiError(
            f"No se pudo conectar con la API en {API_URL}. Iníciela desde "
            "la raíz del repositorio con: ../bin/python api/app.py"
        ) from error
    except requests.Timeout as error:
        raise ApiError("La API tardó demasiado en responder.") from error

    try:
        body = response.json()
    except ValueError as error:
        raise ApiError(
            f"La API respondió {response.status_code} sin JSON."
        ) from error

    if not response.ok:
        raise ApiError(body.get("error", f"Error {response.status_code}."))

    return body


@st.cache_data(ttl=15, show_spinner=False)
def get_health() -> dict:
    """
    Consultar el estado de la base de datos, MLflow y Ollama.
    Se guarda 15 segundos para que la barra lateral y las páginas no
    consulten la API en cada interacción.

    :return: Estado de cada servicio, versiones y conteos del dataset.
    """
    return _call_api("GET", "/health")


@st.cache_data(ttl=600, show_spinner=False)
def get_races() -> list[dict]:
    """
    Obtener todas las carreras del dataset.

    :return: Una fila por carrera con ID, año, ronda, nombre y fecha.
    """
    return _call_api("GET", "/races")


@st.cache_data(ttl=600, show_spinner=False)
def get_race_results(race_id: int) -> dict:
    """
    Obtener los resultados de una carrera.

    :param race_id: Id de la carrera.

    :return: Datos de la carrera y una fila por piloto.
    """
    return _call_api("GET", f"/races/{race_id}/results")


def get_driver_cluster(driver_ref: str) -> dict:
    """
    Obtener el grupo del clustering de un piloto.

    :param driver_ref: Ej. 'hamilton'.

    :return: Grupo, perfil, promedios del grupo y versión del modelo.
    """
    return _call_api("GET", f"/drivers/{driver_ref}/cluster")


def predict_podium(payload: dict) -> dict:
    """
    Obtener la probabilidad de podio.

    :param payload: {'race_id', 'driver_id'} o las variables del modelo.

    :return: Probabilidad, clase, umbral y versión del modelo.
    """
    return _call_api("POST", "/predict/podium", json=payload)


def ask(question: str) -> dict:
    """
    Preguntar al asistente LLM.

    :param question: Pregunta en español.

    :return: Respuesta, estrategia usada, consulta SQL y datos.
    """
    return _call_api(
        "POST", "/ask", timeout=ASK_TIMEOUT_SECONDS,
        json={"question": question})


def is_unavailable(service: str) -> bool:
    """
    Indicar si la API informa que un servicio no está disponible.

    :param service: 'Database', 'mlflow' o 'llm'.

    :return: True si el servicio no está disponible.
    """
    try:
        return get_health()[service] != "ok"
    except ApiError:
        return False
