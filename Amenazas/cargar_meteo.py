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
    meta = doc.get("meta") or {}
    lecturas = doc.get("lecturas", doc.get("alertas_meteorologicas", []))
    unidad = meta.get("unidad_viento", "km/h")
    fecha_doc = meta.get("generado")

    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute(
                "TRUNCATE meteo_alertas_nodo, meteo_alertas_arista, meteo_alertas RESTART IDENTITY CASCADE"
            )
            cur.execute("SELECT id, source, target FROM aristas")
            incidentes = {}
            for aid, s, t in cur.fetchall():
                incidentes.setdefault(s, []).append((aid, s, t))
                incidentes.setdefault(t, []).append((aid, s, t))

            for lec in lecturas:
                nodo_id = lec.get("nodo_id", lec.get("nodo_origen_alerta"))
                if lec.get("temperatura") is None or lec.get("viento") is None:
                    print(f"Cámara {nodo_id}: lectura incompleta, se omite.")
                    continue
                evitar = bool(lec.get("evitar", "lecturas" not in doc))
                cur.execute(
                    """
                    INSERT INTO meteo_alertas (
                        nodo_id, fecha, temperatura, humedad, viento, rafaga,
                        lluvia_mm_h, unidad_viento, evitar, geom
                    ) VALUES (
                        %s, COALESCE(%s::date, CURRENT_DATE), %s, %s, %s, %s, %s, %s, %s,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                    )
                    RETURNING id
                    """,
                    (
                        nodo_id, lec.get("fecha") or fecha_doc,
                        lec["temperatura"], lec.get("humedad") or 0, lec["viento"],
                        lec.get("rafaga"), lec.get("lluvia_mm_h"), unidad, evitar,
                        lec["lon"], lec["lat"],
                    ),
                )
                alerta_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO meteo_alertas_nodo (alerta_id, nodo_id, distancia_m) VALUES (%s, %s, 0)",
                    (alerta_id, nodo_id),
                )
                for aid, s, t in incidentes.get(nodo_id, []):
                    cur.execute(
                        """
                        INSERT INTO meteo_alertas_arista (
                            alerta_id, arista_id, source, target, distancia_m, evitar
                        ) VALUES (%s, %s, %s, %s, 0, %s)
                        """,
                        (alerta_id, aid, s, t, evitar),
                    )
        conn.commit()
    print(f"Cargadas {len(lecturas)} lecturas en meteo_alertas (viento en {unidad}).")


if __name__ == "__main__":
    main()
