import time
from contextlib import contextmanager

from . import grafo, probabilidades, resiliencia
from .config import amenazas_cfg, conectar, parametros_mision
from .mision import bases as mod_bases
from .mision import bloques, sectores as mod_sectores
from .mision.prioridad import binomio
from .rutas import aco, dijkstra_distancia, dijkstra_ponderado, milp
from .rutas.comun import Consulta, Contexto, ProblemaSector

TECNICAS = ("dijkstra_distancia", "milp", "dijkstra_ponderado", "aco")
ETIQUETAS = {"dijkstra_distancia": dijkstra_distancia.ETIQUETA, "milp": milp.ETIQUETA,
             "dijkstra_ponderado": dijkstra_ponderado.ETIQUETA, "aco": aco.ETIQUETA}


@contextmanager
def _conexion(esc):
    if esc.fuente != "db":
        yield None
        return
    try:
        conn = conectar()
    except Exception:
        yield None
        return
    try:
        yield conn
    finally:
        conn.close()


def escenario_para(c: Consulta, esc, focos_simulados=None):
    if c.fecha:
        from . import escenarios

        esc = escenarios.aplicar(esc, c.fecha)
    if focos_simulados:
        extra = [{**f, "id": f.get("id", 9000 + k), "simulado": True} for k, f in enumerate(focos_simulados)]
        esc = esc.copia_amenazas(focos=list(esc.focos) + extra)
    return esc


def grupos_objetivo(c: Consulta, esc, m: dict) -> tuple[list, list, str]:
    excluidas = set(c.excluir_nodos)
    sectores = mod_sectores.leer_sectores(esc)
    if c.modo == "sector":
        candidatos = [s for s in sectores if s["base"]] or sectores
        s = next((x for x in sectores if x["id"] == c.sector_id), None) if c.sector_id else \
            max(candidatos, key=lambda x: x["prioridad"])
        if s is None:
            raise ValueError(f"El sector {c.sector_id} no existe.")
        cams = [x for x in s["camaras"] if x not in excluidas]
        return [{"id": s["id"], "camaras": cams, "subtitulo": s["subtitulo"], "prioridad": s["prioridad"]}], \
            sectores, f"Sector {s['id']}"
    if c.modo == "parque":
        orden = sorted(sectores, key=lambda x: -x["prioridad"])
        grupos = [{"id": s["id"], "camaras": [x for x in s["camaras"] if x not in excluidas],
                   "subtitulo": s["subtitulo"], "prioridad": s["prioridad"]} for s in orden]
        return [g for g in grupos if g["camaras"]], sectores, "Todo el parque"
    if c.modo == "especie":
        if not c.especie:
            raise ValueError("Elige una especie.")
        objetivo = binomio(c.especie)
        cams = [v for v in esc.camaras() if v not in excluidas and any(
            binomio(sp["cientifico"]) == objetivo for sp in esc.nodos[v].get("especies", []))]
        titulo = f"Especie: {(esc.especies.get(objetivo) or {}).get('comun', objetivo)}"
    else:
        cams = [v for v in c.camaras if v in esc.nodos and v not in excluidas]
        titulo = f"{len(cams)} cámara{'s' if len(cams) != 1 else ''} elegida{'s' if len(cams) != 1 else ''}"
    if not cams:
        raise ValueError("No hay cámaras que cumplan el modo elegido.")
    grupos = mod_sectores.particion(esc, cams, m)
    salida = []
    for k, g in enumerate(sorted(grupos, key=lambda g: -max(esc.nodos[x]["lat"] for x in g["camaras"])), start=1):
        salida.append({"id": f"G{k}", "camaras": g["camaras"], "subtitulo": None, "prioridad": None})
    return salida, sectores, titulo


def _geojson_vuelo(esc, vuelo: dict, props: dict) -> dict:
    coords = []
    for k, aid in enumerate(vuelo["aristas"]):
        seg = [list(p[:2]) for p in esc.aristas[aid]["coords"]]
        u = esc.nodos[vuelo["nodos"][k]]
        ini, fin = seg[0], seg[-1]
        if (ini[0] - u["lon"]) ** 2 + (ini[1] - u["lat"]) ** 2 > (fin[0] - u["lon"]) ** 2 + (fin[1] - u["lat"]) ** 2:
            seg.reverse()
        coords.extend(seg if not coords else seg[1:])
    if not coords:
        n = esc.nodos[vuelo["nodos"][0]]
        coords = [[n["lon"], n["lat"]], [n["lon"], n["lat"]]]
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords}, "properties": props}


def _resolver_sector(prob: ProblemaSector, tecnicas, conn, aco_params) -> dict:
    salida = {}
    t0 = time.perf_counter()
    salida["dijkstra_distancia"] = dijkstra_distancia.resolver(prob, conn)
    t_dist = (time.perf_counter() - t0) * 1000 - salida["dijkstra_distancia"]["tiempo_ms"]
    t1 = time.perf_counter()
    prob.calcular_tramos("modelo", conn)
    t_modelo = (time.perf_counter() - t1) * 1000
    salida["dijkstra_distancia"]["tiempo_ms"] += max(t_dist, 0)
    for nombre in ("milp", "dijkstra_ponderado", "aco"):
        if nombre not in tecnicas:
            continue
        if nombre == "milp":
            r = milp.resolver(prob, conn)
        elif nombre == "dijkstra_ponderado":
            r = dijkstra_ponderado.resolver(prob, conn)
        else:
            r = aco.resolver(prob, conn, params=aco_params)
        r["tiempo_ms"] += t_modelo
        r["extra"]["tiempo_tramos_ms"] = round(t_modelo, 2)
        salida[nombre] = r
    return salida


def _plan_vacio(tecnica: str) -> dict:
    return {"tecnica": tecnica, "etiqueta": ETIQUETAS[tecnica], "vuelos": [], "factible": True, "mensajes": [],
            "distancia_m": 0.0, "tiempo_s": 0.0, "tiempo_vuelo_s": 0.0, "tiempo_ms": 0.0, "costo": 0.0,
            "por_sector": [], "extra": {}}


def planificar(consulta: dict, esc=None, n_mc: int | None = None, aco_params: dict | None = None) -> dict:
    m = parametros_mision()
    n_mc = n_mc or m["n_mc"]
    c = Consulta.desde_dict(consulta)
    esc = escenario_para(c, esc or grafo.cargar(), consulta.get("focos_simulados"))
    cfg = amenazas_cfg()
    doc = probabilidades.calcular(esc, cfg, c.overrides_prob)
    ctx = Contexto(esc, doc, c, cfg["cota_superior"], m)
    grupos, sectores, titulo = grupos_objetivo(c, esc, m)
    tecnicas = [t for t in (c.tecnicas or TECNICAS) if t in TECNICAS]
    if "dijkstra_distancia" not in tecnicas:
        tecnicas = ["dijkstra_distancia"] + tecnicas

    planes = {t: _plan_vacio(t) for t in tecnicas}
    resumen_sectores, no_visitadas, capas_bases, bloqueadas = [], {}, [], {}
    with _conexion(esc) as conn:
        for g in grupos:
            forzada = c.base_id if len(grupos) == 1 else None
            base, regla = mod_bases.elegir(esc, g["camaras"], forzada)
            info = {"id": g["id"], "camaras": g["camaras"], "subtitulo": g["subtitulo"], "prioridad": g["prioridad"],
                    "base": mod_bases.resumen(base), "regla_base": regla}
            if base is None:
                for x in g["camaras"]:
                    no_visitadas[x] = regla
                info["mensaje"] = regla
                resumen_sectores.append(info)
                continue
            prob = ProblemaSector(ctx, base, g["camaras"], g["id"])
            res = _resolver_sector(prob, tecnicas, conn, aco_params)
            capas_bases.append(info["base"])
            for aid, motivo in base["bloqueadas"].items():
                bloqueadas.setdefault(aid, motivo)
            for t, r in res.items():
                p = planes[t]
                p["etiqueta"] = r["etiqueta"]
                p["tiempo_ms"] += r["tiempo_ms"]
                p["extra"].setdefault("por_sector", []).append({"sector": g["id"], **r["extra"]})
                for x, motivo in r["no_visitadas"].items():
                    no_visitadas.setdefault(x, motivo)
                if not r["factible"]:
                    p["factible"] = False
                    p["mensajes"].append(f"{g['id']}: {r['mensaje']}")
                for v in r["vuelos"]:
                    v["sector"] = g["id"]
                    v["base_id"] = base["id"]
                    v["id"] = f"{t}-{len(p['vuelos']) + 1}"
                    v["tecnica"] = t
                    v["vuelo"] = len(p["vuelos"]) + 1
                    p["vuelos"].append(v)
                if r["total"]:
                    p["distancia_m"] += r["total"]["distancia"]
                    p["tiempo_s"] += r["total"]["tiempo_sector"]
                    p["tiempo_vuelo_s"] += r["total"]["tiempo_vuelo"]
                    p["costo"] = None if r["total"]["costo"] is None or p["costo"] is None else p["costo"] + r["total"]["costo"]
                p["por_sector"].append({"sector": g["id"], "vuelos": len(r["vuelos"]), "factible": r["factible"],
                                        "R": r["total"]["R"] if r["total"] else None,
                                        "costo": r["total"]["costo"] if r["total"] else None})
            info["camaras_plan"] = prob.camaras
            resumen_sectores.append(info)

    lista = [planes[t] for t in tecnicas]
    for p in lista:
        if not p["vuelos"]:
            p["factible"] = False
        p["mensaje"] = "; ".join(p.pop("mensajes")) or "ok"
    umbral = c.r_min or m["r_min_plan"]
    res = resiliencia.evaluar_planes(lista, ctx, n_mc, c.semilla, umbral)
    for p in lista:
        for v in p["vuelos"]:
            v["geojson"] = _geojson_vuelo(esc, v, {"tecnica": p["tecnica"], "vuelo": v["vuelo"],
                                                   "sector": v["sector"], "R": v["R"]})
        p["distancia_m"] = round(p["distancia_m"], 1)
        p["tiempo_s"] = round(p["tiempo_s"], 1)

    camaras_plan = sorted({x for s in resumen_sectores for x in s.get("camaras_plan", [])})
    return {
        "consulta": consulta,
        "titulo": titulo,
        "modo": c.modo,
        "escenario": esc.resumen(),
        "parametros": {"theta": ctx.theta, "bateria": {"util_s": m["t_util_s"], "reserva_s": m["t_res_s"],
                                                        "muestreo_s": m["s_i"]},
                       "radio_operacion_m": m["r_op"], "umbral_R": umbral},
        "sectores": resumen_sectores,
        "no_visitadas": {str(k): v for k, v in no_visitadas.items()},
        "nodos_excluidos": {str(k): v for k, v in ctx.motivos_nodo.items()},
        "planes": lista,
        "resiliencia": res,
        "mas_resiliente": res["mas_resiliente"],
        "capas": {
            "bases": capas_bases,
            "bloques": bloques.geojson_bloques(esc, camaras_plan, m),
            "aristas_bloqueadas": [{"id": a, "motivo": mot} for a, mot in sorted(bloqueadas.items())],
            "radio_m": m["r_op"],
        },
        "probabilidades": {
            "meta": {k: doc["meta"][k] for k in ("generado", "datos", "amenazas_activas", "overrides_prob")},
            "nodos_con_riesgo": {n["id"]: n["p_total"] for n in doc["nodos"] if n["p_total"] > 0},
            "aristas_con_riesgo": {a["id"]: a["p_total"] for a in doc["aristas"] if a["p_total"] > 0},
        },
    }


def simular_fallas(vuelos: list | None, esc=None, overrides: dict | None = None, semilla: int | None = None) -> dict:
    if vuelos:
        return resiliencia.sortear_fallas(vuelos, semilla)
    import numpy as np

    esc = esc or grafo.cargar()
    doc = probabilidades.calcular(esc, overrides=overrides)
    rng = np.random.default_rng(semilla)
    salida = {}
    for tipo in ("nodos", "aristas"):
        elems = doc[tipo]
        r = rng.uniform(0, 100, size=len(elems))
        salida[tipo] = [{"id": e["id"], "p_fallo": e["p_total"], "umbral": 100 * e["p_total"], "r": float(ri),
                         "falla": bool(ri <= 100 * e["p_total"])} for e, ri in zip(elems, r)]
    salida["regla"] = "r ~ Uniforme(0, 100); falla si r ≤ 100 · p"
    salida["semilla"] = semilla
    return salida
