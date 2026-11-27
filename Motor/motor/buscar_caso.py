import argparse
import json
import random
from datetime import date, timedelta

import numpy as np
from pyproj import Transformer

from . import escenarios, grafo, servicio
from .config import CONFIG, RESULTADOS, fuente_por_defecto
from .mision import sectores as mod_sectores

FECHAS_JSON = RESULTADOS / "fechas_firms.json"
CASO_JSON = CONFIG / "caso_ejemplo.json"
RADIO_BUSQUEDA_M = 3000
MEJORA_MINIMA = 0.01
_A_GEO = Transformer.from_crs(grafo.CRS_METRICO, "EPSG:4326", always_xy=True)


def fechas_con_focos(esc, desde: date, hasta: date, radio_m: float = RADIO_BUSQUEDA_M) -> list:
    previas = json.loads(FECHAS_JSON.read_text(encoding="utf-8")) if FECHAS_JSON.exists() else {"revisado_hasta": None, "fechas": {}}
    inicio = date.fromisoformat(previas["revisado_hasta"]) + timedelta(days=1) if previas["revisado_hasta"] else desde
    camaras = [grafo.xy(esc.nodos[c]["lon"], esc.nodos[c]["lat"]) for c in esc.camaras()]
    d = inicio
    while d <= hasta:
        try:
            focos, _ = escenarios.focos(esc, d + timedelta(days=4), dias=5)
        except Exception as exc:
            print(f"  {d}: {exc}")
            break
        for f in focos:
            p = grafo.xy(f["lon"], f["lat"])
            dmin = min(float(np.linalg.norm(p - c)) for c in camaras)
            if dmin <= radio_m:
                previas["fechas"].setdefault(f["fecha"], {"n": 0, "dmin_m": dmin})
                previas["fechas"][f["fecha"]]["n"] += 1
                previas["fechas"][f["fecha"]]["dmin_m"] = min(previas["fechas"][f["fecha"]]["dmin_m"], dmin)
        previas["revisado_hasta"] = (d + timedelta(days=4)).isoformat()
        d += timedelta(days=5)
        if d.month == 1 and d.day <= 5:
            FECHAS_JSON.write_text(json.dumps(previas, indent=1), encoding="utf-8")
            print(f"  revisado hasta {d.year - 1}: {len(previas['fechas'])} fechas con focos a ≤ {radio_m:.0f} m")
    RESULTADOS.mkdir(exist_ok=True)
    FECHAS_JSON.write_text(json.dumps(previas, indent=1), encoding="utf-8")
    return sorted(previas["fechas"], key=lambda f: (previas["fechas"][f]["dmin_m"], f))


def firma(plan: dict) -> tuple:
    return tuple(tuple(v["camaras"]) + tuple(v["aristas"]) for v in plan["vuelos"])


def puntaje(res: dict) -> dict:
    planes = {p["tecnica"]: p for p in res["planes"]}
    if len(planes) < 4 or not all(p["vuelos"] for p in planes.values()):
        return {"distintas": 0, "valido": False}
    firmas = {t: firma(p) for t, p in planes.items()}
    distintas = len(set(firmas.values()))
    tramos = [set(a for v in p["vuelos"] for a in v["aristas"]) for p in planes.values()]
    union = set().union(*tramos)
    comunes = set.intersection(*tramos) if tramos else set()
    no_compartidos = 1 - len(comunes) / len(union) if union else 0.0
    r1 = planes["dijkstra_distancia"]["R"] or 0.0
    r2 = planes["milp"]["R"] or 0.0
    menor_r1 = r1 <= min(p["R"] or 0 for p in planes.values()) + 1e-12
    orden_o_reparto = [tuple(v["camaras"]) for v in planes["dijkstra_ponderado"]["vuelos"]] != \
                      [tuple(v["camaras"]) for v in planes["milp"]["vuelos"]]
    return {"distintas": distintas, "no_compartidos": round(no_compartidos, 3), "mejora_R": round(r2 - r1, 4),
            "tecnica1_menor_R": menor_r1, "t3_difiere_de_gurobi": orden_o_reparto,
            "aco_igual_gurobi": firmas["aco"] == firmas["milp"], "valido": True}


def evaluar(esc, consulta: dict) -> tuple[dict, dict]:
    res = servicio.planificar(consulta, esc, n_mc=2000)
    return res, puntaje(res)


def candidatos_sector(esc, minimo=2) -> list:
    return [s for s in mod_sectores.leer_sectores(esc) if s["base"] and s["n_camaras"] >= minimo]


def buscar_historico(esc, fechas: list, restricciones: dict, limite: int = 40) -> list:
    hallazgos = []
    for f in fechas[:limite]:
        try:
            esc_f = escenarios.aplicar(esc, f)
        except Exception as exc:
            print(f"  {f}: no se pudo cargar el escenario ({exc})")
            continue
        for s in candidatos_sector(esc_f):
            consulta = {"modo": "sector", "sector_id": s["id"], "fecha": None, "restricciones": restricciones}
            res, pts = evaluar(esc_f, consulta)
            if pts["valido"]:
                hallazgos.append({"fecha": f, "sector": s["id"], "consulta": {**consulta, "fecha": f}, **pts})
    return hallazgos


def buscar_simulado(esc, fecha: str, restricciones: dict, intentos: int = 20, semilla: int = 0) -> list:
    rng = random.Random(semilla)
    esc_f = escenarios.aplicar(esc, fecha)
    hallazgos = []
    for s in candidatos_sector(esc_f):
        r0 = servicio.planificar({"modo": "sector", "sector_id": s["id"], "restricciones": restricciones}, esc_f, n_mc=500)
        aristas_t1 = [a for v in r0["planes"][0]["vuelos"] for a in v["aristas"]]
        if not aristas_t1:
            continue
        for _ in range(intentos):
            aid = rng.choice(aristas_t1)
            coords = esc_f.aristas[aid]["coords"]
            a, b = grafo.xy(*coords[0]), grafo.xy(*coords[-1])
            medio = (a + b) / 2
            normal = np.array([-(b - a)[1], (b - a)[0]])
            normal = normal / (np.linalg.norm(normal) or 1.0)
            desplazamiento = rng.choice((0.0, 500.0, -500.0, 800.0, -800.0))
            lon, lat = _A_GEO.transform(*(medio + desplazamiento * normal))
            foco = {"id": 9001, "lon": round(lon, 6), "lat": round(lat, 6), "confidence": "n", "fecha": fecha}
            consulta = {"modo": "sector", "sector_id": s["id"], "restricciones": restricciones,
                        "focos_simulados": [foco]}
            res, pts = evaluar(esc_f, consulta)
            if pts["valido"]:
                hallazgos.append({"fecha": fecha, "sector": s["id"], "foco_simulado": foco, "arista": aid,
                                  "desplazamiento_m": desplazamiento,
                                  "consulta": {**consulta, "fecha": fecha}, **pts})
    return hallazgos


def ordenar(hallazgos: list) -> list:
    return sorted(hallazgos, key=lambda h: (-h["distintas"], not h["tecnica1_menor_R"], not h["t3_difiere_de_gurobi"],
                                            -h["no_compartidos"], -h["mejora_R"]))


def main():
    ap = argparse.ArgumentParser(description="Busca un caso real donde las cuatro técnicas planifican distinto.")
    ap.add_argument("--desde", default="2012-01-20")
    ap.add_argument("--hasta", default=None)
    ap.add_argument("--fecha-simulado", default=None, help="fecha histórica para el escenario mixto si no hay caso real")
    ap.add_argument("--solo-simulado", action="store_true")
    ap.add_argument("--limite", type=int, default=15, help="fechas históricas a probar, de la más cercana a la más lejana")
    args = ap.parse_args()
    esc = grafo.cargar(fuente_por_defecto(), usar_cache=False)
    restricciones = {"solo_bosque": True}
    hasta = date.fromisoformat(args.hasta) if args.hasta else date.today() - timedelta(days=1)

    hallazgos = []
    if not args.solo_simulado:
        print("1. Fechas con focos FIRMS a ≤ 3 km de las cámaras")
        fechas = fechas_con_focos(esc, date.fromisoformat(args.desde), hasta)
        print(f"   {len(fechas)} fechas: {fechas[:12]}{' …' if len(fechas) > 12 else ''}")
        print("2. Las cuatro técnicas en cada fecha y sector")
        hallazgos = buscar_historico(esc, fechas, restricciones, args.limite)
    reales = [h for h in hallazgos if h["distintas"] >= 3 and h["tecnica1_menor_R"] and h["mejora_R"] >= MEJORA_MINIMA]
    busqueda = {"fechas_probadas": len({h["fecha"] for h in hallazgos}), "casos_probados": len(hallazgos),
                "con_planes_distintos": sum(1 for h in hallazgos if h["distintas"] >= 3),
                "mejor_mejora_R": max([h["mejora_R"] for h in hallazgos] + [0.0])}
    if args.solo_simulado and CASO_JSON.exists():
        busqueda = json.loads(CASO_JSON.read_text(encoding="utf-8")).get("busqueda_real", busqueda)
    if reales:
        elegido = {**ordenar(reales)[0], "simulado": False, "busqueda_real": busqueda}
    else:
        fecha = args.fecha_simulado or (ordenar(hallazgos)[0]["fecha"] if hallazgos else
                                        (date.today() - timedelta(days=30)).isoformat())
        print(f"3. Sin caso real útil: escenario mixto con clima y aves reales del {fecha} y un foco simulado")
        simulados = buscar_simulado(esc, fecha, restricciones)
        if not simulados:
            print("No se encontró ningún caso.")
            return
        pool = ([h for h in simulados if h["distintas"] >= 3 and h["mejora_R"] >= 0.05]
                or [h for h in simulados if h["mejora_R"] >= MEJORA_MINIMA] or simulados)
        elegido = {**ordenar(pool)[0], "simulado": True, "busqueda_real": busqueda,
                   "nota": ("El foco de incendio es simulado; el clima y las aves son reales de esa fecha. "
                            f"En las {busqueda['fechas_probadas']} fechas reales con focos más cercanos a las cámaras "
                            "ningún foco cambió la resiliencia de los planes.")}
    CASO_JSON.write_text(json.dumps(elegido, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Caso elegido: sector {elegido['sector']} del {elegido['fecha']} · {elegido['distintas']} planes distintos · "
          f"ΔR = {elegido['mejora_R']} · {'simulado' if elegido['simulado'] else 'real'}. Escrito: {CASO_JSON.name}")


if __name__ == "__main__":
    main()
