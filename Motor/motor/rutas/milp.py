import math
import time

from .comun import EPS, Problema

TECNICA, ETIQUETA = "milp", "Gurobi (MILP)"

ESTADOS = {1: "LOADED", 2: "OPTIMAL", 3: "INFEASIBLE", 4: "INF_OR_UNBD", 5: "UNBOUNDED",
           9: "TIME_LIMIT", 11: "INTERRUPTED", 13: "SUBOPTIMAL"}


def construir(prob: Problema, time_limit=30.0, mip_gap=0.0):
    import gurobipy as gp
    from gurobipy import GRB

    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 0)
    env.start()
    m = gp.Model("ruta_resiliente", env=env)
    m.Params.TimeLimit = time_limit
    m.Params.MIPGap = mip_gap
    m.Params.Seed = prob.c.semilla
    m.Params.Threads = 1

    arcos = list(prob.arcos())
    nodos = [v for v in prob.esc.nodos if v not in prob.nodos_excluidos]
    x = {(u, v, a): m.addVar(vtype=GRB.BINARY, name=f"x_{u}_{v}_e{a}") for u, v, a in arcos}
    y = {v: m.addVar(vtype=GRB.BINARY, name=f"y_{v}") for v in nodos}

    sale = {v: [] for v in nodos}
    entra = {v: [] for v in nodos}
    for k in x:
        sale[k[0]].append(x[k])
        entra[k[1]].append(x[k])

    for v in nodos:
        b = 1 if v == prob.s else (-1 if v == prob.t else 0)
        m.addConstr(gp.quicksum(sale[v]) - gp.quicksum(entra[v]) == b, name=f"flujo_{v}")
        m.addConstr(gp.quicksum(entra[v]) <= 1, name=f"una_visita_{v}")
        if v == prob.s:
            m.addConstr(y[v] == 1, name="y_origen")
        else:
            m.addConstr(y[v] >= gp.quicksum(entra[v]), name=f"visita_{v}")

    d = {k: prob.esc.aristas[k[2]]["distancia_m"] for k in x}
    if prob.d_max:
        m.addConstr(gp.quicksum(d[k] * x[k] for k in x) <= prob.d_max, name="autonomia")
    riesgo = gp.quicksum(prob.w[k[2]] * x[k] for k in x) + gp.quicksum(prob.u[v] * y[v] for v in y)
    if prob.c.r_min:
        m.addConstr(riesgo <= -math.log(prob.c.r_min), name="resiliencia_minima")

    m.setObjective(
        (1 - prob.theta + EPS) * gp.quicksum(d[k] / prob.d_ref * x[k] for k in x)
        + prob.theta * riesgo,
        GRB.MINIMIZE,
    )
    return m, x, y, env


def _camino(prob: Problema, x) -> tuple[list, list]:
    usados = {k[0]: k for k, var in x.items() if var.X > 0.5}
    nodos, aristas, v = [prob.s], [], prob.s
    while v != prob.t and v in usados and len(nodos) <= len(prob.esc.nodos):
        _, w, a = usados[v]
        nodos.append(w)
        aristas.append(a)
        v = w
    return nodos, aristas


def resolver(prob: Problema, conn=None, time_limit=30.0, mip_gap=0.0) -> dict:
    error = prob.validar_extremos()
    if error or prob.d_ref is None:
        return prob.resultado(TECNICA, ETIQUETA, [], [], 0.0,
                              mensaje=error or "Sin distancia de referencia (no hay ruta por distancia).")
    if prob.s in prob.nodos_excluidos or prob.t in prob.nodos_excluidos:
        return prob.resultado(TECNICA, ETIQUETA, [], [], 0.0, mensaje="Origen o destino excluido.")

    t0 = time.perf_counter()
    m, x, y, env = construir(prob, time_limit, mip_gap)
    m.optimize()
    ms = (time.perf_counter() - t0) * 1000

    extra = {
        "solver": "Gurobi",
        "version": ".".join(map(str, __import__("gurobipy").gurobi.version())),
        "estado": ESTADOS.get(m.Status, str(m.Status)),
        "n_variables": m.NumVars, "n_restricciones": m.NumConstrs,
        "time_limit_s": time_limit, "mip_gap_param": mip_gap,
        "tiempo_solver_ms": round(m.Runtime * 1000, 2),
    }
    try:
        if m.SolCount == 0:
            msg = ("No existe ruta que cumpla la autonomía y las restricciones (modelo infactible)."
                   if m.Status in (3, 4) else f"Gurobi terminó sin solución ({extra['estado']}).")
            return prob.resultado(TECNICA, ETIQUETA, [], [], ms, extra=extra, mensaje=msg)
        extra["objetivo"] = m.ObjVal
        extra["cota_inferior"] = m.ObjBound
        extra["gap"] = m.MIPGap
        nodos, aristas = _camino(prob, x)
        if nodos[-1] != prob.t:
            return prob.resultado(TECNICA, ETIQUETA, [], [], ms, extra=extra,
                                  mensaje="No se pudo reconstruir el camino de la solución.")
        return prob.resultado(TECNICA, ETIQUETA, nodos, aristas, ms, extra=extra)
    finally:
        m.dispose()
        env.dispose()
