import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "Motor"))
sys.path.insert(0, str(RAIZ / "experimentos"))

import numpy as np

from aves_historicas import CACHE, dia
from hotspots_sectores import pedir
from motor import escenarios, grafo
from motor.config import cargar_env

RES = RAIZ / "experimentos" / "resultados"
VENTANA = 14
RADIO_M = 5000
CANDIDATAS = 10


def fecha_lista(x) -> str:
    from datetime import datetime

    texto = str(x.get("obsDt") or x.get("obsDate") or "").strip()
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(texto[:11] if fmt == "%d %b %Y" else texto[:len(fmt) + 2], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def dia_con_reintentos(token, dd, bbox, region):
    for intento in range(10):
        try:
            return dia(token, dd, bbox, region)
        except Exception as exc:
            if "429" not in str(exc) or intento == 9:
                raise
            time.sleep(60)


def main(sector: int = 20, region: str = "CL-LL-CHA"):
    cargar_env()
    token = os.getenv("EBIRD_API_KEY", "").strip()
    esc = grafo.desde_repo()
    hs = json.loads((RES / "E10b_hotspots.json").read_text(encoding="utf-8"))[str(sector)]
    cams = [grafo.xy(esc.nodos[c]["lon"], esc.nodos[c]["lat"]) for c in hs["camaras"]]
    listas = []
    for h in hs["hotspots"]:
        r = pedir(f"https://api.ebird.org/v2/product/lists/{h['locId']}", {"maxResults": 200}, token)
        listas += [{"hotspot": h["nombre"], "fecha": fecha_lista(x)} for x in r]
        time.sleep(2)
    fechas = Counter(date.fromisoformat(x["fecha"]) for x in listas if x["fecha"])
    ventanas = Counter()
    for f in fechas:
        for k in range(VENTANA):
            ventanas[f + timedelta(days=k)] += fechas[f]
    candidatas = []
    for d, _ in ventanas.most_common():
        if d < date.today() and all(abs((d - c).days) >= VENTANA for c in candidatas):
            candidatas.append(d)
        if len(candidatas) == CANDIDATAS:
            break
    bbox = escenarios._bbox(esc)
    (CACHE / region).mkdir(parents=True, exist_ok=True)
    filas = []
    for d in candidatas:
        ids = {}
        for k in range(VENTANA):
            dd = d - timedelta(days=k)
            for a in dia_con_reintentos(token, dd, bbox, region):
                p = grafo.xy(a["lon"], a["lat"])
                if min(float(np.linalg.norm(p - c)) for c in cams) <= RADIO_M:
                    ids[a["id"]] = a
            time.sleep(1)
        filas.append({"sector": sector, "fecha": d.isoformat(), "listas_en_hotspots": ventanas[d],
                      "avistamientos_a_5km": len(ids),
                      "especies": "; ".join(f"{a['comun']} ({a['cantidad']})" for a in ids.values())})
        print(filas[-1], flush=True)
    filas.sort(key=lambda f: (-f["avistamientos_a_5km"], -f["listas_en_hotspots"]))
    with (RES / "E10b_fechas_aves.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    (RES / "E10b_listas_hotspots.json").write_text(json.dumps({"listas": listas}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Listas en hotspots: {len(listas)} | fechas con listas: {len(fechas)} | candidatas revisadas: {len(candidatas)}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
