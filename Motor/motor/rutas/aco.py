import random
import time

from ..config import aco_cfg
from .comun import ProblemaSector, resultado

TECNICA, ETIQUETA = "aco", "ACO"


class ACO:
    def __init__(self, prob: ProblemaSector, tramos: dict, camaras: list, params: dict, semilla: int = 0):
        self.prob = prob
        self.tramos = tramos
        self.camaras = list(camaras)
        self.p = params
        self.rng = random.Random(semilla)
        self.b = prob.b
        pts = [self.b] + self.camaras
        self.tau = {(i, j): params["tau_max"] for i in pts for j in pts if (i, j) in tramos}
        self.historia = []
        self.evaluadas = 0
        self.q0 = self.q0_iteracion(0)

    def q0_iteracion(self, k: int) -> float:
        if self.p.get("q0_calendario") != "mai":
            return self.p.get("q0", 0.0)
        K = self.p["iteraciones"]
        q0i = self.p["q0_inicial"]
        k0 = self.p.get("q0_k0", 0.7) * K
        if k < k0:
            return (K - k) / K * q0i
        return (k - k0) / K * q0i + q0i / 2

    def vuelo(self, seq):
        paradas = [self.b] + list(seq) + [self.b]
        costo = tiempo = clima = 0.0
        for i, j in zip(paradas[:-1], paradas[1:]):
            t = self.tramos.get((i, j))
            if t is None:
                return None
            costo += t.costo
            tiempo += t.tiempo
            clima = max(clima, t.clima)
        tiempo += self.prob.s_i * len(seq)
        return costo + self.prob.theta * clima, tiempo

    def evaluar(self, vuelos):
        self.evaluadas += 1
        total = 0.0
        for seq in vuelos:
            r = self.vuelo(seq)
            if r is None or r[1] > self.prob.t_util + 1e-9:
                return None
            total += r[0]
        return {"vuelos": [list(s) for s in vuelos if s], "f": total}

    def hormiga(self):
        a, b, q0 = self.p["alpha"], self.p["beta"], self.q0
        pendientes = list(self.camaras)
        vuelos, seq, actual, usado = [], [], self.b, 0.0
        while pendientes:
            cand = []
            for c in pendientes:
                ida, vuelta = self.tramos.get((actual, c)), self.tramos.get((c, self.b))
                if ida and vuelta and usado + ida.tiempo + self.prob.s_i + vuelta.tiempo <= self.prob.t_util + 1e-9:
                    cand.append((c, ida))
            if not cand:
                if not seq:
                    return None
                vuelos.append(seq)
                seq, actual, usado = [], self.b, 0.0
                continue
            etas = [1.0 / (t.costo + 1e-9) for _, t in cand]
            emax = max(etas)
            pesos = [(self.tau[(actual, c)] ** a) * ((e / emax) ** b) for (c, _), e in zip(cand, etas)]
            if q0 > 0 and self.rng.random() < q0:
                k = max(range(len(cand)), key=lambda i: pesos[i])
            else:
                r, acc, k = self.rng.random() * sum(pesos), 0.0, len(cand) - 1
                for i, w in enumerate(pesos):
                    acc += w
                    if acc >= r:
                        k = i
                        break
            c, ida = cand[k]
            seq.append(c)
            usado += ida.tiempo + self.prob.s_i
            actual = c
            pendientes.remove(c)
        if seq:
            vuelos.append(seq)
        return self.evaluar(vuelos)

    def vecino(self, vuelos):
        v = [list(s) for s in vuelos]
        mov = self.rng.choice(("2opt", "mover", "intercambiar"))
        if mov == "2opt":
            largos = [k for k, s in enumerate(v) if len(s) >= 2]
            if not largos:
                return None
            k = self.rng.choice(largos)
            i, j = sorted(self.rng.sample(range(len(v[k])), 2))
            v[k][i:j + 1] = reversed(v[k][i:j + 1])
        elif mov == "mover":
            k = self.rng.randrange(len(v))
            c = v[k].pop(self.rng.randrange(len(v[k])))
            destino = self.rng.randrange(len(v) + 1)
            if destino == len(v):
                v.append([c])
            else:
                v[destino].insert(self.rng.randrange(len(v[destino]) + 1), c)
        else:
            if len(v) < 2:
                return None
            k1, k2 = self.rng.sample(range(len(v)), 2)
            i1, i2 = self.rng.randrange(len(v[k1])), self.rng.randrange(len(v[k2]))
            v[k1][i1], v[k2][i2] = v[k2][i2], v[k1][i1]
        return [s for s in v if s]

    def busqueda_local(self, sol):
        mejor = sol
        for _ in range(self.p["pasos_busqueda_local"]):
            nuevo = self.vecino(mejor["vuelos"])
            if nuevo is None:
                continue
            cand = self.evaluar(nuevo)
            if cand and cand["f"] < mejor["f"] - 1e-12:
                mejor = cand
        return mejor

    def actualizar(self, depositantes):
        rho, tmin, tmax = self.p["rho"], self.p["tau_min"], self.p["tau_max"]
        for k in self.tau:
            self.tau[k] *= (1 - rho)
        for sol in depositantes:
            delta = 1.0 / max(sol["f"], 1e-9)
            for seq in sol["vuelos"]:
                paradas = [self.b] + seq + [self.b]
                for par in zip(paradas[:-1], paradas[1:]):
                    if par in self.tau:
                        self.tau[par] += delta
        for k in self.tau:
            self.tau[k] = min(max(self.tau[k], tmin), tmax)

    def correr(self):
        mejor, elite, sin_mejora = None, [], 0
        for it in range(self.p["iteraciones"]):
            self.q0 = self.q0_iteracion(it)
            sols = [s for s in (self.hormiga() for _ in range(self.p["hormigas"])) if s]
            if sols:
                it_mejor = self.busqueda_local(min(sols, key=lambda s: s["f"]))
                if mejor is None or it_mejor["f"] < mejor["f"] - 1e-12:
                    mejor, sin_mejora = it_mejor, 0
                else:
                    sin_mejora += 1
                if self.p.get("elite"):
                    vistos = {str(e["vuelos"]) for e in elite}
                    for s in sols + [it_mejor]:
                        if str(s["vuelos"]) not in vistos:
                            elite.append(s)
                            vistos.add(str(s["vuelos"]))
                    elite = sorted(elite, key=lambda s: s["f"])[: self.p["elite"]]
                self.actualizar([it_mejor] + ([mejor] if mejor is not it_mejor else []) + elite)
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
    return nombre, params, cfg[nombre].get("fuente")


def resolver(prob: ProblemaSector, conn=None, config: str | None = None, semilla: int | None = None,
             params: dict | None = None) -> dict:
    tramos = prob.tramos_modelo
    viables, motivos = prob.viables(tramos)
    nombre, base, fuente = parametros_config(config or prob.ctx.c.aco_config)
    if params:
        base = {**base, **params}
    semilla = prob.ctx.c.semilla if semilla is None else semilla
    if not viables:
        return resultado(prob, TECNICA, f"{ETIQUETA} ({nombre})", [], None, 0.0, no_viables=motivos)
    t0 = time.perf_counter()
    aco = ACO(prob, tramos, viables, base, semilla)
    mejor = aco.correr()
    ms = (time.perf_counter() - t0) * 1000
    extra = {"config": nombre, "fuente_config": fuente, "parametros_aco": base, "semilla": semilla,
             "iteraciones_corridas": len(aco.historia), "soluciones_evaluadas": aco.evaluadas,
             "convergencia": aco.historia, "f": mejor["f"] if mejor else None}
    if mejor is None:
        return resultado(prob, TECNICA, f"{ETIQUETA} ({nombre})", [], None, ms, extra=extra,
                         mensaje="Ninguna hormiga armó un plan factible.", no_viables=motivos)
    return resultado(prob, TECNICA, f"{ETIQUETA} ({nombre})", mejor["vuelos"], tramos, ms, extra=extra,
                     no_viables=motivos)
