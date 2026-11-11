import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
SALIDA = AQUI / "amenaza_meteo.json"
CONFIG_MOTOR = RAIZ / "Motor" / "config" / "amenazas.yaml"

API = "https://api.open-meteo.com/v1/forecast"
VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
    "precipitation",
]

LIMITES = {"v_max_ms": 12.0, "temperatura_min_c": -10.0, "temperatura_max_c": 40.0}


def cargar_limites():
    try:
        import yaml

        meteo = yaml.safe_load(CONFIG_MOTOR.read_text(encoding="utf-8"))["amenazas"]["meteo"]
        for k in LIMITES:
            LIMITES[k] = float(meteo[k]["valor"])
    except Exception as exc:
        print(f"Aviso: no se leyó {CONFIG_MOTOR.name} ({exc}); se usan los límites por defecto.")


def leer_nodos() -> list[dict]:
    if not NODOS_PATH.exists():
        sys.exit(f"No existe {NODOS_PATH}.")
    data = json.loads(NODOS_PATH.read_text(encoding="utf-8"))
    return data["nodos"] if isinstance(data, dict) else data


def consultar(nodos: list[dict]) -> list[dict]:
    params = {
        "latitude": ",".join(f"{n['lat']:.6f}" for n in nodos),
        "longitude": ",".join(f"{n['lon']:.6f}" for n in nodos),
        "current": ",".join(VARIABLES),
        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
        "timezone": "auto",
    }
    resp = requests.get(API, params=params, timeout=60)
    if resp.status_code != 200:
        sys.exit(f"Open-Meteo respondió {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data if isinstance(data, list) else [data]


def evaluar(lectura: dict) -> tuple[bool, str]:
    motivos = []
    viento = max(v for v in (lectura["viento"], lectura["rafaga"]) if v is not None) \
        if lectura["viento"] is not None or lectura["rafaga"] is not None else None
    if viento is not None and viento > LIMITES["v_max_ms"]:
        motivos.append(f"viento {viento:.1f} m/s > {LIMITES['v_max_ms']:.0f} m/s")
    t = lectura["temperatura"]
    if t is not None and not LIMITES["temperatura_min_c"] <= t <= LIMITES["temperatura_max_c"]:
        motivos.append(f"temperatura {t:.1f} °C fuera de [{LIMITES['temperatura_min_c']:.0f}, "
                       f"{LIMITES['temperatura_max_c']:.0f}] °C")
    return bool(motivos), "; ".join(motivos) or "dentro de los límites del fabricante"


def main():
    cargar_limites()
    nodos = leer_nodos()
    print(f"Consultando Open-Meteo para {len(nodos)} cámaras (viento en m/s)...")
    respuestas = consultar(nodos)
    if len(respuestas) != len(nodos):
        sys.exit(f"Open-Meteo devolvió {len(respuestas)} respuestas para {len(nodos)} cámaras.")

    lecturas = []
    for nodo, r in zip(nodos, respuestas):
        cur = r.get("current", {})
        intervalo = cur.get("interval") or 900
        precip = cur.get("precipitation")
        lectura = {
            "nodo_id": nodo["id"],
            "nombre": nodo.get("nombre"),
            "lat": nodo["lat"],
            "lon": nodo["lon"],
            "fecha": cur.get("time"),
            "temperatura": cur.get("temperature_2m"),
            "humedad": cur.get("relative_humidity_2m"),
            "viento": cur.get("wind_speed_10m"),
            "rafaga": cur.get("wind_gusts_10m"),
            "precipitacion_mm": precip,
            "lluvia_mm_h": None if precip is None else round(precip * 3600 / intervalo, 3),
        }
        lectura["evitar"], lectura["motivo"] = evaluar(lectura)
        lecturas.append(lectura)

    unidades = (respuestas[0].get("current_units") or {}) if respuestas else {}
    documento = {
        "meta": {
            "fuente": "Open-Meteo API (Weather Forecast API)",
            "endpoint": API,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "variables": VARIABLES,
            "unidades_api": unidades,
            "unidad_viento": "m/s",
            "unidad_lluvia": "mm/h",
            "intervalo_s": (respuestas[0].get("current") or {}).get("interval") if respuestas else None,
            "limites_fabricante": LIMITES,
            "regla_evitar": "evitar = true si el viento o la ráfaga supera v_max o la temperatura sale del rango de operación",
            "n_lecturas": len(lecturas),
            "n_evitar": sum(1 for x in lecturas if x["evitar"]),
        },
        "lecturas": lecturas,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    vientos = [x["rafaga"] for x in lecturas if x["rafaga"] is not None]
    if vientos:
        print(f"Ráfaga mínima {min(vientos):.1f} m/s, máxima {max(vientos):.1f} m/s.")
    print(f"Lecturas: {len(lecturas)} | fuera de límites: {documento['meta']['n_evitar']}")
    print(f"Escrito: {SALIDA}")


if __name__ == "__main__":
    main()
