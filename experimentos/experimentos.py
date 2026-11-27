import argparse
import copy
import csv
import itertools
import json
import math
import platform
import random
import statistics as st
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "Motor"))
sys.path.insert(0, str(RAIZ / "Infraestructura"))

import numpy as np

from motor import capacidad, evaluacion, grafo, probabilidades, programador, servicio
from motor.config import CONFIG, aco_cfg, amenazas_cfg, conectar, parametros_mision
from motor.mision import sectores as msec
from motor.rutas import aco, dijkstra_distancia, dijkstra_ponderado, milp
from motor.rutas.comun import Consulta, Contexto, ProblemaSector

RES = RAIZ / "experimentos" / "resultados"
FIG = RAIZ / "experimentos" / "img"
SEMILLA = 2026
TECNICAS = ("dijkstra_distancia", "milp", "dijkstra_ponderado", "aco")
CORTO = {"dijkstra_distancia": "T1 Dijkstra distancia", "milp": "T2 Gurobi", "dijkstra_ponderado": "T3 Dijkstra ponderado",
         "aco": "T4 ACO"}
RESUMEN = {}


def guardar(nombre: str, filas: list):
    if not filas:
        return
    claves = list(dict.fromkeys(k for f in filas for k in f))
    with (RES / nombre).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=claves)
        w.writeheader()
        w.writerows(filas)


def redondo(x, d=4):
    return None if x is None else round(float(x), d)


def nombre_camara(esc, c):
    return str(esc.nodos[c].get("nombre", c)).replace("Camara ", "")


def caso():
    return json.loads((CONFIG / "caso_ejemplo.json").read_text(encoding="utf-8"))


def entorno(esc):
    info = {"fecha_corrida": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "python": platform.python_version(), "plataforma": platform.platform(),
            "procesador": platform.processor() or platform.machine(), "nucleos": __import__("os").cpu_count()}
    try:
        with open("/proc/meminfo") as f:
            info["ram_contenedor_gb"] = round(int(f.readline().split()[1]) / 1024 ** 2, 1)
        with open("/proc/cpuinfo") as f:
            modelos = [l.split(":", 1)[1].strip() for l in f if l.startswith("model name")]
            if modelos:
                info["cpu"] = modelos[0]
    except OSError:
        pass
    try:
        with conectar() as c, c.cursor() as cur:
            cur.execute("SELECT version()")
            info["postgresql"] = cur.fetchone()[0].split(",")[0]
            cur.execute("SELECT postgis_lib_version()")
            info["postgis"] = cur.fetchone()[0]
            cur.execute("SELECT pgr_version()")
            info["pgrouting"] = cur.fetchone()[0]
    except Exception as exc:
        info["base"] = str(exc)
    import gurobipy

    info["gurobi"] = ".".join(map(str, gurobipy.gurobi.version()))
    info["semilla_banco"] = SEMILLA
    info["semilla_planes"] = 0
    info["escenario_cargado"] = esc.resumen()
    RESUMEN["entorno"] = info


def e0():
    from motor.config import mision_cfg, valor

    am = amenazas_cfg()["amenazas"]
    mi = mision_cfg()
    m = parametros_mision()
    filas = [
        ("v_c (crucero)", m["v_c"], "m/s", mi["dron"]["velocidad_crucero_ms"]["fuente"], "verificado en la ficha"),
        ("v_sub (ascenso)", m["v_sub"], "m/s", mi["dron"]["velocidad_ascenso_ms"]["fuente"], "verificado en la ficha"),
        ("Error vertical del dron", valor(mi["dron"]["error_vertical_m"]), "m", mi["dron"]["error_vertical_m"]["fuente"], "verificado en la ficha"),
        ("Error vertical del DEM", valor(mi["operacion"]["error_dem_m"]), "m", mi["operacion"]["error_dem_m"]["fuente"], "verificado (catálogo EEA y Copernicus Data Space)"),
        ("Margen por árboles", valor(mi["operacion"]["margen_arboles_m"]), "m", "Decisión del modelo", "supuesto"),
        ("c_min resultante", valor(mi["operacion"]["error_dem_m"]) + valor(mi["dron"]["error_vertical_m"]) + valor(mi["operacion"]["margen_arboles_m"]), "m", "suma de los tres", "derivado"),
        ("α del viento", valor(am["meteo"]["alpha_perfil"]), "—", " ".join(am["meteo"]["alpha_perfil"]["fuente"].split()), "verificado (fila \"Wooded countryside, many trees\")"),
        ("σ de ráfagas", valor(am["meteo"]["sigma_rafaga_ms"]), "m/s", " ".join(am["meteo"]["sigma_rafaga_ms"]["fuente"].split()), "verificado (Tabla 2, p. 3161: sesgo del modelo de climatología, peor caso)"),
        ("σ de temperatura", valor(am["meteo"]["sigma_temperatura_c"]), "°C", "Decisión del modelo", "supuesto"),
        ("P(foco real | h, n)", valor(am["firms"]["p_real_por_confianza"])["n"], "—", "ATBD VIIRS 375 m (2016), sección 4.3", "verificado (comisión < 1,2 %)"),
        ("P(foco real | l)", valor(am["firms"]["p_real_por_confianza"])["l"], "—", "ATBD VIIRS 375 m (2016), sección 4.3", "verificado (peor caso 40 %)"),
        ("Radio de incendio R", valor(am["firms"]["radio_m"]), "m", "265 m de píxel + margen de humo", "265 m verificado; el margen es supuesto"),
        ("Cambio de batería", m["t_cambio_s"], "s", "Decisión del modelo", "supuesto"),
        ("Ventana de la mañana", m["ventana_h"], "h", "Decisión del modelo; Chang et al. (2025, sec. 2.5) solo dicen \"shortly after sunrise\"", "supuesto"),
        ("Muestreo por cámara s_i", m["s_i"], "s", "Chang et al. (2025), Tabla 1: promedio de 9 vuelos (8 min 30 s a 10 min 2 s)", "verificado"),
        ("p₀ de aves", valor(am["ebird"]["p0"]), "—", "Principio de razón insuficiente", "supuesto"),
        ("Distancia de precaución de aves", valor(am["ebird"]["distancia_precaucion_m"]), "m", "Vas et al. (2015)", "verificado"),
        ("r_mov", valor(am["ebird"]["r_mov_m"]), "m", "calcular_r_mov.py sobre amenaza_ebird.json", "provisional: las especies registradas no tienen dato publicado verificado"),
        ("Reserva t_res", round(m["t_res_s"], 1), "s", "R_op / (v_max − viento límite) + aterrizaje", "derivado (aterrizaje de 60 s supuesto)"),
        ("Batería útil", round(m["t_util_s"], 1), "s", "T_bat − t_res", "derivado"),
    ]
    out = [{"parametro": a, "valor": b, "unidad": c, "fuente": d, "estado": e} for a, b, c, d, e in filas]
    guardar("E0_parametros.csv", out)
    RESUMEN["E0"] = out


def tiempo_sector(esc, s, m):
    if not s["base"]:
        return None
    cfg = amenazas_cfg()
    ctx = Contexto(esc, probabilidades.calcular(esc.copia_amenazas(focos=[], aves=[], meteo={}), cfg), Consulta(),
                   cfg["cota_superior"], m)
    prob = ProblemaSector(ctx, esc.bases[s["base"]["id"]], s["camaras"], s["id"])
    r = dijkstra_distancia.resolver(prob)
    return r


def e1(esc):
    m = parametros_mision()
    sectores = msec.leer_sectores(esc)
    todas = [c for s in sectores for c in s["camaras"]]
    cams = esc.camaras()
    xy = {c: grafo.xy(esc.nodos[c]["lon"], esc.nodos[c]["lat"]) for c in cams}
    dmin = min(float(np.linalg.norm(xy[a] - xy[b])) for a, b in itertools.combinations(cams, 2))
    tam = [s["n_camaras"] for s in sectores]
    filas = []
    for s in sectores:
        b = esc.bases[s["base"]["id"]] if s["base"] else None
        dmax = max(b["camaras"][c]["distancia_m"] for c in s["camaras"]) if b else None
        r = tiempo_sector(esc, s, m)
        tot = r["total"] if r and r["total"] else None
        filas.append({"sector": s["id"], "camaras": " ".join(nombre_camara(esc, c) for c in s["camaras"]),
                      "n_camaras": s["n_camaras"], "base": b["nombre"] if b else "sin base",
                      "tipo_base": b["tipo"] if b else "—", "dist_max_base_m": redondo(dmax, 1),
                      "cumple_alcance": None if dmax is None else dmax <= m["alcance"] + 1e-6,
                      "vuelos": len(r["vuelos"]) if r else None,
                      "min_vuelo": redondo(tot["tiempo_vuelo"] / 60, 2) if tot else None,
                      "min_con_cambios": redondo(tot["tiempo_sector"] / 60, 2) if tot else None,
                      "ascenso_m": redondo(sum(esc.aristas[a]["ascenso_ida_m"] if v["nodos"][k] == esc.aristas[a]["source"]
                                               else esc.aristas[a]["ascenso_vuelta_m"]
                                               for v in r["vuelos"] for k, a in enumerate(v["aristas"])), 1) if tot else None})
    guardar("E1_sectores.csv", filas)
    por_tam = []
    for n in sorted(set(tam)):
        sub = [f for f in filas if f["n_camaras"] == n and f["vuelos"]]
        por_tam.append({"camaras": n, "sectores": tam.count(n), "con_base": len(sub),
                        "vuelos_min": min((f["vuelos"] for f in sub), default=None),
                        "vuelos_max": max((f["vuelos"] for f in sub), default=None),
                        "min_vuelo_min": min((f["min_vuelo"] for f in sub), default=None),
                        "min_vuelo_max": max((f["min_vuelo"] for f in sub), default=None),
                        "min_con_cambios_min": min((f["min_con_cambios"] for f in sub), default=None),
                        "min_con_cambios_max": max((f["min_con_cambios"] for f in sub), default=None)})
    guardar("E1_tiempo_por_tamano.csv", por_tam)

    perf = json.loads((RAIZ / "Infraestructura" / "perfiles_aristas.json").read_text(encoding="utf-8"))["meta"]
    bloqueos = []
    for s in sectores:
        if not s["base"]:
            continue
        b = esc.bases[s["base"]["id"]]
        bxy = grafo.xy(b["lon"], b["lat"])
        cerca = [a for a, ar in esc.aristas.items() if ar.get("base_id") is None and min(
            float(np.linalg.norm(grafo.xy(esc.nodos[ar["source"]]["lon"], esc.nodos[ar["source"]]["lat"]) - bxy)),
            float(np.linalg.norm(grafo.xy(esc.nodos[ar["target"]]["lon"], esc.nodos[ar["target"]]["lat"]) - bxy))) <= m["r_op"]]
        vis = [a for a in cerca if a in b["visibles"]]
        los = [a for a in cerca if b["bloqueadas"].get(a) == "linea_de_vista"]
        alt = [a for a in cerca if esc.aristas[a]["bloqueada"]]
        bloqueos.append({"sector": s["id"], "base": b["nombre"], "aristas_en_radio": len(cerca), "volables": len(vis),
                         "bloqueadas_linea_de_vista": len(los), "bloqueadas_techo": len(alt),
                         "fuera_del_radio": len(cerca) - len(vis) - len(los) - len(alt),
                         "enlaces_directos": len(b["enlaces"])})
    guardar("E1_bloqueos_por_base.csv", bloqueos)
    doc_b = json.loads((RAIZ / "Infraestructura" / "bases.json").read_text(encoding="utf-8"))
    los_global = {x["arista_id"] for bb in doc_b["bases"] for x in bb["aristas_bloqueadas"] if x["motivo"] == "linea_de_vista"}
    cap = capacidad.informe(esc, m=m)
    RESUMEN["E1"] = {
        "n_sectores": len(sectores), "tamanos": {str(k): tam.count(k) for k in sorted(set(tam))},
        "camaras_repetidas": len(todas) - len(set(todas)), "camaras_en_sectores": len(set(todas)),
        "distancia_min_entre_camaras_m": round(dmin, 1),
        "sectores_sin_base": [s["id"] for s in sectores if not s["base"]],
        "tipos_de_base": {t: sum(1 for f in filas if f["tipo_base"] == t) for t in ("camara", "sendero", "camino_camaras")},
        "dist_max_base_m": max(f["dist_max_base_m"] for f in filas if f["dist_max_base_m"] is not None),
        "aristas_total": perf["n_aristas"], "aristas_densificadas": perf["n_densificadas"],
        "aristas_bloqueadas_techo": perf["n_bloqueadas"],
        "aristas_bloqueadas_linea_de_vista_desde_alguna_base": len(los_global),
        "bases_candidatas": doc_b["meta"]["n_bases"], "camaras_sin_base": doc_b["meta"]["camaras_sin_base"],
        "por_tamano": por_tam, "horas_vuelo_parque": cap["horas_vuelo_parque"],
        "mananas_por_pasada": cap["mananas_por_pasada"], "dias_por_pasada": cap["dias_por_pasada"],
        "estimacion_previa_dias": 60, "traslados": cap["traslados"],
    }


def e2(esc):
    sectores = sorted(msec.leer_sectores(esc), key=lambda s: -s["prioridad"])
    filas = [{"rango": k, "sector": s["id"], "camaras": s["n_camaras"], "V": s["valor_conservacion"],
              "V_norm": round(s["V_norm"], 4), "P": s["presion_exoticas"], "P_norm": round(s["P_norm"], 4),
              "prioridad": s["prioridad"], "objetivo": ", ".join(s["descripcion"]["objetivo"]),
              "exoticas": ", ".join(s["descripcion"]["exoticas"]), "con_base": bool(s["base"])}
             for k, s in enumerate(sectores, start=1)]
    guardar("E2_prioridad.csv", filas)
    kendall = evaluacion.sensibilidad_prioridad(esc)
    guardar("E2_kendall.csv", kendall)
    RESUMEN["E2"] = {"top10": filas[:10], "kendall": kendall,
                     "empates_en_prioridad": len(filas) - len({f["prioridad"] for f in filas})}


def e3():
    fechas = json.loads((RAIZ / "Motor" / "resultados" / "fechas_firms.json").read_text(encoding="utf-8"))
    c = caso()
    inicio, fin = date(2012, 1, 20), date.fromisoformat(fechas["revisado_hasta"])
    ventanas = (fin - inicio).days // 5 + 1
    dist = sorted(v["dmin_m"] for v in fechas["fechas"].values())
    filas = [{"fecha": f, "focos": v["n"], "dmin_m": round(v["dmin_m"], 1)}
             for f, v in sorted(fechas["fechas"].items(), key=lambda x: x[1]["dmin_m"])]
    guardar("E3_fechas_firms.csv", filas)
    RESUMEN["E3"] = {"periodo": f"{inicio} a {fin}", "ventanas_de_5_dias": ventanas, "dias_revisados": (fin - inicio).days + 1,
                     "fechas_con_focos_a_3km": len(dist), "fechas_a_1km": sum(1 for d in dist if d <= 1000),
                     "fechas_a_1_5km": sum(1 for d in dist if d <= 1500), "dmin_m": round(dist[0], 1) if dist else None,
                     "busqueda_real": c.get("busqueda_real"), "caso": {k: c[k] for k in c if k != "consulta"},
                     "consulta": c["consulta"]}


def plan_caso(esc, extra=None, n_mc=10_000):
    q = {**caso()["consulta"], **(extra or {})}
    return servicio.planificar(q, esc, n_mc=n_mc), q


def amenazas_en_vuelo(doc, vuelo):
    por_n = {n["id"]: n["por_amenaza"] for n in doc["nodos"]}
    por_a = {a["id"]: a["por_amenaza"] for a in doc["aristas"]}
    salida = {}
    for tipo, ids, tabla in (("nodo", vuelo["nodos"][1:], por_n), ("tramo", vuelo["aristas"], por_a)):
        for i in ids:
            for k, p in tabla.get(i, {}).items():
                if k != "meteo" and p > 0.001:
                    salida.setdefault(k, []).append(f"{tipo} {i} (p={p:.3f})")
    salida["clima"] = [f"p_clima del vuelo = {vuelo['p_clima']:.3f}"]
    return salida


def e4_e5(esc):
    res, q = plan_caso(esc)
    esc_c = servicio.escenario_para(Consulta.desde_dict(q), esc, q.get("focos_simulados"))
    doc = probabilidades.calcular(esc_c, amenazas_cfg(), q.get("overrides_prob"))
    filas, amen, mc = [], [], []
    for p in res["planes"]:
        filas.append({"tecnica": CORTO[p["tecnica"]], "etiqueta": p["etiqueta"], "vuelos": len(p["vuelos"]),
                      "orden": " | ".join(" → ".join(nombre_camara(esc, c) for c in v["camaras"]) for v in p["vuelos"]),
                      "distancia_km": redondo(p["distancia_m"] / 1000, 3), "tiempo_min": redondo(p["tiempo_s"] / 60, 2),
                      "R_por_vuelo": " | ".join(f"{v['R']:.4f}" for v in p["vuelos"]), "R_plan": redondo(p["R"], 4),
                      "costo_modelo": redondo(p["costo"], 6), "computo_ms": redondo(p["tiempo_ms"], 2),
                      "mas_resiliente": p["tecnica"] == res["mas_resiliente"], "leyenda": p["leyenda"]})
        for v in p["vuelos"]:
            a = amenazas_en_vuelo(doc, v)
            amen.append({"tecnica": CORTO[p["tecnica"]], "vuelo": v["vuelo"],
                         "camaras": " → ".join(nombre_camara(esc, c) for c in v["camaras"]),
                         "tramos": " ".join(map(str, v["aristas"])),
                         "incendio": "; ".join(a.get("firms", [])) or "—",
                         "aves": "; ".join(a.get("ebird", [])) or "—",
                         "simulada": "; ".join(a.get("escenario", [])) or "—", "clima": a["clima"][0]})
        if p["R"] is not None:
            mc.append({"tecnica": CORTO[p["tecnica"]], "R_plan": round(p["R"], 5), "R_montecarlo": round(p["R_montecarlo"], 5),
                       "diferencia": round(p["R_montecarlo"] - p["R"], 5), "ic95_inf": round(p["ic95"][0], 5),
                       "ic95_sup": round(p["ic95"][1], 5), "R_en_ic": p["analitico_en_ic"], "sorteos": res["resiliencia"]["n_montecarlo"]})
    guardar("E4_caso_tecnicas.csv", filas)
    guardar("E4_caso_amenazas.csv", amen)
    guardar("E5_montecarlo.csv", mc)
    planes = {p["tecnica"]: p for p in res["planes"]}
    firma = lambda p: [tuple(v["camaras"]) for v in p["vuelos"]]
    tramos = {t: set(a for v in p["vuelos"] for a in v["aristas"]) for t, p in planes.items()}
    comparacion = []
    for a, b in itertools.combinations(TECNICAS, 2):
        pa, pb = planes[a], planes[b]
        comparacion.append({"par": f"{CORTO[a]} vs {CORTO[b]}",
                            "mismo_reparto": sorted(map(sorted, firma(pa))) == sorted(map(sorted, firma(pb))),
                            "mismo_orden": firma(pa) == firma(pb),
                            "mismos_tramos": tramos[a] == tramos[b],
                            "tramos_no_compartidos": len(tramos[a] ^ tramos[b])})
    guardar("E4_comparacion.csv", comparacion)
    corto = min((p for p in res["planes"] if p["R"] is not None), key=lambda p: p["tiempo_s"])
    mejor = planes[res["mas_resiliente"]]
    c = caso()
    foco = c.get("foco_simulado")
    p1 = planes["dijkstra_distancia"]
    RESUMEN["E4"] = {"sector": c["sector"], "fecha": c["fecha"], "simulado": c["simulado"], "foco_simulado": foco,
                     "base": res["sectores"][0]["base"], "camaras": [nombre_camara(esc, x) for x in res["sectores"][0]["camaras"]],
                     "tabla": filas, "comparacion": comparacion, "mas_resiliente": CORTO[res["mas_resiliente"]],
                     "mas_corta": CORTO[corto["tecnica"]], "delta_R_mejor_vs_corta": round(mejor["R"] - corto["R"], 4),
                     "delta_min_mejor_vs_corta": round((mejor["tiempo_s"] - corto["tiempo_s"]) / 60, 2),
                     "tecnica1_menor_R": p1["R"] <= min(p["R"] for p in res["planes"] if p["R"] is not None) + 1e-12,
                     "gurobi_menor_costo": planes["milp"]["costo"] <= min(p["costo"] for p in res["planes"]) + 1e-12,
                     "aviso": res["resiliencia"]["aviso"], "empate_en_R": res["resiliencia"]["empate_en_R"],
                     "escenario": res["escenario"], "aristas_bloqueadas_desde_base": res["capas"]["aristas_bloqueadas"]}
    RESUMEN["E5"] = mc


def e6(esc):
    filas = []
    for th in [round(0.1 * k, 1) for k in range(11)]:
        res, _ = plan_caso(esc, {"theta": th}, n_mc=2000)
        for p in res["planes"]:
            if p["tecnica"] == "dijkstra_distancia":
                continue
            filas.append({"theta": th, "tecnica": CORTO[p["tecnica"]], "tiempo_min": redondo(p["tiempo_s"] / 60, 3),
                          "distancia_km": redondo(p["distancia_m"] / 1000, 3), "R_plan": redondo(p["R"], 5),
                          "vuelos": len(p["vuelos"])})
    guardar("E6_theta.csv", filas)
    figura_theta(filas)
    figura_theta(filas, ingles=True)
    RESUMEN["E6"] = filas


def figura_theta(filas, ingles=False):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 9, "font.family": "DejaVu Sans"})
    fig, ax = plt.subplots(figsize=(3.46, 2.5))
    estilos = {"T2 Gurobi": ("#2f6f9f", "o", "-", "Gurobi"),
               "T3 Dijkstra ponderado": ("#c98a1b", "s", "--", "Weighted Dijkstra" if ingles else "Dijkstra ponderado"),
               "T4 ACO": ("#7b3fa0", "^", ":", "ACO")}
    for t, (col, mk, ls, nombre) in estilos.items():
        sub = [f for f in filas if f["tecnica"] == t and f["R_plan"] not in (None, "")]
        ax.plot([float(f["tiempo_min"]) for f in sub], [float(f["R_plan"]) for f in sub], marker=mk, linestyle=ls,
                color=col, label=nombre, markersize=4, linewidth=1.2)
    ax.set_xlabel("Plan time (min)" if ingles else "Tiempo del plan (min)")
    ax.set_ylabel("Plan R" if ingles else "R del plan")
    ax.grid(alpha=0.3)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / ("fig_theta_en.png" if ingles else "fig_theta.png"), dpi=300)
    plt.close(fig)


def problema_banco(esc_f, s, overrides, factor):
    m = parametros_mision()
    m["t_util_s"] *= factor
    cfg = amenazas_cfg()
    c = Consulta.desde_dict({"modo": "camaras", "camaras": s["camaras"], "overrides_prob": overrides})
    ctx = Contexto(esc_f, probabilidades.calcular(esc_f, cfg, overrides), c, cfg["cota_superior"], m)
    return ProblemaSector(ctx, esc_f.bases[s["base"]["id"]], s["camaras"], s["id"])


def correr_tecnicas(prob, aco_config=None, semilla=0):
    salida = {}
    t0 = time.perf_counter()
    salida["dijkstra_distancia"] = dijkstra_distancia.resolver(prob)
    t1 = time.perf_counter()
    prob.calcular_tramos("modelo")
    t_modelo = (time.perf_counter() - t1) * 1000
    salida["dijkstra_distancia"]["tiempo_ms"] = (t1 - t0) * 1000
    salida["milp"] = milp.resolver(prob)
    salida["dijkstra_ponderado"] = dijkstra_ponderado.resolver(prob)
    salida["aco"] = aco.resolver(prob, config=aco_config, semilla=semilla)
    for k in ("milp", "dijkstra_ponderado", "aco"):
        salida[k]["tiempo_ms"] += t_modelo
    return salida


def e7(esc):
    fecha = caso()["fecha"]
    esc_f = servicio.escenario_para(Consulta.desde_dict({"fecha": fecha}), esc)
    rng = random.Random(SEMILLA)
    filas, mayor = [], {"variables": 0, "restricciones": 0, "caso": None}
    for s in [x for x in msec.leer_sectores(esc_f) if x["base"]]:
        base = esc_f.bases[s["base"]["id"]]
        visibles = sorted(base["visibles"])
        casos = [("base", {}, 1.0), ("bateria 80 %", {}, 0.8), ("bateria 60 %", {}, 0.6)]
        for k in range(20):
            elegidas = rng.sample(visibles, min(3, len(visibles))) if visibles else []
            casos.append((f"variante {k + 1}", {"aristas": {str(a): round(rng.uniform(0.2, 0.9), 3) for a in elegidas}}, 1.0))
        for nombre, ov, fac in casos:
            prob = problema_banco(esc_f, s, ov, fac)
            r = correr_tecnicas(prob)
            opt = r["milp"]
            c_opt = opt["total"]["costo"] if opt["factible"] else None
            ex = opt["extra"]
            if ex.get("n_variables", 0) > mayor["variables"]:
                mayor = {"variables": ex["n_variables"], "restricciones": ex["n_restricciones"], "caso": f"sector {s['id']} {nombre}"}
            for t in TECNICAS:
                x = r[t]
                ok = x["factible"] and not x["no_visitadas"]
                c = x["total"]["costo"] if x["total"] else None
                R = x["total"]["R"] if x["total"] else None
                filas.append({"sector": s["id"], "camaras": s["n_camaras"], "caso": nombre, "tecnica": CORTO[t],
                              "factible": ok, "R_plan": redondo(R, 5), "tiempo_plan_min": redondo(x["total"]["tiempo_sector"] / 60, 3) if x["total"] else None,
                              "costo": redondo(c, 7), "costo_optimo": redondo(c_opt, 7),
                              "brecha_pct": redondo((c - c_opt) / c_opt * 100, 5) if (ok and c_opt and c is not None) else None,
                              "computo_ms": redondo(x["tiempo_ms"], 3)})
    guardar("E7_banco.csv", filas)
    resumen = []
    for t in TECNICAS:
        sub = [f for f in filas if f["tecnica"] == CORTO[t]]
        fac = [f for f in sub if f["factible"]]
        con_brecha = [f for f in fac if f["brecha_pct"] is not None]
        resumen.append({"tecnica": CORTO[t], "casos": len(sub), "factibles_pct": round(100 * len(fac) / len(sub), 1),
                        "R_plan_promedio": round(st.mean(f["R_plan"] for f in fac), 4) if fac else None,
                        "tiempo_plan_min_promedio": round(st.mean(f["tiempo_plan_min"] for f in fac), 2) if fac else None,
                        "brecha_promedio_pct": round(st.mean(f["brecha_pct"] for f in con_brecha), 3) if con_brecha else None,
                        "brecha_max_pct": round(max(f["brecha_pct"] for f in con_brecha), 3) if con_brecha else None,
                        "iguala_optimo_pct": round(100 * sum(abs(f["brecha_pct"]) < 1e-6 for f in con_brecha) / len(con_brecha), 1) if con_brecha else None,
                        "computo_ms_promedio": round(st.mean(f["computo_ms"] for f in sub), 2)})
    guardar("E7_resumen.csv", resumen)
    multi = [f for f in filas if f["camaras"] >= 2]
    resumen_multi = []
    for t in TECNICAS:
        sub = [f for f in multi if f["tecnica"] == CORTO[t] and f["factible"] and f["brecha_pct"] is not None]
        resumen_multi.append({"tecnica": CORTO[t], "casos": len(sub),
                              "brecha_promedio_pct": round(st.mean(f["brecha_pct"] for f in sub), 3) if sub else None,
                              "iguala_optimo_pct": round(100 * sum(abs(f["brecha_pct"]) < 1e-6 for f in sub) / len(sub), 1) if sub else None})
    guardar("E7_resumen_multicamara.csv", resumen_multi)
    sint = []
    for caso_s in evaluacion.banco_sintetico(10, SEMILLA):
        prob = evaluacion.preparar_caso(esc, caso_s)
        r = correr_tecnicas(prob)
        c_opt = r["milp"]["total"]["costo"]
        ex = r["milp"]["extra"]
        if ex.get("n_variables", 0) > mayor["variables"]:
            mayor = {"variables": ex["n_variables"], "restricciones": ex["n_restricciones"], "caso": caso_s["nombre"]}
        for t in TECNICAS:
            x = r[t]
            c = x["total"]["costo"]
            sint.append({"caso": caso_s["nombre"], "tecnica": CORTO[t], "vuelos": len(x["vuelos"]),
                         "R_plan": redondo(x["total"]["R"], 5), "costo": redondo(c, 7),
                         "brecha_pct": redondo((c - c_opt) / c_opt * 100, 4), "computo_ms": redondo(x["tiempo_ms"], 2),
                         "milp_variables": ex.get("n_variables"), "milp_restricciones": ex.get("n_restricciones")})
    guardar("E7_banco_sintetico.csv", sint)
    resumen_s = []
    for t in TECNICAS:
        sub = [f for f in sint if f["tecnica"] == CORTO[t]]
        resumen_s.append({"tecnica": CORTO[t], "casos": len(sub), "R_plan_promedio": round(st.mean(f["R_plan"] for f in sub), 4),
                          "brecha_promedio_pct": round(st.mean(f["brecha_pct"] for f in sub), 3),
                          "brecha_max_pct": round(max(f["brecha_pct"] for f in sub), 3),
                          "iguala_optimo_pct": round(100 * sum(abs(f["brecha_pct"]) < 1e-6 for f in sub) / len(sub), 1),
                          "computo_ms_promedio": round(st.mean(f["computo_ms"] for f in sub), 2)})
    guardar("E7_resumen_sintetico.csv", resumen_s)
    RESUMEN["E7"] = {"fecha_amenazas": fecha, "resumen": resumen, "resumen_multicamara": resumen_multi,
                     "resumen_sintetico": resumen_s, "milp_mas_grande": mayor, "supera_2000": mayor["variables"] > 2000,
                     "casos_por_sector": 23, "sectores": len({f["sector"] for f in filas})}


def e8(esc, semillas=30):
    casos = evaluacion.banco_sintetico(10, SEMILLA)
    probs = []
    for c in casos:
        prob = evaluacion.preparar_caso(esc, c)
        probs.append((c["nombre"], prob, milp.resolver(prob)["total"]["costo"]))
    cfg = aco_cfg()
    grid = cfg["calibracion"]

    def corridas(etiqueta, config, params):
        out = []
        for nombre, prob, c_opt in probs:
            for sem in range(semillas):
                r = aco.resolver(prob, config=config, semilla=sem, params=params)
                gap = (r["total"]["costo"] - c_opt) / c_opt * 100
                out.append({"configuracion": etiqueta, "caso": nombre, "semilla": sem, "brecha_pct": round(gap, 5),
                            "optimo": abs(gap) < 1e-6, "tiempo_ms": round(r["tiempo_ms"], 2),
                            "convergencia": r["extra"]["convergencia"], "c_opt": c_opt})
        return out

    todas = []
    todas += corridas("config_mai", "config_mai", None)
    todas += corridas("config_zhang", "config_zhang", None)
    for clave in ("alpha", "beta", "rho", "hormigas", "q0_inicial"):
        for v in grid[clave]:
            todas += corridas(f"config_mai, {clave}={v}, {grid['iteraciones']} iteraciones", grid["base"],
                              {clave: v, "iteraciones": grid["iteraciones"]})
    resumen = []
    for etiqueta in dict.fromkeys(f["configuracion"] for f in todas):
        sub = [f for f in todas if f["configuracion"] == etiqueta]
        g = [f["brecha_pct"] for f in sub]
        resumen.append({"configuracion": etiqueta, "corridas": len(sub), "brecha_media_pct": round(st.mean(g), 4),
                        "brecha_desv_pct": round(st.pstdev(g), 4), "brecha_max_pct": round(max(g), 4),
                        "optimos_pct": round(100 * sum(f["optimo"] for f in sub) / len(sub), 1),
                        "tiempo_ms_medio": round(st.mean(f["tiempo_ms"] for f in sub), 2)})
    guardar("E8_aco_calibracion.csv", resumen)
    guardar("E8_aco_corridas.csv", [{k: v for k, v in f.items() if k != "convergencia"} for f in todas])
    mejor = min(resumen, key=lambda r: (r["brecha_media_pct"], -r["optimos_pct"], r["tiempo_ms_medio"]))
    grande = max(probs, key=lambda x: len(x[1].camaras))
    curvas = [f for f in todas if f["configuracion"] == mejor["configuracion"] and f["caso"] == grande[0]]
    largo = max(len(f["convergencia"]) for f in curvas)
    matriz = []
    for f in curvas:
        c = [x for x in f["convergencia"]]
        ult = None
        fila = []
        for k in range(largo):
            v = c[k] if k < len(c) else c[-1]
            ult = v if v is not None else ult
            fila.append(math.nan if ult is None else (ult - f["c_opt"]) / f["c_opt"] * 100)
        matriz.append(fila)
    arr = np.array(matriz, dtype=float)
    media, desv = np.nanmean(arr, axis=0), np.nanstd(arr, axis=0)
    guardar("E8_convergencia.csv", [{"iteracion": k + 1, "brecha_media_pct": round(float(media[k]), 5),
                                     "brecha_desv_pct": round(float(desv[k]), 5)} for k in range(largo)])
    figura_convergencia(media, desv)
    figura_convergencia(media, desv, ingles=True)
    RESUMEN["E8"] = {"instancias": [p[0] for p in probs], "semillas": semillas, "resumen": resumen, "mejor": mejor,
                     "curva_en": grande[0], "iteraciones_curva": largo}


def figura_convergencia(media, desv, ingles=False):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    media, desv = np.asarray(media, dtype=float), np.asarray(desv, dtype=float)
    plt.rcParams.update({"font.size": 9, "font.family": "DejaVu Sans"})
    fig, ax = plt.subplots(figsize=(3.46, 2.4))
    x = np.arange(1, len(media) + 1)
    ax.plot(x, media, color="#7b3fa0", linewidth=1.3)
    ax.fill_between(x, np.maximum(media - desv, 0), media + desv, color="#7b3fa0", alpha=0.2, linewidth=0)
    ax.set_xlabel("Iteration" if ingles else "Iteración")
    ax.set_ylabel("Gap to Gurobi (%)" if ingles else "Brecha con Gurobi (%)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / ("fig_convergencia_en.png" if ingles else "fig_convergencia.png"), dpi=300)
    plt.close(fig)


def e9(esc):
    filas = []
    for rmin in (0.3, 0.35, 0.38, 0.4, 0.45, 0.5, 0.9):
        res, _ = plan_caso(esc, {"r_min": rmin}, n_mc=2000)
        filas.append({"r_min": rmin, "planes_factibles": sum(1 for p in res["planes"] if p["R"] is not None),
                      "mensajes": " || ".join(f"{CORTO[p['tecnica']]}: {p['mensaje']}" for p in res["planes"]),
                      "aviso": res["resiliencia"]["aviso"]})
    guardar("E9_rmin.csv", filas)
    primero = next((f for f in filas if f["planes_factibles"] == 0), None)
    RESUMEN["E9"] = {"tabla": filas, "primer_rmin_sin_plan": primero}


def e10(esc):
    base_cfg = amenazas_cfg()
    variantes = [("p0 aves", ("ebird", "p0"), v) for v in (0.3, 0.5, 0.7)] + \
                [("r_mov (m)", ("ebird", "r_mov_m"), v) for v in (1000, 2000, 5000)] + \
                [("radio incendio (m)", ("firms", "radio_m"), v) for v in (500, 1000, 1500)] + \
                [("alpha viento", ("meteo", "alpha_perfil"), v) for v in (0.20, 0.25, 0.30)]
    original = servicio.amenazas_cfg
    filas = []
    try:
        for nombre, ruta, v in variantes:
            cfg = copy.deepcopy(base_cfg)
            cfg["amenazas"][ruta[0]][ruta[1]]["valor"] = v
            servicio.amenazas_cfg = lambda cfg=cfg: cfg
            res, _ = plan_caso(esc, n_mc=2000)
            fila = {"parametro": nombre, "valor": v, "mas_resiliente": CORTO[res["mas_resiliente"]] if res["mas_resiliente"] else None}
            for p in res["planes"]:
                fila[f"R_{p['tecnica']}"] = redondo(p["R"], 4)
            filas.append(fila)
    finally:
        servicio.amenazas_cfg = original
    guardar("E10_sensibilidad.csv", filas)
    RESUMEN["E10"] = filas


def e11(esc):
    m = parametros_mision()
    sectores = msec.leer_sectores(esc)
    tiempos = {s["id"]: capacidad.tiempo_sector_s(s, esc, m)[0] for s in sectores}
    t_tras = capacidad.traslados(sectores, m)
    dias = {"verano": 48, "otono": 33, "invierno": 22, "primavera": 35}
    validos = [s["id"] for s in sectores if not math.isnan(tiempos[s["id"]])]
    filas, pend, visitados, rondas_cubrir = [], [], set(), None
    for ronda in range(1, 13):
        temporada = list(dias)[(ronda - 1) % 4]
        r = capacidad.asignar(sectores, dias[temporada], pend, m, tiempos, t_tras)
        pend = r["pendientes"]
        visitados |= set(r["sectores"])
        if rondas_cubrir is None and visitados >= set(validos):
            rondas_cubrir = ronda
        if ronda <= 4:
            filas.append({"ronda": ronda, "temporada": temporada, "dias_volables": dias[temporada],
                          "cubre_parque": r["cubre_parque"], "sectores": len(r["sectores"]),
                          "por_prioridad": len(r["por_prioridad"]), "por_rotacion": len(r["por_rotacion"]),
                          "pendientes": len(r["pendientes"]), "mananas": len(r["mananas"])})
    guardar("E11_rondas.csv", filas)
    calendario = calendario_ejemplo(esc, sectores)
    RESUMEN["E11"] = {"dias_por_temporada": dias, "fuente_dias": "mañanas volables por temporada, Open-Meteo 2020-2024, α = 0,25",
                      "rondas": filas, "rondas_para_cubrir_el_parque": rondas_cubrir, "sectores_validos": len(validos),
                      "calendario": calendario}


def calendario_ejemplo(esc, sectores):
    s = max((x for x in sectores if x["base"] and x["n_camaras"] >= 2), key=lambda x: x["prioridad"])
    salida = {"sector": s["id"], "campanas": []}
    filas = []
    for etiqueta, inicio in (("verano", "2024-01-15"), ("invierno", "2024-06-10")):
        store = programador.AlmacenJSON(RES / f"E11_campana_{etiqueta}.json")
        if store.ruta.exists():
            store.ruta.unlink()
        programador.crear({"modo": "sector", "sector_id": s["id"]}, inicio, nombre=f"Sector {s['id']} ({etiqueta} 2024)", store=store)
        for _ in range(20):
            camp = store.campanas()[0]
            pendientes = sorted([d for d in camp["dias"] if d["estado"] in ("programada", "postergada")], key=lambda d: d["visita"])
            if not pendientes or camp["estado"] in ("incompleta", "completa"):
                break
            dia = pendientes[0]
            r = programador.decidir(camp, dia, store, esc)
            filas.append({"campana": etiqueta, "visita": dia["visita"], "fecha": dia["fecha"], "decision": r["decision"],
                          "R": redondo(r["R"], 4), "p_clima_max": redondo(r["p_clima_max"], 3)})
            if r["decision"].startswith("Volar"):
                programador.marcar_volada(camp["id"], dia["id"], store)
        camp = store.campanas()[0]
        salida["campanas"].append({"temporada": etiqueta, "inicio": inicio, "estado_final": camp["estado"],
                                   "decisiones": sum(1 for f in filas if f["campana"] == etiqueta),
                                   "dias": [{k: d[k] for k in ("visita", "fecha", "estado")} for d in camp["dias"]]})
    guardar("E11_calendario.csv", filas)
    return salida


def e10b(esc):
    filas_f = list(csv.DictReader((RES / "E10b_fechas_aves.csv").open(encoding="utf-8")))
    del20 = [f for f in filas_f if f["sector"] == "20"]
    if del20:
        elegido, nota = del20[0], "sector 20 (el del caso de E4)"
    elif filas_f:
        elegido, nota = filas_f[0], "ninguna fecha tiene aves a ≤ 5 km del sector 20: se usa el sector de 2 o 3 cámaras con más avistamientos"
    else:
        RESUMEN["E10b"] = {"nota": "ninguna fecha del barrido tiene aves a ≤ 5 km de un sector de 2 o 3 cámaras"}
        return
    sector, fecha = int(elegido["sector"]), elegido["fecha"]
    base = caso()["consulta"]
    consulta = {"modo": "sector", "sector_id": sector, "theta": 0.5,
                "restricciones": base["restricciones"], "focos_simulados": base.get("focos_simulados", [])}
    from datetime import timedelta

    from motor import escenarios

    f = date.fromisoformat(fecha)
    focos, _ = escenarios.focos(esc, f)
    meteo, _, modo = escenarios.meteo(esc, f)
    aves_cache = {}
    for k in range(14):
        ruta = RES / "ebird_diario" / "CL-LL-CHA" / f"{(f - timedelta(days=k)).isoformat()}.json"
        for a in json.loads(ruta.read_text(encoding="utf-8")):
            aves_cache[a["id"]] = {**a, "fecha_obs": grafo.fecha(a["fecha_obs"])}
    esc_d = esc.copia_amenazas(focos=focos, aves=list(aves_cache.values()), meteo=meteo, fecha=fecha, modo_meteo=modo)
    grafo.completar_meteo_bases(esc_d)
    esc_f = servicio.escenario_para(Consulta.desde_dict(consulta), esc_d, consulta["focos_simulados"])
    sec = next(x for x in msec.leer_sectores(esc) if x["id"] == sector)
    cams = [grafo.xy(esc.nodos[c]["lon"], esc.nodos[c]["lat"]) for c in sec["camaras"]]
    aves = [a for a in esc_f.aves if min(float(np.linalg.norm(grafo.xy(a["lon"], a["lat"]) - c)) for c in cams) <= 5000]
    base_cfg = amenazas_cfg()
    original = servicio.amenazas_cfg
    filas = []
    try:
        for nombre, clave, v in [("p0 aves", "p0", x) for x in (0.3, 0.5, 0.7)] + [("r_mov (m)", "r_mov_m", x) for x in (1000, 2000, 5000)]:
            cfg = copy.deepcopy(base_cfg)
            cfg["amenazas"]["ebird"][clave]["valor"] = v
            servicio.amenazas_cfg = lambda cfg=cfg: cfg
            res = servicio.planificar(consulta, esc_d, n_mc=2000)
            doc = probabilidades.calcular(esc_f, cfg)
            nodos_aves = sum(1 for n in doc["nodos"] if n["id"] in res["sectores"][0]["camaras"] + [res["sectores"][0]["base"]["id"]]
                             and n["por_amenaza"].get("ebird", 0) > 0) if res["sectores"][0]["base"] else None
            fila = {"parametro": nombre, "valor": v, "mas_resiliente": CORTO[res["mas_resiliente"]] if res["mas_resiliente"] else None,
                    "empate": " ".join(CORTO[t] for t in res["resiliencia"]["empate_en_R"]),
                    "camaras_y_base_con_p_aves": nodos_aves}
            for p in res["planes"]:
                fila[f"R_{p['tecnica']}"] = redondo(p["R"], 4)
                fila[f"p_aves_max_{p['tecnica']}"] = redondo(max([e["p"] for v_ in p["vuelos"] for e in v_["elementos"]
                                                                  if e["tipo"] != "clima"] + [0.0]), 4)
            filas.append(fila)
    finally:
        servicio.amenazas_cfg = original
    guardar("E10b_sensibilidad_aves.csv", filas)
    RESUMEN["E10b"] = {"sector": sector, "fecha": fecha, "aves_en_ventana_comuna": len(aves_cache),
                       "fuente_aves": "eBird histórico, comuna de Chaitén (CL-LL-CHA), 14 días hasta la fecha", "avistamientos_ventana_a_5km": int(elegido["avistamientos_a_5km"]),
                       "nota": nota, "aves_en_escenario_a_5km": [{"especie": a.get("comun"), "cantidad": a.get("cantidad"),
                                                                 "fecha": str(a.get("fecha_obs"))[:10]} for a in aves],
                       "tabla": filas}


EXPERIMENTOS = ("e0", "e1", "e2", "e3", "e4", "e6", "e7", "e8", "e9", "e10", "e11")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("solo", nargs="*", default=list(EXPERIMENTOS))
    ap.add_argument("--semillas", type=int, default=30)
    args = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    ruta = RES / "resumen.json"
    if ruta.exists():
        RESUMEN.update(json.loads(ruta.read_text(encoding="utf-8")))
    esc = grafo.desde_bd()
    entorno(esc)
    for e in args.solo:
        t0 = time.time()
        print(f"{e.upper()}…", flush=True)
        {"e0": e0, "e1": lambda: e1(esc), "e2": lambda: e2(esc), "e3": e3, "e4": lambda: e4_e5(esc),
         "e6": lambda: e6(esc), "e7": lambda: e7(esc), "e8": lambda: e8(esc, args.semillas),
         "e9": lambda: e9(esc), "e10": lambda: e10(esc), "e10b": lambda: e10b(esc), "e11": lambda: e11(esc)}[e]()
        RESUMEN.setdefault("duraciones_s", {})[e] = round(time.time() - t0, 1)
        ruta.write_text(json.dumps(RESUMEN, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"  listo en {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
