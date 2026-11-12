import math
import random
import time

import numpy as np

from .. import grafo
from ..config import aco_cfg
from .comun import EPS, Problema, dijkstra, distancias_desde

TECNICA, ETIQUETA = "aco", "ACO"


class ACO:
    def __init__(self, prob: Problema, params: dict, comunes: dict, semilla: int = 0):
        self.prob = prob
        self.p = params
        self.gamma = comunes["gamma"]["valor"]
        self.margen_corte = comunes["margen_corte"]["valor"]
        self.rng = random.Random(semilla)
        self.adj = prob.adyacencia("combinado")
        inv = {v: [] for v in prob.esc.nodos}
        for u, lst in self.adj.items():
            for v, aid, c in lst:
                inv[v].append((u, aid, c))
        alcanzables = distancias_desde(inv, prob.t)
        if params.get("heuristica", "euclidiana") == "dijkstra":
            self.h = alcanzables
        else:
            t_xy = grafo.xy(prob.esc.nodos[prob.t]["lon"], prob.esc.nodos[prob.t]["lat"])
            self.h = {
                v: (1 - prob.theta + EPS) * float(np.linalg.norm(
                    grafo.xy(prob.esc.nodos[v]["lon"], prob.esc.nodos[v]["lat"]) - t_xy)) / prob.d_ref
                for v in alcanzables
            }
        self.tau = {aid: params["tau_max"] for aid in prob.esc.aristas
                    if aid not in prob.aristas_excluidas}
        self.historia = []
        self.q0 = self.q0_iteracion(0)
        self.evaluadas = 0

    def evaluar(self, nodos, aristas):
        pr = self.prob
        dist = sum(pr.esc.aristas[a]["distancia_m"] for a in aristas)
        costo = pr.theta * pr.u[nodos[0]] + sum(
            pr.costo_arco(nodos[i], nodos[i + 1], a) for i, a in enumerate(aristas))
        exceso = max(0.0, dist - pr.d_max) if pr.d_max else 0.0
        f = costo + self.gamma * exceso / pr.d_ref
        self.evaluadas += 1
        return {"nodos": nodos, "aristas": aristas, "dist": dist, "costo": costo,
                "f": f, "factible": exceso <= 1e-6}

    @staticmethod
    def clave(sol):
        return (not sol["factible"], sol["f"])

    def hormiga(self):
        pr, a, b, q0 = self.prob, self.p["alpha"], self.p["beta"], self.q0
        limite = pr.d_max * (1 + self.margen_corte) if pr.d_max else math.inf
        actual, nodos, aristas, visit, dist = pr.s, [pr.s], [], {pr.s}, 0.0
        while actual != pr.t:
            cand = [(v, aid, c) for v, aid, c in self.adj[actual]
                    if v not in visit and v in self.h
                    and dist + pr.esc.aristas[aid]["distancia_m"] <= limite]
            if not cand:
                return None
            etas = [1.0 / (c + self.h[v] + 1e-12) for v, _, c in cand]
            emax = max(etas)
            pesos = [(self.tau[aid] ** a) * ((e / emax) ** b) for (v, aid, c), e in zip(cand, etas)]
            if q0 > 0 and self.rng.random() < q0:
                k = max(range(len(cand)), key=lambda i: pesos[i])
            else:
                tot = sum(pesos)
                r, acc, k = self.rng.random() * tot, 0.0, len(cand) - 1
                for i, w in enumerate(pesos):
                    acc += w
                    if acc >= r:
                        k = i
                        break
            v, aid, _ = cand[k]
            nodos.append(v)
            aristas.append(aid)
            visit.add(v)
            dist += pr.esc.aristas[aid]["distancia_m"]
            actual = v
        return self.evaluar(nodos, aristas)

    def busqueda_local(self, sol):
        mejor = sol
        for _ in range(self.p["pasos_busqueda_local"]):
            n = len(mejor["nodos"])
            if n < 3:
                break
            tramo = min(self.p.get("tramo_max", 3), n - 2)
            if tramo < 2:
                break
            largo = self.rng.randint(2, tramo)
            i = self.rng.randrange(0, n - largo)
            j = i + largo
            nodos, aristas = mejor["nodos"], mejor["aristas"]
            prohibidos = frozenset(nodos[:i] + nodos[j + 1:])
            r = dijkstra(self.adj, nodos[i], nodos[j], prohibidos)
            if r is None:
                continue
            tramo_n, tramo_a, _ = r
            nueva = self.evaluar(nodos[:i] + tramo_n + nodos[j + 1:],
                                 aristas[:i] + tramo_a + aristas[j:])
            if self.clave(nueva) < self.clave(mejor):
                mejor = nueva
        return mejor

    def actualizar(self, depositantes):
        rho, tmin, tmax = self.p["rho"], self.p["tau_min"], self.p["tau_max"]
        for aid in self.tau:
            self.tau[aid] *= (1 - rho)
        for sol in depositantes:
            delta = 1.0 / max(sol["f"], 1e-9)
            for aid in sol["aristas"]:
                self.tau[aid] += delta
        for aid in self.tau:
            self.tau[aid] = min(max(self.tau[aid], tmin), tmax)

    def q0_iteracion(self, k: int) -> float:
        if self.p.get("q0_calendario") != "mai":
            return self.p.get("q0", 0.0)
        K = self.p["iteraciones"]
        q0i = self.p["q0_inicial"]
        k0 = self.p.get("q0_k0", 0.7) * K
        if k < k0:
            return (K - k) / K * q0i
        return (k - k0) / K * q0i + q0i / 2

    def correr(self):
        pr = self.prob
        if pr.s not in self.h:
            return None
        mejor, elite, sin_mejora = None, [], 0
        for it in range(self.p["iteraciones"]):
            self.q0 = self.q0_iteracion(it)
            sols = [s for s in (self.hormiga() for _ in range(self.p["hormigas"])) if s]
            if sols:
                it_mejor = self.busqueda_local(min(sols, key=self.clave))
                if mejor is None or self.clave(it_mejor) < self.clave(mejor):
                    mejor, sin_mejora = it_mejor, 0
                else:
                    sin_mejora += 1
                if self.p.get("elite"):
                    vistos = {tuple(e["aristas"]) for e in elite}
                    for s in sols + [it_mejor]:
                        if tuple(s["aristas"]) not in vistos:
                            elite.append(s)
                            vistos.add(tuple(s["aristas"]))
                    elite = sorted(elite, key=self.clave)[: self.p["elite"]]
                dep = [it_mejor] + ([mejor] if mejor is not it_mejor else []) + elite
                self.actualizar(dep)
            else:
                sin_mejora += 1
            self.historia.append(mejor["f"] if mejor else None)
            if self.p.get("sin_mejora") and sin_mejora >= self.p["sin_mejora"]:
                break
        return mejor


def parametros_config(nombre: str | None = None):
    cfg = aco_cfg()
    nombre = nombre or cfg["por_defecto"]
    params = {k: v for k, v in cfg[nombre].items() if k != "fuente"}
    return nombre, params, cfg["comunes"], cfg[nombre].get("fuente")


def resolver(prob: Problema, conn=None, config: str | None = None, semilla: int | None = None,
             params: dict | None = None) -> dict:
    error = prob.validar_extremos()
    if error or prob.d_ref is None:
        return prob.resultado(TECNICA, ETIQUETA, [], [], 0.0,
                              mensaje=error or "Sin distancia de referencia (no hay ruta por distancia).")
    nombre, base, comunes, fuente = parametros_config(config or prob.c.aco_config)
    if params:
        base = {**base, **params}
    semilla = prob.c.semilla if semilla is None else semilla

    t0 = time.perf_counter()
    aco = ACO(prob, base, comunes, semilla)
    mejor = aco.correr()
    ms = (time.perf_counter() - t0) * 1000

    extra = {"config": nombre, "fuente_config": fuente, "parametros_aco": base, "semilla": semilla,
             "iteraciones_corridas": len(aco.historia), "soluciones_evaluadas": aco.evaluadas,
             "convergencia": aco.historia, "f": mejor["f"] if mejor else None}
    if mejor is None:
        return prob.resultado(TECNICA, ETIQUETA, [], [], ms, extra=extra,
                              mensaje="Ninguna hormiga llegó al destino.")
    msg = None if mejor["factible"] else "Ninguna ruta cumplió D_max: se devuelve la menos mala."
    return prob.resultado(TECNICA, f"{ETIQUETA} ({nombre})", mejor["nodos"], mejor["aristas"], ms,
                          extra=extra, mensaje=msg)
