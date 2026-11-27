import json
import math
import os
from functools import lru_cache
from pathlib import Path

import yaml

MOTOR = Path(__file__).resolve().parents[1]
RAIZ = MOTOR.parent
CONFIG = MOTOR / "config"
RESULTADOS = MOTOR / "resultados"
ESCENARIOS = MOTOR / "escenarios"
PROB_FALLO_JSON = MOTOR / "prob_fallo.json"
SECTORES_JSON = MOTOR / "sectores.json"


def cargar_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(RAIZ / ".env")


def leer_yaml(nombre: str) -> dict:
    return yaml.safe_load((CONFIG / nombre).read_text(encoding="utf-8"))


def amenazas_cfg() -> dict:
    cfg = leer_yaml("amenazas.yaml")
    calculado = RAIZ / "Amenazas" / "aves_desplazamiento.json"
    if calculado.exists():
        r_mov = json.loads(calculado.read_text(encoding="utf-8"))["meta"]["r_mov_m"]
        cfg["amenazas"]["ebird"]["r_mov_m"]["valor"] = r_mov
        cfg["amenazas"]["ebird"]["r_mov_m"]["calculado"] = True
    return cfg


def aco_cfg() -> dict:
    return leer_yaml("aco.yaml")


@lru_cache(maxsize=1)
def _mision_base() -> dict:
    return leer_yaml("mision.yaml")


def mision_cfg() -> dict:
    return json.loads(json.dumps(_mision_base()))


def valor(x):
    return x["valor"] if isinstance(x, dict) and "valor" in x else x


def parametros_mision(cfg: dict | None = None) -> dict:
    cfg = cfg or mision_cfg()
    dron, op, mu = cfg["dron"], cfg["operacion"], cfg["muestreo"]
    r_op = float(valor(op["radio_operacion_m"]))
    lado = (valor(mu["puntos_por_lado"]) - 1) * valor(mu["separacion_m"])
    r_b = lado / 2 * math.sqrt(2)
    t_res = r_op / (valor(dron["velocidad_max_ms"]) - valor(dron["viento_limite_ms"])) + valor(dron["tiempo_aterrizaje_s"])
    t_bat = float(valor(dron["tiempo_bateria_s"]))
    return {
        "t_bat_s": t_bat,
        "t_res_s": t_res,
        "t_util_s": t_bat - t_res,
        "v_c": float(valor(dron["velocidad_crucero_ms"])),
        "v_sub": float(valor(dron["velocidad_ascenso_ms"])),
        "t_cambio_s": float(valor(dron["tiempo_cambio_bateria_s"])),
        "s_i": float(valor(mu["tiempo_por_camara_s"])),
        "r_op": r_op,
        "r_b": r_b,
        "alcance": r_op - r_b,
        "diametro_max": 2 * (r_op - r_b),
        "altura": float(valor(op["altura_vuelo_m"])),
        "lado_bloque": float(lado),
        "puntos_por_lado": int(valor(mu["puntos_por_lado"])),
        "separacion": float(valor(mu["separacion_m"])),
        "r_min_plan": float(valor(cfg["resiliencia"]["r_min_plan"])),
        "n_mc": int(valor(cfg["resiliencia"]["n_montecarlo"])),
        "peso_rli": dict(valor(cfg["prioridad"]["peso_rli"])),
        "peso_valor": float(valor(cfg["prioridad"]["peso_valor"])),
        "visitas": int(valor(cfg["campanas"]["visitas"])),
        "ventana_h": float(valor(cfg["campanas"]["ventana_manana_h"])),
        "inicio_ventana_min": int(valor(cfg["campanas"]["inicio_ventana_min"])),
        "fraccion_prioridad": float(valor(cfg["campanas"]["fraccion_prioridad"])),
        "anticipacion_dias_habiles": int(valor(cfg["campanas"]["anticipacion_dias_habiles"])),
        "temporadas": dict(valor(cfg["campanas"]["temporadas"])),
        "v_pie_kmh": float(valor(cfg["traslados"]["velocidad_pie_kmh"])),
    }


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
