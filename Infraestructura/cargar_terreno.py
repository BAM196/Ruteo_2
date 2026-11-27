import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
PERFILES = AQUI / "perfiles_aristas.json"
BASES = AQUI / "bases.json"
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


def linea_z(puntos) -> str | None:
    if not puntos or len(puntos) < 2:
        return None
    return "SRID=4326;LINESTRING Z(" + ", ".join(f"{x} {y} {z}" for x, y, z in puntos) + ")"


def main():
    for path, script in ((PERFILES, "perfiles_aristas.py"), (BASES, "generar_bases.py")):
        if not path.exists():
            sys.exit(f"No existe {path}. Corre Infraestructura/{script} primero.")
    perfiles = json.loads(PERFILES.read_text(encoding="utf-8"))["perfiles"]
    bases = json.loads(BASES.read_text(encoding="utf-8"))["bases"]

    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute("SELECT COUNT(*) FROM aristas")
            if cur.fetchone()[0] == 0:
                sys.exit("La tabla aristas está vacía. Corre Infraestructura/cargar_infraestructura.py primero.")
            cur.execute("TRUNCATE sector_camara, sectores, base_arista_visible, base_enlace, "
                        "base_camara, bases, arista_perfil CASCADE")
            execute_values(cur, """
                INSERT INTO arista_perfil (arista_id, largo_2d_m, largo_3d_m, ascenso_ida_m,
                    ascenso_vuelta_m, despeje_min_m, altura_max_sobre_superficie_m, densificada,
                    bloqueada, motivo, geom)
                VALUES %s
            """, [(p["arista_id"], p["largo_2d_m"], p.get("largo_3d_m"), p.get("ascenso_ida_m"),
                   p.get("ascenso_vuelta_m"), p.get("despeje_min_m"),
                   p.get("altura_max_sobre_superficie_m"), bool(p.get("densificada")),
                   bool(p["bloqueada"]), p.get("motivo"), linea_z(p.get("puntos")))
                  for p in perfiles])
            execute_values(cur, """
                INSERT INTO bases (id, tipo, nodo_id, nombre, sendero_id, elevacion_m, geom)
                VALUES %s
            """, [(b["id"], b["tipo"], b.get("nodo_id"), b.get("nombre"), b.get("sendero_id"),
                   b.get("elevacion_m"), f"SRID=4326;POINT({b['lon']} {b['lat']})") for b in bases])
            execute_values(cur, """
                INSERT INTO base_camara (base_id, camara_id, distancia_m, bloque_visible, fraccion_visible)
                VALUES %s
            """, [(b["id"], c["camara_id"], c["distancia_m"], c["bloque_visible"], c["fraccion_visible"])
                  for b in bases for c in b["camaras"]])
            filas = [(e["id"], b["id"], e["nodo_id"], e["distancia_m"], e["largo_3d_m"],
                      e["ascenso_ida_m"], e["ascenso_vuelta_m"], e["despeje_min_m"], linea_z(e["puntos"]))
                     for b in bases for e in b["enlaces"]]
            if filas:
                execute_values(cur, """
                    INSERT INTO base_enlace (id, base_id, nodo_id, distancia_m, largo_3d_m,
                        ascenso_ida_m, ascenso_vuelta_m, despeje_min_m, geom)
                    VALUES %s
                """, filas)
            execute_values(cur, """
                INSERT INTO base_arista_visible (base_id, arista_id, visible, motivo) VALUES %s
            """, [(b["id"], a, True, None) for b in bases for a in b["aristas_visibles"]]
                + [(b["id"], x["arista_id"], False, x["motivo"]) for b in bases for x in b["aristas_bloqueadas"]])
        conn.commit()
    print(f"Cargados {len(perfiles)} perfiles de aristas y {len(bases)} bases con su visibilidad.")


if __name__ == "__main__":
    main()
