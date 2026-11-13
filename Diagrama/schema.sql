CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

CREATE TABLE IF NOT EXISTS nodos (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    localidad TEXT,
    n_registros INTEGER,
    anios TEXT,
    codigos_estacion TEXT,
    geom geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS nodo_especie (
    nodo_id INTEGER REFERENCES nodos(id) ON DELETE CASCADE,
    cientifico TEXT NOT NULL,
    comun TEXT,
    registros INTEGER NOT NULL,
    PRIMARY KEY (nodo_id, cientifico)
);

CREATE TABLE IF NOT EXISTS aristas (
    id INTEGER PRIMARY KEY,
    source INTEGER NOT NULL REFERENCES nodos(id),
    target INTEGER NOT NULL REFERENCES nodos(id),
    distancia_m DOUBLE PRECISION NOT NULL,
    costo_km DOUBLE PRECISION NOT NULL,
    tipo TEXT NOT NULL,
    excede_max BOOLEAN NOT NULL,
    geom geometry(LineString, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata_gee (
    nodo_id INTEGER PRIMARY KEY REFERENCES nodos(id) ON DELETE CASCADE,
    nombre TEXT,
    landcover_code INTEGER,
    landcover_clase TEXT,
    landcover_clase_es TEXT,
    tiene_especie_objetivo BOOLEAN,
    tiene_especie_invasora BOOLEAN,
    clase_prioritaria_default BOOLEAN,
    preferencia_default TEXT,
    nota_pixel TEXT,
    geom geometry(Point, 4326)
);

CREATE TABLE IF NOT EXISTS metadata_gee_especie (
    nodo_id INTEGER REFERENCES metadata_gee(nodo_id) ON DELETE CASCADE,
    cientifico TEXT NOT NULL,
    comun TEXT,
    registros INTEGER NOT NULL,
    PRIMARY KEY (nodo_id, cientifico)
);

CREATE TABLE IF NOT EXISTS metadata_senderos (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL, -- 'trazado' o 'punto_interes'
    descripcion TEXT,
    longitud_km DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    geom geometry(Geometry, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata_senderos_nodo (
    sendero_id INTEGER REFERENCES metadata_senderos(id) ON DELETE CASCADE,
    nodo_id INTEGER REFERENCES nodos(id) ON DELETE CASCADE,
    distancia_m DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (sendero_id, nodo_id)
);

CREATE TABLE IF NOT EXISTS metadata_senderos_arista (
    sendero_id INTEGER REFERENCES metadata_senderos(id) ON DELETE CASCADE,
    arista_id INTEGER REFERENCES aristas(id) ON DELETE CASCADE,
    distancia_m DOUBLE PRECISION NOT NULL,
    buffer_privacidad BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (sendero_id, arista_id)
);

CREATE TABLE IF NOT EXISTS metadata_fauna (
    id INTEGER PRIMARY KEY,
    documento JSONB NOT NULL,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS amenazas_firms (
    id INTEGER PRIMARY KEY,
    acq_date DATE,
    acq_time TEXT,
    satellite TEXT,
    confidence TEXT,
    frp DOUBLE PRECISION,
    daynight TEXT,
    geom geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS amenazas_firms_nodo (
    foco_id INTEGER REFERENCES amenazas_firms(id) ON DELETE CASCADE,
    nodo_id INTEGER REFERENCES nodos(id) ON DELETE CASCADE,
    distancia_m DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (foco_id, nodo_id)
);

CREATE TABLE IF NOT EXISTS amenazas_firms_arista (
    foco_id INTEGER REFERENCES amenazas_firms(id) ON DELETE CASCADE,
    arista_id INTEGER REFERENCES aristas(id) ON DELETE CASCADE,
    source INTEGER,
    target INTEGER,
    distancia_m DOUBLE PRECISION NOT NULL,
    costo_km DOUBLE PRECISION,
    costo_resiliente_km DOUBLE PRECISION,
    evitar BOOLEAN NOT NULL,
    PRIMARY KEY (foco_id, arista_id)
);

CREATE TABLE IF NOT EXISTS meteo_alertas (
    id SERIAL PRIMARY KEY,
    nodo_id INTEGER REFERENCES nodos(id) ON DELETE CASCADE,
    fecha DATE NOT NULL,
    temperatura DOUBLE PRECISION NOT NULL,
    humedad DOUBLE PRECISION NOT NULL,
    viento DOUBLE PRECISION NOT NULL,
    geom geometry(Point, 4326) NOT NULL
);
ALTER TABLE meteo_alertas ADD COLUMN IF NOT EXISTS rafaga DOUBLE PRECISION;
ALTER TABLE meteo_alertas ADD COLUMN IF NOT EXISTS lluvia_mm_h DOUBLE PRECISION;
ALTER TABLE meteo_alertas ADD COLUMN IF NOT EXISTS unidad_viento TEXT DEFAULT 'km/h';
ALTER TABLE meteo_alertas ADD COLUMN IF NOT EXISTS evitar BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS meteo_alertas_nodo (
    alerta_id INTEGER REFERENCES meteo_alertas(id) ON DELETE CASCADE,
    nodo_id INTEGER REFERENCES nodos(id) ON DELETE CASCADE,
    distancia_m DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (alerta_id, nodo_id)
);
CREATE TABLE IF NOT EXISTS meteo_alertas_arista (
    alerta_id INTEGER REFERENCES meteo_alertas(id) ON DELETE CASCADE,
    arista_id INTEGER REFERENCES aristas(id) ON DELETE CASCADE,
    source INTEGER,
    target INTEGER,
    distancia_m DOUBLE PRECISION NOT NULL,
    costo_km DOUBLE PRECISION,
    costo_resiliente_km DOUBLE PRECISION,
    evitar BOOLEAN NOT NULL,
    PRIMARY KEY (alerta_id, arista_id)
);

CREATE TABLE IF NOT EXISTS amenazas_ebird (
    id TEXT PRIMARY KEY, -- subId alfanumérico entregado por eBird
    especie_cientifico TEXT NOT NULL,
    especie_comun TEXT,
    fecha_obs TIMESTAMP,
    cantidad INTEGER,
    localidad TEXT,
    geom geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS amenazas_ebird_nodo (
    avistamiento_id TEXT REFERENCES amenazas_ebird(id) ON DELETE CASCADE,
    nodo_id INTEGER REFERENCES nodos(id) ON DELETE CASCADE,
    distancia_m DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (avistamiento_id, nodo_id)
);

CREATE TABLE IF NOT EXISTS amenazas_ebird_arista (
    avistamiento_id TEXT REFERENCES amenazas_ebird(id) ON DELETE CASCADE,
    arista_id INTEGER REFERENCES aristas(id) ON DELETE CASCADE,
    source INTEGER REFERENCES nodos(id),
    target INTEGER REFERENCES nodos(id),
    distancia_m DOUBLE PRECISION NOT NULL,
    costo_km DOUBLE PRECISION,
    costo_resiliente_km DOUBLE PRECISION,
    evitar BOOLEAN NOT NULL,
    PRIMARY KEY (avistamiento_id, arista_id)
);


CREATE TABLE IF NOT EXISTS prob_fallo_nodo (
    nodo_id INTEGER REFERENCES nodos(id) ON DELETE CASCADE,
    amenaza TEXT NOT NULL,
    p_fallo DOUBLE PRECISION NOT NULL CHECK (p_fallo >= 0 AND p_fallo < 1),
    detalle JSONB,
    generado TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (nodo_id, amenaza)
);

CREATE TABLE IF NOT EXISTS prob_fallo_arista (
    arista_id INTEGER REFERENCES aristas(id) ON DELETE CASCADE,
    amenaza TEXT NOT NULL,
    p_fallo DOUBLE PRECISION NOT NULL CHECK (p_fallo >= 0 AND p_fallo < 1),
    detalle JSONB,
    generado TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (arista_id, amenaza)
);

CREATE OR REPLACE VIEW prob_fallo_nodo_total AS
SELECT n.id AS nodo_id,
       COALESCE(1 - EXP(SUM(LN(1 - p.p_fallo))), 0) AS p_total,
       COALESCE(json_object_agg(p.amenaza, p.p_fallo) FILTER (WHERE p.amenaza IS NOT NULL), '{}'::json) AS por_amenaza
FROM nodos n
LEFT JOIN prob_fallo_nodo p ON p.nodo_id = n.id
GROUP BY n.id;

CREATE OR REPLACE VIEW prob_fallo_arista_total AS
SELECT a.id AS arista_id, a.source, a.target,
       COALESCE(1 - EXP(SUM(LN(1 - p.p_fallo))), 0) AS p_total,
       COALESCE(json_object_agg(p.amenaza, p.p_fallo) FILTER (WHERE p.amenaza IS NOT NULL), '{}'::json) AS por_amenaza
FROM aristas a
LEFT JOIN prob_fallo_arista p ON p.arista_id = a.id
GROUP BY a.id, a.source, a.target;

CREATE INDEX IF NOT EXISTS idx_nodos_geom ON nodos USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_aristas_geom ON aristas USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_metadata_gee_geom ON metadata_gee USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_metadata_senderos_geom ON metadata_senderos USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_amenazas_firms_geom ON amenazas_firms USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_amenazas_ebird_geom ON amenazas_ebird USING GIST (geom);