-- Consultas de ejemplo sobre la base de datos de F1.
-- Se pueden ejecutar con:
--     sqlite3 -header -column data/f1.db < sql/queries.sql

-- 1. ¿Quién ganó en Monza en 2019?
SELECT year, race_name, driver_name, constructor_name
FROM v_race_winners
WHERE circuit_ref = 'monza' AND year = 2019;

-- 2. Campeón de pilotos de cada temporada: líder del campeonato tras la
--    última carrera del año
SELECT ra.year,
       d.forename || ' ' || d.surname AS champion,
       co.name AS constructor_name,
       ds.points,
       ds.wins
FROM driver_standings AS ds
JOIN races AS ra ON ra.race_id = ds.race_id
JOIN drivers AS d ON d.driver_id = ds.driver_id
-- escudería con la que corrió la última carrera
JOIN results AS re ON re.race_id = ds.race_id AND re.driver_id = ds.driver_id
JOIN constructors AS co ON co.constructor_id = re.constructor_id
WHERE ds.position = 1
  AND ra.round = (SELECT MAX(round) FROM races WHERE year = ra.year)
ORDER BY ra.year DESC
LIMIT 10;

-- 3. Pilotos con más victorias en la historia
SELECT driver_name, COUNT(*) AS wins
FROM v_race_winners
GROUP BY driver_id
ORDER BY wins DESC
LIMIT 10;

-- 4. Escuderías con más victorias
SELECT constructor_name, COUNT(*) AS wins
FROM v_race_winners
GROUP BY constructor_id
ORDER BY wins DESC
LIMIT 10;

-- 5. Pilotos con más poles (salir primero en la parrilla)
SELECT driver_name, COUNT(*) AS poles
FROM v_race_results
WHERE grid = 1
GROUP BY driver_id
ORDER BY poles DESC
LIMIT 10;

-- 6. Circuitos con más Grandes Premios disputados
SELECT ci.name AS circuit_name,
       ci.country,
       COUNT(*) AS races,
       MIN(ra.year) AS first_year,
       MAX(ra.year) AS last_year
FROM races AS ra
JOIN circuits AS ci ON ci.circuit_id = ra.circuit_id
GROUP BY ci.circuit_id
ORDER BY races DESC
LIMIT 10;

-- 7. Causas de abandono más frecuentes (excluye a quienes terminaron o
--    quedaron a vueltas)
SELECT status, COUNT(*) AS cases
FROM v_race_results
WHERE status <> 'Finished' AND status NOT LIKE '+%Lap%'
GROUP BY status
ORDER BY cases DESC
LIMIT 10;

-- 8. Victorias desde la pole: ¿cuántas veces ganó quien salió primero, por
--    década?
SELECT (year / 10) * 10 AS decade,
       COUNT(*) AS races,
       SUM(grid = 1) AS wins_from_pole,
       ROUND(100.0 * SUM(grid = 1) / COUNT(*), 1) AS pct_from_pole
FROM v_race_winners
GROUP BY decade
ORDER BY decade;
