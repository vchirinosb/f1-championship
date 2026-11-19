"""Página Asistente: chat con el asistente LLM.

El historial se guarda en st.session_state y dura lo que dura la sesión
del navegador. Bajo cada respuesta se puede desplegar la consulta usada.
"""

import pandas as pd
import streamlit as st

import api_client

EXAMPLES = [
    "¿Quién ganó en Silverstone en 2020?",
    "¿Quién fue campeón del mundo en 2008?",
    "¿Cuántas victorias tiene Checo Pérez?",
    "¿Qué escudería ganó más carreras en 2014?",
]


def describe_strategy(strategy: str) -> str:
    """
    Describir en español cómo se obtuvo la respuesta.

    :param strategy: 'tool:<nombre>' o 'sql'.

    :return: ej. 'Herramienta race_winner'.
    """
    if strategy.startswith("tool:"):
        return f"Herramienta {strategy.removeprefix('tool:')}"
    return "Texto-a-SQL (consulta generada por el modelo)"


def show_message(message: dict) -> None:
    """
    Mostrar un mensaje del historial.

    :param message: {'role', 'content'} y, en las respuestas, 'error' o
        'strategy', 'sql' y 'data'.
    """
    with st.chat_message(message["role"]):
        if message.get("error"):
            st.error(message["content"])
            return
        st.markdown(message["content"])
        if message.get("sql"):
            with st.expander("Consulta usada"):
                st.caption(describe_strategy(message["strategy"]))
                st.code(message["sql"], language="sql")
                if message["data"]:
                    st.dataframe(pd.DataFrame(message["data"]),
                                 hide_index=True)


def answer(question: str) -> dict:
    """Preguntar a la API y armar el mensaje de respuesta.

    :param question: pregunta del usuario.
    :return: mensaje del asistente para el historial.
    """
    try:
        body = api_client.ask(question)
    except api_client.ApiError as error:
        return {"role": "assistant", "content": str(error), "error": True}
    return {"role": "assistant", "content": body["text"],
            "strategy": body["strategy"], "sql": body["sql"],
            "data": body["data"]}


st.title("Asistente")
st.caption("Responde en español con el modelo local llama3.2:3b (Ollama). "
           "Los datos salen siempre de la base de datos del proyecto.")
if api_client.is_unavailable("llm"):
    st.warning("Ollama no está disponible. Inícielo con 'ollama serve' "
               "para usar el asistente.")

messages = st.session_state.setdefault("messages", [])

st.markdown("**Preguntas de ejemplo**")
clicked = None
columns = st.columns(2)
for index, example in enumerate(EXAMPLES):
    if columns[index % 2].button(example, width="stretch"):
        clicked = example
if messages and st.button("Borrar conversación", icon=":material/delete:"):
    messages.clear()

for message in messages:
    show_message(message)

question = st.chat_input("Escribe una pregunta sobre la F1") or clicked
if question:
    messages.append({"role": "user", "content": question})
    show_message(messages[-1])
    with st.spinner("Consultando..."):
        messages.append(answer(question))
    show_message(messages[-1])
