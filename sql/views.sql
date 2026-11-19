-- Vistas de consulta sobre la base de datos de F1.
--
-- La vista creada simplifica las preguntas más comunes (para el notebook, la API
-- y el asistente LLM).

-- Resultado de cada piloto en cada carrera, con carrera, circuito, piloto,
-- escudería y estado
CREATE VIEW v_race_results AS
SELECT
    ra.race_id,
    ra.year,
    ra.round,
    ra.name                                AS race_name,
    ra.date                                AS race_date,
    ci.circuit_id,
    ci.circuit_ref,
    ci.name                                AS circuit_name,
    ci.location,
    ci.country,
    d.driver_id,
    d.driver_ref,
    d.forename || ' ' || d.surname         AS driver_name,
    d.nationality                          AS driver_nationality,
    co.constructor_id,
    co.constructor_ref,
    co.name                                AS constructor_name,
    re.grid,
    re.position,
    re.position_text,
    re.position_order,
    re.points,
    re.laps,
    re.time,
    re.milliseconds,
    re.fastest_lap_rank,
    re.fastest_lap_time,
    st.status
FROM results AS re
JOIN races AS ra         ON ra.race_id = re.race_id
JOIN circuits AS ci      ON ci.circuit_id = ra.circuit_id
JOIN drivers AS d        ON d.driver_id = re.driver_id
JOIN constructors AS co  ON co.constructor_id = re.constructor_id
JOIN status AS st        ON st.status_id = re.status_id;

-- Ganador de cada carrera.
-- Tres carreras de los años 50 (Francia 1951, Argentina 1956, Gran Bretaña
-- 1957) tienen dos filas: dos pilotos compartieron el coche ganador y ambos
-- figuran como vencedores.
CREATE VIEW v_race_winners AS
SELECT
    race_id,
    year,
    round,
    race_name,
    race_date,
    circuit_id,
    circuit_ref,
    circuit_name,
    location,
    country,
    driver_id,
    driver_ref,
    driver_name,
    constructor_id,
    constructor_ref,
    constructor_name,
    grid,
    time
FROM v_race_results
WHERE position_order = 1;
