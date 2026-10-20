-- Este archivo no crea la base, es solo para crear el diagrama en dbdiagram.io
-- geom es Point en nodos, metadata_gee y amenazas_firms, y LineString en aristas
-- La base real se crea con Diagrama/schema.sql

CREATE TABLE nodos (
  id integer PRIMARY KEY,
  nombre text NOT NULL,
  localidad text,
  n_registros integer,
  anios text,
  codigos_estacion text,
  geom geometry
);

CREATE TABLE nodo_especie (
  nodo_id integer,
  cientifico text,
  comun text,
  registros integer NOT NULL,
  PRIMARY KEY (nodo_id, cientifico),
  FOREIGN KEY (nodo_id) REFERENCES nodos (id)
);

CREATE TABLE aristas (
  id integer PRIMARY KEY,
  source integer NOT NULL,
  target integer NOT NULL,
  distancia_m float,
  costo_km float NOT NULL,
  tipo text NOT NULL,
  excede_max boolean NOT NULL,
  geom geometry,
  FOREIGN KEY (source) REFERENCES nodos (id),
  FOREIGN KEY (target) REFERENCES nodos (id)
);

CREATE TABLE metadata_gee (
  nodo_id integer PRIMARY KEY,
  nombre text,
  landcover_code integer,
  landcover_clase text,
  landcover_clase_es text,
  tiene_especie_objetivo boolean,
  tiene_especie_invasora boolean,
  clase_prioritaria_default boolean,
  preferencia_default text,
  nota_pixel text,
  geom geometry,
  FOREIGN KEY (nodo_id) REFERENCES nodos (id)
);

CREATE TABLE metadata_gee_especie (
  nodo_id integer,
  cientifico text,
  comun text,
  registros integer NOT NULL,
  PRIMARY KEY (nodo_id, cientifico),
  FOREIGN KEY (nodo_id) REFERENCES metadata_gee (nodo_id)
);

CREATE TABLE amenazas_firms (
  id integer PRIMARY KEY,
  acq_date date,
  acq_time text,
  satellite text,
  confidence text,
  frp float,
  daynight text,
  geom geometry
);

CREATE TABLE amenazas_firms_nodo (
  foco_id integer,
  nodo_id integer,
  distancia_m float NOT NULL,
  PRIMARY KEY (foco_id, nodo_id),
  FOREIGN KEY (foco_id) REFERENCES amenazas_firms (id),
  FOREIGN KEY (nodo_id) REFERENCES nodos (id)
);

CREATE TABLE amenazas_firms_arista (
  foco_id integer,
  arista_id integer,
  source integer,
  target integer,
  distancia_m float NOT NULL,
  costo_km float,
  costo_resiliente_km float,
  evitar boolean NOT NULL,
  PRIMARY KEY (foco_id, arista_id),
  FOREIGN KEY (foco_id) REFERENCES amenazas_firms (id),
  FOREIGN KEY (arista_id) REFERENCES aristas (id)
);
--no funciona
--CREATE INDEX IF NOT EXISTS idx_meteo_alertas_nodo_geom ON meteo_alertas_nodo USING GIST (alerta_id, nodo_id);
