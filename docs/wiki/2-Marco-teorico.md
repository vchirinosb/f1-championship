# 2. Marco teórico

Esta sección describe las tecnologías y librerías usadas en el proyecto y para qué se usó cada una. Las versiones
exactas están en `requirements.txt`; todo se ejecuta con Python 3.13.

## Jupyter Lab

Jupyter Lab es el entorno web del proyecto Jupyter para trabajar con *notebooks*: documentos que mezclan celdas de
código, sus resultados (tablas y gráficos) y texto en Markdown (Kluyver et al., 2016; Project Jupyter, s. f.). Permite
ejecutar un análisis paso a paso y dejar escrita la interpretación junto a cada resultado.

**En el proyecto:** los cinco notebooks (`01` a `05`) se desarrollaron y se entregan ejecutados en Jupyter Lab, con
sus salidas visibles en GitHub. También se pueden ejecutar desde la terminal con `jupyter nbconvert`.

## Pandas

Pandas es la librería de Python para manipular datos tabulares (McKinney, 2010; pandas development team, s. f.). Su
estructura central, el `DataFrame`, es una tabla con columnas de distinto tipo sobre la que se filtra, agrupa, une y
resume. Se apoya en **NumPy**, la librería de arreglos numéricos de Python (NumPy Developers, s. f.).

**En el proyecto:** lee las dos fuentes de datos (`pd.read_sql` para la base de datos y `pd.read_csv` para los CSV),
analiza las columnas (`dtypes`, `isna`, `describe`, `value_counts`), limpia los datos, une los tiempos por vuelta con
los resultados (`merge`) y calcula las variables de los modelos con operaciones por grupo (`groupby`, `shift`,
`rolling`).

## SQLite y SQL

SQL (*Structured Query Language*) es el lenguaje estándar para definir y consultar bases de datos relacionales, donde
los datos se guardan en tablas relacionadas por **claves primarias** (identifican cada fila) y **claves foráneas**
(apuntan a una fila de otra tabla). Una **vista** es una consulta guardada que se usa como si fuera una tabla.

SQLite es un motor de base de datos relacional que no necesita servidor: toda la base de datos es un único archivo
(SQLite, s. f.). Es adecuado para un volumen como el de este proyecto y se puede versionar en GitHub junto con el
código.

**En el proyecto:** `sql/schema.sql` crea las 12 tablas con sus claves e índices, `sql/views.sql` define las vistas
`v_race_results` y `v_race_winners`, y `sql/queries.sql` reúne consultas de ejemplo. El script
`scripts/build_database.py` construye `data/f1.db` a partir de los CSV.

## SQLAlchemy

SQLAlchemy es la librería de Python para trabajar con bases de datos relacionales. Ofrece un *engine* que administra
las conexiones y permite ejecutar SQL con parámetros, de modo que los valores nunca se concatenan en el texto de la
consulta (SQLAlchemy, s. f.).

**En el proyecto:** `src/f1/db.py` crea un *engine* de **solo lectura** sobre `data/f1.db`. Lo usan los notebooks, la
API y el asistente LLM: ninguno puede modificar la base de datos, ni siquiera con una consulta generada por el modelo.

## Matplotlib

Matplotlib es la librería de gráficos estáticos más usada en Python (Hunter, 2007). Permite controlar cada elemento de
la figura (ejes, colores, anotaciones) y exportarla como imagen (Matplotlib Development Team, s. f.).

**En el proyecto:** gráficos para el informe como las victorias por escudería y década, el mapa de circuitos, la
duración de las paradas por año, la probabilidad de victoria según la posición de salida, la matriz de confusión y las
curvas ROC y precisión-recall del clasificador.

## Bokeh

Bokeh es una librería de gráficos **interactivos** para el navegador: permite acercar, desplazarse y ver el detalle de
cada punto al pasar el cursor (`HoverTool`) (Bokeh Development Team, s. f.). Con **Playwright**, que controla un
navegador sin interfaz, los gráficos se exportan como PNG (Microsoft, s. f.).

**En el proyecto:** histogramas, la evolución del campeonato 2021, el ritmo vuelta a vuelta de Abu Dhabi 2021 y los
gráficos de los grupos del clustering. La función `render` de `src/f1/plots.py` muestra el gráfico y lo guarda en
`images/`: con `INTERACTIVE = False` muestra el PNG, visible en GitHub y en esta wiki.

## scikit-learn

scikit-learn es la librería de machine learning de Python (Pedregosa et al., 2011; scikit-learn developers, s. f.).
Ofrece algoritmos de clasificación, regresión y clustering con una interfaz común (`fit`, `predict`) y herramientas de
preprocesamiento, métricas y `Pipeline` (una cadena de transformaciones y un modelo que se entrena y aplica como una
sola pieza).

**En el proyecto:**

- **Clustering:** K-Means agrupa a los pilotos asignando cada uno al centro más cercano. Se comparó con el clustering
  jerárquico (Ward) y con un modelo de mezcla gaussiana (GMM). El número de grupos se eligió con el **método del codo**
  (inercia) y el **coeficiente de silueta**, que mide de -1 a 1 qué tan separado está cada punto de los otros grupos
  (Rousseeuw, 1987). DBSCAN se usó para buscar pilotos atípicos.
- **Clasificación:** regresión logística, Random Forest (muchos árboles de decisión entrenados con muestras distintas;
  Breiman, 2001) y HistGradientBoosting, evaluados con ROC-AUC, PR-AUC, F1, recall y precisión, y con la importancia de
  variables por permutación.
- **Preprocesamiento:** imputación de nulos (`SimpleImputer`), estandarización (`StandardScaler`) y escala logarítmica,
  siempre dentro de un `Pipeline`.

Los modelos se guardan con **skops**, un formato para modelos de scikit-learn que se puede inspeccionar antes de
cargarlo (skops developers, s. f.).

## MLflow

MLflow es una plataforma de código abierto para gestionar el ciclo de vida de los modelos de machine learning (MLflow
Project, s. f.; Zaharia et al., 2018). Registra cada **ejecución** (*run*) con sus parámetros, métricas y archivos,
permite agrupar ejecuciones en **experimentos** y compararlas en una interfaz web, y tiene un **Model Registry** que
versiona los modelos y les asigna **alias** (por ejemplo, `champion` para la versión en uso).

**En el proyecto:** un servidor local (puerto 9090) guarda tres experimentos: `f1-clustering`, `f1-podium` y `f1-llm`.
Cada comparación se registra como una ejecución padre con una ejecución hija por algoritmo o combinación. Los modelos
elegidos se registran como `f1-driver-clustering` y `f1-podium-classifier` con el alias `champion`, que es la versión
que carga la API.

## Flask

Flask es un *microframework* web para Python: con pocas líneas se define una aplicación y las rutas que responden a
cada URL (Pallets, s. f.). Es adecuado para construir APIs REST que devuelven JSON.

**En el proyecto:** `api/app.py` expone las consultas a la base de datos, las predicciones de los modelos de MLflow y
el asistente LLM en el puerto 5001 (`/health`, `/races`, `/winner`, `/drivers/<ref>/cluster`, `/predict/podium`,
`/ask`). Valida los parámetros y responde los errores en JSON con mensajes en español.

## Streamlit

Streamlit es un framework para construir aplicaciones web de datos escribiendo solo Python: cada script se convierte
en una página con controles (selectores, botones, formularios), tablas, gráficos y chat (Streamlit, s. f.).

**En el proyecto:** `app/` tiene una aplicación con cuatro páginas (Inicio, Explorar, Predicciones y Asistente) en el
puerto 8501. Consume la API con `requests`; nunca lee la base de datos ni los modelos directamente.

## Ollama

Ollama ejecuta modelos de lenguaje (LLM) en la propia computadora y los expone en una API local (puerto 11434), sin
enviar los datos a un servicio externo (Ollama, s. f.-a). Admite *tool calling*: el modelo recibe una lista de funciones
y responde cuál llamar y con qué parámetros.

**En el proyecto:** el asistente usa `llama3.2:3b`, un modelo de 3 200 millones de parámetros cuantizado a 4 bits
(2 GB) (Ollama, s. f.-b), con dos estrategias:

- **Herramientas SQL:** el modelo solo elige una función con una consulta fija (`race_winner`, `season_champion`,
  `driver_stats`) y extrae sus parámetros; la respuesta se arma con una plantilla, así que no puede contener datos
  inventados. Los nombres de pilotos y carreras se resuelven con **rapidfuzz**, que compara textos de forma aproximada
  (RapidFuzz, s. f.).
- **Texto-a-SQL:** para las preguntas que no encajan en ninguna herramienta, el modelo escribe la consulta SQL a partir
  del esquema de las vistas y de ejemplos. La consulta se valida (una sola sentencia `SELECT`) y se ejecuta con límite
  de filas y de tiempo sobre la conexión de solo lectura.

## Otras herramientas

- **requests:** cliente HTTP con el que Streamlit consume la API (Requests, s. f.).
- **pytest:** pruebas automáticas de la base de datos, las variables, MLflow, el asistente y la API (`tests/`)
  (pytest-dev, s. f.).
- **Git y GitHub:** control de versiones del código, los datos y esta wiki.
