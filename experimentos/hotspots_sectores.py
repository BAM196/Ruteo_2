import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "Motor"))

import numpy as np

from motor import escenarios, grafo
from motor.config import cargar_env
from motor.mision import sectores as msec

SALIDA = RAIZ / "experimentos" / "resultados" / "E10b_hotspots.json"


def pedir(url, params, token):
    for intento in range(10):
        try:
            return json.loads(escenarios._get(url, params, {"X-eBirdApiToken": token}))
        except Exception as exc:
            if "429" not in str(exc) or intento == 9:
                raise
            time.sleep(60)


def main():
    cargar_env()
    token = os.getenv("EBIRD_API_KEY", "").strip()
    esc = grafo.desde_repo()
    salida = {}
    for s in [x for x in msec.leer_sectores(esc) if x["base"] and x["n_camaras"] >= 2]:
        lat = float(np.mean([esc.nodos[c]["lat"] for c in s["camaras"]]))
        lon = float(np.mean([esc.nodos[c]["lon"] for c in s["camaras"]]))
        hs = pedir("https://api.ebird.org/v2/ref/hotspot/geo", {"lat": f"{lat:.4f}", "lng": f"{lon:.4f}", "dist": 6, "fmt": "json"}, token)
        cams = [grafo.xy(esc.nodos[c]["lon"], esc.nodos[c]["lat"]) for c in s["camaras"]]
        cerca = []
        for h in hs:
            d = min(float(np.linalg.norm(grafo.xy(h["lng"], h["lat"]) - c)) for c in cams)
            if d <= 5000:
                cerca.append({"locId": h["locId"], "nombre": h["locName"], "distancia_m": round(d), "ultima_obs": h.get("latestObsDt"),
                              "especies_total": h.get("numSpeciesAllTime"), "lat": h["lat"], "lon": h["lng"]})
        salida[s["id"]] = {"camaras": s["camaras"], "hotspots": cerca}
        print(s["id"], len(cerca), flush=True)
        time.sleep(3)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
