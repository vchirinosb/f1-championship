# 5. Conclusiones

## Datos

- Se trabajó con la versión 24 del dataset de Kaggle: 14 CSV con 701 433 filas que cubren las temporadas 1950 a 2024.
  Las 12 tablas relacionales se cargaron en una base de datos SQLite con claves primarias, foráneas, índices y dos
  vistas; `lap_times` y `pit_stops` se leen como CSV. La validación confirmó que cada tabla tiene las mismas filas que
  su CSV y que no hay claves foráneas inválidas.
- Repartir el dataset según su función dio a cada fuente su mejor uso: la base de datos responde con una consulta
  simple preguntas que unen varias tablas, y los CSV de detalle se agregan con Pandas sin cargarlos en ella.
- El análisis de columnas explicó cada nulo (pilotos no clasificados, sesiones de clasificación por eliminación,
  datos que se registran desde 1994, 1996 o 2011) y encontró outliers por banderas rojas y errores del dataset. Tras
  la limpieza, las 587 989 vueltas se unieron con los resultados sin ninguna fila sin correspondencia.
- El **dataset final** tiene 25 146 filas (piloto y carrera) y 39 columnas, con variables pre-carrera calculadas sin
  fuga de información, verificado con una prueba automática.

## Visualizaciones

- Cada década tuvo una escudería dominante (Lotus, McLaren, Williams, Ferrari, Mercedes, Red Bull) y Ferrari es la
  única que ganó en todas.
- El calendario nació en Europa y se extendió a Asia, Medio Oriente y América desde los años 2000.
- La posición de salida es la variable que más se relaciona con el resultado: desde 1994, quien sale desde la pole gana
  el 48.1 % de las carreras y sube al podio en el 74.8 %.

## Clustering de pilotos

- K-Means con 4 grupos sobre 251 pilotos (silueta 0.320, inercia 596.5) superó al clustering jerárquico y a GMM, y dio
  grupos interpretables: **CHAMPION** (15 pilotos, entre ellos 13 campeones del mundo), **WINNER** (93), **MIDFIELD**
  (52) y **BACKMARKER** (91).
- Los pilotos atípicos que encontró DBSCAN eran los grandes campeones, no errores: se conservaron como un grupo propio.
- La diferencia entre zona media y fondo de parrilla refleja también la época: con coches más fiables, los pilotos
  modernos abandonan mucho menos aunque no sumen puntos.

## Clasificación de podio

Resultados en el conjunto de prueba (temporadas 2022-2024), registrados en el experimento `f1-podium` de MLflow:

| Métrica | Random Forest (umbral 0.77) | Línea base (sale entre los 3 primeros) |
|---|---:|---:|
| F1 | 0.677 | 0.649 |
| Recall | 0.721 | 0.647 |
| Precisión | 0.639 | 0.650 |
| ROC-AUC | 0.938 | 0.914 |
| PR-AUC | 0.716 | 0.647 |

- El modelo supera a la línea base en todas las métricas salvo la precisión: encuentra 147 de los 204 podios, 15 más,
  a cambio de 12 falsos podios más.
- La mejora es moderada porque la posición de salida explica la mayor parte del resultado; el modelo agrega la forma
  del piloto y de la escudería y el campeonato. Los abandonos siguen siendo impredecibles con información pre-carrera.
- La partición temporal y el umbral elegido en validación dan una estimación honesta de cómo funcionaría el modelo con
  temporadas futuras.

## Asistente LLM

Resultados con 34 preguntas de respuesta conocida, registrados en el experimento `f1-llm` de MLflow:

| Estrategia | Aciertos | Exactitud | Tiempo medio |
|---|---:|---:|---:|
| Híbrida (herramientas + texto-a-SQL) | 32 de 34 | 94.1 % | 0.27 s |
| Solo texto-a-SQL | 23 de 34 | 67.6 % | 0.40 s |

- Un modelo pequeño y local (`llama3.2:3b`, 2 GB) basta si no se le piden los datos, sino que entienda la pregunta. Las
  **herramientas** son la parte más confiable: aciertan todas las preguntas de ganadores y campeones, frente al 77.8 %
  y 50 % de texto-a-SQL.
- Los errores de texto-a-SQL vienen de nombres mal escritos en la consulta (*Alonso, Fernando*) y de confundir
  conceptos (contar poles solo en las victorias, tomar como campeón al piloto con más victorias), no de datos
  inventados: el asistente responde con filas de la base o dice que no hay datos.
- El modelo no es completamente determinista: entre ejecuciones la estrategia híbrida acertó 32 o 33 preguntas, según
  si elige o no una herramienta para una pregunta abierta. Para compararlas, cada evaluación queda registrada en MLflow.
- El SQL generado es seguro: una sola sentencia `SELECT`, límite de filas y de tiempo y conexión de solo lectura. La
  pregunta que pedía borrar datos se rechazó en las dos estrategias.

## Producto final

- La API Flask y la aplicación Streamlit permiten usar todo lo anterior sin abrir un notebook: explorar cualquier
  carrera, predecir el podio de un piloto, ver su tipo de piloto y preguntar en español. Si un servicio (MLflow u
  Ollama) no está disponible, solo falla la función que lo necesita.
- MLflow dejó registradas todas las comparaciones y versionados los modelos: la API siempre carga la versión con el
  alias `champion`.

## Trabajo futuro

- Agregar herramientas para las preguntas frecuentes que hoy van a texto-a-SQL (rankings por temporada) y resolver los
  apodos también en texto-a-SQL.
- Incorporar al clasificador información de la carrera que se conozca antes de la salida, como el clima o la
  estrategia de neumáticos, que no está en el dataset.
- Actualizar el dataset con nuevas temporadas y volver a evaluar los modelos con ellas.
