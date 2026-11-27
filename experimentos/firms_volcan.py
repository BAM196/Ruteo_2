import csv
import io
import json
import math
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "Motor"))

import numpy as np

from motor import escenarios, grafo
from motor.config import cargar_env

RES = RAIZ / "experimentos" / "resultados"
CRUDO = RES / "E3b_firms_sp_3km.csv"
SALIDA = RES / "E3b_volcan.json"
DOMO = {"lat": -42.8349, "lon": -72.6514, "fuente": "Smithsonian GVP, volcán 358041 (WFS GVP-VOTW)"}
RADIO_CAMARA_M = 3000
TIPOS = {"0": "incendio de vegetación presunto", "1": "volcán activo", "2": "otra fuente estática terrestre", "3": "costa afuera"}


CACHE = RES / "firms_sp"


def ventana(key, desde: date, area: str):
    ruta = CACHE / f"{desde.isoformat()}.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    url = f"{escenarios.API_FIRMS}/{key}/VIIRS_SNPP_SP/{area}/5/{desde.isoformat()}"
    for intento in range(6):
        try:
            texto = escenarios._get(url).decode("utf-8", "replace").strip()
            filas = list(csv.DictReader(io.StringIO(texto))) if texto and "latitude" in texto[:200] else []
            ruta.write_text(json.dumps(filas), encoding="utf-8")
            return filas
        except Exception:
            time.sleep(10 * (intento + 1))
    return None


def recorrer(esc, key, desde: date, hasta: date):
    area = ",".join(f"{v:.4f}" for v in escenarios._bbox(esc))
    cams = {c: grafo.xy(esc.nodos[c]["lon"], esc.nodos[c]["lat"]) for c in esc.camaras()}
    inicios = [desde + timedelta(days=5 * k) for k in range((hasta - desde).days // 5 + 1)]
    filas = []

    fallidas = []

    def una(d):
        salida = []
        crudas = ventana(key, d, area)
        if crudas is None:
            fallidas.append(d.isoformat())
            return salida
        for f in crudas:
            p = grafo.xy(float(f["longitude"]), float(f["latitude"]))
            dist = {c: float(np.linalg.norm(p - xy)) for c, xy in cams.items()}
            cam = min(dist, key=dist.get)
            if dist[cam] <= RADIO_CAMARA_M:
                salida.append({"acq_date": f["acq_date"], "acq_time": f.get("acq_time"), "lat": f["latitude"],
                               "lon": f["longitude"], "confidence": f.get("confidence"), "frp": f.get("frp"),
                               "daynight": f.get("daynight"), "type": f.get("type", ""),
                               "camara_mas_cercana": esc.nodos[cam]["nombre"], "dist_camara_m": round(dist[cam], 1)})
        return salida

    with ThreadPoolExecutor(max_workers=4) as ex:
        for k, lista in enumerate(ex.map(una, inicios), start=1):
            filas += lista
            if k % 100 == 0:
                print(f"  {k}/{len(inicios)} ventanas", flush=True)
    if fallidas:
        raise SystemExit(f"Ventanas sin respuesta ({len(fallidas)}): {fallidas[:10]}. Vuelve a correr para completarlas.")
    return filas, len(inicios)


def main():
    cargar_env()
    key = os.getenv("FIRMS_MAP_KEY", "").strip()
    esc = grafo.desde_repo()
    CACHE.mkdir(parents=True, exist_ok=True)
    if CRUDO.exists():
        filas = list(csv.DictReader(CRUDO.open(encoding="utf-8")))
        ventanas = None
    else:
        filas, ventanas = recorrer(esc, key, date(2012, 1, 20), date(2026, 11, 26))
        vistos, unicas = set(), []
        for f in filas:
            k = (f["acq_date"], f["acq_time"], f["lat"], f["lon"])
            if k not in vistos:
                vistos.add(k)
                unicas.append(f)
        filas = unicas
        with CRUDO.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0]) if filas else ["acq_date"])
            w.writeheader()
            w.writerows(filas)
    domo = grafo.xy(DOMO["lon"], DOMO["lat"])
    for f in filas:
        f["dist_domo_m"] = round(float(np.linalg.norm(grafo.xy(float(f["lon"]), float(f["lat"])) - domo)), 1)
    a1 = [f for f in filas if f["dist_domo_m"] <= 1000]
    a375 = [f for f in filas if f["dist_domo_m"] <= 375 * math.sqrt(2) / 2 + 1000]
    camaras = [esc.nodos[c] for c in esc.camaras()]
    cam_domo = sorted((float(np.linalg.norm(grafo.xy(c["lon"], c["lat"]) - domo)), c["nombre"]) for c in camaras)[:3]
    f2015 = [f for f in filas if f["acq_date"] == "2015-02-27"]
    resumen = {
        "domo": DOMO,
        "ventanas_consultadas": ventanas,
        "focos_a_3km_de_una_camara": len(filas),
        "fechas_distintas": len({f["acq_date"] for f in filas}),
        "tipos": {TIPOS.get(str(k), k or "sin columna type"): v for k, v in Counter(f["type"] for f in filas).items()},
        "focos_a_1km_del_domo": len(a1),
        "tipos_a_1km_del_domo": {TIPOS.get(str(k), k or "sin columna type"): v for k, v in Counter(f["type"] for f in a1).items()},
        "anios_a_1km_del_domo": dict(sorted(Counter(f["acq_date"][:4] for f in a1).items())),
        "anios_todos": dict(sorted(Counter(f["acq_date"][:4] for f in filas).items())),
        "focos_fuera_de_1km_del_domo": len(filas) - len(a1),
        "dist_domo_m": {"min": min((f["dist_domo_m"] for f in filas), default=None),
                        "mediana": float(np.median([f["dist_domo_m"] for f in filas])) if filas else None,
                        "max": max((f["dist_domo_m"] for f in filas), default=None)},
        "dist_camara_m_de_los_focos_del_domo": {"min": min((float(f["dist_camara_m"]) for f in a1), default=None),
                                               "max": max((float(f["dist_camara_m"]) for f in a1), default=None)},
        "camaras_mas_cercanas_al_domo": [{"camara": n, "dist_m": round(d)} for d, n in cam_domo],
        "foco_2015_02_27": f2015,
        "focos_a_1_7km_del_domo": len(a375),
    }
    SALIDA.write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumen.items() if k != "foco_2015_02_27"}, ensure_ascii=False, indent=1))
    print("27-02-2015:", json.dumps(f2015, ensure_ascii=False))


if __name__ == "__main__":
    main()
