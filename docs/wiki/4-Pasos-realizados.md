# 4. Pasos realizados

El proyecto se desarrolló en cinco notebooks que se ejecutan en orden, más una API y una aplicación web que usan sus
resultados. Cada notebook explica los pasos antes del código y deja la interpretación de cada resultado con cifras
reales.

## Paso 1. Construcción de la base de datos (`01_construccion_bd`)

1. Se revisaron los 14 CSV del dataset inicial (`data/raw/`): filas, columnas y significado de cada archivo.
2. Se decidió qué tablas van a la base de datos y cuáles quedan como CSV (ver la
   [sección 3](3-Descripcion-del-dataset#qué-tablas-van-a-la-base-de-datos-y-cuáles-quedan-como-csv)).
3. `scripts/build_database.py` crea las 12 tablas con `sql/schema.sql` (claves primarias, foráneas e índices), carga
   los CSV en orden (primero los catálogos, después los resultados), crea las vistas de `sql/views.sql` y solo
   reemplaza `data/f1.db` si toda la carga es correcta. Las claves foráneas se comprueban durante la carga.
4. **Validación:** cada tabla tiene las mismas filas que su CSV y `PRAGMA foreign_key_check` no encuentra filas que
   apunten a registros inexistentes.
5. **Consultas de ejemplo** con parámetros sobre una conexión de solo lectura: *¿quién ganó en Monza en 2019?*
   (Charles Leclerc, Ferrari), los campeones de las últimas temporadas y los pilotos con más victorias.

## Paso 2. Análisis, limpieza e integración (`02_analisis_visualizaciones`)

Es el notebook principal.

1. **Lectura con Pandas** de las dos fuentes: desde la base de datos la vista `v_race_results` (26 759 resultados) y
   las tablas `qualifying` y `driver_standings`; desde los CSV `lap_times` (589 081 vueltas) y `pit_stops` (11 371
   paradas).
2. **Análisis de las columnas** de cada fuente: significado de las columnas usadas, tipos, nulos y su explicación,
   estadísticas, categorías más frecuentes e histogramas. Por ejemplo, `position` es nula cuando el piloto no fue
   clasificado (casi siempre por abandono), por eso se usa `position_order`; y hay vueltas de más de dos horas y
   paradas de 51 minutos causadas por banderas rojas.
3. **Filtrar datos confiables:** se retiraron 1 613 inscripciones de pilotos que no tomaron la salida (*Did not
   qualify*, *Withdrew*, ...); quedan 25 146 resultados.
4. **Nuevas columnas:** carrera terminada, victoria, podio, posiciones ganadas, puntos con el sistema de 2010 (para
   comparar épocas) y era reglamentaria.
5. **Eliminar outliers:** 517 paradas de más de 60 segundos y 1 092 vueltas de más del doble de la mediana de su
   carrera (banderas rojas y reparaciones).
6. **Integración CSV + base de datos:** las 587 989 vueltas que quedaron se unieron con los resultados por carrera y
   piloto, sin ninguna fila sin correspondencia. Se resumieron por piloto y carrera (mediana del tiempo por vuelta,
   diferencia de ritmo con el más rápido y paradas).
7. **Variables pre-carrera:** puntos y puesto en el campeonato, forma reciente del piloto y de la escudería, historial
   en el circuito y experiencia, calculadas con `shift(1)` para no usar el resultado de la propia carrera. Una prueba
   automática comprueba que cambiar el resultado de una carrera no cambia sus variables.
8. **Visualizaciones** (ver [4.1](#41-visualizaciones-generadas)) y exportación del **dataset final**
   (`data/final/f1_dataset_final.csv`, 25 146 filas y 39 columnas).

## Paso 3. Clustering de pilotos (`03_clustering`)

1. **Perfil de cada piloto** con al menos 20 carreras (251 pilotos): tasas de victorias, podios y abandonos, puntos por
   carrera con el sistema de 2010, posición de salida media, posiciones ganadas y temporadas.
2. **Outliers:** DBSCAN marcó como atípicos a 11 pilotos, todos campeones del mundo. No se eliminaron: son el grupo de
   los campeones.
3. **Escala logarítmica** para las temporadas y **estandarización** de las 7 variables, dentro de un `Pipeline`.
4. **Número de clusters** con el método del codo y la silueta, y **comparación** de K-Means, jerárquico (Ward) y GMM
   con k de 2 a 8. Se eligió **K-Means con 4 grupos** (silueta 0.320): mejor silueta que el jerárquico (0.297) y GMM
   (0.123) con k = 4, y grupos interpretables.
5. **Grupos:** CHAMPION (15 pilotos), WINNER (93), MIDFIELD (52) y BACKMARKER (91), nombrados según su posición de
   salida mediana.
6. **Clasificar un piloto nuevo** con el mismo `Pipeline`, y **registro en MLflow** como `f1-driver-clustering` con el
   alias `champion`.

## Paso 4. Clasificación de podio (`04_clasificacion`)

1. **Datos:** 12 270 participaciones desde 1994 (primer año con clasificación); solo el 14.1 % terminó en el podio, por
   eso se usan métricas centradas en la clase podio y no la exactitud.
2. **Variables pre-carrera:** posición de salida y de clasificación, puntos y puesto en el campeonato, forma reciente
   del piloto, en el circuito y de la escudería, experiencia y ronda.
3. **Partición temporal:** entrenamiento 1994-2018, validación 2019-2021 y prueba 2022-2024, sin carreras repetidas
   entre conjuntos.
4. **Línea base:** "si sale entre los 3 primeros, sube al podio".
5. **Modelos:** 7 combinaciones de regresión logística, Random Forest y HistGradientBoosting con clases balanceadas,
   comparadas por PR-AUC en validación. Ganó un **Random Forest** con hojas de al menos 50 pilotos (PR-AUC 0.736 frente
   a 0.677 de la línea base).
6. **Umbral** de 0.77, elegido en validación para maximizar el F1 de la clase podio.
7. **Evaluación en prueba**, una sola vez, contra la línea base; **importancia de variables** por permutación;
   **predicción** de un caso nuevo (GP de Japón 2023) y **registro en MLflow** como `f1-podium-classifier` con el
   alias `champion`, con el umbral y las variables en sus metadatos.

## Paso 5. Asistente LLM (`05_llm`)

1. **Modelo local:** `llama3.2:3b` con Ollama. El modelo no responde con lo que sabe: solo interpreta la pregunta, y los
   datos salen siempre de la base de datos.
2. **Herramientas SQL:** `race_winner`, `season_champion` y `driver_stats`, con consultas fijas y respuestas armadas con
   plantillas. Los nombres de carreras y pilotos (en español, sin tildes o con apodos como *Checo*) se resuelven con
   `rapidfuzz`.
3. **Texto-a-SQL** como respaldo para las preguntas que no encajan en ninguna herramienta, con cuatro protecciones: una
   sola sentencia `SELECT`, límite de 100 filas, límite de 5 segundos y conexión de solo lectura.
4. **Evaluación** con 34 preguntas de respuesta conocida (`data/eval/preguntas_llm.csv`) en seis categorías, comparando
   la estrategia **híbrida** (herramientas y, si no aplica ninguna, texto-a-SQL) con **solo texto-a-SQL**.
5. **Registro en MLflow** en el experimento `f1-llm`, con la exactitud global y por categoría de cada estrategia.

## Paso 6. API y aplicación web

- **API Flask** (`api/app.py`, puerto 5001): carga al iniciar los modelos `champion` de MLflow y expone las consultas a
  la base de datos, las predicciones de podio y de grupo, y el asistente. Si MLflow u Ollama no están disponibles, solo
  fallan los endpoints que los necesitan, con un mensaje que explica cómo iniciarlos.
- **Aplicación Streamlit** (`app/`, puerto 8501): páginas **Inicio** (cifras del dataset), **Explorar** (podio, tabla de
  resultados y gráfico de salida vs. llegada de cualquier carrera), **Predicciones** (probabilidad de podio de un piloto
  del dataset o con valores manuales, y su tipo de piloto) y **Asistente** (chat que muestra la consulta usada en cada
  respuesta).
- **Pruebas automáticas** (`tests/`, pytest): base de datos, variables sin fuga de información, MLflow, seguridad del
  SQL generado y endpoints de la API.

## 4.1. Visualizaciones generadas

Los gráficos se generaron en los notebooks con Matplotlib y Bokeh, y se exportaron como PNG a `images/`.

### Análisis de las columnas (notebook 02)

**Resultados de carrera.** `grid` tiene un pico en 0 (salidas desde el pit lane y pilotos que no se clasificaron),
`points` está concentrado en 0 (la mayoría no suma puntos) y `laps` tiene dos grupos: abandonos tempranos y carreras
completas de 50 a 80 vueltas.

![Histogramas de los resultados de carrera](images/hist_race_results.png)

**Clasificación.** La posición se reparte de forma uniforme entre 1 y 20; los tiempos de Q1, Q2 y Q3 se concentran entre
70 y 110 segundos según el circuito.

![Histogramas de la clasificación](images/hist_qualifying.png)

**Campeonato de pilotos.** Los puntos se concentran en valores bajos y llegan a 575 (Verstappen en 2023, el récord del
dataset).

![Histogramas del campeonato de pilotos](images/hist_driver_standings.png)

**Tiempos por vuelta** y **paradas en boxes** antes de la limpieza: los valores extremos de las banderas rojas (vueltas
de más de dos horas, paradas de 51 minutos) hacen que los tiempos se vean como una sola barra.

![Histogramas de los tiempos por vuelta](images/hist_lap_times.png)

![Histogramas de las paradas en boxes](images/hist_pit_stops.png)

**Después de eliminar outliers**, los tiempos por vuelta se concentran entre 70 y 120 segundos y las paradas entre 18 y
35 segundos.

![Histogramas de vueltas y paradas sin outliers](images/hist_clean_times.png)

### Visualizaciones de la historia del campeonato (notebook 02)

**Victorias por escudería y década (Matplotlib, base de datos).** Cada década tiene una escudería dominante: Lotus en
los 70, McLaren en los 80, Williams en los 90, Ferrari en los 2000, Mercedes en los 2010 y Red Bull en los 2020.
Ferrari es la única que ganó en todas las décadas.

![Victorias por escudería y década](images/wins_by_constructor_decade.png)

**Mapa de circuitos (Matplotlib, base de datos).** El tamaño indica los Grandes Premios corridos y el color, el año del
primero. Los circuitos más antiguos y con más carreras están en Europa (Monza, Mónaco, Silverstone, Spa); los nuevos,
en Asia, Medio Oriente y América.

![Mapa de circuitos](images/circuits_map.png)

**Evolución del campeonato 2021 (Bokeh, base de datos).** Verstappen y Hamilton se alternaron el liderato y llegaron
empatados a la última carrera; Verstappen terminó con 395.5 puntos frente a 387.5.

![Evolución del campeonato 2021](images/championship_2021.png)

**Ritmo vuelta a vuelta en Abu Dhabi 2021 (Bokeh, CSV + base de datos).** Une `lap_times.csv` con los nombres de la base
de datos. Los dos pilotos giraron alrededor de 88 segundos; los picos son las paradas y los coches de seguridad.
Verstappen cambió neumáticos con el último coche de seguridad y adelantó a Hamilton en la última vuelta.

![Ritmo vuelta a vuelta en Abu Dhabi 2021](images/pace_abu_dhabi_2021.png)

**Duración de las paradas por año (Matplotlib, CSV).** La mediana del tiempo en el pit lane se mantuvo entre 22 y 24
segundos desde 2011: depende sobre todo del largo del pit lane y del límite de velocidad.

![Duración de las paradas por año](images/pit_stop_duration_by_year.png)

**Posición de salida vs. resultado (Matplotlib, base de datos).** Desde 1994, quien sale desde la pole gana el 48.1 %
de las carreras y sube al podio en el 74.8 %; desde la quinta posición, la probabilidad de ganar baja a 2.6 %.

![Posición de salida vs. resultado](images/grid_vs_result.png)

### Clustering de pilotos (notebook 03)

**Histogramas del perfil.** Las tasas de victorias y podios están concentradas en 0 (el 59 % de los pilotos nunca
ganó); los puntos por carrera tienen una cola hacia la derecha.

![Histogramas del perfil de los pilotos](images/hist_driver_profiles.png)

**Temporadas en escala logarítmica.** La mayoría corrió pocas temporadas; `log(1 + x)` evita que los pocos con más de
15 dominen la distancia.

![Temporadas con y sin logaritmo](images/hist_seasons_log.png)

**Método del codo y silueta.** La inercia baja rápido hasta k = 3; con k = 4 la silueta es 0.320, casi igual a la de
k = 5, y los grupos son interpretables.

![Método del codo y coeficiente de silueta](images/elbow_silhouette.png)

**Cantidad de pilotos en cada grupo.**

![Pilotos por grupo](images/drivers_per_group.png)

**Grupos en las dos componentes principales (PCA).** Explican el 78.4 % de la varianza. La primera ordena a los pilotos
por rendimiento, con los 15 campeones separados del resto; la segunda separa la zona media del fondo de parrilla.

![Grupos en las componentes principales](images/clusters_pca.png)

**Tasa de abandonos vs. temporadas.** El fondo de parrilla abandona más de la mitad de las carreras y la zona media,
menos de una de cada cuatro; los campeones y ganadores tienen las carreras más largas.

![Tasa de abandonos vs. temporadas](images/clusters_dnf_seasons.png)

### Clasificación de podio (notebook 04)

**Umbral.** El F1 en validación es máximo con un umbral de 0.77.

![F1 según el umbral](images/podium_threshold.png)

**Curvas ROC y precisión-recall en prueba.** El modelo (ROC-AUC 0.938, PR-AUC 0.716) queda por encima de la línea base
(0.914 y 0.647).

![Curvas ROC y precisión-recall](images/podium_roc_pr.png)

**Matriz de confusión en prueba.** El modelo encuentra 147 de los 204 podios, 15 más que la línea base.

![Matriz de confusión](images/podium_confusion_matrix.png)

**Importancia de variables.** La posición de salida es, por mucho, la más importante; le siguen la clasificación, el
puesto en el campeonato y la forma reciente de la escudería y del piloto.

![Importancia de variables por permutación](images/podium_feature_importance.png)

### Asistente LLM (notebook 05)

**Exactitud por categoría.** La estrategia híbrida acierta todas las preguntas de ganadores y campeones; solo
texto-a-SQL falla sobre todo en estadísticas de pilotos y campeones, pero acierta las preguntas abiertas, donde la
híbrida falla una de seis.

![Exactitud del asistente por categoría](images/llm_accuracy_by_category.png)
