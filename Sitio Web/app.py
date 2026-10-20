import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from psycopg2.extras import RealDictCursor

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = Flask(__name__)

ROUTE_SQL = """
    SELECT path_seq, node, edge, agg_cost
    FROM pgr_dijkstra(
        'SELECT id, source, target, costo_km AS cost FROM aristas',
        %s,
        %s,
        false
    )
    ORDER BY path_seq
"""

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
                'records', n.n_registros,
                'station_codes', n.codigos_estacion,
                'land_cover_code', m.landcover_code,
                'land_cover_label', m.landcover_clase_es,
                'preference', m.preferencia_default,
                'pixel_note', m.nota_pixel,
                'species', (
                    SELECT COALESCE(json_agg(json_build_object(
                        'common', e.comun,
                        'scientific', e.cientifico,
                        'records', e.registros
                    ) ORDER BY e.registros DESC), '[]'::json)
                    FROM nodo_especie e
                    WHERE e.nodo_id = n.id
                )
            )
        ) AS feature
        FROM nodos n
        LEFT JOIN metadata_gee m ON m.nodo_id = n.id
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
            'geometry', ST_AsGeoJSON(geom)::json,
            'properties', json_build_object(
                'id', id,
                'source', source,
                'target', target,
                'distance_m', distancia_m,
                'cost_km', costo_km,
                'kind', tipo,
                'exceeds_max', excede_max
            )
        ) AS feature
        FROM aristas
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
                'wind_speed', viento
            )
        ) AS feature
        FROM meteo_alertas
        ORDER BY fecha DESC
    ) features

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

def endpoint_pair():
    sql = """
        SELECT id FROM (
            (SELECT id, 1 AS ord FROM nodos ORDER BY ST_Y(geom) ASC LIMIT 1)
            UNION ALL
            (SELECT id, 2 AS ord FROM nodos ORDER BY ST_Y(geom) DESC LIMIT 1)
        ) ends
        ORDER BY ord
    """
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return [row[0] for row in cursor.fetchall()]


def line_for(edge_ids):
    if not edge_ids:
        return None
    order = list(range(len(edge_ids)))
    sql = """
        SELECT ST_AsGeoJSON(
            ST_LineMerge(ST_Collect(a.geom ORDER BY u.ord))
        )::json
        FROM unnest(%s::int[], %s::int[]) AS u(edge_id, ord)
        JOIN aristas a ON a.id = u.edge_id
    """
    return query_value(sql, (edge_ids, order))


@app.get("/api/route")
def route():
    start_raw = request.args.get("start_id")
    goal_raw = request.args.get("goal_id")
    try:
        if start_raw and goal_raw:
            start_id = int(start_raw)
            goal_id = int(goal_raw)
        else:
            pair = endpoint_pair()
            if len(pair) < 2:
                return jsonify({"error": "No hay suficientes cámaras para una ruta."}), 404
            start_id, goal_id = pair
    except ValueError:
        return jsonify({"error": "El inicio y el destino deben ser números de cámara."}), 400
    if start_id == goal_id:
        return jsonify({"error": "El inicio y el destino son la misma cámara."}), 400
    try:
        with connect() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(ROUTE_SQL, (start_id, goal_id))
                steps = cursor.fetchall()
        if not steps:
            return jsonify({"error": "No hay camino entre esas cámaras."}), 404
        edge_ids = [step["edge"] for step in steps if step["edge"] > 0]
        geometry = line_for(edge_ids)
        return jsonify({
            "start_id": start_id,
            "goal_id": goal_id,
            "distance_km": round(float(steps[-1]["agg_cost"]), 2),
            "node_ids": [step["node"] for step in steps],
            "geometry": geometry,
        })
    except psycopg2.Error:
        return database_error()


if __name__ == "__main__":
    port = int(os.getenv("WEB_PORT", "8000"))
    print(f"Sitio listo en el puerto {port}.")
    app.run(host="0.0.0.0", port=port)
