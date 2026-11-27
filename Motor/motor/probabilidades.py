import argparse
import json
import math
from datetime import datetime, timezone

from . import grafo
from .config import PROB_FALLO_JSON, RAIZ, amenazas_cfg, conectar, fuente_por_defecto, valor

AMENAZAS = ("firms", "meteo", "ebird")


def acotar(p: float, cota: float) -> float:
    return min(max(float(p), 0.0), cota)


def combinar(ps) -> float:
    prod = 1.0
    for p in ps:
        prod *= 1.0 - p
    return 1.0 - prod


def phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _puntos_cercanos(geom_xy, puntos_xy, es_linea):
    for item, pxy in puntos_xy:
        d = grafo.distancia_punto_linea(pxy, geom_xy) if es_linea else float(((geom_xy - pxy) ** 2).sum() ** 0.5)
        yield item, d


def modelo_firms(geom_xy, es_linea, focos_xy, cfg):
    R = float(valor(cfg["radio_m"]))
    p_real = valor(cfg["p_real_por_confianza"])
    escalon = valor(cfg.get("decaimiento", "lineal")) == "escalon"
    ps, cercanos = [], []
    for foco, d in _puntos_cercanos(geom_xy, focos_xy, es_linea):
        if d >= R:
            continue
        conf = str(foco.get("confidence") or "").strip().lower()[:1]
        p0 = p_real.get(conf, p_real["desconocida"])
        p = p0 if escalon else p0 * max(0.0, 1.0 - d / R)
        ps.append(p)
        cercanos.append({"foco_id": foco["id"], "distancia_m": round(d, 1), "confianza": foco.get("confidence"),
                         "p_foco_real": p0, "p": round(p, 6)})
    return combinar(ps), {"focos_en_radio": cercanos, "radio_m": R}


def radio_aves(cfg) -> float:
    return float(valor(cfg["distancia_precaucion_m"])) + float(valor(cfg["r_mov_m"]))


def modelo_ebird(geom_xy, es_linea, aves_xy, cfg, fecha_ref):
    R = radio_aves(cfg)
    p0 = float(valor(cfg["p0"]))
    ventana = float(valor(cfg["ventana_dias"]))
    ps, cercanos = [], []
    for ave, d in _puntos_cercanos(geom_xy, aves_xy, es_linea):
        if d >= R:
            continue
        f_rec = 1.0
        if ave.get("fecha_obs") and fecha_ref:
            edad = (fecha_ref - ave["fecha_obs"]).total_seconds() / 86400
            f_rec = max(0.0, 1.0 - max(edad, 0.0) / ventana)
        p_i = p0 * f_rec * max(0.0, 1.0 - d / R)
        n = max(1, int(ave.get("cantidad") or 1))
        p = 1.0 - (1.0 - p_i) ** n
        ps.append(p)
        cercanos.append({"avistamiento_id": ave["id"], "especie": ave.get("comun"), "distancia_m": round(d, 1),
                         "f_recencia": round(f_rec, 3), "n_aves": n, "p_por_ave": round(p_i, 6), "p": round(p, 6)})
    return combinar(ps), {"avistamientos_en_radio": cercanos, "radio_m": R}


def rafaga_a_altura(g10: float, cfg, altura: float = 80.0) -> float:
    return g10 * (altura / float(valor(cfg["altura_referencia_m"]))) ** float(valor(cfg["alpha_perfil"]))


def modelo_meteo_nodo(lectura, cfg, altura: float = 80.0):
    if not lectura:
        return 0.0, {"lectura": None, "nota": "sin lectura para este nodo"}
    g10 = lectura.get("rafaga_ms")
    usa = "rafaga_ms"
    if g10 is None:
        g10, usa = lectura.get("viento_ms"), "viento_ms"
    sigma = float(valor(cfg["sigma_rafaga_ms"]))
    p_viento, g80 = 0.0, None
    if g10 is not None:
        g80 = rafaga_a_altura(g10, cfg, altura)
        p_viento = 1.0 - phi((float(valor(cfg["rafaga_max_ms"])) - g80) / sigma)
    st = float(valor(cfg["sigma_temperatura_c"]))
    t_min = lectura.get("temperatura_min", lectura.get("temperatura"))
    t_max = lectura.get("temperatura_max", lectura.get("temperatura"))
    p_temp = 0.0
    if t_min is not None and t_max is not None:
        p_frio = phi((float(valor(cfg["temperatura_min_c"])) - t_min) / st)
        p_calor = 1.0 - phi((float(valor(cfg["temperatura_max_c"])) - t_max) / st)
        p_temp = min(1.0, p_frio + p_calor)
    if lectura.get("prob_lluvia") is not None:
        p_lluvia, regla = float(lectura["prob_lluvia"]) / 100.0, "probabilidad de precipitación"
    elif lectura.get("precipitacion_mm") is not None:
        p_lluvia, regla = (1.0 if lectura["precipitacion_mm"] > 0 else 0.0), "llovió en la ventana (1) o no (0)"
    else:
        p_lluvia, regla = 0.0, "sin dato de lluvia"
    p = combinar([p_viento, p_temp, p_lluvia])
    return p, {
        "lectura": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in lectura.items()},
        "viento_usado": usa, "rafaga_80m_ms": None if g80 is None else round(g80, 2),
        "p_viento": round(p_viento, 6), "p_temperatura": round(p_temp, 6),
        "p_lluvia": round(p_lluvia, 6), "regla_lluvia": regla,
    }


def fecha_referencia(esc) -> datetime | None:
    if esc.fecha:
        f = grafo.fecha(esc.fecha)
        if f:
            return f.replace(hour=12)
    fechas = [a["fecha_obs"] for a in esc.aves if a.get("fecha_obs")]
    return max(fechas) if fechas else None


def _overrides(overrides, tipo):
    return {int(k): float(v) for k, v in ((overrides or {}).get(tipo) or {}).items()}


def calcular(esc, cfg: dict | None = None, overrides: dict | None = None) -> dict:
    cfg = cfg or amenazas_cfg()
    cota = cfg["cota_superior"]
    am = cfg["amenazas"]
    activas = [k for k in AMENAZAS if am.get(k, {}).get("activa")]
    focos_xy = [(f, grafo.xy(f["lon"], f["lat"])) for f in esc.focos]
    aves_xy = [(a, grafo.xy(a["lon"], a["lat"])) for a in esc.aves]
    fecha_ref = fecha_referencia(esc)
    ov_n, ov_a = _overrides(overrides, "nodos"), _overrides(overrides, "aristas")

    nodos_out, p_meteo = [], {}
    for nid, n in sorted(esc.nodos.items()):
        g = grafo.xy(n["lon"], n["lat"])
        por, det = {}, {}
        if "firms" in activas:
            por["firms"], det["firms"] = modelo_firms(g, False, focos_xy, am["firms"])
        if "meteo" in activas:
            por["meteo"], det["meteo"] = modelo_meteo_nodo(esc.meteo.get(nid), am["meteo"])
            p_meteo[nid] = por["meteo"]
        if "ebird" in activas:
            por["ebird"], det["ebird"] = modelo_ebird(g, False, aves_xy, am["ebird"], fecha_ref)
        if nid in ov_n:
            por["escenario"], det["escenario"] = ov_n[nid], {"nota": "probabilidad simulada"}
        por = {k: acotar(v, cota) for k, v in por.items()}
        nodos_out.append({"id": nid, "p_total": acotar(combinar(por.values()), cota), "por_amenaza": por, "detalle": det})

    aristas_out = []
    for aid, a in sorted(esc.aristas.items()):
        linea = [grafo.xy(lon, lat) for lon, lat in a["coords"]]
        por, det = {}, {}
        if "firms" in activas:
            por["firms"], det["firms"] = modelo_firms(linea, True, focos_xy, am["firms"])
        if "meteo" in activas:
            pu, pv = p_meteo.get(a["source"], 0.0), p_meteo.get(a["target"], 0.0)
            por["meteo"] = max(pu, pv)
            det["meteo"] = {"regla": "max(p_u, p_v)", "p_source": round(pu, 6), "p_target": round(pv, 6)}
        if "ebird" in activas:
            por["ebird"], det["ebird"] = modelo_ebird(linea, True, aves_xy, am["ebird"], fecha_ref)
        if aid in ov_a:
            por["escenario"], det["escenario"] = ov_a[aid], {"nota": "probabilidad simulada"}
        por = {k: acotar(v, cota) for k, v in por.items()}
        aristas_out.append({"id": aid, "source": a["source"], "target": a["target"],
                            "p_total": acotar(combinar(por.values()), cota), "por_amenaza": por, "detalle": det})

    return {
        "meta": {
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "principio": cfg.get("principio"),
            "datos": esc.resumen(),
            "amenazas_activas": activas,
            "combinacion": "q = 1 − Π_k (1 − q_k), amenazas independientes",
            "cota_superior": cota,
            "nota_cota": "un elemento con p igual a la cota se excluye en las técnicas 2, 3 y 4",
            "overrides_prob": overrides or {},
            "fecha_referencia": fecha_ref.isoformat() if fecha_ref else None,
            "radio_aves_m": radio_aves(am["ebird"]),
            "parametros": am,
            "independencia": (
                "Si las amenazas son independientes la combinación es exacta; si se correlacionan "
                "positivamente, la probabilidad real de que falle alguna es menor, así que la fórmula "
                "es una cota superior del riesgo y nunca baja de la mayor de las q_k."
            ),
        },
        "nodos": nodos_out,
        "aristas": aristas_out,
    }


def mapas(doc: dict) -> tuple[dict, dict]:
    return ({n["id"]: n["p_total"] for n in doc["nodos"]}, {a["id"]: a["p_total"] for a in doc["aristas"]})


def log_supervivencia(p: float) -> float:
    return -math.log(1.0 - p)


def aplicar_schema(cur):
    for sentencia in (RAIZ / "Diagrama" / "schema.sql").read_text(encoding="utf-8").split(";"):
        if sentencia.strip():
            cur.execute(sentencia)


def cargar_bd(doc: dict, conn=None):
    from psycopg2.extras import Json, execute_values

    propia = conn is None
    conn = conn or conectar()
    try:
        with conn.cursor() as cur:
            aplicar_schema(cur)
            cur.execute("TRUNCATE prob_fallo_nodo, prob_fallo_arista")
            cur.execute("SELECT id FROM nodos")
            nodos_bd = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT id FROM aristas")
            aristas_bd = {r[0] for r in cur.fetchall()}
            gen = doc["meta"]["generado"]
            execute_values(cur, "INSERT INTO prob_fallo_nodo (nodo_id, amenaza, p_fallo, detalle, generado) VALUES %s",
                           [(n["id"], k, p, Json(n["detalle"].get(k, {})), gen)
                            for n in doc["nodos"] if n["id"] in nodos_bd for k, p in n["por_amenaza"].items()])
            execute_values(cur, "INSERT INTO prob_fallo_arista (arista_id, amenaza, p_fallo, detalle, generado) VALUES %s",
                           [(a["id"], k, p, Json(a["detalle"].get(k, {})), gen)
                            for a in doc["aristas"] if a["id"] in aristas_bd for k, p in a["por_amenaza"].items()])
        conn.commit()
    finally:
        if propia:
            conn.close()


def main():
    ap = argparse.ArgumentParser(description="Probabilidad de falla del dron por nodo y por arista.")
    ap.add_argument("--fuente", choices=["db", "json"], default=None)
    ap.add_argument("--cargar", action="store_true", help="cargar el resultado a la base")
    ap.add_argument("--salida", default=str(PROB_FALLO_JSON))
    args = ap.parse_args()
    fuente = args.fuente or fuente_por_defecto()
    esc = grafo.cargar(fuente, usar_cache=False)
    doc = calcular(esc)
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, default=str)
    n = sum(1 for x in doc["nodos"] if x["p_total"] > 0)
    a = sum(1 for x in doc["aristas"] if x["p_total"] > 0)
    print(f"Probabilidades ({fuente}): {len(doc['nodos'])} nodos ({n} con p > 0), "
          f"{len(doc['aristas'])} aristas ({a} con p > 0). Escrito: {args.salida}")
    if args.cargar:
        cargar_bd(doc)
        print("Cargado en prob_fallo_nodo y prob_fallo_arista.")


if __name__ == "__main__":
    main()
