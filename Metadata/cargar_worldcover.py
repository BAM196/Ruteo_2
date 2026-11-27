import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
JSON_PATH = Path(os.getenv("METADATA_COBERTURA_PATH", AQUI / "metadata_cobertura.json"))
DEM_JSON = AQUI / "metadata_dem.json"
SCHEMA = RAIZ / "Diagrama" / "schema.sql"


def cargar_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(RAIZ / ".env")


def aplicar_schema(cur):
    for sentencia in SCHEMA.read_text(encoding="utf-8").split(";"):
        if sentencia.strip():
            cur.execute(sentencia)


def conectar():
    cargar_env()
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        sys.exit("Define POSTGRES_PASSWORD, la misma del .env del docker-compose.")
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=os.getenv("POSTGRES_DB", "gisdb"),
        user=os.getenv("POSTGRES_USER", "gisuser"),
        password=password,
    )


def main():
    if not JSON_PATH.exists():
        sys.exit(f"No existe {JSON_PATH}. Corre extraer_worldcover.py primero.")
    registros = json.loads(JSON_PATH.read_text(encoding="utf-8"))["registros"]
    elevacion = {}
    if DEM_JSON.exists():
        elevacion = {r["nodo_id"]: r["elevacion_m"]
                     for r in json.loads(DEM_JSON.read_text(encoding="utf-8"))["nodos"]}
    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute("SELECT COUNT(*) FROM nodos")
            if cur.fetchone()[0] == 0:
                sys.exit("La tabla nodos está vacía. Corre Infraestructura/cargar_infraestructura.py primero.")
            cur.execute("TRUNCATE metadata_cobertura")
            execute_values(cur, """
                INSERT INTO metadata_cobertura (nodo_id, landcover_code, landcover_clase,
                    landcover_clase_es, elevacion_m, nota_pixel)
                VALUES %s
            """, [(r["nodo_id"], r.get("landcover_code"), r.get("landcover_clase"),
                   r.get("landcover_clase_es"), elevacion.get(r["nodo_id"]), r.get("nota_pixel"))
                  for r in registros])
        conn.commit()
    print(f"Cargados {len(registros)} nodos en metadata_cobertura (con elevación del DEM).")


if __name__ == "__main__":
    main()
