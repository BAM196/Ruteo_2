import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = Flask(__name__)

NODE_SQL = """
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(feature), '[]'::json)
    )
    FROM (
        SELECT json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(n.geom)::json,
            'properties', json_build_object(
                'id', n.id,
                'name', n.nombre,
                'is_camera', (n.nombre ILIKE 'Camara%%'),
                'records', n.n_registros,
                'land_cover_code', m.landcover_code,
                'land_cover_label', m.landcover_clase_es,
                'elevation_m', m.elevacion_m,
                'pixel_note', m.nota_pixel,
                'species', (
                    SELECT COALESCE(json_agg(json_build_object(
                        'common', COALESCE(r.comun, e.comun),
                        'scientific', e.cientifico,
                        'records', e.registros,
                        'category', r.categoria_los_lagos,
                        'origin', r.origen,
                        'target', r.objetivo,
                        'pressure', r.presion
                    ) ORDER BY e.registros DESC), '[]'::json)
                    FROM nodo_especie e
                    LEFT JOIN especie_rce r ON e.cientifico ILIKE r.cientifico || '%%'
                    WHERE e.nodo_id = n.id
                )
            )
        ) AS feature
        FROM nodos n
        LEFT JOIN metadata_cobertura m ON m.nodo_id = n.id
        ORDER BY n.id
    ) features
"""

EDGE_SQL = """
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(feature), '[]'::json)
    )
    FROM (
        SELECT json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(COALESCE(ST_Force2D(p.geom), a.geom))::json,
            'properties', json_build_object(
                'id', a.id,
                'source', a.source,
                'target', a.target,
                'distance_m', a.distancia_m,
                'kind', a.tipo,
                'length_3d_m', p.largo_3d_m,
                'climb_m', p.ascenso_ida_m,
                'climb_back_m', p.ascenso_vuelta_m,
                'clearance_m', p.despeje_min_m,
                'densified', p.densificada,
                'blocked', p.bloqueada,
                'blocked_reason', p.motivo
            )
        ) AS feature
        FROM aristas a
        LEFT JOIN arista_perfil p ON p.arista_id = a.id
        ORDER BY a.id
    ) features
"""

LINK_SQL = """
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(feature), '[]'::json)
    )
    FROM (
        SELECT json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(ST_Force2D(geom))::json,
            'properties', json_build_object(
                'id', id, 'base_id', base_id, 'target', nodo_id, 'distance_m', distancia_m,
                'length_3d_m', largo_3d_m, 'climb_m', ascenso_ida_m, 'clearance_m', despeje_min_m,
                'kind', 'enlace_base'
            )
        ) AS feature
        FROM base_enlace
        ORDER BY id
    ) features
"""

FIRE_SQL = """
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(feature), '[]'::json)
    )
    FROM (
        SELECT json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(geom)::json,
            'properties', json_build_object(
                'id', id,
                'acquired_on', acq_date,
                'acquired_at', acq_time,
                'satellite', satellite,
                'confidence', confidence,
                'frp', frp,
                'day_night', daynight
            )
        ) AS feature
        FROM amenazas_firms
        ORDER BY id
    ) features
"""
meteo_alertas_sql = """
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(feature), '[]'::json)
    )
    FROM (
        SELECT json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(geom)::json,
            'properties', json_build_object(
                'id', id,
                'node_id', nodo_id,
                'date', fecha,
                'temperature', temperatura,
                'humidity', humedad,
                'wind_speed', viento,
                'gust', rafaga,
                'temp_min', temperatura_min,
                'temp_max', temperatura_max,
                'rain_mm', precipitacion_mm,
                'rain_probability', prob_lluvia,
                'mode', modo
            )
        ) AS feature
        FROM meteo_alertas
        ORDER BY fecha DESC
    ) features
"""
TRAIL_SQL = """
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(feature), '[]'::json)
    )
    FROM (
        SELECT json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(geom)::json,
            'properties', json_build_object(
                'id', id,
                'name', nombre,
                'type', tipo,
                'description', descripcion,
                'length_km', longitud_km
            )
        ) AS feature
        FROM metadata_senderos
        ORDER BY id
    ) features
"""

EBIRD_SQL = """
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(feature), '[]'::json)
    )
    FROM (
        SELECT json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(geom)::json,
            'properties', json_build_object(
                'id', id,
                'common_name', especie_comun,
                'scientific_name', especie_cientifico,
                'observed_at', to_char(fecha_obs, 'YYYY-MM-DD HH24:MI'),
                'count', cantidad,
                'location', localidad
            )
        ) AS feature
        FROM amenazas_ebird
        ORDER BY fecha_obs DESC NULLS LAST
    ) features
"""


def connect():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "gisdb"),
        user=os.getenv("POSTGRES_USER", "gisuser"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def query_value(sql, params=None):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return row[0] if row else None


def database_error():
    print("No se pudo consultar la base.")
    return jsonify({"error": "No se pudo consultar la base."}), 500


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/nodes")
def nodes():
    try:
        return jsonify(query_value(NODE_SQL))
    except psycopg2.Error:
        return database_error()


@app.get("/api/edges")
def edges():
    try:
        return jsonify(query_value(EDGE_SQL))
    except psycopg2.Error:
        return database_error()


@app.get("/api/fires")
def fires():
    try:
        return jsonify(query_value(FIRE_SQL))
    except psycopg2.Error:
        return database_error()

@app.get("/api/meteo")
def meteo_alertas():
    try:
        return jsonify(query_value(meteo_alertas_sql))
    except psycopg2.Error:
        return database_error()

@app.get("/api/trails")
def trails():
    try:
        return jsonify(query_value(TRAIL_SQL))
    except psycopg2.Error:
        return database_error()

@app.get("/api/ebird")
def ebird():
    try:
        return jsonify(query_value(EBIRD_SQL))
    except psycopg2.Error:
        return database_error()

@app.get("/api/links")
def links():
    try:
        return jsonify(query_value(LINK_SQL))
    except psycopg2.Error:
        return database_error()


if __name__ == "__main__":
    port = int(os.getenv("WEB_PORT", "8000"))
    print(f"Sitio listo en el puerto {port}.")
    app.run(host="0.0.0.0", port=port)
