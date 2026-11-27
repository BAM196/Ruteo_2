import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "Motor"))

import numpy as np

from motor import escenarios, grafo
from motor.config import cargar_env
from motor.mision import sectores as msec

CACHE = RAIZ / "experimentos" / "resultados" / "ebird_diario"
SALIDA = RAIZ / "experimentos" / "resultados" / "E10b_fechas_aves.csv"
RADIO_M = 5000
VENTANA = 14


def dia(token, d: date, bbox, region) -> list:
    ruta = CACHE / region / f"{d.isoformat()}.json"
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    crudos = json.loads(escenarios._get(f"{escenarios.API_EBIRD}/{region}/historic/{d.year}/{d.month}/{d.day}",
                                        {"rank": "mrec", "detail": "simple"}, {"X-eBirdApiToken": token}))
    oeste, sur, este, norte = bbox
    filtrados = [{"id": f"{o.get('subId')}:{o.get('speciesCode')}", "lon": o["lng"], "lat": o["lat"],
                  "cientifico": o.get("sciName"), "comun": o.get("comName"), "cantidad": o.get("howMany") or 1,
                  "fecha_obs": o.get("obsDt")}
                 for o in crudos if "lat" in o and any((o.get("sciName") or "").lower().startswith(g) for g in escenarios.GENEROS_AVES)
                 and oeste <= o["lng"] <= este and sur <= o["lat"] <= norte]
    ruta.write_text(json.dumps(filtrados, ensure_ascii=False), encoding="utf-8")
    return filtrados


def main():
    ap = argparse.ArgumentParser(description="Fechas con avistamientos de eBird cerca de cada sector.")
    ap.add_argument("--desde", default="2016-01-01")
    ap.add_argument("--hasta", default="2025-12-31")
    ap.add_argument("--hilos", type=int, default=3)
    ap.add_argument("--regiones", default="CL-LL-CHA,CL-LL-HUA",
                    help="comunas de eBird que cubren el parque: Chaitén y Hualaihué")
    args = ap.parse_args()
    cargar_env()
    token = os.getenv("EBIRD_API_KEY", "").strip()
    if not token:
        sys.exit("Falta EBIRD_API_KEY.")
    for region in args.regiones.split(","):
        (CACHE / region).mkdir(parents=True, exist_ok=True)
    esc = grafo.desde_repo()
    bbox = escenarios._bbox(esc)
    d, fin = date.fromisoformat(args.desde), date.fromisoformat(args.hasta)
    fechas = [d + timedelta(days=k) for k in range((fin - d).days + 1)]

    fallidos = []

    def bajar(dd):
        lista = []
        for region in args.regiones.split(","):
            for intento in range(8):
                try:
                    lista += dia(token, dd, bbox, region)
                    break
                except Exception as exc:
                    time.sleep(10 * (intento + 1) if "429" in str(exc) else 3)
                    if intento == 7:
                        fallidos.append((dd.isoformat(), region, str(exc)))
        return dd, lista

    from concurrent.futures import ThreadPoolExecutor

    por_dia = {}
    with ThreadPoolExecutor(max_workers=args.hilos) as ex:
        for k, (dd, lista) in enumerate(ex.map(bajar, fechas), start=1):
            por_dia[dd] = lista
            if k % 365 == 0:
                print(f"  {k}/{len(fechas)} días", flush=True)
    sectores = [s for s in msec.leer_sectores(esc) if s["base"] and s["n_camaras"] >= 2]
    cams = {s["id"]: [grafo.xy(esc.nodos[c]["lon"], esc.nodos[c]["lat"]) for c in s["camaras"]] for s in sectores}
    cerca = {}
    for dd, lista in por_dia.items():
        for a in lista:
            p = grafo.xy(a["lon"], a["lat"])
            for sid, cs in cams.items():
                if min(float(np.linalg.norm(p - c)) for c in cs) <= RADIO_M:
                    cerca.setdefault(sid, {}).setdefault(dd, set()).add(a["id"])
    filas = []
    dias = sorted(por_dia)
    for sid in cams:
        serie = cerca.get(sid, {})
        for dd in dias:
            ids = set().union(*[serie.get(dd - timedelta(days=k), set()) for k in range(VENTANA)])
            if ids:
                filas.append({"sector": sid, "fecha": dd.isoformat(), "avistamientos_a_5km": len(ids)})
    filas.sort(key=lambda f: (-f["avistamientos_a_5km"], f["sector"], f["fecha"]))
    import csv

    with SALIDA.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sector", "fecha", "avistamientos_a_5km"])
        w.writeheader()
        w.writerows(filas)
    total = sum(len(v) for v in por_dia.values())
    print(f"Días revisados: {len(dias)} | comunas {args.regiones} | avistamientos filtrados en el parque: {total} | "
          f"consultas fallidas: {len(fallidos)}")
    for sid in cams:
        mejores = [f for f in filas if f["sector"] == sid][:1]
        print(f"  sector {sid}: " + (f"{mejores[0]['avistamientos_a_5km']} el {mejores[0]['fecha']}" if mejores else "sin avistamientos a 5 km"))


if __name__ == "__main__":
    main()
