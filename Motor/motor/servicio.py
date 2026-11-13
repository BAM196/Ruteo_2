from contextlib import contextmanager

from . import grafo, probabilidades, resiliencia
from .config import amenazas_cfg, conectar, d_max_por_defecto
from .rutas import aco, dijkstra_distancia, dijkstra_ponderado, milp
from .rutas.comun import Consulta, Problema

TECNICAS = {
    "dijkstra_distancia": dijkstra_distancia.resolver,
    "milp": milp.resolver,
    "dijkstra_ponderado": dijkstra_ponderado.resolver,
    "aco": aco.resolver,
}


@contextmanager
def _conexion(esc):
    if esc.fuente != "db":
        yield None
        return
    conn = conectar()
    try:
        yield conn
    finally:
        conn.close()


def preparar(consulta: dict, esc: grafo.Escenario, cfg: dict | None = None):
    cfg = cfg or amenazas_cfg()
    c = Consulta.desde_dict(consulta, d_max_por_defecto(cfg))
    doc = probabilidades.calcular(esc, cfg, c.overrides_prob)
    q, p = probabilidades.mapas(doc)
    amenaza_nodo = {n["id"]: n["por_amenaza"] for n in doc["nodos"]}
    amenaza_arista = {a["id"]: a["por_amenaza"] for a in doc["aristas"]}
    return Problema(esc, q, p, c, cfg["cota_superior"], amenaza_nodo, amenaza_arista), doc


def calcular_rutas(consulta: dict, esc: grafo.Escenario | None = None, tecnicas=None,
                   n_mc: int = 10_000, aco_params: dict | None = None) -> dict:
    esc = esc or grafo.cargar()
    prob, doc = preparar(consulta, esc)
    tecnicas = tecnicas or consulta.get("tecnicas") or list(TECNICAS)

    rutas = []
    with _conexion(esc) as conn:
        rutas.append(dijkstra_distancia.resolver(prob, conn))
        for nombre in ("milp", "dijkstra_ponderado", "aco"):
            if nombre not in tecnicas:
                continue
            if nombre == "aco":
                rutas.append(aco.resolver(prob, conn, params=aco_params))
            else:
                rutas.append(TECNICAS[nombre](prob, conn))
    if "dijkstra_distancia" not in tecnicas:
        rutas = rutas[1:]

    resumen = resiliencia.evaluar_rutas(rutas, prob.q, prob.p, n_mc, prob.c.semilla)
    return {
        "consulta": {**consulta, "autonomia_m": prob.d_max},
        "parametros": prob.parametros(),
        "nodos_excluidos": {str(k): v for k, v in prob.motivos_nodo.items()},
        "rutas": rutas,
        "resiliencia": resumen,
        "mas_resiliente": resumen["mas_resiliente"],
        "probabilidades": {
            "meta": {k: doc["meta"][k] for k in ("generado", "datos", "amenazas_activas", "overrides_prob")},
            "nodos_con_riesgo": {n["id"]: n["p_total"] for n in doc["nodos"] if n["p_total"] > 0},
            "aristas_con_riesgo": {a["id"]: a["p_total"] for a in doc["aristas"] if a["p_total"] > 0},
        },
    }


def simular_fallas(esc: grafo.Escenario, overrides: dict | None = None, semilla: int | None = None):
    import numpy as np

    doc = probabilidades.calcular(esc, overrides=overrides)
    rng = np.random.default_rng(semilla)
    salida = {}
    for tipo in ("nodos", "aristas"):
        elems = doc[tipo]
        r = rng.uniform(0, 100, size=len(elems))
        salida[tipo] = [{"id": e["id"], "p_fallo": e["p_total"], "umbral": 100 * e["p_total"],
                         "r": float(ri), "falla": bool(ri <= 100 * e["p_total"])}
                        for e, ri in zip(elems, r)]
    salida["regla"] = "r ~ Uniforme(0, 100); falla si r <= 100 * p"
    salida["semilla"] = semilla
    return salida
