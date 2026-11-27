import math

import numpy as np


def elementos_vuelo(vuelo: dict, ctx) -> list:
    nodos = vuelo["nodos"][1:]
    salida = [{"tipo": "nodo", "id": v, "p": ctx.p_nodo.get(v, 0.0)} for v in nodos]
    salida += [{"tipo": "arista", "id": a, "p": ctx.p_arista.get(a, 0.0)} for a in vuelo["aristas"]]
    salida.append({"tipo": "clima", "id": f"vuelo {vuelo['vuelo']}", "p": vuelo.get("p_clima", 0.0)})
    return salida


def r_analitico(elementos: list) -> float:
    return math.prod(1.0 - e["p"] for e in elementos)


def sortear(probs: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    r = rng.uniform(0.0, 100.0, size=(n, len(probs)))
    return r <= 100.0 * probs[None, :]


def montecarlo_plan(vuelos_elem: list, n: int = 10_000, semilla: int = 0) -> dict:
    rng = np.random.default_rng(semilla)
    sobrevive_plan = np.ones(n, dtype=bool)
    por_vuelo = []
    for elems in vuelos_elem:
        probs = np.array([e["p"] for e in elems], dtype=float)
        ok = ~sortear(probs, n, rng).any(axis=1) if len(probs) else np.ones(n, dtype=bool)
        por_vuelo.append(float(ok.mean()))
        sobrevive_plan &= ok
    r = float(sobrevive_plan.mean())
    medio = 1.96 * math.sqrt(max(r * (1 - r), 0.0) / n)
    return {"r_mc": r, "ic95": [max(0.0, r - medio), min(1.0, r + medio)], "n": n, "semilla": semilla,
            "por_vuelo": por_vuelo}


def _fmt(x: float, dec: int) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def leyenda(plan: dict) -> str:
    if not plan.get("vuelos"):
        return f"{plan['etiqueta']} | sin plan | {_fmt(plan['tiempo_ms'], 0)} ms"
    n = len(plan["vuelos"])
    partes = [plan["etiqueta"], f"{n} vuelo{'s' if n != 1 else ''}",
              f"{_fmt(plan['distancia_m'] / 1000, 1)} km", f"{_fmt(plan['tiempo_s'] / 60, 0)} min",
              f"R plan = {_fmt(plan['R'], 3)}" if plan.get("R") is not None else "R plan = no factible",
              f"{_fmt(plan['tiempo_ms'], 0)} ms"]
    return " | ".join(partes)


def evaluar_planes(planes: list, ctx, n_mc: int = 10_000, semilla: int = 0, umbral: float = 0.9) -> dict:
    base = next((p for p in planes if p["tecnica"] == "dijkstra_distancia"), None)
    for plan in planes:
        elems = [elementos_vuelo(v, ctx) for v in plan["vuelos"]]
        for v, e in zip(plan["vuelos"], elems):
            v["R"] = r_analitico(e)
            v["elementos"] = e
        plan["R"] = plan["R_montecarlo"] = plan["ic95"] = plan["delta_R"] = None
        if plan["vuelos"]:
            r = math.prod(v["R"] for v in plan["vuelos"])
            plan["R_si_se_volara"] = r
            if plan["factible"]:
                mc = montecarlo_plan(elems, n_mc, semilla)
                plan["R"] = r
                plan["R_montecarlo"] = mc["r_mc"]
                plan["ic95"] = mc["ic95"]
                plan["R_montecarlo_por_vuelo"] = mc["por_vuelo"]
                plan["analitico_en_ic"] = mc["ic95"][0] - 1e-12 <= r <= mc["ic95"][1] + 1e-12
                plan["cumple_umbral"] = r >= umbral
        plan["leyenda"] = leyenda(plan)
    r_base = base["R"] if base else None
    for plan in planes:
        if plan["R"] is not None and r_base is not None:
            plan["delta_R"] = plan["R"] - r_base
    factibles = [p for p in planes if p["R"] is not None]
    ranking = sorted(factibles, key=lambda p: (-round(p["R"], 12), p["tiempo_s"], p["tiempo_ms"]))
    for i, p in enumerate(ranking, start=1):
        p["ranking"] = i
    mejor = ranking[0] if ranking else None
    empate = [p["tecnica"] for p in ranking if mejor and abs(p["R"] - mejor["R"]) < 1e-9]
    aviso = None
    if not factibles:
        aviso = "Ninguna técnica encontró un plan factible: prueba otra base, menos restricciones o posterga la campaña."
    elif mejor["R"] < umbral:
        aviso = (f"Ningún plan alcanza R ≥ {_fmt(umbral, 2)}: conviene elegir otra base o postergar la campaña "
                 "hasta que cambien las amenazas.")
    return {
        "metrica": "R_vuelo = Π (1 − p) sobre los elementos del vuelo y el clima; R_plan = Π R_vuelo",
        "regla_falla": "r ~ Uniforme(0, 100); un elemento falla si r ≤ 100 · p",
        "n_montecarlo": n_mc,
        "umbral": umbral,
        "mas_resiliente": mejor["tecnica"] if mejor else None,
        "mas_resiliente_etiqueta": mejor["etiqueta"] if mejor else None,
        "empate_en_R": empate if len(empate) > 1 else [],
        "criterio_desempate": "a igual R gana el plan más corto en tiempo y luego el más rápido de calcular",
        "ranking": [p["tecnica"] for p in ranking],
        "R_referencia_tecnica_1": r_base,
        "aviso": aviso,
    }


def sortear_fallas(vuelos: list, semilla: int | None = None) -> dict:
    rng = np.random.default_rng(semilla)
    salida = []
    for v in vuelos:
        elems = v.get("elementos") or []
        r = rng.uniform(0, 100, size=len(elems))
        detalle = [{**e, "r": round(float(ri), 3), "umbral": round(100 * e["p"], 4), "falla": bool(ri <= 100 * e["p"])}
                   for e, ri in zip(elems, r)]
        salida.append({"id": v.get("id"), "tecnica": v.get("tecnica"), "vuelo": v.get("vuelo"),
                       "falla": any(d["falla"] for d in detalle),
                       "fallan": [d for d in detalle if d["falla"]], "elementos": detalle})
    return {"regla": "r ~ Uniforme(0, 100); un elemento falla si r ≤ 100 · p; un vuelo falla si falla alguno",
            "semilla": semilla, "vuelos": salida}
