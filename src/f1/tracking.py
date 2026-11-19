"""
Registro de experimentos y modelos en MLflow.
Al importarse conecta con el servidor de MLFLOW_TRACKING_URI. La API carga
la versión marcada con el alias champion con load_champion y lee su número
de versión y sus metadatos con get_champion_info.
"""
import logging
import os

# Salida de MLflow en los notebooks: sin el mensaje informativo al importarse,
# sin el enlace de cada ejecución y sin barras de descarga.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_SUPPRESS_PRINTING_URL_TO_STDOUT", "true")
os.environ.setdefault("MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR", "false")

import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import pandas as pd
import skops.io
from mlflow import MlflowClient
from mlflow.models import infer_signature
from mlflow.models.model import ModelInfo

from f1.config import MLFLOW_TRACKING_URI

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
# Solo se muestran advertencias y errores de MLflow.
logging.getLogger("mlflow").setLevel(logging.WARNING)

# Experimentos.
CLUSTERING_EXPERIMENT = "f1-clustering"
PODIUM_EXPERIMENT = "f1-podium"
LLM_EXPERIMENT = "f1-llm"

# Modelos del Model Registry.
CLUSTERING_MODEL = "f1-driver-clustering"
PODIUM_MODEL = "f1-podium-classifier"

# Alias de la versión que sirve la API.
CHAMPION_ALIAS = "champion"


def start_run(
    experiment: str | None = None,
    run_name: str | None = None,
    nested: bool = False,
    run_id: str | None = None,
):
    """
    Iniciar una ejecución de MLflow, o retomar una existente.

    :param experiment: Nombre del experimento, ej. PODIUM_EXPERIMENT.
    :param run_name: Nombre de la ejecución en la interfaz de MLflow.
    :param nested: True para crear una ejecución hija de la activa, ej.
        una combinación de hiperparámetros dentro de la búsqueda.
    :param run_id: Id de una ejecución existente para volver a registrar
        en ella, ej. la ejecución padre al terminar la búsqueda.

    :return: Ejecución activa de MLflow.
    """
    if experiment is not None:
        mlflow.set_experiment(experiment)

    return mlflow.start_run(run_id=run_id, run_name=run_name, nested=nested)


def log_figure(figure: plt.Figure, file_name: str) -> None:
    """
    Guardar una figura de Matplotlib en la ejecución activa y cerrarla.

    :param figure: Figura de Matplotlib, ej. una matriz de confusión.
    :param file_name: nombre del archivo en los artefactos, ej.
        'confusion_matrix.png'.
    """
    mlflow.log_figure(figure, file_name)
    plt.close(figure)


def log_model(
        pipeline, X: pd.DataFrame, metadata: dict | None = None) -> ModelInfo:
    """
    Guardar el pipeline en la ejecución activa, sin registrarlo.
    El modelo se guarda en formato skops.

    :param pipeline: Pipeline de scikit-learn ya entrenado.
    :param X: Datos de entrada con los que se entrenó el pipeline.
    :param metadata: Datos que acompañan al modelo, ej. el nombre de
        cada grupo del clustering; se leen con get_model_info.

    :return: Información del modelo guardado; model_uri se usa para
        registrar el mejor modelo con register_champion.
    """
    integers = X.select_dtypes("integer").columns
    example = X.head(5).astype(dict.fromkeys(integers, "float64"))
    trusted = skops.io.get_untrusted_types(data=skops.io.dumps(pipeline))

    return mlflow.sklearn.log_model(
        pipeline,
        name="model",
        signature=infer_signature(example, pipeline.predict(example)),
        input_example=example,
        serialization_format="skops",
        skops_trusted_types=trusted,
        metadata=metadata,
    )


def register_champion(model_uri: str, model_name: str) -> int:
    """
    Registrar un modelo como nueva versión y marcarla como champion.

    :param model_uri: Model_uri que devolvió log_model para el mejor modelo.
    :param model_name: Nombre en el Model Registry, ej. PODIUM_MODEL.

    :return: Número de la versión creada.
    """
    version = mlflow.register_model(model_uri, model_name).version
    MlflowClient().set_registered_model_alias(
        model_name, CHAMPION_ALIAS, str(version)
    )

    return int(version)


def load_champion(model_name: str):
    """
    Cargar la versión champion de un modelo del Model Registry.

    :param model_name: Nombre en el Model Registry, ej. PODIUM_MODEL.

    :return: Pipeline de scikit-learn listo para predecir.
    """
    return mlflow.sklearn.load_model(f"models:/{model_name}@{CHAMPION_ALIAS}")


def get_champion_info(model_name: str) -> dict:
    """
    Obtener la versión y los metadatos de la versión champion de un modelo.

    :param model_name: Nombre en el Model Registry, ej. PODIUM_MODEL.

    :return: Diccionario con version (número de versión) y metadata (los
        datos guardados con log_model, ej. el umbral del podio).
    """
    version = MlflowClient().get_model_version_by_alias(
        model_name, CHAMPION_ALIAS
    ).version
    metadata = mlflow.models.get_model_info(
        f"models:/{model_name}@{CHAMPION_ALIAS}"
    ).metadata

    return {"version": int(version), "metadata": metadata}
