import ast
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from terreno import DEM, a_geo, a_metrico, bloque, linea_de_vista, parametros, perfil

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", AQUI / "nodosv2.json"))
ARISTAS_PATH = Path(os.getenv("ARISTAS_PATH", AQUI / "aristasv2.json"))
SENDEROS_PATH = RAIZ / "Metadata" / "metadata_senderos.json"
DEM_PATH = Path(os.getenv("DEM_PATH", RAIZ / "data" / "dem_pumalin.tif"))
SALIDA = AQUI / "bases.json"
PASO_SENDERO_M = 100.0
ENLACES_POR_BASE = 4
ID_BASE = 100000
ID_ENLACE = 100000


def ruta_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(path)


def leer(path: Path, clave: str) -> list:
    if not path.exists():
        sys.exit(f"No existe {path}.")
    return json.loads(path.read_text(encoding="utf-8"))[clave]


def coords_sendero(s: dict) -> list:
    c = s["coordenadas"]
    if isinstance(c, str):
        c = ast.literal_eval(c)
    return c


def candidatas_sendero(senderos: list) -> list[dict]:
    salida = []
    for s in senderos:
        if s.get("tipo") != "trazado":
            continue
        c = coords_sendero(s)
        if len(c) < 2:
            continue
        x, y = a_metrico([p[0] for p in c], [p[1] for p in c])
        acum = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
        for d in np.arange(0.0, acum[-1] + 1e-9, PASO_SENDERO_M):
            salida.append({"sendero_id": int(s["id"]), "sendero": s.get("nombre"),
                           "x": float(np.interp(d, acum, x)), "y": float(np.interp(d, acum, y))})
    return salida


def candidatas_entre_camaras(camaras: list, xy_nodo: dict, diametro: float) -> list[dict]:
    salida = []
    for i, a in enumerate(camaras):
        for b in camaras[i + 1:]:
            (xa, ya), (xb, yb) = xy_nodo[a["id"]], xy_nodo[b["id"]]
            largo = math.hypot(xb - xa, yb - ya)
            if largo > diametro:
                continue
            for d in np.arange(PASO_SENDERO_M, largo - PASO_SENDERO_M / 2, PASO_SENDERO_M):
                t = d / largo
                salida.append({"entre": [a["id"], b["id"]], "nombre": f"Entre {a.get('nombre')} y {b.get('nombre')}",
                               "x": xa + t * (xb - xa), "y": ya + t * (yb - ya)})
    return salida


def objetivos_perfil(pf: dict):
    xs, ys, zs = pf["muestras_xy"]
    return np.column_stack([xs, ys, zs])


def main():
    if not DEM_PATH.exists():
        sys.exit(f"No existe {DEM_PATH}. Corre Metadata/extraer_dem.py primero.")
    p = parametros()
    dem = DEM(DEM_PATH, p["paso"])
    nodos = leer(NODOS_PATH, "nodos")
    aristas = leer(ARISTAS_PATH, "aristas")
    senderos = leer(SENDEROS_PATH, "senderos") if SENDEROS_PATH.exists() else []

    nx, ny = a_metrico([n["lon"] for n in nodos], [n["lat"] for n in nodos])
    xy_nodo = {n["id"]: (float(a), float(b)) for n, a, b in zip(nodos, nx, ny)}
    camaras = [n for n in nodos if n.get("es_camara")]
    cam_xy = np.array([xy_nodo[c["id"]] for c in camaras])
    bloques = {c["id"]: bloque(dem, *xy_nodo[c["id"]], p) for c in camaras}

    perfiles = {}
    for a in aristas:
        x, y = a_metrico([c[0] for c in a["coordenadas"]], [c[1] for c in a["coordenadas"]])
        perfiles[a["id"]] = perfil(dem, np.column_stack([x, y]), p)

    candidatas = [{"tipo": "camara", "nodo_id": c["id"], "nombre": c.get("nombre"),
                   "x": xy_nodo[c["id"]][0], "y": xy_nodo[c["id"]][1]} for c in camaras]
    candidatas += [{"tipo": "sendero", **s} for s in candidatas_sendero(senderos)]
    candidatas += [{"tipo": "camino_camaras", **s} for s in candidatas_entre_camaras(camaras, xy_nodo, 2 * p["alcance"])]
    utiles = []
    for c in candidatas:
        d = np.hypot(cam_xy[:, 0] - c["x"], cam_xy[:, 1] - c["y"])
        if d.min() <= p["alcance"]:
            utiles.append(c)
    print(f"Candidatas: {len(candidatas)} ({len(camaras)} cámaras); "
          f"{len(utiles)} quedan a ≤ {p['alcance']:.0f} m de alguna cámara.")

    bases = []
    id_enlace = ID_ENLACE
    for i, c in enumerate(utiles):
        bx, by = c["x"], c["y"]
        sup = float(dem.altura(bx, by))
        ojo = (bx, by, sup + p["ojo"])
        lon, lat = a_geo(bx, by)
        base_id = c["nodo_id"] if c["tipo"] == "camara" else ID_BASE + i

        alcanzables = []
        for cam in camaras:
            cx, cy = xy_nodo[cam["id"]]
            d = math.hypot(cx - bx, cy - by)
            if d > p["alcance"]:
                continue
            visible = linea_de_vista(dem, ojo, bloques[cam["id"]], p)
            alcanzables.append({"camara_id": cam["id"], "distancia_m": round(d, 1),
                                "bloque_visible": bool(visible.all()),
                                "fraccion_visible": round(float(visible.mean()), 3)})

        enlaces = []
        cerca = sorted((math.hypot(x - bx, y - by), nid) for nid, (x, y) in xy_nodo.items()
                       if nid != base_id)
        destinos = [] if c["tipo"] == "camara" else [nid for d, nid in cerca if d <= p["r_op"]
                                                     and nid < ID_BASE][:ENLACES_POR_BASE]
        destinos += [a["camara_id"] for a in alcanzables
                     if a["bloque_visible"] and a["camara_id"] != base_id and a["camara_id"] not in destinos]
        for nid in destinos:
            tx, ty = xy_nodo[nid]
            d = math.hypot(tx - bx, ty - by)
            pf = perfil(dem, np.array([[bx, by], [tx, ty]]), p)
            if pf["bloqueada"] or not linea_de_vista(dem, ojo, objetivos_perfil(pf), p).all():
                continue
            enlaces.append({"id": id_enlace, "nodo_id": nid, "distancia_m": round(d, 1),
                            "largo_3d_m": round(pf["largo_3d_m"], 1),
                            "ascenso_ida_m": round(pf["ascenso_ida_m"], 1),
                            "ascenso_vuelta_m": round(pf["ascenso_vuelta_m"], 1),
                            "despeje_min_m": round(pf["despeje_min_m"], 1),
                            "puntos": [[round(float(lon), 6), round(float(lat), 6), round(sup + p["altura"], 1)]]
                            + pf["puntos"][1:]})
            id_enlace += 1

        visibles, bloqueadas = [], []
        for a in aristas:
            ux, uy = xy_nodo[a["source"]]
            vx, vy = xy_nodo[a["target"]]
            du, dv = math.hypot(ux - bx, uy - by), math.hypot(vx - bx, vy - by)
            if max(du, dv) > p["r_op"]:
                continue
            pf = perfiles[a["id"]]
            if pf["bloqueada"]:
                bloqueadas.append({"arista_id": a["id"], "motivo": "altura"})
                continue
            obj = objetivos_perfil(pf)
            if np.hypot(obj[:, 0] - bx, obj[:, 1] - by).max() > p["r_op"]:
                continue
            if not linea_de_vista(dem, ojo, obj, p).all():
                bloqueadas.append({"arista_id": a["id"], "motivo": "linea_de_vista"})
                continue
            visibles.append(a["id"])

        bases.append({
            "id": base_id, "tipo": c["tipo"], "nodo_id": c.get("nodo_id"),
            "nombre": c.get("nombre") or f"Sendero {c.get('sendero')}",
            "entre_camaras": c.get("entre"),
            "sendero_id": c.get("sendero_id"),
            "lon": round(float(lon), 6), "lat": round(float(lat), 6), "elevacion_m": round(sup, 1),
            "camaras": alcanzables, "enlaces": enlaces,
            "aristas_visibles": visibles, "aristas_bloqueadas": bloqueadas,
        })
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(utiles)} bases")

    servibles = {cam["camara_id"] for b in bases for cam in b["camaras"] if cam["bloque_visible"]}
    documento = {
        "meta": {
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dem": ruta_repo(DEM_PATH),
            "nodos_origen": ruta_repo(NODOS_PATH),
            "aristas_origen": ruta_repo(ARISTAS_PATH),
            "senderos_origen": ruta_repo(SENDEROS_PATH),
            "regla_candidatas": (
                "Posición de cada cámara (CONAF las instala y revisa a pie), un punto cada 100 m sobre los "
                "senderos oficiales y un punto cada 100 m en la caminata recta entre dos cámaras a ≤ 2 · alcance; "
                "se guardan solo las que quedan a ≤ alcance de alguna cámara."
            ),
            "radio_operacion_m": p["r_op"],
            "media_diagonal_bloque_m": round(p["r_b"], 1),
            "alcance_camara_m": round(p["alcance"], 1),
            "ojo_operador_m": p["ojo"],
            "claro_operador_m": p["claro"],
            "regla_visibilidad": (
                "Una arista es volable desde la base si todo su perfil queda a ≤ R_op y la recta entre "
                "el ojo del operador y cada punto del perfil no corta la superficie del DEM. Una cámara "
                "se puede atender si queda a ≤ alcance y los 25 puntos de su bloque son visibles."
            ),
            "enlaces_por_base": ENLACES_POR_BASE,
            "n_bases": len(bases),
            "n_bases_camara": sum(1 for b in bases if b["tipo"] == "camara"),
            "n_bases_sendero": sum(1 for b in bases if b["tipo"] == "sendero"),
            "n_bases_camino_camaras": sum(1 for b in bases if b["tipo"] == "camino_camaras"),
            "camaras_con_base": len(servibles),
            "camaras_sin_base": sorted({c["id"] for c in camaras} - servibles),
        },
        "bases": bases,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False), encoding="utf-8")
    vis = [len(b["aristas_visibles"]) for b in bases]
    blo = [len(b["aristas_bloqueadas"]) for b in bases]
    print(f"Bases: {len(bases)} | cámaras con base visible: {len(servibles)}/{len(camaras)} | "
          f"aristas visibles por base: mediana {np.median(vis):.0f}, bloqueadas: mediana {np.median(blo):.0f}")
    print(f"Escrito: {ruta_repo(SALIDA)}")


if __name__ == "__main__":
    main()
