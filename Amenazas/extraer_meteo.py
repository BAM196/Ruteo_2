import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
SALIDA = AQUI / "amenaza_meteo.json"
AMENAZAS_YAML = RAIZ / "Motor" / "config" / "amenazas.yaml"
MISION_YAML = RAIZ / "Motor" / "config" / "mision.yaml"

API_PRONOSTICO = "https://api.open-meteo.com/v1/forecast"
API_HISTORICO = "https://archive-api.open-meteo.com/v1/archive"
ZONA = "America/Santiago"
VARIABLES = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_gusts_10m", "precipitation"]


def valor(x):
    return x["valor"] if isinstance(x, dict) and "valor" in x else x


def ventana_cfg() -> tuple[int, int]:
    campanas = yaml.safe_load(MISION_YAML.read_text(encoding="utf-8"))["campanas"]
    return int(valor(campanas["inicio_ventana_min"])), int(round(float(valor(campanas["ventana_manana_h"]))))


def limites() -> dict:
    meteo = yaml.safe_load(AMENAZAS_YAML.read_text(encoding="utf-8"))["amenazas"]["meteo"]
    return {k: float(valor(meteo[k])) for k in ("rafaga_max_ms", "temperatura_min_c", "temperatura_max_c")}


def leer_camaras() -> list[dict]:
    if not NODOS_PATH.exists():
        sys.exit(f"No existe {NODOS_PATH}.")
    nodos = json.loads(NODOS_PATH.read_text(encoding="utf-8"))["nodos"]
    return [n for n in nodos if n.get("es_camara")]


def consultar(camaras, fecha: date | None) -> list[dict]:
    variables = VARIABLES + ([] if fecha else ["precipitation_probability"])
    params = {
        "latitude": ",".join(f"{n['lat']:.6f}" for n in camaras),
        "longitude": ",".join(f"{n['lon']:.6f}" for n in camaras),
        "hourly": ",".join(variables),
        "daily": "sunrise",
        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
        "timezone": ZONA,
    }
    if fecha:
        api = API_HISTORICO
        params.update(start_date=fecha.isoformat(), end_date=fecha.isoformat())
    else:
        api = API_PRONOSTICO
        params["forecast_days"] = 3
    resp = requests.get(api, params=params, timeout=120)
    if resp.status_code != 200:
        sys.exit(f"Open-Meteo respondió {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return data if isinstance(data, list) else [data]


def horas_ventana(r: dict, fecha_obj: date | None, inicio_min: int, largo_h: int):
    ahora = datetime.now()
    for dia, amanecer in zip(r["daily"]["time"], r["daily"]["sunrise"]):
        sr = datetime.fromisoformat(amanecer)
        primera = (sr + timedelta(minutes=inicio_min)).replace(minute=0, second=0)
        ultima = primera + timedelta(hours=largo_h)
        if fecha_obj or ultima > ahora:
            horas = [(primera + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M") for k in range(largo_h)]
            return dia, sr, horas
    return None, None, []


def resumir(r: dict, horas: list[str]) -> dict:
    h = r["hourly"]
    idx = [h["time"].index(t) for t in horas if t in h["time"]]

    def serie(var):
        return [h[var][i] for i in idx if var in h and h[var][i] is not None]

    temp, gust, viento = serie("temperature_2m"), serie("wind_gusts_10m"), serie("wind_speed_10m")
    prec, prob, hum = serie("precipitation"), serie("precipitation_probability"), serie("relative_humidity_2m")
    return {
        "temperatura": round(sum(temp) / len(temp), 2) if temp else None,
        "temperatura_min": min(temp) if temp else None,
        "temperatura_max": max(temp) if temp else None,
        "humedad": round(sum(hum) / len(hum), 1) if hum else None,
        "viento": max(viento) if viento else None,
        "rafaga": max(gust) if gust else None,
        "precipitacion_mm": round(sum(prec), 2) if prec else None,
        "lluvia_mm_h": max(prec) if prec else None,
        "prob_lluvia": max(prob) if prob else None,
        "horas": len(idx),
    }


def main():
    ap = argparse.ArgumentParser(description="Condiciones de Open-Meteo en cada cámara para la ventana de la mañana.")
    ap.add_argument("--fecha", default=os.getenv("ESCENARIO_FECHA") or None,
                    help="YYYY-MM-DD: usa el histórico de esa mañana; sin fecha, el pronóstico de la próxima mañana")
    args = ap.parse_args()
    fecha = date.fromisoformat(args.fecha) if args.fecha else None
    inicio_min, largo_h = ventana_cfg()
    lim = limites()
    camaras = leer_camaras()
    modo = "historico" if fecha else "pronostico"
    print(f"Consultando Open-Meteo ({modo}) para {len(camaras)} cámaras")
    respuestas = consultar(camaras, fecha)
    if len(respuestas) != len(camaras):
        sys.exit(f"Open-Meteo devolvió {len(respuestas)} respuestas para {len(camaras)} cámaras.")

    lecturas, dia_ventana, ventana = [], None, None
    for nodo, r in zip(camaras, respuestas):
        dia, amanecer, horas = horas_ventana(r, fecha, inicio_min, largo_h)
        dia_ventana = dia_ventana or dia
        ventana = ventana or (horas[0] if horas else None, horas[-1] if horas else None)
        lec = {"nodo_id": nodo["id"], "nombre": nodo.get("nombre"), "lat": nodo["lat"], "lon": nodo["lon"],
               "fecha": dia, "amanecer": amanecer.isoformat() if amanecer else None, **resumir(r, horas)}
        motivos = []
        if lec["rafaga"] is not None and lec["rafaga"] > lim["rafaga_max_ms"]:
            motivos.append(f"ráfaga {lec['rafaga']:.1f} m/s a 10 m")
        if lec["temperatura_min"] is not None and lec["temperatura_min"] < lim["temperatura_min_c"]:
            motivos.append(f"temperatura {lec['temperatura_min']:.1f} °C")
        if lec["temperatura_max"] is not None and lec["temperatura_max"] > lim["temperatura_max_c"]:
            motivos.append(f"temperatura {lec['temperatura_max']:.1f} °C")
        if (lec["precipitacion_mm"] or 0) > 0:
            motivos.append(f"lluvia {lec['precipitacion_mm']:.1f} mm")
        lec["evitar"] = bool(motivos)
        lec["motivo"] = "; ".join(motivos) or "dentro de los límites del dron"
        lecturas.append(lec)

    documento = {
        "meta": {
            "fuente": "Open-Meteo " + ("Historical Weather API (reanálisis)" if fecha else "Weather Forecast API"),
            "endpoint": API_HISTORICO if fecha else API_PRONOSTICO,
            "modo": modo,
            "fecha_escenario": dia_ventana,
            "ventana": {"inicio": ventana[0] if ventana else None, "ultima_hora": ventana[1] if ventana else None,
                        "regla": f"{largo_h} horas desde la primera hora completa {inicio_min} min después del amanecer"},
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "variables": VARIABLES + ([] if fecha else ["precipitation_probability"]),
            "unidad_viento": "m/s",
            "unidad_lluvia": "mm/h",
            "resumen_ventana": (
                "Por cámara se guarda la peor hora de la ventana: ráfaga y viento máximos, temperatura mínima "
                "y máxima, lluvia acumulada y máxima, y la mayor probabilidad de lluvia (solo pronóstico)."
            ),
            "limites_dron": lim,
            "n_lecturas": len(lecturas),
            "n_evitar": sum(1 for x in lecturas if x["evitar"]),
        },
        "lecturas": lecturas,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    rafagas = [x["rafaga"] for x in lecturas if x["rafaga"] is not None]
    if rafagas:
        print(f"Mañana del {dia_ventana}: ráfaga entre {min(rafagas):.1f} y {max(rafagas):.1f} m/s a 10 m.")
    print(f"Lecturas: {len(lecturas)} | con alguna condición fuera de límites: {documento['meta']['n_evitar']}")
    print(f"Escrito: {SALIDA}")


if __name__ == "__main__":
    main()
