import argparse
import json
import math

import numpy as np

from . import grafo
from .config import RAIZ, RESULTADOS, fuente_por_defecto, parametros_mision
from .mision import sectores as mod_sectores

TRASLADOS_JSON = RAIZ / "Infraestructura" / "traslados_bases.json"


def tiempo_sector_s(sector: dict, esc, m: dict) -> tuple[float, int]:
    from . import probabilidades
    from .config import amenazas_cfg
    from .rutas import dijkstra_distancia
    from .rutas.comun import Consulta, Contexto, ProblemaSector

    if not sector.get("base"):
        return math.nan, 0
    base = esc.bases[sector["base"]["id"]]
    cfg = amenazas_cfg()
    ctx = Contexto(esc, probabilidades.calcular(esc.copia_amenazas(focos=[], aves=[], meteo={}), cfg),
                   Consulta(), cfg["cota_superior"], m)
    prob = ProblemaSector(ctx, base, sector["camaras"], sector["id"])
    r = dijkstra_distancia.resolver(prob)
    if not r["total"]:
        return math.nan, 0
    return r["total"]["tiempo_sector"], len(r["vuelos"])


def traslados(sectores: list, m: dict) -> dict:
    if TRASLADOS_JSON.exists():
        doc = json.loads(TRASLADOS_JSON.read_text(encoding="utf-8"))
        return {(p["base_i"], p["base_j"]): p["total_min"] * 60 for p in doc["pares"]} | \
               {(p["base_j"], p["base_i"]): p["total_min"] * 60 for p in doc["pares"]}
    salida = {}
    bases = [s["base"] for s in sectores if s.get("base")]
    for a in bases:
        for b in bases:
            if a["id"] != b["id"]:
                d = float(np.linalg.norm(grafo.xy(a["lon"], a["lat"]) - grafo.xy(b["lon"], b["lat"])))
                salida[(a["id"], b["id"])] = d / (m["v_pie_kmh"] / 3.6)
    return salida


def mananas(sectores: list, tiempos: dict, t_tras: dict, m: dict) -> list:
    ventana = m["ventana_h"] * 3600
    pendientes = [s for s in sectores if not math.isnan(tiempos.get(s["id"], math.nan))]
    salida = []
    while pendientes:
        actual = pendientes.pop(0)
        dia, usado = [actual["id"]], tiempos[actual["id"]]
        while True:
            opciones = []
            for s in pendientes:
                t = t_tras.get((actual["base"]["id"], s["base"]["id"]), math.inf)
                if usado + t + tiempos[s["id"]] <= ventana:
                    opciones.append((t, s))
            if not opciones:
                break
            t, s = min(opciones, key=lambda o: o[0])
            dia.append(s["id"])
            usado += t + tiempos[s["id"]]
            pendientes.remove(s)
            actual = s
        salida.append({"sectores": dia, "tiempo_min": round(usado / 60, 1)})
    return salida


def asignar(sectores: list, dias: int, pendientes_previos: list, m: dict, tiempos: dict, t_tras: dict,
            fraccion: float | None = None) -> dict:
    fraccion = m["fraccion_prioridad"] if fraccion is None else fraccion
    visitas = m["visitas"]
    validos = [s for s in sectores if not math.isnan(tiempos.get(s["id"], math.nan))]
    todas = mananas(sorted(validos, key=lambda s: -s["prioridad"]), tiempos, t_tras, m)
    dias_pasada = visitas * len(todas)
    if dias >= dias_pasada:
        return {"cubre_parque": True, "dias_por_pasada": dias_pasada, "mananas": todas,
                "sectores": [s["id"] for s in validos], "por_prioridad": [], "por_rotacion": [],
                "pendientes": [], "campanas_parciales": []}
    if dias < visitas:
        prim = sorted(validos, key=lambda s: (s["id"] not in pendientes_previos, -s["prioridad"]))[:1]
        return {"cubre_parque": False, "dias_por_pasada": dias_pasada, "mananas": [],
                "sectores": [], "por_prioridad": [], "por_rotacion": [], "pendientes": [s["id"] for s in validos],
                "campanas_parciales": [{"sector": prim[0]["id"], "visitas": dias, "incompleta": True}] if prim and dias else []}
    elegidos, usados = [], 0
    presupuesto_prio = int(dias * fraccion)
    for s in sorted(validos, key=lambda s: -s["prioridad"]):
        costo = visitas * len(mananas([s], tiempos, t_tras, m))
        if usados + costo > presupuesto_prio:
            break
        elegidos.append(s)
        usados += costo
    prioritarios = [s["id"] for s in elegidos]
    resto = [s for s in validos if s not in elegidos]
    rotacion = sorted(resto, key=lambda s: (s["id"] not in pendientes_previos, -s["prioridad"]))
    for s in rotacion:
        prueba = mananas(elegidos + [s], tiempos, t_tras, m)
        if visitas * len(prueba) <= dias:
            elegidos.append(s)
    plan = mananas(sorted(elegidos, key=lambda s: -s["prioridad"]), tiempos, t_tras, m)
    ids = [s["id"] for s in elegidos]
    return {"cubre_parque": False, "dias_por_pasada": dias_pasada, "mananas": plan, "sectores": ids,
            "por_prioridad": prioritarios, "por_rotacion": [x for x in ids if x not in prioritarios],
            "pendientes": [s["id"] for s in validos if s["id"] not in ids], "campanas_parciales": []}


def informe(esc, dias_por_temporada: dict | None = None, m: dict | None = None) -> dict:
    m = m or parametros_mision()
    sectores = mod_sectores.leer_sectores(esc)
    tiempos, vuelos = {}, {}
    for s in sectores:
        tiempos[s["id"]], vuelos[s["id"]] = tiempo_sector_s(s, esc, m)
    t_tras = traslados(sectores, m)
    validos = [s for s in sectores if not math.isnan(tiempos[s["id"]])]
    pasada = mananas(sorted(validos, key=lambda s: -s["prioridad"]), tiempos, t_tras, m)
    dias_pasada = m["visitas"] * len(pasada)
    dias_por_temporada = dias_por_temporada or {"verano": 51, "otono": 36, "invierno": 25, "primavera": 37}
    rondas, pendientes = {}, []
    for temporada, dias in dias_por_temporada.items():
        r = asignar(sectores, int(dias), pendientes, m, tiempos, t_tras)
        pendientes = r["pendientes"]
        rondas[temporada] = {"dias": dias, **r}
    por_ronda = [max(1, len(r["sectores"])) for r in rondas.values()]
    return {
        "sectores": [{"id": s["id"], "camaras": s["camaras"], "vuelos": vuelos[s["id"]],
                      "tiempo_min": None if math.isnan(tiempos[s["id"]]) else round(tiempos[s["id"]] / 60, 1),
                      "prioridad": s["prioridad"]} for s in sectores],
        "horas_vuelo_parque": round(sum(t for t in tiempos.values() if not math.isnan(t)) / 3600, 2),
        "mananas_por_pasada": len(pasada),
        "dias_por_pasada": dias_pasada,
        "mananas": pasada,
        "rondas": rondas,
        "rondas_para_cubrir_parque": round(len(validos) / (sum(por_ronda) / len(por_ronda)), 2),
        "traslados": "medidos (Infraestructura/traslados_bases.json)" if TRASLADOS_JSON.exists()
                     else f"línea recta a {m['v_pie_kmh']:.0f} km/h (no hay traslados medidos)",
        "reglas": {
            "manana": "Cada mañana agrupa sectores cercanos sin pasarse de la ventana: Σ T_s + Σ traslados ≤ T_ventana",
            "pasada": "días por pasada = visitas · mañanas",
            "ronda": ("Si los días alcanzan, la ronda cubre el parque. Si no, la mitad de los días va a los sectores "
                      "de mayor prioridad y el resto a la rotación de pendientes."),
        },
    }


def main():
    ap = argparse.ArgumentParser(description="Capacidad del equipo: mañanas, días por pasada y rondas.")
    ap.add_argument("--fuente", choices=["db", "json"], default=None)
    args = ap.parse_args()
    esc = grafo.cargar(args.fuente or fuente_por_defecto(), usar_cache=False)
    doc = informe(esc)
    RESULTADOS.mkdir(exist_ok=True)
    (RESULTADOS / "capacidad.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Horas de vuelo del parque: {doc['horas_vuelo_parque']} h | mañanas por pasada: {doc['mananas_por_pasada']} "
          f"| días por pasada: {doc['dias_por_pasada']} | rondas para cubrir el parque: {doc['rondas_para_cubrir_parque']}")
    for t, r in doc["rondas"].items():
        print(f"  {t}: {r['dias']} días → {len(r['sectores'])} sectores, pendientes {len(r['pendientes'])}")


if __name__ == "__main__":
    main()
