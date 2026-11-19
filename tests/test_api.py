"""Pruebas de la API Flask con el cliente de prueba de Flask."""
import numpy as np
import pandas as pd
import pytest

from api import app as api
from f1 import llm
from f1.config import FINAL_DATA_DIR
from f1.features import PODIUM_FEATURES

GROUP_NAMES = ["BACKMARKER", "MIDFIELD", "CHAMPION", "WINNER"]


class FakePodium:

    """Clasificador falso: siempre da 0.9 de probabilidad de podio."""

    def predict_proba(self, X):
        """
        Devolver siempre 0.9 de probabilidad de podio.

        :param X: Variables del modelo.

        :return: Probabilidades [no podio, podio] de cada fila.
        """
        return np.tile([0.1, 0.9], (len(X), 1))


class FakeClustering:

    """Clustering falso: todos los pilotos van al grupo 2 (CHAMPION)."""

    def predict(self, X):
        """
        Asignar todos los pilotos al grupo 2.

        :param X: Perfiles de los pilotos.

        :return: Número de grupo de cada fila.
        """
        return np.full(len(X), 2)


MODELS = {
    "podium": {
        "pipeline": FakePodium(), "version": 3,
        "metadata": {
            "threshold": 0.77,
            "features": PODIUM_FEATURES
        }
    },
    "clustering": {
        "pipeline": FakeClustering(), "version": 5,
        "metadata": {"group_names": GROUP_NAMES}},
}

VALID_FEATURES = {
    "grid": 2, "quali_position": 2, "driver_points_before": 100,
    "driver_rank_before": 2, "driver_form": 3.0, "driver_circuit_form": None,
    "constructor_form": 3.0, "driver_races_before": 50, "round": 10,
}


@pytest.fixture(scope="module")
def dataset():
    """
    Leer el dataset final una sola vez para todas las pruebas.

    :return: DataFrame con las variables pre-carrera.
    """
    return pd.read_csv(FINAL_DATA_DIR / "f1_dataset_final.csv")


@pytest.fixture
def client(dataset):
    """
    Crear el cliente de prueba con los modelos falsos.

    :param dataset: Dataset final.
    :return: Cliente de prueba de Flask.
    """
    return api.create_app(MODELS, dataset).test_client()


def test_health_without_ollama(client, monkeypatch):
    """
    Verificar que, con Ollama detenido, /health responda 200 e indique cada
    servicio.

    :param client: Cliente de prueba.
    :param monkeypatch: Utilidad de pytest para cambiar valores.
    """
    monkeypatch.setattr(api, "OLLAMA_HOST", "http://127.0.0.1:9")
    body = client.get("/health").get_json()
    assert body["database"] == "ok"
    assert body["llm"] == "unavailable"
    assert body["models"] == {"podium": 3, "clustering": 5}
    assert body["counts"]["races"] == 1125


def test_winner(client):
    """
    Verificar que el ganador de Monza 2019 sea Leclerc, con escudería y fecha.
    """
    response = client.get("/winner?circuit=monza&year=2019")
    assert response.status_code == 200

    winner = response.get_json()["winners"][0]
    assert winner["driver_name"] == "Charles Leclerc"
    assert winner["constructor_name"] == "Ferrari"
    assert winner["race_date"] == "2019-09-08"


@pytest.mark.parametrize(
    "url, field",
    [
        ("/winner?circuit=monza", "year"),
        ("/winner?year=2019", "circuit"),
        ("/winner?circuit=monza&year=dos", "year"),
        ("/races?year=abc", "year"),
    ],
)
def test_invalid_parameters(client, url, field):
    """
    Verificar que un parámetro faltante o no numérico responda 400 y lo nombre.

    :param client: Cliente de prueba.
    :param url: Ruta con parámetros inválidos.
    :param field: Parámetro que se espera en el error.
    """
    response = client.get(url)
    assert response.status_code == 400
    assert response.get_json()["field"] == field


@pytest.mark.parametrize(
    "url",
    [
        "/winner?circuit=monza&year=1940",
        "/races?year=1940",
        "/races/99999/results",
        "/drivers/nadie/cluster",
        "/no-existe",
    ],
)
def test_not_found(client, url):
    """
    Verificar que lo que no existe responda 404 con un mensaje.

    :param client: Cliente de prueba.
    :param url: Ruta sin resultados.
    """
    response = client.get(url)
    assert response.status_code == 404
    assert response.get_json()["error"]


def test_races_and_results(client):
    """
    Verificar que 2023 tenga 22 carreras y que Verstappen ganara en Bélgica
    (race_id 1110).
    """
    races = client.get("/races?year=2023").get_json()
    assert len(races) == 22

    body = client.get("/races/1110/results").get_json()
    assert body["race"]["race_name"] == "Belgian Grand Prix"
    assert body["results"][0]["driver_name"] == "Max Verstappen"


def test_driver_cluster(client):
    """
    Verificar que el grupo de un piloto use los nombres de los metadatos del
    modelo.
    """
    body = client.get("/drivers/hamilton/cluster").get_json()
    assert body["group"] == "CHAMPION"
    assert body["model_version"] == 5
    assert body["profile"]["races"] == 356


def test_driver_with_few_races(client):
    """
    Verificar que un piloto con menos de MIN_RACES carreras no tenga grupo.
    """
    response = client.get("/drivers/doornbos/cluster")
    assert response.status_code == 404
    assert "al menos 20" in response.get_json()["error"]


def test_predict_podium_from_dataset(client):
    """
    Verificar que, por carrera y piloto, se devuelva la probabilidad, la clase,
    la versión y el resultado real.
    """
    response = client.post(
        "/predict/podium",
        json={"race_id": 1110, "driver_id": 830}
    )
    assert response.status_code == 200

    body = response.get_json()
    assert (body["probability"], body["podium"]) == (0.9, True)
    assert body["model_version"] == 3
    assert body["result"]["driver_name"] == "Max Verstappen"
    assert body["features"]["grid"] == 6


def test_predict_podium_from_features(client):
    """
    Verificar que, con las variables del modelo, los valores opcionales acepten
    null.
    """
    response = client.post("/predict/podium", json=VALID_FEATURES)
    assert response.status_code == 200
    assert response.get_json()["result"] is None


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"grid": -1}, "grid"),
        ({"round": None}, "round"),
        ({"driver_form": "rápido"}, "driver_form"),
        ({"quali_position": True}, "quali_position"),
    ],
)
def test_predict_podium_invalid(client, changes, field):
    """
    Verificar que una variable inválida o faltante responda 400 y nombre el
    campo.

    :param client: Cliente de prueba.
    :param changes: Valores que reemplazan a los válidos.
    :param field: Campo que se espera en el error.
    """
    response = client.post(
        "/predict/podium", json={**VALID_FEATURES, **changes})
    assert response.status_code == 400
    assert response.get_json()["field"] == field


@pytest.mark.parametrize(
    "body, field",
    [
        ({"race_id": "1110", "driver_id": 830}, "race_id"),
        ({"race_id": 1110}, "driver_id")
    ],
)
def test_predict_podium_invalid_ids(client, body, field):
    """
    Verificar que un ID no numérico o faltante responda 400 y nombre el campo.

    :param client: Cliente de prueba.
    :param body: JSON enviado.
    :param field: Campo que se espera en el error.
    """
    response = client.post("/predict/podium", json=body)
    assert response.status_code == 400
    assert response.get_json()["field"] == field


def test_predict_podium_unknown_driver(client):
    """
    Verificar que un piloto que no corrió esa carrera responda 404 (Verstappen
    en el GP de Gran Bretaña de 1950).
    """
    response = client.post(
        "/predict/podium", json={"race_id": 833, "driver_id": 830})
    assert response.status_code == 404


def test_models_unavailable(dataset):
    """
    Verificar que, sin MLflow, las predicciones respondan 503 y los datos sigan
    disponibles.

    :param dataset: Dataset final.
    """
    models = {"podium": None, "clustering": None}
    client = api.create_app(models, dataset).test_client()
    assert client.post(
        "/predict/podium", json=VALID_FEATURES).status_code == 503
    assert client.get("/drivers/hamilton/cluster").status_code == 503
    assert client.get("/races?year=2019").status_code == 200
    assert client.get("/health").get_json()["mlflow"] == "unavailable"


def test_ask(client, monkeypatch):
    """
    Verificar que POST /ask devuelva la respuesta, la estrategia, el SQL y los
    datos.

    :param client: Cliente de prueba.
    :param monkeypatch: Utilidad de pytest para cambiar valores.
    """
    def fake_ask(question, strategy):
        return llm.Answer(
            "Charles Leclerc ganó.", "tool:race_winner",
            "SELECT ...",
            [
                {
                    "driver_name": "Charles Leclerc",
                    "laps": float("nan")
                }
            ]
        )

    monkeypatch.setattr(llm, "ask", fake_ask)
    question = "¿Quién ganó en Monza en 2019?"
    response = client.post("/ask", json={"question": question})
    assert response.status_code == 200

    body = response.get_json()
    assert body["strategy"] == "tool:race_winner"
    # NaN no es JSON válido: se envía como null.
    assert body["data"] == [{"driver_name": "Charles Leclerc", "laps": None}]


@pytest.mark.parametrize(
    "body",
    [
        {"question": "  "}, {}, ["hola"],
        {"question": "¿Quién ganó?", "strategy": "otra"}
    ],
)
def test_ask_empty_question(client, body):
    """
    Verificar que una pregunta vacía, un cuerpo inválido o una estrategia
    desconocida respondan 400.

    :param client: Cliente de prueba.
    :param body: JSON enviado.
    """
    assert client.post("/ask", json=body).status_code == 400


def test_ask_without_ollama(client, monkeypatch):
    """
    Verificar que, sin Ollama, /ask responda 503 con el mensaje para iniciarlo.

    :param client: Cliente de prueba.
    :param monkeypatch: Utilidad de pytest para cambiar valores.
    """
    monkeypatch.setattr(llm, "OLLAMA_HOST", "http://127.0.0.1:9")
    response = client.post("/ask", json={"question": "¿Quién ganó?"})
    assert response.status_code == 503
    assert "ollama serve" in response.get_json()["error"]
