import os
from pathlib import Path

import yaml

MOTOR = Path(__file__).resolve().parents[1]
RAIZ = MOTOR.parent
CONFIG = MOTOR / "config"
RESULTADOS = MOTOR / "resultados"
PROB_FALLO_JSON = MOTOR / "prob_fallo.json"


def cargar_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(RAIZ / ".env")


def leer_yaml(nombre: str) -> dict:
    return yaml.safe_load((CONFIG / nombre).read_text(encoding="utf-8"))


def amenazas_cfg() -> dict:
    return leer_yaml("amenazas.yaml")


def aco_cfg() -> dict:
    return leer_yaml("aco.yaml")


def valor(x):
    return x["valor"] if isinstance(x, dict) and "valor" in x else x


def d_max_por_defecto(cfg: dict | None = None) -> float:
    dron = (cfg or amenazas_cfg())["dron"]
    total = (
        valor(dron["velocidad_crucero_ms"])
        * valor(dron["tiempo_vuelo_min"])
        * 60
        * (1 - valor(dron["margen_seguridad"]))
    )
    return total / 2 if valor(dron["ida_y_vuelta"]) else total


def conectar():
    import psycopg2

    cargar_env()
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=os.getenv("POSTGRES_DB", "gisdb"),
        user=os.getenv("POSTGRES_USER", "gisuser"),
        password=os.getenv("POSTGRES_PASSWORD"),
        connect_timeout=5,
    )


def fuente_por_defecto() -> str:
    cargar_env()
    return os.getenv("MOTOR_FUENTE", "db")
