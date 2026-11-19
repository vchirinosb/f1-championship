"""Funciones para mostrar y exportar gráficos."""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from bokeh.io import export_png, show
from bokeh.plotting import figure
from IPython.display import Image, display
from matplotlib.figure import Figure

from f1.config import IMAGES_DIR

# False: se exporta y muestra la imagen PNG.
# True: se muestra el gráfico interactivo de Bokeh.
INTERACTIVE = False


def render(chart, name: str) -> Path | None:
    """
    Mostrar un gráfico de Bokeh o de Matplotlib y guardarlo como PNG.
    Con INTERACTIVE = True, los gráficos de Bokeh se muestran interactivos y
    no se exportan.

    :param chart: Figura de Bokeh (o gridplot) o figura de Matplotlib.
    :param name: Nombre del archivo PNG en images/, sin extensión.

    :return: Ruta del PNG generado, o None si no se exportó.
    """
    file_name = IMAGES_DIR / f"{name}.png"

    if isinstance(chart, Figure):
        chart.savefig(file_name, dpi=150, bbox_inches="tight")
        display(chart)
        # Se cierra para que Jupyter no muestre la figura una segunda vez.
        plt.close(chart)
        return file_name

    if INTERACTIVE:
        show(chart)
        return None

    # La barra de herramientas no sirve en una imagen estática.
    if hasattr(chart, "toolbar_location"):
        chart.toolbar_location = None

    # Se fuerza Playwright porque Bokeh usa Selenium por defecto.
    export_png(chart, filename=file_name, backend="playwright")
    display(Image(filename=file_name))
    return file_name


def create_histogram(values, title: str, bins: int = 40):
    """
    Crear el histograma de Bokeh de una columna numérica.
    Los valores nulos se ignoran.

    :param values: Valores de la columna (Series, lista o arreglo).
    :param title: Título del gráfico.
    :param bins: Número de barras del histograma.

    :return: Figura de Bokeh con el histograma.
    """
    values = np.asarray(values, dtype=float)
    counts, edges = np.histogram(values[~np.isnan(values)], bins=bins)
    chart = figure(title=title, width=250, height=200)
    chart.quad(
        top=counts,
        bottom=0,
        left=edges[:-1],
        right=edges[1:],
        line_color="white",
    )
    return chart
