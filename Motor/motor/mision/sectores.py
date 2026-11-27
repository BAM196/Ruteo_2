import argparse
import itertools
import json
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np

from .. import grafo
from ..config import SECTORES_JSON, conectar, fuente_por_defecto, parametros_mision
from . import bases as mod_bases
from . import bloques, prioridad


def _xy(esc, c):
    n = esc.nodos[c]
    return grafo.xy(n["lon"], n["lat"])


def diametro(esc, camaras) -> float:
    pts = [_xy(esc, c) for c in camaras]
    return max([float(np.linalg.norm(a - b)) for a, b in itertools.combinations(pts, 2)] + [0.0])


def subconjuntos_factibles(esc, camaras) -> dict:
    objetivo = set(camaras)
    factibles = {}
    for b in esc.bases.values():
        servidas = sorted(c for c, info in b["camaras"].items() if info["bloque_visible"] and c in objetivo)
        for k in range(1, len(servidas) + 1):
            for comb in itertools.combinations(servidas, k):
                factibles.setdefault(frozenset(comb), True)
    for c in camaras:
        factibles.setdefault(frozenset([c]), False)
    return factibles


def particion(esc, camaras, m: dict | None = None) -> list:
    m = m or parametros_mision()
    camaras = sorted(set(camaras))
    factibles = subconjuntos_factibles(esc, camaras)
    por_camara = {c: [s for s in factibles if c in s] for c in camaras}
    diam = {s: diametro(esc, s) for s in factibles}
    escala = m["diametro_max"] * len(camaras) + 1.0

    @lru_cache(maxsize=None)
    def mejor(restantes: frozenset):
        if not restantes:
            return 0.0, ()
        c = min(restantes)
        opciones = []
        for s in por_camara[c]:
            if s <= restantes:
                costo, resto = mejor(restantes - s)
                opciones.append((1.0 + diam[s] / escala + costo, (s,) + resto))
        return min(opciones, key=lambda o: o[0])

    _, grupos = mejor(frozenset(camaras))
    return [{"camaras": sorted(g), "con_base": factibles[g], "diametro_m": round(diam[g], 1)} for g in grupos]


def _envolvente(puntos):
    pts = sorted(set(puntos))
    if len(pts) <= 2:
        return pts

    def cruz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    inf, sup = [], []
    for p in pts:
        while len(inf) >= 2 and cruz(inf[-2], inf[-1], p) <= 0:
            inf.pop()
        inf.append(p)
    for p in reversed(pts):
        while len(sup) >= 2 and cruz(sup[-2], sup[-1], p) <= 0:
            sup.pop()
        sup.append(p)
    return inf[:-1] + sup[:-1]


def poligono(esc, camaras, m) -> list:
    esquinas = []
    for c in camaras:
        n = esc.nodos[c]
        esquinas += [tuple(p) for p in bloques.cuadrado(n["lon"], n["lat"], m)[:-1]]
    casco = _envolvente(esquinas)
    return [[list(p) for p in casco + casco[:1]]]


def armar_sectores(esc, camaras=None, m: dict | None = None, peso_valor: float | None = None) -> list:
    m = m or parametros_mision()
    camaras = sorted(camaras or esc.camaras())
    grupos = particion(esc, camaras, m)
    grupos.sort(key=lambda g: -max(esc.nodos[c]["lat"] for c in g["camaras"]))
    sectores = []
    for k, g in enumerate(grupos, start=1):
        base, regla = mod_bases.elegir(esc, g["camaras"])
        comp = prioridad.componentes(esc, g["camaras"], m["peso_rli"])
        s = {
            "id": k, "camaras": g["camaras"], "n_camaras": len(g["camaras"]), "diametro_m": g["diametro_m"],
            "base": mod_bases.resumen(base), "regla_base": regla,
            "valor_conservacion": round(comp["V"], 4), "presion_exoticas": round(comp["P"], 4),
            "descripcion": prioridad.describir(esc, comp),
            "registros": comp["registros"],
            "poligono": poligono(esc, g["camaras"], m),
        }
        sectores.append(s)
    prioridad.normalizar(sectores, m["peso_valor"] if peso_valor is None else peso_valor)
    for s in sectores:
        s["subtitulo"] = prioridad.subtitulo(s)
    return sectores


def documento(esc, sectores, m) -> dict:
    tam = [s["n_camaras"] for s in sectores]
    return {
        "meta": {
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "metodo": (
                "Partición exacta: el mínimo número de grupos tal que cada grupo tiene una base que deja todas "
                "sus cámaras a ≤ R_op − r_b y con su bloque de muestreo a la vista; a igual número, la menor "
                "suma de diámetros."
            ),
            "diametro_max_m": round(m["diametro_max"], 1),
            "alcance_m": round(m["alcance"], 1),
            "n_sectores": len(sectores),
            "tamanos": {str(k): tam.count(k) for k in sorted(set(tam))},
            "sin_base": [s["id"] for s in sectores if s["base"] is None],
            "prioridad": "Prioridad = 100 · (V̂ + P̂) / 2; V = Σ w_e f_e,s sobre nativas; P = fracción de cámaras con exóticas",
            "numeracion": "De norte a sur",
        },
        "sectores": sectores,
    }


def cargar_bd(sectores, conn=None):
    from psycopg2.extras import Json, execute_values

    propia = conn is None
    conn = conn or conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE sector_camara, sectores CASCADE")
            filas = []
            for s in sectores:
                anillo = ", ".join(f"{x} {y}" for x, y in s["poligono"][0])
                filas.append((s["id"], s["base"]["id"] if s["base"] else None, s["n_camaras"], s["diametro_m"],
                              s["valor_conservacion"], s["presion_exoticas"], s["prioridad"], s["subtitulo"],
                              Json({k: s[k] for k in ("descripcion", "registros", "V_norm", "P_norm", "regla_base")}),
                              f"SRID=4326;POLYGON(({anillo}))" if len(s["poligono"][0]) >= 4 else None))
            execute_values(cur, """
                INSERT INTO sectores (id, base_id, n_camaras, diametro_m, valor_conservacion, presion_exoticas,
                                      prioridad, subtitulo, detalle, geom) VALUES %s""", filas)
            execute_values(cur, "INSERT INTO sector_camara (sector_id, camara_id) VALUES %s",
                           [(s["id"], c) for s in sectores for c in s["camaras"]])
        conn.commit()
    finally:
        if propia:
            conn.close()


def leer_sectores(esc) -> list:
    if SECTORES_JSON.exists():
        doc = json.loads(SECTORES_JSON.read_text(encoding="utf-8"))
        if set(c for s in doc["sectores"] for c in s["camaras"]) == set(esc.camaras()):
            return doc["sectores"]
    return armar_sectores(esc)


def main():
    ap = argparse.ArgumentParser(description="Sectores de monitoreo, su base y su prioridad.")
    ap.add_argument("--fuente", choices=["db", "json"], default=None)
    ap.add_argument("--cargar", action="store_true")
    args = ap.parse_args()
    m = parametros_mision()
    esc = grafo.cargar(args.fuente or fuente_por_defecto(), usar_cache=False)
    sectores = armar_sectores(esc, m=m)
    doc = documento(esc, sectores, m)
    SECTORES_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(esc.camaras())} cámaras → {len(sectores)} sectores; tamaños {doc['meta']['tamanos']}; "
          f"sin base: {doc['meta']['sin_base']}")
    for s in sorted(sectores, key=lambda s: -s["prioridad"])[:5]:
        print("  " + s["subtitulo"])
    if args.cargar:
        cargar_bd(sectores)
        print("Cargado en sectores y sector_camara.")


if __name__ == "__main__":
    main()
