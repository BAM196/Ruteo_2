import json
import os
import sys
from pathlib import Path

import psycopg2

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS = Path(os.getenv("NODOS_PATH", AQUI / "nodosv2.json"))
ARISTAS = Path(os.getenv("ARISTAS_PATH", AQUI / "aristasv2.json"))
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
        sys.exit("Define POSTGRES_PASSWORD en .env.")
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "gisdb"),
        user=os.getenv("POSTGRES_USER", "gisuser"),
        password=password,
    )


def leer(path: Path, clave: str) -> list[dict]:
    if not path.exists():
        sys.exit(f"No existe {path}.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data[clave]


def main():
    nodos = leer(NODOS, "nodos")
    aristas = leer(ARISTAS, "aristas")
    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute(
                """
                TRUNCATE
                    amenazas_firms_nodo,
                    amenazas_firms_arista,
                    amenazas_firms,
                    metadata_gee_especie,
                    metadata_gee,
                    nodo_especie,
                    aristas,
                    nodos
                """
            )
            for n in nodos:
                cur.execute(
                    """
                    INSERT INTO nodos (
                        id, nombre, localidad, n_registros, anios, codigos_estacion, geom
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                    )
                    """,
                    (
                        n["id"], n["nombre"], n.get("localidad"), n.get("n_registros"),
                        ", ".join(str(a) for a in n.get("anios", [])),
                        "; ".join(n.get("codigos_estacion", [])),
                        n["lon"], n["lat"],
                    ),
                )
                for sp in n.get("especies", []):
                    cur.execute(
                        """
                        INSERT INTO nodo_especie (nodo_id, cientifico, comun, registros)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (n["id"], sp["cientifico"], sp.get("comun"), sp["registros"]),
                    )
            for a in aristas:
                (lon1, lat1), (lon2, lat2) = a["coordenadas"]
                cur.execute(
                    """
                    INSERT INTO aristas (
                        id, source, target, distancia_m, costo_km, tipo, excede_max, geom
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        ST_SetSRID(ST_MakeLine(ST_MakePoint(%s, %s), ST_MakePoint(%s, %s)), 4326)
                    )
                    """,
                    (
                        a["id"], a["source"], a["target"], a["distancia_m"], a["costo_km"],
                        a["tipo"], a["excede_max"], lon1, lat1, lon2, lat2,
                    ),
                )
        conn.commit()
    print(f"Cargados {len(nodos)} nodos y {len(aristas)} aristas.")


if __name__ == "__main__":
    main()
