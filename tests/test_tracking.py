"""Pruebas del registro en MLflow con un almacén temporal.

No necesitan el servidor de MLflow: usan una base SQLite en una carpeta
temporal, que también recibe los artefactos.
"""
import matplotlib.pyplot as plt
import mlflow
import pandas as pd
import pytest
from mlflow import MlflowClient
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from f1 import tracking

MODEL_NAME = "f1-test"


@pytest.fixture
def local_mlflow(tmp_path, monkeypatch):
    """
    Apuntar MLflow a una base SQLite temporal.

    :param tmp_path: Carpeta temporal de pytest.
    :param monkeypatch: Utilidad de pytest para cambiar valores.

    :return: URI del almacén temporal.
    """
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    # Los artefactos se guardan en ./mlruns de la carpeta actual.
    monkeypatch.chdir(tmp_path)
    mlflow.set_tracking_uri(uri)
    yield uri
    mlflow.set_tracking_uri(tracking.MLFLOW_TRACKING_URI)


def test_tuning_registers_best_and_moves_champion(local_mlflow):
    """
    Verificar que en la búsqueda anidada solo se registre el elegido, como
    champion.

    :param local_mlflow: URI del almacén temporal.
    """
    X = pd.DataFrame({"grid": [1, 2, 15, 18]})
    client = MlflowClient(local_mlflow)
    uris = []
    with tracking.start_run("f1-test", "tuning") as parent:
        for labels in ([1, 1, 0, 0], [0, 0, 1, 1]):
            pipeline = make_pipeline(
                SimpleImputer(), LogisticRegression()
            ).fit(X, labels)
            with tracking.start_run(nested=True):
                info = tracking.log_model(pipeline, X, {"labels": labels})
                uris.append(info.model_uri)

    assert client.search_registered_models() == []

    flavor = mlflow.models.get_model_info(uris[0]).flavors["sklearn"]
    assert flavor["serialization_format"] == "skops"

    metadata = mlflow.models.get_model_info(uris[1]).metadata
    assert metadata == {"labels": [0, 0, 1, 1]}

    with tracking.start_run(run_id=parent.info.run_id):
        figure, ax = plt.subplots()
        ax.plot([1, 2, 3])
        tracking.log_figure(figure, "line.png")

    artifacts = client.list_artifacts(parent.info.run_id)
    assert "line.png" in [item.path for item in artifacts]
    assert not plt.fignum_exists(figure.number)

    children = client.search_runs(
        [parent.info.experiment_id],
        f"tags.mlflow.parentRunId = '{parent.info.run_id}'",
    )
    assert len(children) == 2

    sample = pd.DataFrame({"grid": [1.0, None]})
    for uri, expected in zip(uris, [1, 0]):
        version = tracking.register_champion(uri, MODEL_NAME)
        champion = client.get_model_version_by_alias(
            MODEL_NAME, tracking.CHAMPION_ALIAS
        )
        assert int(champion.version) == version

        info = tracking.get_champion_info(MODEL_NAME)
        assert info == {
            "version": version,
            "metadata": {
                "labels": [expected] * 2 + [1 - expected] * 2
            }
        }

        model = tracking.load_champion(MODEL_NAME)
        assert model.predict(sample).tolist()[0] == expected
