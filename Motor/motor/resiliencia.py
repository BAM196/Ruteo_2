import math

import numpy as np


def r_analitico(nodos, aristas, q: dict, p: dict) -> float:
    return math.prod(1 - q[v] for v in nodos) * math.prod(1 - p[a] for a in aristas)


def sortear_fallas(probs: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    r = rng.uniform(0.0, 100.0, size=(n, len(probs)))
    return r <= 100.0 * probs[None, :]


def montecarlo(nodos, aristas, q: dict, p: dict, n: int = 10_000, semilla: int = 0) -> dict:
    probs = np.array([q[v] for v in nodos] + [p[a] for a in aristas], dtype=float)
    rng = np.random.default_rng(semilla)
    sobrevive = ~sortear_fallas(probs, n, rng).any(axis=1)
    r = float(sobrevive.mean())
    medio = 1.96 * math.sqrt(max(r * (1 - r), 0.0) / n)
    return {"r_mc": r, "ic95": [max(0.0, r - medio), min(1.0, r + medio)], "n": n, "semilla": semilla}


def _fmt(x: float, dec: int) -> str:
    return f"{x:.{dec}f}".replace(".", ",")


def leyenda(ruta: dict) -> str:
    if not ruta.get("factible") and ruta.get("distancia_m") is None:
        return f"{ruta['etiqueta']} | sin ruta | {_fmt(ruta['tiempo_ms'], 0)} ms"
    partes = [ruta["etiqueta"], f"{_fmt(ruta['distancia_m'] / 1000, 1)} km"]
    partes.append(f"R = {_fmt(ruta['R'], 3)}" if ruta.get("R") is not None else "R = no factible")
    partes.append(f"{_fmt(ruta['tiempo_ms'], 0)} ms")
    return " | ".join(partes)


def evaluar_rutas(rutas: list, q: dict, p: dict, n_mc: int = 10_000, semilla: int = 0) -> dict:
    base = next((r for r in rutas if r["tecnica"] == "dijkstra_distancia"), None)
    r_base = None
    if base and base.get("nodos"):
        r_base = r_analitico(base["nodos"], base["aristas"], q, p)

    for ruta in rutas:
        ruta["R"] = ruta["R_montecarlo"] = ruta["ic95"] = ruta["delta_R"] = None
        if ruta.get("nodos"):
            r = r_analitico(ruta["nodos"], ruta["aristas"], q, p)
            mc = montecarlo(ruta["nodos"], ruta["aristas"], q, p, n_mc, semilla)
            ruta["R_si_se_volara"] = r
            if ruta["factible"]:
                ruta["R"] = r
                ruta["R_montecarlo"] = mc["r_mc"]
                ruta["ic95"] = mc["ic95"]
                ruta["analitico_en_ic"] = mc["ic95"][0] - 1e-12 <= r <= mc["ic95"][1] + 1e-12
                if r_base is not None:
                    ruta["delta_R"] = r - r_base
        ruta["leyenda"] = leyenda(ruta)
        if ruta.get("geojson"):
            ruta["geojson"]["properties"].update({"leyenda": ruta["leyenda"], "R": ruta["R"],
                                                  "factible": ruta["factible"]})

    factibles = [r for r in rutas if r["R"] is not None]
    ranking = sorted(factibles, key=lambda r: (-r["R"], r["distancia_m"], r["tiempo_ms"]))
    for i, r in enumerate(ranking, start=1):
        r["ranking"] = i
    mejor = ranking[0] if ranking else None
    empate = [r["tecnica"] for r in ranking if mejor and abs(r["R"] - mejor["R"]) < 1e-9]
    return {
        "metrica": "R(P) = prod_v (1 - q_v) * prod_a (1 - p_a)",
        "regla_falla": "r ~ Uniforme(0, 100); falla si r <= 100 * p",
        "n_montecarlo": n_mc,
        "mas_resiliente": mejor["tecnica"] if mejor else None,
        "mas_resiliente_etiqueta": mejor["etiqueta"] if mejor else None,
        "empate_en_R": empate if len(empate) > 1 else [],
        "criterio_desempate": "a igual R gana la ruta más corta y luego la más rápida de calcular",
        "ranking": [r["tecnica"] for r in ranking],
        "R_referencia_dijkstra": r_base,
    }
