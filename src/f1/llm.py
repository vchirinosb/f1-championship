"""
Asistente que responde preguntas sobre la F1 con un LLM local (Ollama).

La base de datos es la única fuente de los datos. Estrategias:

1. Herramientas: el modelo elige una función parametrizada (ganador de una
   carrera, campeón de una temporada, estadísticas de un piloto) y extrae sus
   parámetros. La función consulta la base de datos y arma la respuesta con una
   plantilla.
2. Texto-a-SQL: si ninguna herramienta aplica, el modelo escribe una consulta
   SELECT sobre las vistas, que se valida y se ejecuta en modo de solo lectura,
   con límite de filas y de tiempo. El modelo redacta la respuesta solo con las
   filas devueltas.
"""
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from functools import cache

import httpx
import ollama
import pandas as pd
from rapidfuzz import fuzz, process
from sqlalchemy import text

from f1.config import OLLAMA_HOST, OLLAMA_MODEL
from f1.db import get_engine, query

# Límites del SQL generado por el modelo.
MAX_ROWS = 100
SQL_TIMEOUT_SECONDS = 5

# Puntaje mínimo (0-100) para aceptar un nombre aproximado.
MIN_NAME_SCORE = 85

# Nombre en español de cada Gran Premio del dataset.
RACE_NAMES_ES = {
    "70th Anniversary Grand Prix": ["70 aniversario", "70.º aniversario"],
    "Abu Dhabi Grand Prix": ["abu dabi"],
    "Argentine Grand Prix": ["argentina"],
    "Australian Grand Prix": ["australia"],
    "Austrian Grand Prix": ["austria"],
    "Azerbaijan Grand Prix": ["azerbaiyan", "bakú"],
    "Bahrain Grand Prix": ["barein", "bahrein"],
    "Belgian Grand Prix": ["belgica"],
    "Brazilian Grand Prix": ["brasil"],
    "British Grand Prix": ["gran bretaña", "inglaterra", "reino unido"],
    "Canadian Grand Prix": ["canada"],
    "Chinese Grand Prix": ["china"],
    "Dutch Grand Prix": ["paises bajos", "holanda"],
    "Emilia Romagna Grand Prix": ["emilia-romaña", "emilia romaña"],
    "European Grand Prix": ["europa"],
    "French Grand Prix": ["francia"],
    "German Grand Prix": ["alemania"],
    "Hungarian Grand Prix": ["hungria"],
    "Indian Grand Prix": ["india"],
    "Indianapolis 500": ["500 millas de indianapolis"],
    "Italian Grand Prix": ["italia"],
    "Japanese Grand Prix": ["japon"],
    "Korean Grand Prix": ["corea"],
    "Luxembourg Grand Prix": ["luxemburgo"],
    "Malaysian Grand Prix": ["malasia"],
    "Mexican Grand Prix": ["mexico"],
    "Mexico City Grand Prix": ["ciudad de mexico"],
    "Moroccan Grand Prix": ["marruecos"],
    "Pacific Grand Prix": ["pacifico"],
    "Portuguese Grand Prix": ["portugal"],
    "Qatar Grand Prix": ["catar"],
    "Russian Grand Prix": ["rusia"],
    "Saudi Arabian Grand Prix": ["arabia saudita", "arabia saudi"],
    "Singapore Grand Prix": ["singapur"],
    "South African Grand Prix": ["sudafrica"],
    "Spanish Grand Prix": ["españa"],
    "Styrian Grand Prix": ["estiria"],
    "Swedish Grand Prix": ["suecia"],
    "Swiss Grand Prix": ["suiza"],
    "Turkish Grand Prix": ["turquia"],
    "Tuscan Grand Prix": ["toscana"],
    "United States Grand Prix": ["estados unidos", "eeuu"],
}

# Apodos de pilotos que no se parecen a su nombre.
DRIVER_NICKNAMES = {
    "checo": "perez",
    "schumi": "michael_schumacher",
    "el nano": "alonso",
    "el kaiser": "michael_schumacher",
}

# Prefijos que no ayudan a reconocer una carrera.
RACE_PREFIXES = r"^(el |la )?(gran premio|grand prix|gp)( de| del)? "


class LLMUnavailableError(RuntimeError):
    """Ollama no está en ejecución o el modelo no está descargado."""
    pass


class UnsafeSQLError(ValueError):
    """El SQL generado no es una única sentencia de lectura."""
    pass


@dataclass
class Answer:
    """
    Respuesta del asistente.

    :param text: Respuesta en español.
    :param strategy: 'tool:<nombre>' o 'sql'.
    :param sql: Consulta ejecutada, con sus parámetros.
    :param data: Filas devueltas por la consulta.
    """

    text: str
    strategy: str
    sql: str
    data: list[dict] = field(default_factory=list)


def normalize(value: str) -> str:
    """
    Pasar un nombre a minúsculas, sin tildes ni signos de puntuación.

    :param value: Texto original, ej. 'Gran Premio de Japón'.

    :return: Texto normalizado, ej. 'gran premio de japon'.
    """
    value = unicodedata.normalize("NFKD", value.lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9 ]", " ", value.replace("_", " "))

    return re.sub(r"\s+", " ", value).strip()


def _build_race_key(value: str) -> str:
    """
    Normalizar el nombre de una carrera y quitar 'gran premio de' o 'gp'.

    :param value: Nombre de carrera o circuito.

    :return: Nombre normalizado sin prefijo ni 'grand prix'.
    """
    value = re.sub(RACE_PREFIXES, "", normalize(value))
    return re.sub(r" (grand prix|gp)$", "", value).strip()


@cache
def _list_race_aliases() -> dict[str, tuple[str, str]]:
    """
    Listar los nombres con los que se puede pedir una carrera.
    Cada nombre normalizado apunta a un filtro (columna, valor): el nombre
    de la carrera ('GP de Italia') o el circuito ('Monza').

    :return: Diccionario nombre -> (columna de v_race_results, valor).
    """
    aliases = {}
    circuits = query(
        "SELECT DISTINCT circuit_ref, circuit_name, location "
        "FROM v_race_results"
    )

    for row in circuits.itertuples():
        for name in (row.circuit_ref, row.circuit_name, row.location):
            aliases[_build_race_key(name)] = ("circuit_ref", row.circuit_ref)

    # Los nombres de carrera se agregan después y tienen prioridad.
    for race in query("SELECT DISTINCT race_name FROM v_race_results")[
        "race_name"
    ]:
        for name in [race, *RACE_NAMES_ES.get(race, [])]:
            aliases[_build_race_key(name)] = ("race_name", race)

    return aliases


def resolve_race(name: str) -> tuple[str, str] | None:
    """
    Reconocer una carrera o un circuito escrito de forma aproximada.

    :param name: Ej. 'GP de Italia', 'Gran Premio de Japón' o 'Monza'.

    :return: Filtro (columna, valor), ej. ('race_name', 'Italian Grand Prix'), o
        None si no se reconoce.
    """
    aliases = _list_race_aliases()
    match = process.extractOne(
        _build_race_key(name), aliases.keys(), scorer=fuzz.token_sort_ratio,
        score_cutoff=MIN_NAME_SCORE,
    )

    return aliases[match[0]] if match else None


@cache
def _load_drivers() -> pd.DataFrame:
    """
    Leer los pilotos con su nombre normalizado y número de carreras.

    :return: Una fila por piloto.
    """
    drivers = query(
        "SELECT driver_ref, driver_name, COUNT(*) AS races "
        "FROM v_race_results GROUP BY driver_ref, driver_name"
    )
    drivers["full"] = drivers["driver_name"].map(normalize)
    drivers["surname"] = drivers["full"].str.split().str[-1]
    drivers["ref"] = drivers["driver_ref"].map(normalize)

    return drivers


def resolve_driver(name: str) -> str | None:
    """
    Reconocer un piloto escrito de forma aproximada o con su apodo.
    Si varios pilotos se parecen igual (ej. 'Schumacher'), se elige el que
    corrió más carreras.

    :param name: Ej. 'Hamilton', 'Checo Pérez' o 'Michael Schumacher'.

    :return: Driver_ref del piloto, o None si no se reconoce.
    """
    key = normalize(name)
    for nickname, ref in DRIVER_NICKNAMES.items():
        if nickname in key.split() or key == nickname:
            return ref

    drivers = _load_drivers()
    choices = {}
    for row in drivers.itertuples():
        for alias in (row.full, row.surname, row.ref):
            choices.setdefault(alias, set()).add(row.Index)

    matches = process.extract(
        key, choices.keys(), scorer=fuzz.token_sort_ratio, limit=10,
        score_cutoff=MIN_NAME_SCORE,
    )
    if not matches:
        return None

    best = max(score for _, score, _ in matches)
    candidates = set().union(
        *(choices[alias] for alias, score, _ in matches if score == best)
    )

    return drivers.loc[list(candidates)].nlargest(1, "races")[
        "driver_ref"
    ].iloc[0]


def _format_sql(sql: str, params: dict) -> str:
    """
    Mostrar una consulta con sus parámetros.

    :param sql: Consulta con parámetros ':nombre'.
    :param params: Valores de los parámetros.

    :return: Consulta y parámetros en una cadena.
    """
    return f"{' '.join(sql.split())}  -- {params}"


def get_race_winner(race: str, year: int) -> Answer:
    """
    Buscar el ganador de una carrera; si hubo varias en el circuito, el de
    todas.

    :param race: Carrera o circuito, ej. 'GP de Italia' o 'Silverstone'.
    :param year: Temporada, ej. 2019.

    :return: Respuesta con piloto, escudería y carrera.
    """
    target = resolve_race(race)
    sql, rows = "", pd.DataFrame()
    if target is not None:
        column, value = target
        template = (
            "SELECT race_name, race_date, circuit_name, driver_name, "
            "constructor_name FROM v_race_winners "
            f"WHERE {column} = :value AND year = :year ORDER BY race_date"
        )
        params = {"value": value, "year": int(year)}
        rows = query(template, **params)
        sql = _format_sql(template, params)

    if rows.empty:
        return Answer(
            f"No hay datos de {race} en {year} en el dataset.",
            "tool:race_winner", sql,
        )

    parts = [
        f"{row.driver_name} ({row.constructor_name}) ganó el "
        f"{row.race_name} del {row.race_date}"
        for row in rows.itertuples()
    ]
    return Answer(
        "; ".join(parts) + ".", "tool:race_winner", sql,
        rows.to_dict("records"),
    )


def get_season_champion(year: int) -> Answer:
    """
    Buscar el campeón de pilotos de una temporada.

    :param year: Temporada, ej. 2008.

    :return: Respuesta con piloto, puntos y victorias.
    """
    sql = (
        "SELECT ra.year, d.forename || ' ' || d.surname AS driver_name, "
        "ds.points, ds.wins FROM driver_standings AS ds "
        "JOIN races AS ra ON ra.race_id = ds.race_id "
        "JOIN drivers AS d ON d.driver_id = ds.driver_id "
        "WHERE ra.year = :year AND ds.position = 1 "
        "ORDER BY ra.round DESC LIMIT 1"
    )
    params = {"year": int(year)}
    rows = query(sql, **params)
    if rows.empty:
        return Answer(
            f"No hay datos de la temporada {year} en el dataset.",
            "tool:season_champion",
            _format_sql(sql, params),
        )

    row = rows.iloc[0]
    return Answer(
        f"{row.driver_name} fue campeón del mundo de {year} con "
        f"{row.points:g} puntos y {row.wins} victorias.",
        "tool:season_champion", _format_sql(sql, params),
        rows.to_dict("records"),
    )


def get_driver_stats(driver: str) -> Answer:
    """
    Calcular las estadísticas de la carrera deportiva de un piloto.
    Las poles se cuentan como salidas desde el primer lugar (grid = 1) y los
    abandonos como carreras sin ver la bandera a cuadros.

    :param driver: Piloto, ej. 'Hamilton' o 'Checo Pérez'.

    :return: Respuesta con carreras, victorias, podios, poles, abandonos y
        títulos.
    """
    ref = resolve_driver(driver)
    if ref is None:
        return Answer(
            f"No hay datos del piloto {driver} en el dataset.",
            "tool:driver_stats", "",
        )

    sql = (
        "SELECT driver_name, COUNT(*) AS races, "
        "MIN(year) AS first_year, MAX(year) AS last_year, "
        "SUM(position_order = 1) AS wins, "
        "SUM(position_order <= 3) AS podiums, SUM(grid = 1) AS poles, "
        "SUM(status <> 'Finished' AND status NOT LIKE '+%Lap%') AS dnfs, "
        "(SELECT COUNT(*) FROM driver_standings AS ds "
        " JOIN races AS ra ON ra.race_id = ds.race_id "
        " JOIN drivers AS d ON d.driver_id = ds.driver_id "
        " WHERE d.driver_ref = :ref AND ds.position = 1 AND ra.round = "
        " (SELECT MAX(round) FROM races WHERE year = ra.year)) AS titles "
        "FROM v_race_results WHERE driver_ref = :ref"
    )
    params = {"ref": ref}
    row = query(sql, **params).iloc[0]

    return Answer(
        f"{row.driver_name} corrió {row.races} carreras entre "
        f"{row.first_year} y {row.last_year}: {row.wins} victorias, "
        f"{row.podiums} podios, {row.poles} poles, {row.dnfs} abandonos y "
        f"{row.titles} títulos mundiales.",
        "tool:driver_stats", _format_sql(sql, params), [row.to_dict()],
    )


TOOLS = {
    "race_winner": get_race_winner,
    "season_champion": get_season_champion,
    "driver_stats": get_driver_stats,
}

# Descripción de las herramientas para el modelo.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "race_winner",
            "description": "Ganador de una carrera de un año. Úsala para "
            "'¿quién ganó en X en AÑO?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "race": {
                        "type": "string",
                        "description": "Carrera o circuito tal como lo "
                        "escribe el usuario, ej. 'GP de Italia', "
                        "'Monza' o 'Silverstone'",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Temporada, ej. 2019"
                    },
                },
                "required": ["race", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "season_champion",
            "description": "Campeón del mundo de pilotos de una temporada",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "Temporada, ej. 2008"
                    },
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "driver_stats",
            "description": "Total de carreras, victorias, podios, poles, "
            "abandonos y títulos de toda la carrera de un piloto",
            "parameters": {
                "type": "object",
                "properties": {
                    "driver": {
                        "type": "string",
                        "description": "Nombre del piloto"
                    },
                },
                "required": ["driver"],
            },
        },
    },
]

TOOLS_PROMPT = """Eres un asistente de Fórmula 1. Si la pregunta se responde \
con una de las herramientas, llama a esa herramienta con los parámetros tal \
como aparecen en la pregunta. Si ninguna herramienta responde exactamente la \
pregunta (ej. preguntas sobre escuderías, conteos de una temporada o \
comparaciones), responde solo con la palabra NINGUNA."""


SQL_PROMPT = """Escribe una consulta SQLite que responda la pregunta. \
Responde solo con JSON: {"sql": "SELECT ..."}.

Vistas disponibles (una fila por piloto y carrera):
v_race_results(race_id, year, round, race_name, race_date, circuit_ref, \
circuit_name, location, country, driver_ref, driver_name, \
driver_nationality, constructor_ref, constructor_name, grid, position, \
position_order, points, laps, status)
v_race_winners(race_id, year, round, race_name, race_date, circuit_ref, \
circuit_name, country, driver_ref, driver_name, constructor_ref, \
constructor_name, grid)

Reglas:
- Una sola sentencia SELECT, sin punto y coma.
- Los nombres de carreras están en inglés: 'Italian Grand Prix', \
'British Grand Prix'. Usa LIKE para nombres: driver_name LIKE '%Senna%'.
- position_order = 1 es la victoria; position_order <= 3 es el podio; \
grid = 1 es la pole.
- Terminó la carrera si status = 'Finished' o status LIKE '+%Lap%'.

Ejemplos:
P: ¿Cuántas carreras ganó Ferrari en 2004?
{"sql": "SELECT COUNT(*) AS wins FROM v_race_winners WHERE \
constructor_name = 'Ferrari' AND year = 2004"}
P: ¿Qué escudería ganó más carreras en 2014?
{"sql": "SELECT constructor_name, COUNT(*) AS wins FROM v_race_winners \
WHERE year = 2014 GROUP BY constructor_name ORDER BY wins DESC LIMIT 1"}
P: ¿Cuántas carreras se disputaron en 1990?
{"sql": "SELECT COUNT(DISTINCT race_id) AS races FROM v_race_results \
WHERE year = 1990"}
P: ¿Quién ganó más veces el GP de Mónaco?
{"sql": "SELECT driver_name, COUNT(*) AS wins FROM v_race_winners WHERE \
race_name = 'Monaco Grand Prix' GROUP BY driver_name ORDER BY wins DESC \
LIMIT 1"}
P: ¿En qué circuito ganó más veces Alain Prost?
{"sql": "SELECT circuit_name, COUNT(*) AS wins FROM v_race_winners WHERE \
driver_name LIKE '%Prost%' GROUP BY circuit_name ORDER BY wins DESC \
LIMIT 1"}
P: ¿Cuántos pilotos españoles corrieron en 2005?
{"sql": "SELECT COUNT(DISTINCT driver_ref) AS drivers FROM v_race_results \
WHERE driver_nationality = 'Spanish' AND year = 2005"}"""

ANSWER_PROMPT = """Responde la pregunta en español, en una o dos frases, \
usando solo los datos de la consulta. No agregues información que no esté \
en los datos."""

def validate_sql(sql: str) -> str:
    """
    Comprobar que el SQL sea una única sentencia de lectura.

    :param sql: Consulta generada por el modelo.

    :return: Consulta envuelta en un SELECT con LIMIT MAX_ROWS.
    """
    sql = sql.strip().rstrip(";").strip()
    if ";" in sql:
        raise UnsafeSQLError("Solo se permite una sentencia SQL.")
    if not re.match(r"^(select|with)\b", sql, re.IGNORECASE):
        raise UnsafeSQLError("Solo se permiten consultas SELECT.")

    return f"SELECT * FROM ({sql}) LIMIT {MAX_ROWS}"


def run_sql(sql: str) -> pd.DataFrame:
    """
    Ejecutar de forma segura el SQL generado por el modelo.
    La conexión es de solo lectura y la consulta se interrumpe si tarda más de
    SQL_TIMEOUT_SECONDS.

    :param sql: Consulta generada por el modelo.

    :return: Hasta MAX_ROWS filas.
    """
    limited = validate_sql(sql)
    deadline = time.monotonic() + SQL_TIMEOUT_SECONDS
    with get_engine().connect() as connection:
        sqlite = connection.connection.driver_connection
        # Se llama cada 10 000 instrucciones; devolver True la interrumpe
        sqlite.set_progress_handler(
            lambda: time.monotonic() > deadline, 10_000
        )
        try:
            return pd.read_sql(text(limited), connection)
        except Exception as error:
            if "interrupted" in str(error):
                raise TimeoutError(
                    f"La consulta superó {SQL_TIMEOUT_SECONDS} segundos."
                ) from error
            raise
        finally:
            sqlite.set_progress_handler(None, 0)


def _chat(**kwargs) -> ollama.ChatResponse:
    """
    Llamar al modelo de Ollama con temperatura 0.

    :param kwargs: Argumentos de ollama.Client.chat (messages, tools,
        format...).

    :return: Respuesta del modelo.
    """
    client = ollama.Client(host=OLLAMA_HOST)
    try:
        return client.chat(
            model=OLLAMA_MODEL, options={"temperature": 0}, **kwargs
        )
    except (ConnectionError, httpx.HTTPError) as error:
        raise LLMUnavailableError(
            f"No se pudo conectar con Ollama en {OLLAMA_HOST}. Inícielo con "
            "'ollama serve' (o abriendo la aplicación de Ollama)."
        ) from error
    except ollama.ResponseError as error:
        if error.status_code == 404:
            raise LLMUnavailableError(
                f"El modelo {OLLAMA_MODEL} no está descargado. Descárguelo "
                f"con 'ollama pull {OLLAMA_MODEL}'."
            ) from error
        raise


def _check_arguments(arguments: dict) -> bool:
    """
    Comprobar que el modelo extrajo parámetros utilizables.
    Un modelo pequeño a veces llama a una herramienta que no corresponde,
    ej. race_winner(race='Lewis Hamilton', year=None). En ese caso la
    pregunta se responde con texto-a-SQL. Un año que no es número se
    detecta después, al convertirlo con int() dentro de la herramienta.

    :param arguments: Parámetros de la llamada a la herramienta.

    :return: True si no falta ningún valor y la carrera o el piloto se
        reconocen.
    """
    if any(value in (None, "") for value in arguments.values()):
        return False
    if "race" in arguments and resolve_race(arguments["race"]) is None:
        return False
    if "driver" in arguments and resolve_driver(arguments["driver"]) is None:
        return False

    return True


def _ask_with_tools(question: str) -> Answer | None:
    """
    Intentar responder con una herramienta parametrizada.

    :param question: Pregunta del usuario.

    :return: Respuesta de la herramienta, o None si ninguna aplica.
    """
    response = _chat(
        messages=[
            {"role": "system", "content": TOOLS_PROMPT},
            {"role": "user", "content": question}
        ],
        tools=TOOL_SCHEMAS,
    )
    for call in response.message.tool_calls or []:
        tool = TOOLS.get(call.function.name)
        arguments = call.function.arguments
        if tool is None or not _check_arguments(arguments):
            continue
        try:
            return tool(**arguments)
        except (TypeError, ValueError):
            # Parámetros de otro tipo: se prueba con SQL
            return None
    return None


def _ask_with_sql(question: str) -> Answer:
    """
    Responder generando SQL, con un reintento si la consulta falla.

    :param question: Pregunta del usuario.

    :return: Respuesta redactada solo con las filas devueltas.
    """
    messages = [
        {"role": "system", "content": SQL_PROMPT},
        {"role": "user", "content": question}
    ]
    sql = ""
    for _ in range(2):
        response = _chat(messages=messages, format="json")
        try:
            sql = json.loads(response.message.content)["sql"]
            rows = run_sql(sql)
            break
        except UnsafeSQLError as unsafe:
            return Answer(
                f"No puedo ejecutar esa consulta: {unsafe}",
                "sql", sql,
            )
        except Exception as failure:  # SQL inválido o JSON mal formado
            messages += [
                {"role": "assistant", "content": response.message.content},
                {"role": "user",
                 "content": f"La consulta falló: {failure}. Corrígela."},
            ]
    else:
        return Answer("No pude responder la pregunta.", "sql", sql)

    if rows.empty:
        return Answer(
            "No hay datos para esa pregunta en el dataset.",
            "sql", sql,
        )
    data = rows.head(20).to_dict("records")
    response = _chat(
        messages=[
            {"role": "system", "content": ANSWER_PROMPT},
            {"role": "user", "content": f"Pregunta: {question}\n"
             f"Datos: {json.dumps(data, ensure_ascii=False, default=str)}"},
        ]
    )

    return Answer(
        response.message.content.strip(), "sql", sql,
        rows.to_dict("records"),
    )


def ask(question: str, strategy: str = "hybrid") -> Answer:
    """
    Responder una pregunta sobre la F1 con los datos de la base.

    :param question: Pregunta en lenguaje natural, ej. '¿Quién ganó en
        Monza en 2019?'.
    :param strategy: 'hybrid' (herramientas y, si ninguna aplica,
        texto-a-SQL) o 'sql' (solo texto-a-SQL).

    :return: Respuesta con el texto, la consulta usada y los datos.
    """
    if not question.strip():
        raise ValueError("La pregunta está vacía.")
    if strategy not in ("hybrid", "sql"):
        raise ValueError(f"Estrategia desconocida: {strategy}")
    if strategy == "hybrid":
        answer = _ask_with_tools(question)
        if answer is not None:
            return answer

    return _ask_with_sql(question)
