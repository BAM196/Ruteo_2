import math
import time

from .comun import ProblemaSector, resultado, vecino_mas_cercano

TECNICA, ETIQUETA = "milp", "Gurobi (MILP)"
ESCALA = 1000.0
LIMITE_VARIABLES = 2000
ESTADOS = {1: "LOADED", 2: "OPTIMAL", 3: "INFEASIBLE", 4: "INF_OR_UNBD", 5: "UNBOUNDED",
           9: "TIME_LIMIT", 11: "INTERRUPTED", 13: "SUBOPTIMAL"}


def n_variables(n: int, k: int) -> int:
    variables = k * ((n + 1) * n + n + 1 + n + 1)
    restricciones = n + k * (2 * (n + 1) + n + 2 + n * (n - 1) + (n + 1) * n + n)
    return max(variables, restricciones)


def vuelos_maximos(prob: ProblemaSector, tramos: dict, camaras: list) -> int:
    n = len(camaras)
    if n_variables(n, n) <= LIMITE_VARIABLES:
        return max(1, n)
    k = min(n, len(vecino_mas_cercano(prob, tramos, camaras, con_clima=True)) + 1)
    while k > 1 and n_variables(n, k) > LIMITE_VARIABLES:
        k -= 1
    return k


def construir(prob: ProblemaSector, tramos: dict, camaras: list, K: int, time_limit=30.0, mip_gap=0.0):
    import gurobipy as gp
    from gurobipy import GRB

    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 0)
    env.start()
    m = gp.Model("plan_de_vuelos", env=env)
    m.Params.TimeLimit = time_limit
    m.Params.MIPGap = mip_gap
    m.Params.Seed = prob.ctx.c.semilla
    m.Params.Threads = 1

    b = prob.b
    V = ["base"] + list(camaras)
    nodo = {"base": b, **{c: c for c in camaras}}
    arcos = [(i, j) for i in V for j in V if i != j and (nodo[i], nodo[j]) in tramos]
    n = len(camaras)
    Ks = range(K)
    x = {(i, j, k): m.addVar(vtype=GRB.BINARY, name=f"x_{i}_{j}_{k}") for i, j in arcos for k in Ks}
    y = {(i, k): m.addVar(vtype=GRB.BINARY, name=f"y_{i}_{k}") for i in camaras for k in Ks}
    z = {k: m.addVar(vtype=GRB.BINARY, name=f"z_{k}") for k in Ks}
    u = {(i, k): m.addVar(lb=1, ub=max(n, 1), name=f"u_{i}_{k}") for i in camaras for k in Ks}
    clima = {k: m.addVar(lb=0, name=f"clima_{k}") for k in Ks}

    t = {(i, j): tramos[(nodo[i], nodo[j])] for i, j in arcos}
    for i in camaras:
        m.addConstr(gp.quicksum(y[i, k] for k in Ks) == 1, name=f"una_vez_{i}")
    for k in Ks:
        for i in V:
            sale = gp.quicksum(x[i, j, k] for j in V if (i, j) in t)
            entra = gp.quicksum(x[j, i, k] for j in V if (j, i) in t)
            if i == "base":
                m.addConstr(sale == z[k], name=f"sale_base_{k}")
                m.addConstr(entra == z[k], name=f"vuelve_base_{k}")
            else:
                m.addConstr(sale == y[i, k], name=f"sale_{i}_{k}")
                m.addConstr(entra == y[i, k], name=f"entra_{i}_{k}")
                m.addConstr(y[i, k] <= z[k], name=f"usa_{i}_{k}")
        if k + 1 < K:
            m.addConstr(z[k] >= z[k + 1], name=f"simetria_{k}")
        m.addConstr(gp.quicksum(t[a].tiempo * x[a[0], a[1], k] for a in t)
                    + gp.quicksum(prob.s_i * y[i, k] for i in camaras) <= prob.t_util, name=f"bateria_{k}")
        for i, j in arcos:
            if i != "base" and j != "base":
                m.addConstr(u[i, k] - u[j, k] + n * x[i, j, k] <= n - 1, name=f"mtz_{i}_{j}_{k}")
            m.addConstr(clima[k] >= t[i, j].clima * x[i, j, k], name=f"clima_{i}_{j}_{k}")
        for i in camaras:
            m.addConstr(clima[k] >= prob.ctx.mu_nodo.get(i, 0.0) * y[i, k], name=f"clima_nodo_{i}_{k}")
    riesgo = gp.quicksum(t[a].riesgo * x[a[0], a[1], k] for a in t for k in Ks) + gp.quicksum(clima.values())
    if prob.ctx.c.r_min:
        m.addConstr(riesgo <= -math.log(prob.ctx.c.r_min), name="r_minima_plan")
    m.setObjective(ESCALA * (gp.quicksum(t[a].costo * x[a[0], a[1], k] for a in t for k in Ks)
                             + prob.theta * gp.quicksum(clima.values())), GRB.MINIMIZE)
    return m, x, z, env, V


def _vuelos(x, z, V, K, camaras, b):
    vuelos = []
    for k in range(K):
        if z[k].X < 0.5:
            continue
        sig = {i: j for (i, j, kk), var in x.items() if kk == k and var.X > 0.5}
        seq, actual = [], "base"
        while actual in sig and len(seq) <= len(camaras):
            actual = sig[actual]
            if actual == "base":
                break
            seq.append(actual)
        if seq:
            vuelos.append(seq)
    return vuelos


def resolver(prob: ProblemaSector, conn=None, time_limit=30.0, mip_gap=0.0) -> dict:
    tramos = prob.tramos_modelo
    viables, motivos = prob.viables(tramos)
    if not viables:
        return resultado(prob, TECNICA, ETIQUETA, [], None, 0.0, no_viables=motivos)
    K = vuelos_maximos(prob, tramos, viables)
    t0 = time.perf_counter()
    m, x, z, env, V = construir(prob, tramos, viables, K, time_limit, mip_gap)
    m.optimize()
    ms = (time.perf_counter() - t0) * 1000
    import gurobipy

    extra = {"solver": "Gurobi", "version": ".".join(map(str, gurobipy.gurobi.version())),
             "estado": ESTADOS.get(m.Status, str(m.Status)), "n_variables": m.NumVars,
             "n_restricciones": m.NumConstrs, "vuelos_maximos": K, "time_limit_s": time_limit,
             "mip_gap_param": mip_gap, "tiempo_solver_ms": round(m.Runtime * 1000, 2)}
    try:
        if m.SolCount == 0:
            msg = ("Ningún plan cumple la batería, las restricciones y la R mínima."
                   if m.Status in (3, 4) else f"Gurobi terminó sin solución ({extra['estado']}).")
            return resultado(prob, TECNICA, ETIQUETA, [], None, ms, extra=extra, mensaje=msg, no_viables=motivos)
        extra.update(objetivo=m.ObjVal / ESCALA, cota_inferior=m.ObjBound / ESCALA, gap=m.MIPGap,
                     escala_objetivo=ESCALA)
        vuelos = _vuelos(x, z, V, K, viables, prob.b)
        return resultado(prob, TECNICA, ETIQUETA, vuelos, tramos, ms, extra=extra, no_viables=motivos)
    finally:
        m.dispose()
        env.dispose()
