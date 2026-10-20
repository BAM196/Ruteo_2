import json
import os
import sys
from pathlib import Path

import psycopg2

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
JSON_PATH = Path(os.getenv("METADATA_SENDEROS_PATH", AQUI / "metadata_senderos.json"))
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


def generar_wkt(s: dict) -> str:
    coords = s["coordenadas"]
    if s["tipo"] == "trazado":
        pts = ", ".join(f"{c[0]} {c[1]}" for c in coords)
        return f"LINESTRING({pts})"
    return f"POINT({coords[0]} {coords[1]})"


def main():
    if not JSON_PATH.exists():
        sys.exit(f"No existe {JSON_PATH}. Corre extraer_senderos.py primero.")
    doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    senderos = doc["senderos"]

    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute("TRUNCATE metadata_senderos_nodo, metadata_senderos_arista, metadata_senderos RESTART IDENTITY CASCADE")

            for s in senderos:
                wkt = generar_wkt(s)
                cur.execute(
                    """
                    INSERT INTO metadata_senderos (id, nombre, tipo, descripcion, longitud_km, geom)
                    VALUES (%s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))
                    RETURNING id
                    """,
                    (s["id"], s.get("nombre"), s["tipo"], s.get("descripcion"), s.get("longitud_km", 0.0), wkt),
                )

                for n in s.get("nodos_cercanos", []):
                    cur.execute(
                        """
                        INSERT INTO metadata_senderos_nodo (sendero_id, nodo_id, distancia_m)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (s["id"], n["id"], n["distancia_m"]),
                    )

                for ar in s.get("aristas_cercanas", []):
                    cur.execute(
                        """
                        INSERT INTO metadata_senderos_arista (sendero_id, arista_id, distancia_m, buffer_privacidad)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (s["id"], ar["id"], ar["distancia_m"], ar.get("buffer_privacidad", False)),
                    )

        conn.commit()
    print(f"Cargados {len(senderos)} senderos/hitos en metadata_senderos.")


if __name__ == "__main__":
    main()