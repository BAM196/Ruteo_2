CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;
-- Crear la tabla
CREATE TABLE waypoints (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    geom GEOMETRY(POINT, 4326) NOT NULL
    );

CREATE TABLE rutas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    geom GEOMETRY(LINESTRING, 4326) NOT NULL --,
   -- cost FLOAT NOT NULL
    );

CREATE TABLE area_estudio (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    geom GEOMETRY(POLYGON, 4326) NOT NULL
    );

CREATE TABLE animales (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    especie VARCHAR(100) NOT NULL,
    );

CREATE INDEX idx_waypoints_geom ON waypoints USING GIST (geom);
