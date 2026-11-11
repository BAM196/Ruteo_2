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


def rampa(x, x0, x1) -> float:
    if x is None:
        return 0.0
    if x1 <= x0:
        return 1.0 if x >= x1 else 0.0
    return min(max((x - x0) / (x1 - x0), 0.0), 1.0)


def _puntos_cercanos(geom_xy, puntos_xy, es_linea):
    for item, pxy in puntos_xy:
        d = grafo.distancia_punto_linea(pxy, geom_xy) if es_linea else float(
            ((geom_xy - pxy) ** 2).sum() ** 0.5)
        yield item, d


def modelo_firms(geom_xy, es_linea, focos_xy, cfg):
    R = valor(cfg["radio_m"])
    p0s = valor(cfg["p0_por_confianza"])
    ps, cercanos = [], []
    for foco, d in _puntos_cercanos(geom_xy, focos_xy, es_linea):
        if d >= R:
            continue
        conf = str(foco.get("confidence") or "").strip().lower()[:1]
        p0 = p0s.get(conf, p0s["desconocida"])
        p = p0 * max(0.0, 1.0 - d / R)
        ps.append(p)
        cercanos.append({"foco_id": foco["id"], "distancia_m": round(d, 1),
                         "confianza": foco.get("confidence"), "p": round(p, 6)})
    return combinar(ps), {"focos_en_radio": cercanos, "radio_m": R}


def modelo_ebird(geom_xy, es_linea, aves_xy, cfg, fecha_ref):
    R = valor(cfg["distancia_precaucion_m"]) + valor(cfg["incertidumbre_ubicacion_m"])
    p0 = valor(cfg["p0"])
    n_ref = valor(cfg["cantidad_referencia"])
    ventana = valor(cfg["ventana_dias"])
    ps, cercanos = [], []
    for ave, d in _puntos_cercanos(geom_xy, aves_xy, es_linea):
        if d >= R:
            continue
        f_cant = min(1.0, (ave.get("cantidad") or n_ref) / n_ref)
        f_rec = 1.0
        if ave.get("fecha_obs") and fecha_ref:
            edad = (fecha_ref - ave["fecha_obs"]).total_seconds() / 86400
            f_rec = max(0.0, 1.0 - max(edad, 0.0) / ventana)
        p = p0 * f_rec * f_cant * max(0.0, 1.0 - d / R)
        ps.append(p)
        cercanos.append({"avistamiento_id": ave["id"], "especie": ave.get("comun"),
                         "distancia_m": round(d, 1), "f_recencia": round(f_rec, 3),
                         "f_cantidad": round(f_cant, 3), "p": round(p, 6)})
    return combinar(ps), {"avistamientos_en_radio": cercanos, "radio_m": R}


def modelo_meteo_nodo(lectura, cfg):
    if not lectura:
        return 0.0, {"lectura": None, "nota": "sin lectura para este nodo"}
    viento = lectura.get("rafaga_ms")
    usa = "rafaga_ms"
    if viento is None:
        viento, usa = lectura.get("viento_ms"), "viento_ms"
    p_viento = rampa(viento, valor(cfg["v_seguro_ms"]), valor(cfg["v_max_ms"]))
    t = lectura.get("temperatura")
    p_temp = 0.0 if t is None else float(
        t < valor(cfg["temperatura_min_c"]) or t > valor(cfg["temperatura_max_c"]))
    p_lluvia = rampa(lectura.get("lluvia_mm_h"), 0.0, valor(cfg["lluvia_max_mm_h"]))
    p = combinar([p_viento, p_temp, p_lluvia])
    return p, {
        "lectura": {k: (None if v is None else round(v, 3)) for k, v in lectura.items()},
        "viento_usado": usa,
        "p_viento": round(p_viento, 6), "p_temperatura": p_temp, "p_lluvia": round(p_lluvia, 6),
    }


def _fecha_ref_aves(aves):
    fechas = [a["fecha_obs"] for a in aves if a.get("fecha_obs")]
    return max(fechas) if fechas else None


def _overrides(overrides, tipo):
    return {int(k): float(v) for k, v in ((overrides or {}).get(tipo) or {}).items()}


def calcular(esc: grafo.Escenario, cfg: dict | None = None, overrides: dict | None = None) -> dict:
    cfg = cfg or amenazas_cfg()
    cota = cfg["cota_superior"]
    am = cfg["amenazas"]
    activas = [k for k in AMENAZAS if am.get(k, {}).get("activa")]

    focos_xy = [(f, grafo.xy(f["lon"], f["lat"])) for f in esc.focos]
    aves_xy = [(a, grafo.xy(a["lon"], a["lat"])) for a in esc.aves]
    fecha_ref = _fecha_ref_aves(esc.aves)
    ov_n, ov_a = _overrides(overrides, "nodos"), _overrides(overrides, "aristas")

    nodos_out, p_meteo_nodo = [], {}
    for nid, n in sorted(esc.nodos.items()):
        g = grafo.xy(n["lon"], n["lat"])
        por, det = {}, {}
        if "firms" in activas:
            por["firms"], det["firms"] = modelo_firms(g, False, focos_xy, am["firms"])
        if "meteo" in activas:
            por["meteo"], det["meteo"] = modelo_meteo_nodo(esc.meteo.get(nid), am["meteo"])
            p_meteo_nodo[nid] = por["meteo"]
        if "ebird" in activas:
            por["ebird"], det["ebird"] = modelo_ebird(g, False, aves_xy, am["ebird"], fecha_ref)
        if nid in ov_n:
            por["escenario"], det["escenario"] = ov_n[nid], {"nota": "probabilidad forzada (overrides_prob)"}
        por = {k: acotar(v, cota) for k, v in por.items()}
        nodos_out.append({"id": nid, "p_total": acotar(combinar(por.values()), cota),
                          "por_amenaza": por, "detalle": det})

    aristas_out = []
    for aid, a in sorted(esc.aristas.items()):
        linea = [grafo.xy(lon, lat) for lon, lat in a["coords"]]
        por, det = {}, {}
        if "firms" in activas:
            por["firms"], det["firms"] = modelo_firms(linea, True, focos_xy, am["firms"])
        if "meteo" in activas:
            pu, pv = p_meteo_nodo.get(a["source"], 0.0), p_meteo_nodo.get(a["target"], 0.0)
            por["meteo"] = max(pu, pv)
            det["meteo"] = {"regla": "max(p_u, p_v), conservador", "p_source": round(pu, 6),
                            "p_target": round(pv, 6)}
        if "ebird" in activas:
            por["ebird"], det["ebird"] = modelo_ebird(linea, True, aves_xy, am["ebird"], fecha_ref)
        if aid in ov_a:
            por["escenario"], det["escenario"] = ov_a[aid], {"nota": "probabilidad forzada (overrides_prob)"}
        por = {k: acotar(v, cota) for k, v in por.items()}
        aristas_out.append({"id": aid, "source": a["source"], "target": a["target"],
                            "p_total": acotar(combinar(por.values()), cota),
                            "por_amenaza": por, "detalle": det})

    return {
        "meta": {
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "datos": esc.resumen(),
            "amenazas_activas": activas,
            "combinacion": "q = 1 - prod_k (1 - q_k), amenazas independientes",
            "cota_superior": cota,
            "nota_cota": "p = cota_superior equivale a exclusión del elemento en las técnicas 2, 3 y 4",
            "overrides_prob": overrides or {},
            "fecha_referencia_ebird": fecha_ref.isoformat() if fecha_ref else None,
            "parametros": am,
            "limitacion": (
                "Tratar las amenazas como independientes, y un nodo y sus aristas como "
                "independientes entre sí, sobreestima el riesgo cuando un mismo foco "
                "afecta a ambos. Es una aproximación conservadora."
            ),
        },
        "nodos": nodos_out,
        "aristas": aristas_out,
    }


def mapas(doc: dict) -> tuple[dict, dict]:
    return ({n["id"]: n["p_total"] for n in doc["nodos"]},
            {a["id"]: a["p_total"] for a in doc["aristas"]})


def log_supervivencia(p: float) -> float:
    return -math.log(1.0 - p)


def aplicar_schema(cur):
    schema = RAIZ / "Diagrama" / "schema.sql"
    sql = schema.read_text(encoding="utf-8")
    for sentencia in sql.split(";"):
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
            gen = doc["meta"]["generado"]
            execute_values(cur, """
                INSERT INTO prob_fallo_nodo (nodo_id, amenaza, p_fallo, detalle, generado)
                VALUES %s
            """, [(n["id"], k, p, Json(n["detalle"].get(k, {})), gen)
                  for n in doc["nodos"] for k, p in n["por_amenaza"].items()])
            execute_values(cur, """
                INSERT INTO prob_fallo_arista (arista_id, amenaza, p_fallo, detalle, generado)
                VALUES %s
            """, [(a["id"], k, p, Json(a["detalle"].get(k, {})), gen)
                  for a in doc["aristas"] for k, p in a["por_amenaza"].items()])
        conn.commit()
    finally:
        if propia:
            conn.close()


def main():
    ap = argparse.ArgumentParser(description="Punto 5: probabilidad de falla por nodo y arista.")
    ap.add_argument("--fuente", choices=["db", "json"], default=None)
    ap.add_argument("--cargar", action="store_true", help="cargar el resultado a la base")
    ap.add_argument("--salida", default=str(PROB_FALLO_JSON))
    args = ap.parse_args()

    fuente = args.fuente or fuente_por_defecto()
    esc = grafo.cargar(fuente)
    doc = calcular(esc)
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, default=str)

    con_riesgo_n = sum(1 for n in doc["nodos"] if n["p_total"] > 0)
    con_riesgo_a = sum(1 for a in doc["aristas"] if a["p_total"] > 0)
    print(f"Probabilidades calculadas ({fuente}): {len(doc['nodos'])} nodos "
          f"({con_riesgo_n} con p > 0), {len(doc['aristas'])} aristas ({con_riesgo_a} con p > 0).")
    print(f"Escrito: {args.salida}")
    if args.cargar:
        cargar_bd(doc)
        print("Cargado en prob_fallo_nodo y prob_fallo_arista.")


if __name__ == "__main__":
    main()
