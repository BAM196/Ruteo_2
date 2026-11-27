import heapq
import math
from dataclasses import dataclass, field

from ..config import parametros_mision
from ..grafo import BOSQUE

EPS = 1e-6
UMBRAL_EVITAR_CLIMA = 0.5
MODOS = ("sector", "parque", "especie", "camaras")


@dataclass
class Consulta:
    modo: str = "sector"
    sector_id: int | None = None
    especie: str | None = None
    camaras: list = field(default_factory=list)
    base_id: int | None = None
    theta: float = 0.5
    fecha: str | None = None
    solo_bosque: bool = False
    evitar_senderos: bool = False
    evitar_clima: bool = False
    evitar_aves: bool = False
    excluir_nodos: list = field(default_factory=list)
    overrides_prob: dict = field(default_factory=dict)
    r_min: float | None = None
    semilla: int = 0
    aco_config: str | None = None
    tecnicas: list | None = None

    @classmethod
    def desde_dict(cls, d: dict) -> "Consulta":
        r = d.get("restricciones") or {}
        modo = d.get("modo") or "sector"
        if modo not in MODOS:
            raise ValueError(f"Modo desconocido: {modo}")
        return cls(
            modo=modo,
            sector_id=None if d.get("sector_id") in (None, "") else int(d["sector_id"]),
            especie=d.get("especie") or None,
            camaras=[int(x) for x in d.get("camaras") or []],
            base_id=None if d.get("base_id") in (None, "") else int(d["base_id"]),
            theta=float(d.get("theta", 0.5)),
            fecha=d.get("fecha") or None,
            solo_bosque=bool(r.get("solo_bosque", False)),
            evitar_senderos=bool(r.get("evitar_senderos", False)),
            evitar_clima=bool(r.get("evitar_clima", False)),
            evitar_aves=bool(r.get("evitar_aves", False)),
            excluir_nodos=[int(x) for x in r.get("excluir_nodos", [])],
            overrides_prob=d.get("overrides_prob") or {},
            r_min=d.get("r_min"),
            semilla=int(d.get("semilla", 0)),
            aco_config=d.get("aco_config"),
            tecnicas=d.get("tecnicas"),
        )


def _q(p: float) -> float:
    return -math.log(1.0 - p)


class Contexto:
    def __init__(self, esc, doc_prob: dict, consulta: Consulta, cota: float = 0.999999, params: dict | None = None):
        self.esc = esc
        self.c = consulta
        self.cota = cota
        self.m = params or parametros_mision()
        self.theta = min(max(consulta.theta, 0.0), 1.0)
        self.p_nodo, self.p_arista, self.clima_nodo, self.clima_arista = {}, {}, {}, {}
        self.amenaza_nodo, self.amenaza_arista = {}, {}
        for n in doc_prob["nodos"]:
            por = n["por_amenaza"]
            self.amenaza_nodo[n["id"]] = por
            self.p_nodo[n["id"]] = min(1 - math.prod(1 - p for k, p in por.items() if k != "meteo"), cota)
            self.clima_nodo[n["id"]] = min(por.get("meteo", 0.0), cota)
        for a in doc_prob["aristas"]:
            por = a["por_amenaza"]
            self.amenaza_arista[a["id"]] = por
            self.p_arista[a["id"]] = min(1 - math.prod(1 - p for k, p in por.items() if k != "meteo"), cota)
            self.clima_arista[a["id"]] = min(por.get("meteo", 0.0), cota)
        self.u = {v: _q(p) for v, p in self.p_nodo.items()}
        self.w = {a: _q(p) for a, p in self.p_arista.items()}
        self.mu_nodo = {v: _q(p) for v, p in self.clima_nodo.items()}
        self.mu_arista = {a: _q(p) for a, p in self.clima_arista.items()}

        self.excl_usuario = set(consulta.excluir_nodos)
        self.motivos_nodo = {v: "excluida por el usuario" for v in self.excl_usuario}
        for v, n in esc.nodos.items():
            if consulta.solo_bosque and not n.get("es_base_sendero") and n.get("landcover_code") != BOSQUE:
                self.motivos_nodo.setdefault(v, "no es bosque")
            if consulta.evitar_clima and self.clima_nodo.get(v, 0.0) >= UMBRAL_EVITAR_CLIMA:
                self.motivos_nodo.setdefault(v, "clima fuera de los límites del dron")
            if consulta.evitar_aves and self.amenaza_nodo.get(v, {}).get("ebird", 0.0) > 0:
                self.motivos_nodo.setdefault(v, "zona de influencia de aves")
            if self.clima_nodo.get(v, 0.0) >= cota:
                self.motivos_nodo.setdefault(v, "clima fuera de los límites del dron (lluvia o viento)")
            if self.p_nodo.get(v, 0.0) >= cota:
                self.motivos_nodo.setdefault(v, "probabilidad de falla igual a 1")
        self.nodos_excluidos = set(self.motivos_nodo)

        self.motivos_arista = {}
        for aid, a in esc.aristas.items():
            por = self.amenaza_arista.get(aid, {})
            if a.get("bloqueada"):
                self.motivos_arista[aid] = "bloqueada por altura"
            elif consulta.evitar_senderos and a.get("buffer_privacidad"):
                self.motivos_arista[aid] = "cerca de un sendero"
            elif consulta.evitar_clima and self.clima_arista.get(aid, 0.0) >= UMBRAL_EVITAR_CLIMA:
                self.motivos_arista[aid] = "clima fuera de los límites del dron"
            elif consulta.evitar_aves and por.get("ebird", 0.0) > 0:
                self.motivos_arista[aid] = "zona de influencia de aves"
            elif self.p_arista.get(aid, 0.0) >= cota or self.clima_arista.get(aid, 0.0) >= cota:
                self.motivos_arista[aid] = "probabilidad de falla igual a 1"
        self.aristas_excluidas = set(self.motivos_arista)

    def tiempo_arista(self, aid: int, desde: int) -> float:
        a = self.esc.aristas[aid]
        subida = a["ascenso_ida_m"] if desde == a["source"] else a["ascenso_vuelta_m"]
        return a["distancia_m"] / self.m["v_c"] + subida / self.m["v_sub"]


@dataclass
class Tramo:
    i: int
    j: int
    nodos: list
    aristas: list
    distancia: float
    tiempo: float
    riesgo: float
    clima: float
    costo: float


class ProblemaSector:
    def __init__(self, ctx: Contexto, base: dict, camaras: list, sector_id=None):
        self.ctx = ctx
        self.esc = ctx.esc
        self.base = base
        self.b = base["nodo"]
        self.sector_id = sector_id
        self.theta = ctx.theta
        self.m = ctx.m
        self.t_util = self.m["t_util_s"]
        self.s_i = self.m["s_i"]
        self.t_ref = None
        self.no_visitables = {}
        pedidas = list(dict.fromkeys(camaras))
        for c in pedidas:
            if c in ctx.nodos_excluidos and c != self.b:
                self.no_visitables[c] = ctx.motivos_nodo[c]
            elif c not in base["camaras"] or not base["camaras"][c]["bloque_visible"]:
                self.no_visitables[c] = "fuera del alcance o sin línea de vista desde la base"
        self.camaras = [c for c in pedidas if c not in self.no_visitables]
        self.permitidos = set(self.camaras) | {self.b}
        self.arcos = []
        for aid in sorted(base["visibles"]):
            if aid in ctx.aristas_excluidas or aid not in self.esc.aristas:
                continue
            a = self.esc.aristas[aid]
            u, v = a["source"], a["target"]
            if not (self._paso_libre(u) and self._paso_libre(v)):
                continue
            self.arcos.append((u, v, aid))
            self.arcos.append((v, u, aid))
        self.tramos_dist = None
        self.tramos_modelo = None

    def _paso_libre(self, x) -> bool:
        if x in self.permitidos:
            return True
        n = self.esc.nodos[x]
        return x not in self.ctx.nodos_excluidos and not n.get("es_camara") and not n.get("es_base_sendero")

    def costo_arco(self, u, v, aid) -> float:
        return ((1 - self.theta + EPS) * self.ctx.tiempo_arista(aid, u) / self.t_ref
                + self.theta * (self.ctx.w[aid] + self.ctx.u[v]))

    def costo_modelo(self, nodos, aristas, clima) -> float | None:
        if self.t_ref is None:
            return None
        return sum(self.costo_arco(nodos[k], nodos[k + 1], a) for k, a in enumerate(aristas)) + self.theta * clima

    def adyacencia(self, tipo: str) -> dict:
        adj = {}
        for u, v, aid in self.arcos:
            if tipo == "distancia":
                c = self.esc.aristas[aid]["largo_3d_m"]
            else:
                c = self.costo_arco(u, v, aid)
            adj.setdefault(u, []).append((v, aid, c))
        return adj

    def puntos(self) -> list:
        return [self.b] + self.camaras

    def _tramo(self, i, j, nodos, aristas, tipo) -> Tramo:
        ctx = self.ctx
        dist = sum(self.esc.aristas[a]["largo_3d_m"] for a in aristas)
        tiempo = sum(ctx.tiempo_arista(a, nodos[k]) for k, a in enumerate(aristas))
        riesgo = sum(ctx.w[a] for a in aristas) + sum(ctx.u[v] for v in nodos[1:])
        clima = max([ctx.mu_arista[a] for a in aristas] + [ctx.mu_nodo.get(v, 0.0) for v in nodos] + [0.0])
        costo = dist if tipo == "distancia" else sum(self.costo_arco(nodos[k], nodos[k + 1], a)
                                                     for k, a in enumerate(aristas))
        return Tramo(i, j, nodos, aristas, dist, tiempo, riesgo, clima, costo)

    def calcular_tramos(self, tipo: str, conn=None) -> dict:
        from .matriz import caminos

        adj = self.adyacencia(tipo)
        pts = self.puntos()
        rutas, motor = caminos(self, adj, pts, tipo, conn)
        tramos = {(i, j): self._tramo(i, j, *r, tipo) for (i, j), r in rutas.items()}
        if self.b in self.camaras:
            tramos[(self.b, self.b)] = Tramo(self.b, self.b, [self.b], [], 0.0, 0.0, 0.0,
                                             self.ctx.mu_nodo.get(self.b, 0.0), 0.0)
        if tipo == "distancia":
            self.tramos_dist = tramos
        else:
            self.tramos_modelo = tramos
        self.motor_tramos = motor
        return tramos

    def viables(self, tramos: dict) -> tuple[list, dict]:
        ok, motivos = [], {}
        for c in self.camaras:
            ida, vuelta = tramos.get((self.b, c)), tramos.get((c, self.b))
            if c == self.b:
                ok.append(c)
            elif ida is None or vuelta is None:
                motivos[c] = "sin camino volable desde la base"
            elif ida.tiempo + self.s_i + vuelta.tiempo > self.t_util:
                motivos[c] = "no cabe en una batería"
            else:
                ok.append(c)
        return ok, motivos

    def evaluar(self, vuelos: list, tramos: dict, tipo: str = "modelo") -> dict:
        salida, total = [], {"distancia": 0.0, "tiempo_vuelo": 0.0, "riesgo": 0.0, "costo": 0.0}
        factible, motivos = True, []
        for k, seq in enumerate(vuelos):
            if not seq:
                continue
            paradas = [self.b] + list(seq) + [self.b]
            nodos, aristas, dist, tiempo, riesgo, clima, costo = [self.b], [], 0.0, 0.0, 0.0, 0.0, 0.0
            for i, j in zip(paradas[:-1], paradas[1:]):
                t = tramos.get((i, j))
                if t is None and i == j:
                    continue
                if t is None:
                    factible = False
                    motivos.append(f"no hay tramo de {i} a {j}")
                    continue
                nodos += t.nodos[1:]
                aristas += t.aristas
                dist += t.distancia
                tiempo += t.tiempo
                riesgo += t.riesgo
                clima = max(clima, t.clima)
                costo += t.costo
            muestreo = self.s_i * len(seq)
            t_total = tiempo + muestreo
            if t_total > self.t_util + 1e-6:
                factible = False
                motivos.append(f"el vuelo {k + 1} dura {t_total / 60:.1f} min y la batería útil es {self.t_util / 60:.1f} min")
            costo_vuelo = self.costo_modelo(nodos, aristas, clima)
            r = math.exp(-riesgo - clima)
            salida.append({
                "vuelo": len(salida) + 1, "camaras": list(seq), "nodos": nodos, "aristas": aristas,
                "distancia_m": round(dist, 1), "tiempo_traslado_s": round(tiempo, 1),
                "tiempo_muestreo_s": muestreo, "tiempo_s": round(t_total, 1),
                "riesgo_log": riesgo, "clima_log": clima, "p_clima": 1 - math.exp(-clima),
                "R": r, "costo": costo_vuelo,
            })
            total["distancia"] += dist
            total["tiempo_vuelo"] += t_total
            total["riesgo"] += riesgo + clima
            total["costo"] = None if costo_vuelo is None or total["costo"] is None else total["costo"] + costo_vuelo
        n = len(salida)
        total["tiempo_sector"] = total["tiempo_vuelo"] + self.m["t_cambio_s"] * max(0, n - 1)
        total["R"] = math.exp(-total["riesgo"]) if salida else None
        if self.ctx.c.r_min and total["R"] is not None and total["R"] < self.ctx.c.r_min:
            motivos.append(f"R del plan {total['R']:.3f} menor que el mínimo {self.ctx.c.r_min}")
            factible = False
        return {"vuelos": salida, "total": total, "factible": factible and bool(salida), "motivos": motivos}


def dijkstra(adj: dict, s, t, prohibidos=frozenset()):
    dist, prev = {s: 0.0}, {}
    heap = [(0.0, s)]
    hecho = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in hecho:
            continue
        hecho.add(u)
        if u == t:
            break
        for v, aid, c in adj.get(u, ()):
            if v in prohibidos or v in hecho:
                continue
            nd = d + c
            if nd < dist.get(v, math.inf) - 1e-12:
                dist[v], prev[v] = nd, (u, aid)
                heapq.heappush(heap, (nd, v))
    if t not in hecho:
        return None
    nodos, aristas, v = [t], [], t
    while v != s:
        u, aid = prev[v]
        nodos.append(u)
        aristas.append(aid)
        v = u
    return nodos[::-1], aristas[::-1], dist[t]


def vecino_mas_cercano(prob: ProblemaSector, tramos: dict, camaras: list, con_clima: bool = False) -> list:
    pendientes = list(camaras)
    vuelos, actual, seq, usado, clima = [], prob.b, [], 0.0, 0.0
    while pendientes:
        candidatos = []
        for c in pendientes:
            ida, vuelta = tramos.get((actual, c)), tramos.get((c, prob.b))
            if ida is None or vuelta is None:
                continue
            if usado + ida.tiempo + prob.s_i + vuelta.tiempo <= prob.t_util + 1e-9:
                extra = prob.theta * max(0.0, max(clima, ida.clima, vuelta.clima) - clima) if con_clima else 0.0
                candidatos.append((ida.costo + extra, c, ida))
        if candidatos:
            _, c, ida = min(candidatos, key=lambda x: (x[0], x[1]))
            seq.append(c)
            usado += ida.tiempo + prob.s_i
            clima = max(clima, ida.clima)
            actual = c
            pendientes.remove(c)
        elif seq:
            vuelos.append(seq)
            actual, seq, usado, clima = prob.b, [], 0.0, 0.0
        else:
            break
    if seq:
        vuelos.append(seq)
    return vuelos


def resultado(prob: ProblemaSector, tecnica: str, etiqueta: str, vuelos: list, tramos: dict | None,
              tiempo_ms: float, extra: dict | None = None, mensaje: str | None = None,
              no_viables: dict | None = None) -> dict:
    base = {"tecnica": tecnica, "etiqueta": etiqueta, "sector_id": prob.sector_id, "base_id": prob.base["id"],
            "tiempo_ms": round(tiempo_ms, 2), "extra": extra or {},
            "no_visitadas": {**prob.no_visitables, **(no_viables or {})}}
    if not vuelos or tramos is None:
        return {**base, "vuelos": [], "total": None, "factible": False,
                "mensaje": mensaje or "No hay vuelos posibles con estas restricciones."}
    ev = prob.evaluar(vuelos, tramos)
    msgs = ([mensaje] if mensaje else []) + ev["motivos"]
    return {**base, "vuelos": ev["vuelos"], "total": ev["total"], "factible": ev["factible"],
            "mensaje": "; ".join(msgs) if msgs else "ok"}
