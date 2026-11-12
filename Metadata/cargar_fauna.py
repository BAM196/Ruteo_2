import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
JSON_PATH = Path(os.getenv("METADATA_FAUNA_PATH", AQUI / "fauna.json"))
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
        **{"password": password},
    )

#cargar de datos
def leer_documento() -> dict:
    if not JSON_PATH.exists():
        sys.exit(f"No existe {JSON_PATH}. Corre Metadata/extraer_fauna.py primero.")
    try:
        documento = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        sys.exit(f"JSON inválido en {JSON_PATH}: {error}")

    if not isinstance(documento, dict):
        sys.exit("El documento de fauna debe ser un objeto JSON.")
    meta = documento.get("meta")
    especies = documento.get("especies")
    if not isinstance(meta, dict):
        sys.exit("El documento de fauna debe incluir el objeto 'meta'.")
    if not isinstance(especies, list):
        sys.exit("El documento de fauna debe incluir el arreglo 'especies'.")
    for indice, especie in enumerate(especies):
        if not isinstance(especie, dict) or not especie.get("nombre_cientifico"):
            sys.exit(
                "Cada elemento de 'especies' debe ser un objeto con "
                f"'nombre_cientifico'; registro inválido en posición {indice}."
            )
    return documento


def main():
    documento = leer_documento()
    with conectar() as conn:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute(
                """
                INSERT INTO metadata_fauna (id, documento, actualizado)
                VALUES (1, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    documento = EXCLUDED.documento,
                    actualizado = EXCLUDED.actualizado
                """,
                (Json(documento),),
            )
        conn.commit()

    print(
        "Catálogo de fauna actualizado en metadata_fauna: "
        f"{len(documento['especies'])} registros."
    )


if __name__ == "__main__":
    main()
