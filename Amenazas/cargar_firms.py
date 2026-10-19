import json
import os
import sys
from pathlib import Path

import psycopg2

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
JSON_PATH = Path(os.getenv("AMENAZA_FIRMS_PATH", AQUI / "amenaza_firms.json"))
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
        sys.exit(f"No existe {JSON_PATH}. Corre extraer_firms.py primero.")
    doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    focos = doc["focos"]
    costo = {
        a["arista_id"]: a for a in doc.get("aristas_afectadas", [])
    }
    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute(
                "TRUNCATE amenazas_firms_nodo, amenazas_firms_arista, amenazas_firms"
            )
            for foco in focos:
                cur.execute(
                    """
                    INSERT INTO amenazas_firms (
                        id, acq_date, acq_time, satellite, confidence, frp, daynight, geom
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                    )
                    """,
                    (
                        foco["id"], foco.get("acq_date") or None, foco.get("acq_time"),
                        foco.get("satellite"), foco.get("confidence"), foco.get("frp"),
                        foco.get("daynight"), foco["lon"], foco["lat"],
                    ),
                )
                for nodo in foco.get("nodos_dentro_umbral", []):
                    cur.execute(
                        """
                        INSERT INTO amenazas_firms_nodo (foco_id, nodo_id, distancia_m)
                        VALUES (%s, %s, %s)
                        """,
                        (foco["id"], nodo["id"], nodo["distancia_m"]),
                    )
                for arista in foco.get("aristas_dentro_umbral", []):
                    extra = costo.get(arista["id"], {})
                    cur.execute(
                        """
                        INSERT INTO amenazas_firms_arista (
                            foco_id, arista_id, source, target, distancia_m,
                            costo_km, costo_resiliente_km, evitar
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            foco["id"], arista["id"], arista["source"], arista["target"],
                            arista["distancia_m"], extra.get("costo_km"),
                            extra.get("costo_resiliente_km"), True,
                        ),
                    )
        conn.commit()
    print(f"Cargados {len(focos)} focos en amenazas_firms.")


if __name__ == "__main__":
    main()
