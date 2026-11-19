-- Esquema de la base de datos del Campeonato Mundial de F1 (SQLite).
--
-- Contiene las 12 tablas relacionales del dataset de Kaggle. Las tablas
-- lap_times y pit_stops no están aquí: se consumen directamente como CSV
-- desde data/raw/.
--
-- La columna "rank" de results se renombra a fastest_lap_rank para que su
-- significado sea claro.
--
-- SQLite solo comprueba las claves foráneas si la conexión ejecuta
-- PRAGMA foreign_keys = ON; scripts/build_database.py lo activa antes de
-- cargar los datos.

-- ---------------------------------------------------------------------------
-- Dimensiones
-- ---------------------------------------------------------------------------

-- Circuitos donde se ha corrido al menos una carrera
CREATE TABLE circuits (
    circuit_id   INTEGER PRIMARY KEY,
    -- Identificador legible, ej. 'monza'
    circuit_ref  TEXT    NOT NULL UNIQUE,
    name         TEXT    NOT NULL,
    location     TEXT,
    country      TEXT,
    lat          REAL,
    lng          REAL,
    alt          INTEGER,                      -- altitud en metros
    url          TEXT
);

-- Escuderías
CREATE TABLE constructors (
    constructor_id   INTEGER PRIMARY KEY,
    constructor_ref  TEXT    NOT NULL UNIQUE,  -- ej. 'ferrari'
    name             TEXT    NOT NULL,
    nationality      TEXT,
    url              TEXT
);

-- Pilotos
CREATE TABLE drivers (
    driver_id    INTEGER PRIMARY KEY,
    driver_ref   TEXT    NOT NULL UNIQUE,      -- ej. 'hamilton'
    number       INTEGER,                      -- número permanente (desde 2014)
    code         TEXT,                         -- código de tres letras: 'HAM'
    forename     TEXT    NOT NULL,
    surname      TEXT    NOT NULL,
    dob          TEXT,                         -- nacimiento (AAAA-MM-DD)
    nationality  TEXT,
    url          TEXT
);

-- Temporadas
CREATE TABLE seasons (
    year  INTEGER PRIMARY KEY,
    url   TEXT
);

-- Estados de llegada: 'Finished', '+1 Lap', 'Engine', 'Accident', etc.
CREATE TABLE status (
    status_id  INTEGER PRIMARY KEY,
    status     TEXT    NOT NULL
);

-- Carreras (Grandes Premios)
CREATE TABLE races (
    race_id      INTEGER PRIMARY KEY,
    year         INTEGER NOT NULL REFERENCES seasons (year),
    round        INTEGER NOT NULL,             -- fecha dentro de la temporada
    circuit_id   INTEGER NOT NULL REFERENCES circuits (circuit_id),
    name         TEXT    NOT NULL,             -- 'Italian Grand Prix'
    date         TEXT    NOT NULL,             -- AAAA-MM-DD
    time         TEXT,                         -- hora de inicio (UTC)
    url          TEXT,
    fp1_date     TEXT,
    fp1_time     TEXT,
    fp2_date     TEXT,
    fp2_time     TEXT,
    fp3_date     TEXT,
    fp3_time     TEXT,
    quali_date   TEXT,
    quali_time   TEXT,
    sprint_date  TEXT,
    sprint_time  TEXT,
    UNIQUE (year, round)
);

-- ---------------------------------------------------------------------------
-- Hechos por carrera
-- ---------------------------------------------------------------------------

-- Resultado de cada piloto en cada carrera
CREATE TABLE results (
    result_id          INTEGER PRIMARY KEY,
    race_id            INTEGER NOT NULL REFERENCES races (race_id),
    driver_id          INTEGER NOT NULL REFERENCES drivers (driver_id),
    constructor_id     INTEGER NOT NULL
                       REFERENCES constructors (constructor_id),
    number             INTEGER,
    -- posición de salida; 0 = salió desde el pit lane
    grid               INTEGER NOT NULL,
    -- posición final; NULL si no fue clasificado
    position           INTEGER,
    -- '1', '2', ... o 'R' (retirado), 'D' (descalificado), etc.
    position_text      TEXT    NOT NULL,
    -- orden final de todos los pilotos, clasificados o no
    position_order     INTEGER NOT NULL,
    points             REAL    NOT NULL,
    laps               INTEGER NOT NULL,
    time               TEXT,                   -- tiempo total o diferencia
    milliseconds       INTEGER,
    fastest_lap        INTEGER,                -- vuelta más rápida del piloto
    fastest_lap_rank   INTEGER,                -- puesto de esa vuelta
    fastest_lap_time   TEXT,
    fastest_lap_speed  REAL,                   -- km/h
    status_id          INTEGER NOT NULL REFERENCES status (status_id)
);

-- Resultado de cada piloto en las carreras sprint (desde 2021)
CREATE TABLE sprint_results (
    result_id         INTEGER PRIMARY KEY,
    race_id           INTEGER NOT NULL REFERENCES races (race_id),
    driver_id         INTEGER NOT NULL REFERENCES drivers (driver_id),
    constructor_id    INTEGER NOT NULL REFERENCES constructors (constructor_id),
    number            INTEGER,
    grid              INTEGER NOT NULL,
    position          INTEGER,
    position_text     TEXT    NOT NULL,
    position_order    INTEGER NOT NULL,
    points            REAL    NOT NULL,
    laps              INTEGER NOT NULL,
    time              TEXT,
    milliseconds      INTEGER,
    fastest_lap       INTEGER,
    fastest_lap_time  TEXT,
    status_id         INTEGER NOT NULL REFERENCES status (status_id)
);

-- Clasificación del sábado (desde 1994)
CREATE TABLE qualifying (
    qualify_id      INTEGER PRIMARY KEY,
    race_id         INTEGER NOT NULL REFERENCES races (race_id),
    driver_id       INTEGER NOT NULL REFERENCES drivers (driver_id),
    constructor_id  INTEGER NOT NULL REFERENCES constructors (constructor_id),
    number          INTEGER,
    position        INTEGER NOT NULL,
    q1              TEXT,                      -- tiempos en formato 'm:ss.mmm'
    q2              TEXT,
    q3              TEXT
);

-- Campeonato de pilotos acumulado después de cada carrera
CREATE TABLE driver_standings (
    driver_standings_id  INTEGER PRIMARY KEY,
    race_id              INTEGER NOT NULL REFERENCES races (race_id),
    driver_id            INTEGER NOT NULL REFERENCES drivers (driver_id),
    points               REAL    NOT NULL,
    position             INTEGER,
    position_text        TEXT,
    wins                 INTEGER NOT NULL
);

-- Campeonato de constructores acumulado después de cada carrera
CREATE TABLE constructor_standings (
    constructor_standings_id  INTEGER PRIMARY KEY,
    race_id                   INTEGER NOT NULL REFERENCES races (race_id),
    constructor_id            INTEGER NOT NULL
                              REFERENCES constructors (constructor_id),
    points                    REAL    NOT NULL,
    position                  INTEGER,
    position_text             TEXT,
    wins                      INTEGER NOT NULL
);

-- Puntos de cada escudería en cada carrera
CREATE TABLE constructor_results (
    constructor_results_id  INTEGER PRIMARY KEY,
    race_id                 INTEGER NOT NULL REFERENCES races (race_id),
    constructor_id          INTEGER NOT NULL
                            REFERENCES constructors (constructor_id),
    points                  REAL    NOT NULL,
    -- 'D' si la escudería fue descalificada
    status                  TEXT
);

-- ---------------------------------------------------------------------------
-- Índices en claves foráneas y en las búsquedas más frecuentes
-- ---------------------------------------------------------------------------

CREATE INDEX idx_races_year_circuit ON races (year, circuit_id);
CREATE INDEX idx_races_circuit ON races (circuit_id);

CREATE INDEX idx_results_race ON results (race_id);
CREATE INDEX idx_results_driver ON results (driver_id);
CREATE INDEX idx_results_constructor ON results (constructor_id);
CREATE INDEX idx_results_status ON results (status_id);

CREATE INDEX idx_sprint_results_race ON sprint_results (race_id);
CREATE INDEX idx_sprint_results_driver ON sprint_results (driver_id);

CREATE INDEX idx_qualifying_race ON qualifying (race_id);
CREATE INDEX idx_qualifying_driver ON qualifying (driver_id);

CREATE INDEX idx_driver_standings_race ON driver_standings (race_id);
CREATE INDEX idx_driver_standings_driver ON driver_standings (driver_id);

CREATE INDEX idx_constructor_standings_race ON constructor_standings (race_id);
CREATE INDEX idx_constructor_standings_constructor
    ON constructor_standings (constructor_id);

CREATE INDEX idx_constructor_results_race ON constructor_results (race_id);
CREATE INDEX idx_constructor_results_constructor
    ON constructor_results (constructor_id);
