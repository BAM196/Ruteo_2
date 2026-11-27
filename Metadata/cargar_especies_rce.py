import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_values

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
JSON_PATH = AQUI / "especies_rce.json"
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
        sys.exit(f"No existe {JSON_PATH}. Corre Metadata/especies_rce.py primero.")
    especies = json.loads(JSON_PATH.read_text(encoding="utf-8"))["especies"]
    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute("TRUNCATE especie_rce")
            execute_values(cur, """
                INSERT INTO especie_rce (cientifico, comun, origen, categoria_los_lagos,
                    categoria_vigente, decreto, peso_w, objetivo, presion, registros, camaras, ficha)
                VALUES %s
            """, [(e["cientifico"], e["comun"], e["origen"], e.get("categoria_los_lagos"),
                   e.get("categoria_vigente"), e.get("decreto"), e.get("peso_w"), e["objetivo"],
                   e["presion"], e["registros"], e["camaras"],
                   Json({k: e[k] for k in ("amenazas", "comportamiento", "como_presiona") if k in e}))
                  for e in especies])
        conn.commit()
    print(f"Cargadas {len(especies)} especies en especie_rce.")


if __name__ == "__main__":
    main()
