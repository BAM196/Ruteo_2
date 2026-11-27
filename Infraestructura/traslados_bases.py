import json
import math
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
SECTORES = RAIZ / "Motor" / "sectores.json"
MISION = RAIZ / "Motor" / "config" / "mision.yaml"
SALIDA = AQUI / "traslados_bases.json"
OSRM = "https://router.project-osrm.org/table/v1/driving/"


def valor(x):
    return x["valor"] if isinstance(x, dict) and "valor" in x else x


def haversine(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def main():
    cfg = yaml.safe_load(MISION.read_text(encoding="utf-8"))["traslados"]
    v_pie = float(valor(cfg["velocidad_pie_kmh"]))
    radio = float(valor(cfg["radio_vecinos_m"]))
    sectores = json.loads(SECTORES.read_text(encoding="utf-8"))["sectores"]
    bases = list({s["base"]["id"]: s["base"] for s in sectores if s.get("base")}.values())
    coords = ";".join(f"{b['lon']:.6f},{b['lat']:.6f}" for b in bases)
    print(f"Consultando OSRM para {len(bases)} bases")
    r = requests.get(OSRM + coords, params={"annotations": "duration,distance"}, timeout=120)
    r.raise_for_status()
    js = r.json()
    snap = [s["distance"] for s in js["sources"]]
    pares, sin_camino = [], 0
    for i, a in enumerate(bases):
        for j in range(i + 1, len(bases)):
            b = bases[j]
            recta = haversine(a, b)
            if recta > radio:
                continue
            dur, dist = js["durations"][i][j], js["distances"][i][j]
            if dur is None:
                sin_camino += 1
                continue
            pie_min = (snap[i] + snap[j]) / 1000 / v_pie * 60
            pares.append({"base_i": a["id"], "base_j": b["id"], "recta_km": round(recta / 1000, 2),
                          "auto_km": round(dist / 1000, 1), "auto_min": round(dur / 60, 1),
                          "pie_base_i_m": round(snap[i]), "pie_base_j_m": round(snap[j]),
                          "total_min": round(dur / 60 + pie_min, 1)})
    pares.sort(key=lambda p: p["total_min"])
    doc = {
        "meta": {
            "fuente": "OSRM (caminos de OpenStreetMap), router.project-osrm.org",
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "regla": (f"Tiempo en auto entre las bases más la caminata desde el punto de camino más cercano a "
                      f"{v_pie:.0f} km/h; solo pares a ≤ {radio / 1000:.0f} km en línea recta."),
            "limitacion": "OSRM no ve accesos por mar ni el estado real de los senderos.",
            "n_bases": len(bases),
            "n_pares": len(pares),
            "pares_sin_camino": sin_camino,
            "bases_a_mas_de_2_km_de_un_camino": sum(1 for s in snap if s > 2000),
        },
        "pares": pares,
    }
    SALIDA.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Pares medidos: {len(pares)} | ≤ 30 min: {sum(p['total_min'] <= 30 for p in pares)} | "
          f"bases a más de 2 km de un camino: {doc['meta']['bases_a_mas_de_2_km_de_un_camino']}. Escrito: {SALIDA.name}")


if __name__ == "__main__":
    main()
