import json
import os
import sys
from pathlib import Path

import psycopg2

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
JSON_PATH = Path(os.getenv("METADATA_GEE_PATH", AQUI / "metadata_gee.json"))
SCHEMA = RAIZ / "Diagrama" / "schema.sql"


def cargar_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(RAIZ / ".env")


def aplicar_schema(cur):
    sql = SCHEMA.read_text(encoding="utf-8")
    for sentencia in sql.split(";"):
        if sentencia.strip():
            cur.execute(sentencia)


def conectar():
    cargar_env()
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        sys.exit("Define POSTGRES_PASSWORD, la misma del .env del docker-compose.")
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "gisdb"),
        user=os.getenv("POSTGRES_USER", "gisuser"),
        password=password,
    )


def main():
    if not JSON_PATH.exists():
        sys.exit(f"No existe {JSON_PATH}. Corre extraer_gee.py primero.")
    doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    registros = doc["registros"]
    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute("SELECT COUNT(*) FROM nodos")
            if cur.fetchone()[0] == 0:
                sys.exit(
                    "La tabla nodos está vacía. Corre "
                    "Infraestructura/cargar_infraestructura.py primero."
                )
            cur.execute("TRUNCATE metadata_gee_especie, metadata_gee")
            for r in registros:
                cur.execute(
                    """
                    INSERT INTO metadata_gee (
                        nodo_id, nombre, landcover_code, landcover_clase,
                        landcover_clase_es, tiene_especie_objetivo,
                        tiene_especie_invasora, clase_prioritaria_default,
                        preferencia_default, nota_pixel, geom
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                    )
                    """,
                    (
                        r["nodo_id"], r.get("nombre"), r.get("landcover_code"),
                        r.get("landcover_clase"), r.get("landcover_clase_es"),
                        r.get("tiene_especie_objetivo"), r.get("tiene_especie_invasora"),
                        r.get("clase_prioritaria_default"), r.get("preferencia_default"),
                        r.get("nota_pixel"), r["lon"], r["lat"],
                    ),
                )
                for sp in r.get("especies", []):
                    cur.execute(
                        """
                        INSERT INTO metadata_gee_especie (nodo_id, cientifico, comun, registros)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (r["nodo_id"], sp["cientifico"], sp.get("comun"), sp["registros"]),
                    )
        conn.commit()
    print(f"Cargados {len(registros)} nodos en metadata_gee.")


if __name__ == "__main__":
    main()
