"""
API REST del proyecto F1.
Los modelos champion se cargan una sola vez al iniciar. Si MLflow no está
disponible, los endpoints de predicción responden 503 y el resto sigue
funcionando.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Si MLflow no responde, la API inicia sin modelos en pocos segundos en
# lugar de reintentar varios minutos.
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")

import httpx
import pandas as pd
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from f1 import features, llm, tracking
from f1.config import API_URL, FINAL_DATA_DIR, OLLAMA_HOST
from f1.db import query

# Regla de cada campo numérico de /predict/podium: (valor mínimo,
# obligatorio). Las variables no obligatorias pueden ser null, ej.
# driver_rank_before en la primera carrera de la temporada; el pipeline
# imputa esos valores.
INPUT_RULES = {
    "race_id": (1, True),
    "driver_id": (1, True),
    "grid": (0, True),
    "quali_position": (1, False),
    "driver_points_before": (0, True),
    "driver_rank_before": (1, False),
    "driver_form": (1, False),
    "driver_circuit_form": (1, False),
    "constructor_form": (1, False),
    "driver_races_before": (0, True),
    "round": (1, True),
}

# Mensajes de los errores que genera Flask.
HTTP_MESSAGES = {
    400: "La petición no es válida.",
    404: "La ruta no existe.",
    405: "Método no permitido en esta ruta.",
    500: "Error interno de la API.",
}


class ApiError(Exception):

    """Error que se devuelve al cliente como JSON."""

    def __init__(self, message: str, status: int, field: str | None = None):
        """
        Crear el error.

        :param message: Mensaje en español para el usuario.
        :param status: Código HTTP, ej. 400.
        :param field: Campo o parámetro inválido, ej. 'grid'; se incluye en la
            respuesta para que el cliente lo señale.
        """
        super().__init__(message)
        self.body = {"error": message}
        if field is not None:
            self.body["field"] = field
        self.status = status


def convert_records(rows: pd.DataFrame) -> list[dict]:
    """
    Convertir filas en diccionarios con tipos de Python y null.

    :param rows: Filas de una consulta o del dataset.

    :return: Lista de diccionarios serializables como JSON.
    """
    rows = rows.astype(object)
    return rows.where(rows.notna(), None).to_dict("records")


def load_models() -> dict:
    """
    Cargar desde MLflow las versiones champion de los dos modelos.

    :return: Diccionario {'podium': ..., 'clustering': ...}; cada valor
        tiene pipeline, version y metadata, o es None si no se pudo cargar.
    """
    models = {}
    for key, name in (
        ("podium", tracking.PODIUM_MODEL),
        ("clustering", tracking.CLUSTERING_MODEL)
    ):
        try:
            models[key] = {
                "pipeline": tracking.load_champion(name),
                **tracking.get_champion_info(name)
            }
        except Exception as error:  # MLflow detenido o modelo inexistente.
            print(f"No se pudo cargar {name}: {error}", file=sys.stderr)
            models[key] = None

    return models


def read_int_argument(name: str, required: bool = True) -> int | None:
    """
    Leer un parámetro entero de la URL.

    :param name: Nombre del parámetro, ej. 'year'.
    :param required: True si el parámetro es obligatorio.

    :return: Valor entero, o None si falta y no es obligatorio.
    """
    value = request.args.get(name)
    if value is None or value == "":
        if required:
            raise ApiError(f"Falta el parámetro '{name}'.", 400, field=name)
        return None
    if not value.isdigit():
        raise ApiError(
            f"El parámetro '{name}' debe ser un número entero.", 400,
            field=name,
        )

    return int(value)


def read_json_body() -> dict:
    """
    Leer el cuerpo JSON de la petición.

    :return: objeto JSON recibido.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("El cuerpo debe ser un objeto JSON.", 400)

    return body


def validate_numeric_inputs(body: dict, names: list[str]) -> dict:
    """
    Validar los campos numéricos enviados a /predict/podium.

    :param body: JSON recibido, ej. {'grid': 2, 'round': 5, ...}.
    :param names: Campos que se validan, ej. las variables del modelo
        o ['race_id', 'driver_id'].

    :return: Diccionario campo -> valor (o None si se omitió).
    """
    inputs = {}
    for name in names:
        minimum, required = INPUT_RULES[name]
        value = body.get(name)
        if value is None:
            if required:
                raise ApiError(
                    f"Falta el campo obligatorio '{name}'.", 400,
                    field=name,
                )
        elif isinstance(value, bool) or not isinstance(value, int | float):
            raise ApiError(
                f"El campo '{name}' debe ser numérico.", 400, field=name
            )
        elif value < minimum:
            raise ApiError(
                f"El campo '{name}' debe ser mayor o igual a {minimum}.",
                400, field=name,
            )
        inputs[name] = value

    return inputs


def create_app(
        models: dict | None = None,
        dataset: pd.DataFrame | None = None) -> Flask:
    """
    Crear la aplicación Flask.

    :param models: Modelos ya cargados; si es None se cargan las versiones
        champion desde MLflow.
    :param dataset: Dataset final con las variables pre-carrera; si es
        None se lee data/final/f1_dataset_final.csv.

    :return: Aplicación lista para ejecutarse.
    """
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    models = load_models() if models is None else models

    if dataset is None:
        dataset = pd.read_csv(FINAL_DATA_DIR / "f1_dataset_final.csv")

    profiles = features.build_driver_profiles(dataset)
    profile_columns = [
        "races", "first_year", "last_year", *features.PROFILE_FEATURES]

    # El grupo de cada piloto no cambia mientras la API está en ejecución.
    if models.get("clustering") is not None:
        clustering = models["clustering"]
        names = clustering["metadata"]["group_names"]
        clusters = clustering["pipeline"].predict(
            profiles[features.PROFILE_FEATURES]
        )
        profiles["group"] = [names[cluster] for cluster in clusters]

    def get_model(key: str) -> dict:
        """
        Devolver un modelo cargado.

        :param key: 'Podium' o 'clustering'.

        :return: Pipeline, version y metadata del modelo.
        """
        if models.get(key) is None:
            raise ApiError(
                "El modelo no está disponible: inicie MLflow y reinicie "
                "la API.", 503,
            )
        return models[key]

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        """
        Responder un ApiError como JSON.

        :param error: Error lanzado por un endpoint.

        :return: Respuesta JSON con el código del error.
        """
        return jsonify(error.body), error.status

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        """
        Responder como JSON los errores de Flask, ej. una ruta inexistente.

        :param error: Error HTTP de Flask.

        :return: Respuesta JSON con el código del error.
        """
        message = HTTP_MESSAGES.get(error.code, error.name)
        return jsonify({"error": message}), error.code

    @app.get("/health")
    def get_health():
        """
        Informar el estado de la base de datos, los modelos y Ollama.

        :return: Estado de cada servicio, versiones de los modelos y
            cantidad de temporadas, carreras, pilotos y escuderías.
        """
        try:
            counts = convert_records(
                query(
                    "SELECT COUNT(DISTINCT year) AS seasons, "
                    "COUNT(DISTINCT race_id) AS races, "
                    "COUNT(DISTINCT driver_id) AS drivers, "
                    "COUNT(DISTINCT constructor_id) AS constructors "
                    "FROM v_race_results"
                )
            )[0]
            database = "ok"
        except Exception:
            counts, database = None, "unavailable"

        try:
            httpx.get(OLLAMA_HOST, timeout=2).raise_for_status()
            ollama = "ok"
        except httpx.HTTPError:
            ollama = "unavailable"

        versions = {
            key: value and value["version"] for key, value in models.items()
        }

        return jsonify(
            {
                "database": database,
                "mlflow": "ok" if all(versions.values()) else "unavailable",
                "llm": ollama,
                "models": versions,
                "counts": counts,
            }
        )

    @app.get("/races")
    def get_races():
        """
        Listar las carreras de una temporada, o de todas si no se indica el año.

        :return: Lista de carreras con ID, ronda, nombre, fecha y circuito.
        """
        year = read_int_argument("year", required=False)
        sql = (
            "SELECT ra.race_id, ra.year, ra.round, ra.name AS race_name, "
            "ra.date AS race_date, ci.circuit_ref, "
            "ci.name AS circuit_name, ci.country FROM races AS ra "
            "JOIN circuits AS ci ON ci.circuit_id = ra.circuit_id "
            "WHERE :year IS NULL OR ra.year = :year "
            "ORDER BY ra.year, ra.round"
        )
        rows = query(sql, year=year)
        if rows.empty:
            raise ApiError(f"No hay carreras en {year}.", 404)

        return jsonify(convert_records(rows))

    @app.get("/races/<int:race_id>/results")
    def get_race_results(race_id: int):
        """
        Devolver los resultados completos de una carrera.

        :param race_id: Id de la carrera, ej. 1017.

        :return: Datos de la carrera y una fila por piloto, en orden de
            llegada.
        """
        rows = query(
            "SELECT race_id, year, round, race_name, race_date, "
            "circuit_name, position_order, position, driver_id, "
            "driver_ref, driver_name, constructor_name, grid, points, laps, "
            "time, status FROM v_race_results WHERE race_id = :race_id "
            "ORDER BY position_order",
            race_id=race_id,
        )
        if rows.empty:
            raise ApiError(f"No existe la carrera {race_id}.", 404)

        race = [
            "race_id", "year", "round", "race_name", "race_date", "circuit_name"]

        return jsonify(
            {
                "race": convert_records(rows[race].head(1))[0],
                "results": convert_records(rows.drop(columns=race)),
            }
        )

    @app.get("/winner")
    def get_winner():
        """
        Devolver el ganador por circuito (o nombre de carrera) y año.

        Si el circuito tuvo varias carreras ese año, devuelve todas.

        :return: Piloto, escudería, carrera y fecha de cada ganador.
        """
        circuit = request.args.get("circuit", "").strip()
        if not circuit:
            raise ApiError(
                "Falta el parámetro 'circuit'.", 400, field="circuit")

        year = read_int_argument("year")
        answer = llm.get_race_winner(circuit, year)
        if not answer.data:
            raise ApiError(answer.text, 404)

        return jsonify(
            {
                "circuit": circuit, "year": year,
                "winners": convert_records(pd.DataFrame(answer.data))
            }
        )

    @app.get("/drivers/<ref>/cluster")
    def get_driver_cluster(ref: str):
        """
        Devolver el grupo del clustering al que pertenece un piloto.

        :param ref: Driver_ref del piloto, ej. 'hamilton'.

        :return: Grupo, perfil del piloto, tamaño y promedios del grupo y
            versión del modelo.
        """
        clustering = get_model("clustering")
        races = dataset.loc[dataset["driver_ref"] == ref, "race_id"].size
        if races == 0:
            raise ApiError(f"No existe el piloto '{ref}'.", 404)
        if races < features.MIN_RACES:
            raise ApiError(
                f"El piloto '{ref}' corrió {races} carreras; el clustering "
                f"solo incluye pilotos con al menos {features.MIN_RACES}.",
                404,
            )
        driver = profiles[profiles["driver_ref"] == ref]
        group = driver["group"].iloc[0]
        members = profiles.loc[
            profiles["group"] == group,
            features.PROFILE_FEATURES
        ]
        return jsonify(
            {
                "driver_ref": ref,
                "driver_name": driver["driver_name"].iloc[0],
                "group": group,
                "profile": convert_records(driver[profile_columns].round(3))[0],
                "group_size": len(members),
                "group_mean": members.mean().round(3).to_dict(),
                "model_version": clustering["version"],
            }
        )

    @app.post("/predict/podium")
    def predict_podium():
        """
        Predecir la probabilidad de podio de un piloto en una carrera.

        Acepta {'race_id': ..., 'driver_id': ...} de una carrera del
        dataset, o un JSON con las variables del modelo.

        :return: Probabilidad, clase, umbral, versión del modelo, variables
            usadas y, para una carrera del dataset, el resultado real.
        """
        podium = get_model("podium")
        names = podium["metadata"]["features"]
        threshold = podium["metadata"]["threshold"]
        body = read_json_body()
        result = None
        if "race_id" in body or "driver_id" in body:
            ids = validate_numeric_inputs(body, ["race_id", "driver_id"])
            row = dataset[
                (dataset["race_id"] == ids["race_id"])
                & (dataset["driver_id"] == ids["driver_id"])
            ]
            if row.empty:
                raise ApiError(
                    f"El piloto {ids['driver_id']} no corrió la carrera "
                    f"{ids['race_id']}.", 404,
                )
            inputs = convert_records(row[names])[0]
            result = convert_records(
                row[
                    [
                        "year", "race_name", "driver_name", "constructor_name",
                        "position_order", "is_podium",
                    ]
                ]
            )[0]
        else:
            inputs = validate_numeric_inputs(body, names)

        X = pd.DataFrame([inputs], columns=names).astype(float)
        probability = float(podium["pipeline"].predict_proba(X)[0, 1])

        return jsonify(
            {
                "probability": round(probability, 3),
                "podium": probability >= threshold,
                "threshold": threshold,
                "model_version": podium["version"],
                "features": inputs,
                "result": result,
            }
        )

    @app.post("/ask")
    def ask():
        """
        Responder una pregunta con el asistente LLM.

        Recibe {'question': '...', 'strategy': 'hybrid' | 'sql'}; la
        estrategia es opcional.

        :return: Respuesta, estrategia usada, consulta SQL y datos.
        """
        body = read_json_body()
        question = body.get("question")
        if not isinstance(question, str):
            raise ApiError("Falta la pregunta.", 400)

        try:
            # llm.ask rechaza la pregunta vacía y la estrategia desconocida.
            answer = llm.ask(question, body.get("strategy", "hybrid"))
        except llm.LLMUnavailableError as error:
            raise ApiError(str(error), 503) from error
        except ValueError as error:
            raise ApiError(str(error), 400) from error

        return jsonify(
            {
                "question": question,
                "text": answer.text,
                "strategy": answer.strategy,
                "sql": answer.sql,
                "data": convert_records(pd.DataFrame(answer.data)),
            }
        )

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=urlsplit(API_URL).port or 5001)
