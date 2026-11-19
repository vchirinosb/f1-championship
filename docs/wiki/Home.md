# Campeonato Mundial de Fórmula 1: análisis, modelos y asistente

- **Maestría:** Inteligencia Artificial Aplicada UCSM - UTPL
- **Curso:** Herramientas para Inteligencia Artificial
- **Repositorio:** https://github.com/vchirinosb/f1-championship

Este informe describe un proyecto de análisis de datos sobre los resultados del Campeonato Mundial de Fórmula 1 de
1950 a 2024. El proyecto combina dos fuentes de datos (una base de datos SQLite y archivos CSV), las lee e integra con
Pandas, genera visualizaciones con Matplotlib y Bokeh, entrena dos modelos de machine learning registrados en MLflow y
construye un asistente que responde preguntas en español con un LLM local. Los resultados se sirven con una API en
Flask y una aplicación en Streamlit.

## Contenido

1. [Introducción](1-Introduccion)
2. [Marco teórico](2-Marco-teorico)
3. [Descripción del dataset](3-Descripcion-del-dataset)
4. [Pasos realizados](4-Pasos-realizados)
   - [4.1. Visualizaciones generadas](4-Pasos-realizados#41-visualizaciones-generadas)
5. [Conclusiones](5-Conclusiones)
6. [Bibliografía](6-Bibliografia)

## Resultados principales

| Componente | Resultado |
|---|---|
| Base de datos | 12 tablas relacionales y 2 vistas en SQLite; 2 tablas de detalle se leen como CSV |
| Dataset final | 25 146 filas (piloto y carrera) y 39 columnas |
| Clustering de pilotos | K-Means con 4 grupos sobre 251 pilotos, silueta 0.320 |
| Clasificador de podio | Random Forest: F1 0.677 y ROC-AUC 0.938 en 2022-2024, frente a 0.649 y 0.914 de la línea base |
| Asistente LLM | `llama3.2:3b` con herramientas SQL y texto-a-SQL: 94.1 % de acierto en 34 preguntas |
