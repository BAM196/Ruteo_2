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

CREATE INDEX IF NOT EXISTS idx_nodos_geom ON nodos USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_aristas_geom ON aristas USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_metadata_gee_geom ON metadata_gee USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_amenazas_firms_geom ON amenazas_firms USING GIST (geom);
