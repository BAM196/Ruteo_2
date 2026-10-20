import json
import os
import sys
from pathlib import Path

import psycopg2

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
JSON_PATH = Path(os.getenv("AMENAZA_EBIRD_PATH", AQUI / "amenaza_ebird.json"))
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
        sys.exit(f"No existe {JSON_PATH}. Corre extraer_ebird.py primero.")
    doc = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    avistamientos = doc["avistamientos"]
    costos = {a["arista_id"]: a for a in doc.get("aristas_afectadas", [])}

    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute("TRUNCATE amenazas_ebird_nodo, amenazas_ebird_arista, amenazas_ebird CASCADE")

            for av in avistamientos:
                cur.execute(
                    """
                    INSERT INTO amenazas_ebird (
                        id, especie_cientifico, especie_comun, fecha_obs, cantidad, localidad, geom
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                    )
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        av["id"], av["cientifico"], av["comun"],
                        av.get("fecha_obs") or None, av.get("cantidad", 1),
                        av.get("localidad"), av["lon"], av["lat"]
                    ),
                )

                for nodo in av.get("nodos_dentro_umbral", []):
                    cur.execute(
                        """
                        INSERT INTO amenazas_ebird_nodo (avistamiento_id, nodo_id, distancia_m)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (av["id"], nodo["id"], nodo["distancia_m"]),
                    )

                for ar in av.get("aristas_dentro_umbral", []):
                    extra = costos.get(ar["id"], {})
                    cur.execute(
                        """
                        INSERT INTO amenazas_ebird_arista (
                            avistamiento_id, arista_id, source, target,
                            distancia_m, costo_km, costo_resiliente_km, evitar
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            av["id"], ar["id"], ar["source"], ar["target"],
                            ar["distancia_m"], extra.get("costo_km"),
                            extra.get("costo_resiliente_km"), True
                        ),
                    )

        conn.commit()
    print(f"Cargados {len(avistamientos)} avistamientos de rapaces en amenazas_ebird.")


if __name__ == "__main__":
    main()