# 1. Introducción

La Fórmula 1 registra desde 1950 el resultado de cada piloto en cada carrera: dónde salió, dónde llegó, cuántos puntos
sumó y por qué abandonó. Con 75 temporadas, 1125 Grandes Premios y 861 pilotos, es un buen caso para aplicar las
herramientas del curso a un problema completo: desde los archivos originales hasta una aplicación que cualquiera
puede usar.

## Objetivos

- Trabajar con **dos fuentes de datos**: una base de datos relacional (SQLite) con las tablas de catálogo y resultados,
  y archivos CSV con el detalle vuelta a vuelta y las paradas en boxes.
- **Leer, analizar, limpiar e integrar** ambas fuentes con Pandas, explicando el significado de las columnas, los nulos
  y los valores atípicos.
- **Visualizar** la historia del campeonato con Matplotlib y Bokeh.
- Construir un **dataset final** que sirva de entrada a los modelos.
- Entrenar dos modelos de machine learning y registrarlos en **MLflow**:
  - un **clustering** que agrupa a los pilotos según su perfil de desempeño;
  - un **clasificador** que estima la probabilidad de que un piloto termine en el podio con la información disponible
    antes de la carrera.
- Construir un **asistente** que responda preguntas en español, como *¿Quién ganó en Monza en 2019?*, con un modelo de
  lenguaje local (Ollama) que consulta la base de datos en lugar de responder de memoria.
- Servir los datos, los modelos y el asistente con una **API en Flask** y una **aplicación en Streamlit**.

## Alcance

El proyecto usa la versión 24 del dataset de Kaggle, que cubre las temporadas 1950 a 2024. Los 14 CSV originales se
incluyen en el repositorio (`data/raw/`) para que cualquiera obtenga exactamente los mismos resultados. Todo se ejecuta
en una computadora personal: la base de datos es un archivo SQLite, MLflow y Ollama corren como servicios locales y el
LLM es un modelo pequeño (`llama3.2:3b`, 2 GB) que no necesita una GPU dedicada.

## Organización del trabajo

El trabajo se divide en cinco notebooks de Jupyter Lab, que se ejecutan en orden:

| Notebook | Contenido |
|---|---|
| `01_construccion_bd` | Revisión del dataset, división entre base de datos y CSV, construcción y validación de la base de datos |
| `02_analisis_visualizaciones` | Lectura de ambas fuentes, análisis de columnas, limpieza, integración, visualizaciones y dataset final |
| `03_clustering` | Perfil de cada piloto y agrupamiento con K-Means, comparado con otros algoritmos |
| `04_clasificacion` | Clasificador de podio con variables pre-carrera y partición temporal |
| `05_llm` | Asistente con herramientas SQL y texto-a-SQL, evaluado con 34 preguntas |

El código que comparten los notebooks, la API y la aplicación está en `src/f1/`. Los pasos para ejecutar el proyecto
están en el [README del repositorio](https://github.com/vchirinosb/f1-championship#ejecución).

La sección [2](2-Marco-teorico) describe las tecnologías usadas, la [3](3-Descripcion-del-dataset) el dataset, la
[4](4-Pasos-realizados) los pasos realizados y las visualizaciones, la [5](5-Conclusiones) las conclusiones y la
[6](6-Bibliografia) la bibliografía.
