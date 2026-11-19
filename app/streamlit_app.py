"""
Aplicación Streamlit del proyecto F1.
Cada página está en views/ y consume la API con api_client.
"""
import streamlit as st

import api_client

SERVICES = {
    "database": "Base de datos",
    "mlflow": "MLflow (modelos)",
    "llm": "Ollama (asistente)",
}
MODELS = {
    "podium": "Clasificador de podio",
    "clustering": "Clustering de pilotos"
}


def show_sidebar() -> None:
    """Mostrar el estado de los servicios y las versiones de los modelos."""
    st.sidebar.title("Campeonato Mundial de F1")
    try:
        status = api_client.get_health()
    except api_client.ApiError as error:
        st.sidebar.error(str(error))
        return

    st.sidebar.subheader("Servicios")
    for key, label in SERVICES.items():
        if status[key] == "ok":
            st.sidebar.markdown(f":green[●] {label}: disponible")
        else:
            st.sidebar.markdown(f":red[●] {label}: no disponible")

    st.sidebar.subheader("Modelos champion")
    for key, label in MODELS.items():
        version = status["models"][key]
        st.sidebar.markdown(
            f"{label}: **v{version}**" if version else f"{label}: no cargado"
        )

    st.sidebar.caption(f"API: {api_client.API_URL}")


st.set_page_config(
    page_title="Campeonato Mundial de F1",
    page_icon=":material/sports_motorsports:", layout="wide"
)
page = st.navigation(
    [
        st.Page(
            "views/home.py", title="Inicio", icon=":material/home:",
            default=True
        ),
        st.Page(
            "views/explore.py", title="Explorar",
            icon=":material/table_chart:"
        ),
        st.Page(
            "views/predictions.py", title="Predicciones",
            icon=":material/insights:"
        ),
        st.Page(
            "views/assistant.py", title="Asistente", icon=":material/chat:"
        ),
    ]
)
show_sidebar()
page.run()
