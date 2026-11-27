import argparse
import copy
import csv
import itertools
import json
import random
import statistics as st
from pathlib import Path

from . import capacidad, grafo, probabilidades, servicio
from .config import CONFIG, RESULTADOS, aco_cfg, amenazas_cfg, fuente_por_defecto, parametros_mision
from .mision import prioridad, sectores as mod_sectores
from .rutas import aco, dijkstra_distancia, milp
from .rutas.comun import Consulta, Contexto, ProblemaSector


def _csv(path: Path, filas: list[dict]):
    if not filas:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def caso_ejemplo() -> dict:
    ruta = CONFIG / "caso_ejemplo.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))["consulta"]
    return {"modo": "sector", "restricciones": {"solo_bosque": True}}


def problema(esc, consulta: dict, cfg=None, m=None, base_id=None, camaras=None, sector=None):
    cfg = cfg or amenazas_cfg()
    m = m or parametros_mision()
    c = Consulta.desde_dict(consulta)
    esc = servicio.escenario_para(c, esc, consulta.get("focos_simulados"))
    ctx = Contexto(esc, probabilidades.calcular(esc, cfg, c.overrides_prob), c, cfg["cota_superior"], m)
    prob = ProblemaSector(ctx, esc.bases[base_id], camaras, sector)
    dijkstra_distancia.resolver(prob)
    prob.calcular_tramos("modelo")
    return prob


def banco(esc, n_variantes: int = 3, semilla: int = 1) -> list:
    rng = random.Random(semilla)
    casos = []
    for s in mod_sectores.leer_sectores(esc):
        if not s["base"] or s["n_camaras"] < 2:
            continue
        casos.append({"nombre": f"sector {s['id']}", "sector": s, "overrides": {}, "bateria": 1.0})
        base = esc.bases[s["base"]["id"]]
        visibles = sorted(base["visibles"])
        for k in range(n_variantes):
            amenazadas = rng.sample(visibles, min(len(visibles), 4))
            casos.append({"nombre": f"sector {s['id']} variante {k + 1}", "sector": s,
                          "overrides": {"aristas": {str(a): round(rng.uniform(0.2, 0.9), 2) for a in amenazadas}},
                          "bateria": 0.75 if k == n_variantes - 1 else 1.0})
    return casos


def escenario_sintetico(n: int, semilla: int):
    import math

    rng = random.Random(semilla)
    lon0, lat0 = -72.6, -42.6
    dx, dy = 1 / (111320 * math.cos(math.radians(42.6))), 1 / 111320
    pts = {0: (0.0, 0.0)}
    while len(pts) <= n:
        r, a = rng.uniform(200, 1250), rng.uniform(0, 2 * math.pi)
        x, y = r * math.cos(a), r * math.sin(a)
        if all(math.hypot(x - px, y - py) > 250 for px, py in pts.values()):
            pts[len(pts)] = (x, y)
    ll = {i: [lon0 + x * dx, lat0 + y * dy] for i, (x, y) in pts.items()}
    nodos = [{"id": i, "nombre": f"Camara S{i}" if i else "Base", "lon": ll[i][0], "lat": ll[i][1],
              "es_camara": i > 0, "landcover_code": 10, "especies": []} for i in pts]
    aristas, k = [], 1
    for i in pts:
        for j in pts:
            if i < j and math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]) <= 1500:
                aristas.append({"id": k, "source": i, "target": j, "tipo": "sintetica",
                                "distancia_m": math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]),
                                "coordenadas": [ll[i], ll[j]]})
                k += 1
    camaras = {i: {"camara_id": i, "distancia_m": math.hypot(*pts[i]), "bloque_visible": True, "fraccion_visible": 1.0}
               for i in pts if i}
    esc = grafo.desde_documentos({"nodos": nodos, "aristas": aristas, "bases": [], "especies": []}, "sintetico")
    esc.bases = {0: {"id": 0, "tipo": "camara", "nodo": 0, "nombre": "Base sintética", "lon": ll[0][0],
                     "lat": ll[0][1], "elevacion_m": 0, "camaras": camaras,
                     "visibles": {a["id"] for a in aristas}, "bloqueadas": {}, "enlaces": []}}
    amenazadas = rng.sample([a["id"] for a in aristas], min(len(aristas), 6))
    return esc, {"aristas": {str(a): round(rng.uniform(0.2, 0.9), 2) for a in amenazadas}}


def banco_sintetico(n_instancias: int = 10, semilla: int = 1) -> list:
    rng = random.Random(semilla)
    salida = []
    for k in range(n_instancias):
        n = rng.choice((6, 7, 8))
        esc, ov = escenario_sintetico(n, semilla * 100 + k)
        salida.append({"nombre": f"sintética {k + 1} ({n} cámaras)", "esc": esc, "overrides": ov, "bateria": 1.0,
                       "camaras": list(range(1, n + 1))})
    return salida


def preparar_caso(esc, caso: dict):
    m = parametros_mision()
    m["t_util_s"] *= caso["bateria"]
    if "esc" in caso:
        return problema(caso["esc"], {"modo": "camaras", "camaras": caso["camaras"], "overrides_prob": caso["overrides"]},
                        m=m, base_id=0, camaras=caso["camaras"], sector=caso["nombre"])
    s = caso["sector"]
    return problema(esc, {"modo": "camaras", "camaras": s["camaras"], "overrides_prob": caso["overrides"]},
                    m=m, base_id=s["base"]["id"], camaras=s["camaras"], sector=s["id"])


def calibracion(esc, semillas: int = 30) -> dict:
    filas, curvas = [], {"config_mai": [], "config_zhang": []}
    for caso in banco(esc) + banco_sintetico():
        prob = preparar_caso(esc, caso)
        opt = milp.resolver(prob)
        if not opt["factible"]:
            continue
        c_opt = opt["total"]["costo"]
        for nombre in ("config_mai", "config_zhang"):
            for sem in range(semillas):
                r = aco.resolver(prob, config=nombre, semilla=sem)
                c = r["total"]["costo"] if r["total"] else None
                filas.append({"caso": caso["nombre"], "tipo": "sintética" if "esc" in caso else "real",
                              "config": nombre, "semilla": sem,
                              "camaras": len(prob.camaras), "c_optimo": round(c_opt, 6),
                              "c_aco": None if c is None else round(c, 6),
                              "gap_pct": None if c is None else round((c - c_opt) / c_opt * 100, 4),
                              "optimo": c is not None and abs(c - c_opt) < 1e-9,
                              "tiempo_aco_ms": r["tiempo_ms"], "tiempo_milp_ms": opt["tiempo_ms"],
                              "iteraciones": r["extra"].get("iteraciones_corridas")})
                if caso["nombre"].startswith("sintética 1 ") and sem < 5:
                    curvas[nombre].append(r["extra"]["convergencia"])
    resumen = []
    for nombre, tipo in itertools.product(("config_mai", "config_zhang"), ("real", "sintética")):
        sub = [f for f in filas if f["config"] == nombre and f["tipo"] == tipo and f["gap_pct"] is not None]
        if not sub:
            continue
        resumen.append({"config": nombre, "banco": tipo, "corridas": len(sub), "casos": len({f["caso"] for f in sub}),
                        "gap_promedio_pct": round(st.mean(f["gap_pct"] for f in sub), 4),
                        "gap_max_pct": round(max(f["gap_pct"] for f in sub), 4),
                        "optimos_pct": round(100 * sum(f["optimo"] for f in sub) / len(sub), 1),
                        "tiempo_aco_ms_prom": round(st.mean(f["tiempo_aco_ms"] for f in sub), 2),
                        "tiempo_milp_ms_prom": round(st.mean(f["tiempo_milp_ms"] for f in sub), 2)})
    return {"filas": filas, "resumen": resumen, "curvas": curvas}


def grilla_aco(esc, semillas: int = 10) -> list:
    cfg = aco_cfg()["calibracion"]
    casos = banco_sintetico(5)
    probs = []
    for caso in casos:
        prob = preparar_caso(esc, caso)
        opt = milp.resolver(prob)
        if opt["factible"]:
            probs.append((prob, opt["total"]["costo"]))
    filas = []
    for clave in ("alpha", "beta", "rho", "hormigas", "q0_inicial"):
        for valor in cfg[clave]:
            gaps, tiempos = [], []
            for prob, c_opt in probs:
                for sem in range(semillas):
                    r = aco.resolver(prob, config=cfg["base"], semilla=sem,
                                     params={clave: valor, "iteraciones": cfg["iteraciones"]})
                    if r["total"]:
                        gaps.append((r["total"]["costo"] - c_opt) / c_opt * 100)
                        tiempos.append(r["tiempo_ms"])
            filas.append({"parametro": clave, "valor": valor, "corridas": len(gaps),
                          "gap_promedio_pct": round(st.mean(gaps), 4) if gaps else None,
                          "optimos_pct": round(100 * sum(g < 1e-7 for g in gaps) / len(gaps), 1) if gaps else None,
                          "tiempo_ms_prom": round(st.mean(tiempos), 2) if tiempos else None})
    return filas


def _plan_resumen(res: dict) -> dict:
    planes = {p["tecnica"]: p for p in res["planes"]}
    return {t: {"R": None if p["R"] is None else round(p["R"], 4), "vuelos": len(p["vuelos"]),
                "min": round(p["tiempo_s"] / 60, 1),
                "firma": "|".join(">".join(map(str, v["camaras"])) for v in p["vuelos"])} for t, p in planes.items()}


def sensibilidad(esc, consulta: dict) -> list:
    base_cfg = amenazas_cfg()
    variantes = [
        ("base", None, None),
        ("p0 aves", ("ebird", "p0"), 0.3), ("p0 aves", ("ebird", "p0"), 0.7),
        ("r_mov aves", ("ebird", "r_mov_m"), 1000), ("r_mov aves", ("ebird", "r_mov_m"), 5000),
        ("radio incendio", ("firms", "radio_m"), 500), ("radio incendio", ("firms", "radio_m"), 1500),
        ("decaimiento incendio", ("firms", "decaimiento"), "escalon"),
        ("alpha viento", ("meteo", "alpha_perfil"), 0.20), ("alpha viento", ("meteo", "alpha_perfil"), 0.30),
    ]
    filas = []
    import motor.servicio as srv

    original = srv.amenazas_cfg
    try:
        for nombre, ruta, valor in variantes:
            cfg = copy.deepcopy(base_cfg)
            if ruta:
                cfg["amenazas"][ruta[0]][ruta[1]]["valor"] = valor
            srv.amenazas_cfg = lambda cfg=cfg: cfg
            res = servicio.planificar(consulta, esc, n_mc=1000)
            for t, d in _plan_resumen(res).items():
                filas.append({"parametro": nombre, "valor": "—" if valor is None else valor, "tecnica": t, **d,
                              "mas_resiliente": res["mas_resiliente"] == t})
    finally:
        srv.amenazas_cfg = original
    return filas


def curva_theta(esc, consulta: dict) -> list:
    filas = []
    for th in [round(0.1 * k, 1) for k in range(11)]:
        res = servicio.planificar({**consulta, "theta": th, "tecnicas": ["dijkstra_distancia", "milp"]}, esc, n_mc=500)
        p = next(x for x in res["planes"] if x["tecnica"] == "milp")
        filas.append({"theta": th, "tiempo_min": round(p["tiempo_s"] / 60, 2), "distancia_km": round(p["distancia_m"] / 1000, 3),
                      "R": None if p["R"] is None else round(p["R"], 4), "vuelos": len(p["vuelos"])})
    return filas


def sensibilidad_prioridad(esc) -> list:
    m = parametros_mision()
    ref = sorted(mod_sectores.armar_sectores(esc, m=m, peso_valor=0.5), key=lambda s: -s["prioridad"])
    orden_ref = [s["id"] for s in ref]
    filas = []
    for w in (0.3, 0.4, 0.5, 0.6, 0.7):
        s = sorted(mod_sectores.armar_sectores(esc, m=m, peso_valor=w), key=lambda s: -s["prioridad"])
        orden = [x["id"] for x in s]
        filas.append({"peso_valor": w, "peso_presion": round(1 - w, 1), "kendall_tau": round(prioridad.kendall_tau(orden_ref, orden), 4),
                      "top5": " ".join(map(str, orden[:5]))})
    return filas


def sensibilidad_calendario(esc) -> list:
    filas = []
    for frac in (0.3, 0.5, 0.7):
        m = parametros_mision()
        m["fraccion_prioridad"] = frac
        sectores = mod_sectores.leer_sectores(esc)
        tiempos = {s["id"]: capacidad.tiempo_sector_s(s, esc, m)[0] for s in sectores}
        t_tras = capacidad.traslados(sectores, m)
        pend = []
        for temporada, dias in (("verano", 51), ("otono", 36), ("invierno", 25), ("primavera", 37)):
            r = capacidad.asignar(sectores, dias, pend, m, tiempos, t_tras, frac)
            pend = r["pendientes"]
            filas.append({"fraccion_prioridad": frac, "temporada": temporada, "dias": dias,
                          "sectores": len(r["sectores"]), "pendientes": len(r["pendientes"])})
    for cambio in (180, 300, 480):
        m = parametros_mision()
        m["t_cambio_s"] = cambio
        sectores = mod_sectores.leer_sectores(esc)
        tiempos = {s["id"]: capacidad.tiempo_sector_s(s, esc, m)[0] for s in sectores}
        pas = capacidad.mananas([s for s in sorted(sectores, key=lambda s: -s["prioridad"]) if tiempos[s["id"]] == tiempos[s["id"]]],
                                tiempos, capacidad.traslados(sectores, m), m)
        filas.append({"fraccion_prioridad": f"cambio de batería {cambio // 60} min", "temporada": "pasada",
                      "dias": m["visitas"] * len(pas), "sectores": len(pas), "pendientes": ""})
    return filas


def graficos(curvas: dict, theta: list):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    for nombre, lista in curvas.items():
        for k, c in enumerate(lista):
            ys = [y for y in c if y is not None]
            ax.plot(range(len(ys)), ys, alpha=0.6, label=nombre if k == 0 else None)
    ax.set_xlabel("Iteración")
    ax.set_ylabel("Mejor costo encontrado")
    ax.set_title("Convergencia del ACO (5 semillas por configuración)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTADOS / "aco_convergencia.png", dpi=150)
    plt.close(fig)
    filas = [f for f in theta if f["R"] is not None]
    if filas:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot([f["tiempo_min"] for f in filas], [f["R"] for f in filas], "o-", color="#2f6f9f")
        for f in filas:
            ax.annotate(f"θ={f['theta']}", (f["tiempo_min"], f["R"]), fontsize=8, xytext=(4, 2), textcoords="offset points")
        ax.set_xlabel("Tiempo del plan (min)")
        ax.set_ylabel("R del plan")
        ax.set_title("Tiempo contra resiliencia al variar θ (Gurobi)")
        fig.tight_layout()
        fig.savefig(RESULTADOS / "curva_theta.png", dpi=150)
        plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Evaluación: caso de ejemplo, calibración del ACO y sensibilidad.")
    ap.add_argument("--fuente", choices=["db", "json"], default=None)
    ap.add_argument("--semillas", type=int, default=30)
    ap.add_argument("--sin-grilla", action="store_true")
    args = ap.parse_args()
    RESULTADOS.mkdir(exist_ok=True)
    esc = grafo.cargar(args.fuente or fuente_por_defecto(), usar_cache=False)
    consulta = caso_ejemplo()

    print("Caso de ejemplo")
    res = servicio.planificar(consulta, esc)
    (RESULTADOS / "caso_ejemplo_plan.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    _csv(RESULTADOS / "caso_ejemplo_tabla.csv", [
        {"tecnica": p["tecnica"], "leyenda": p["leyenda"], "vuelos": len(p["vuelos"]),
         "camaras_por_vuelo": " | ".join(" > ".join(map(str, v["camaras"])) for v in p["vuelos"]),
         "distancia_km": round(p["distancia_m"] / 1000, 3), "tiempo_min": round(p["tiempo_s"] / 60, 2),
         "R": None if p["R"] is None else round(p["R"], 6), "R_montecarlo": p["R_montecarlo"],
         "delta_R": None if p["delta_R"] is None else round(p["delta_R"], 6),
         "costo": None if p["costo"] is None else round(p["costo"], 6), "tiempo_ms": p["tiempo_ms"],
         "mas_resiliente": p["tecnica"] == res["mas_resiliente"]} for p in res["planes"]])
    for p in res["planes"]:
        print("  " + p["leyenda"])

    print("Calibración del ACO contra Gurobi")
    cal = calibracion(esc, args.semillas)
    _csv(RESULTADOS / "aco_corridas.csv", cal["filas"])
    _csv(RESULTADOS / "aco_resumen.csv", cal["resumen"])
    for r in cal["resumen"]:
        print(f"  {r['config']} ({r['banco']}): {r['corridas']} corridas en {r['casos']} casos, brecha promedio {r['gap_promedio_pct']} %, "
              f"óptimos {r['optimos_pct']} %")
    if not args.sin_grilla:
        _csv(RESULTADOS / "aco_grilla.csv", grilla_aco(esc, min(10, args.semillas)))

    print("Sensibilidad de los parámetros sin fuente")
    _csv(RESULTADOS / "sensibilidad_amenazas.csv", sensibilidad(esc, consulta))
    pr = sensibilidad_prioridad(esc)
    _csv(RESULTADOS / "sensibilidad_prioridad.csv", pr)
    print("  Kendall del orden de sectores: " + ", ".join(f"w={f['peso_valor']}: {f['kendall_tau']}" for f in pr))
    _csv(RESULTADOS / "sensibilidad_calendario.csv", sensibilidad_calendario(esc))
    theta = curva_theta(esc, consulta)
    _csv(RESULTADOS / "curva_theta.csv", theta)
    graficos(cal["curvas"], theta)
    print(f"Escrito en {RESULTADOS}")


if __name__ == "__main__":
    main()
