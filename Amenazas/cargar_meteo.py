import json
import os
import sys
from pathlib import Path

import psycopg2

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
JSON_PATH = Path(os.getenv("AMENAZA_METEO_PATH", AQUI / "amenaza_meteo.json"))
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
        sys.exit(f"No existe {JSON_PATH}. Corre extraer_meteo.py primero.")
    doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    alertas = doc.get("alertas_meteorologicas", [])
    costo = {
            a["arista_id"]: a for a in doc.get("aristas_afectadas", [])
        }
    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute(
                "TRUNCATE meteo_alertas_nodo, meteo_alertas_arista, meteo_alertas"
            )
            for alerta in alertas:
                cur.execute(
                    """
                    INSERT INTO meteo_alertas (
                        nodo_id, fecha, temperatura, humedad, viento
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        alerta["nodo_id"],
                        alerta["fecha"],
                        alerta["temperatura"],
                        alerta["humedad"],
                        alerta["viento"],
                    ),
                )
            for arista_id, arista in costo.items():
                cur.execute(
                    """
                    INSERT INTO meteo_alertas_arista (
                        arista_id, nodo_cercano_id
                    ) VALUES (%s, %s)
                    """,
                    (arista_id, arista["nodo_cercano_id"]),
                )
        conn.commit()
    print(f"Cargados {len(alertas)} alertas en meteo_alertas.")
if __name__ == "__main__":
    main()