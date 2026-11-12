import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pyproj import Transformer

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
ARISTAS_PATH = Path(os.getenv("ARISTAS_PATH", RAIZ / "Infraestructura" / "aristasv2.json"))
KML_PATH = Path(os.getenv("SENDEROS_KML_PATH", AQUI / "senderos.kml"))
SALIDA = AQUI / "metadata_senderos.json"

UMBRAL_PRIVACIDAD_M = float(os.getenv("UMBRAL_SENDERO_M", "50"))
CRS_METRICO = "EPSG:32718"


def ruta_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(path)


def leer_json(path: Path, clave: str) -> list[dict]:
    if not path.exists():
        sys.exit(f"No existe {path}.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data[clave] if isinstance(data, dict) else data


def proyectar(tr: Transformer, lon: float, lat: float) -> np.ndarray:
    x, y = tr.transform(lon, lat)
    return np.array([x, y], dtype=float)


def distancia_punto_a_segmento(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    den = float(np.dot(ab, ab))
    if den == 0:
        return float(np.linalg.norm(p - a))
    t = float(np.clip(np.dot(p - a, ab) / den, 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def segmentos_se_tocan(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> bool:
    def orientacion(p, q, r):
        pq = q - p
        pr = r - p
        return float(pq[0] * pr[1] - pq[1] * pr[0])

    def sobre_segmento(p, q, r, tolerancia_orientacion):
        return (
            abs(orientacion(p, r, q)) <= tolerancia_orientacion
            and min(p[0], r[0]) - tolerancia_m <= q[0] <= max(p[0], r[0]) + tolerancia_m
            and min(p[1], r[1]) - tolerancia_m <= q[1] <= max(p[1], r[1]) + tolerancia_m
        )

    tolerancia_m = 1e-6
    tol_ab = tolerancia_m * max(float(np.linalg.norm(b - a)), 1.0)
    tol_cd = tolerancia_m * max(float(np.linalg.norm(d - c)), 1.0)
    o1, o2 = orientacion(a, b, c), orientacion(a, b, d)
    o3, o4 = orientacion(c, d, a), orientacion(c, d, b)

    if ((o1 > tol_ab and o2 < -tol_ab) or (o1 < -tol_ab and o2 > tol_ab)) and (
        (o3 > tol_cd and o4 < -tol_cd) or (o3 < -tol_cd and o4 > tol_cd)
    ):
        return True

    return (
        sobre_segmento(a, c, b, tol_ab)
        or sobre_segmento(a, d, b, tol_ab)
        or sobre_segmento(c, a, d, tol_cd)
        or sobre_segmento(c, b, d, tol_cd)
    )


def distancia_segmento_a_segmento(
    a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray
) -> float:
    if segmentos_se_tocan(a, b, c, d):
        return 0.0
    return min(
        distancia_punto_a_segmento(a, c, d),
        distancia_punto_a_segmento(b, c, d),
        distancia_punto_a_segmento(c, a, b),
        distancia_punto_a_segmento(d, a, b),
    )


def distancia_entre_lineas(linea_a: list[np.ndarray], linea_b: list[np.ndarray]) -> float:
    return min(
        distancia_segmento_a_segmento(linea_a[i], linea_a[i + 1], linea_b[j], linea_b[j + 1])
        for i in range(len(linea_a) - 1)
        for j in range(len(linea_b) - 1)
    )


def parsear_coordenadas(texto: str) -> list[tuple[float, float, float]]:
    puntos = []
    for item in texto.strip().split():
        partes = item.split(",")
        if len(partes) >= 2:
            lon = float(partes[0])
            lat = float(partes[1])
            alt = float(partes[2]) if len(partes) > 2 else 0.0
            puntos.append((lon, lat, alt))
    return puntos


def parsear_kml(kml_path: Path) -> list[dict]:
    if not kml_path.exists():
        sys.exit(f"No existe el archivo KML en: {kml_path}")
    tree = ET.parse(kml_path)
    root = tree.getroot()

    # Namespace KML dinámico
    ns = {"kml": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
    prefix = "kml:" if ns else ""

    elementos = []
    idx = 1
    for pm in root.findall(f".//{prefix}Placemark", ns):
        nombre = pm.findtext(f"{prefix}name", default=f"Sendero_{idx}", namespaces=ns).strip()
        desc = pm.findtext(f"{prefix}description", default="", namespaces=ns).strip()

        point_elem = pm.find(f".//{prefix}Point/{prefix}coordinates", ns)
        line_elem = pm.find(f".//{prefix}LineString/{prefix}coordinates", ns)

        if point_elem is not None and point_elem.text:
            coords = parsear_coordenadas(point_elem.text)
            if coords:
                elementos.append({
                    "id": idx,
                    "nombre": nombre,
                    "tipo": "punto_interes",
                    "descripcion": desc,
                    "coordenadas": coords[0],
                })
                idx += 1

        elif line_elem is not None and line_elem.text:
            coords = parsear_coordenadas(line_elem.text)
            if coords:
                elementos.append({
                    "id": idx,
                    "nombre": nombre,
                    "tipo": "trazado",
                    "descripcion": desc,
                    "coordenadas": coords,
                })
                idx += 1

    return elementos


def cruzar_senderos(senderos: list[dict], nodos: list[dict], aristas: list[dict]):
    tr = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    xy_nodos = {n["id"]: proyectar(tr, n["lon"], n["lat"]) for n in nodos}

    for s in senderos:
        if s["tipo"] == "trazado":
            pts_proy = [proyectar(tr, c[0], c[1]) for c in s["coordenadas"]]
            # Longitud del sendero
            long_m = sum(float(np.linalg.norm(pts_proy[i+1] - pts_proy[i])) for i in range(len(pts_proy)-1))
            s["longitud_km"] = round(long_m / 1000.0, 3)

            # Distancia a cada nodo (mínima contra todos los segmentos del sendero)
            nodos_cerca = []
            for nid, p_nodo in xy_nodos.items():
                d_min = min(
                    distancia_punto_a_segmento(p_nodo, pts_proy[i], pts_proy[i+1])
                    for i in range(len(pts_proy)-1)
                )
                if d_min <= 500.0:  # Registrar cercanías hasta 500m
                    nodos_cerca.append({"id": nid, "distancia_m": round(d_min, 1)})
            s["nodos_cercanos"] = sorted(nodos_cerca, key=lambda x: x["distancia_m"])

            # Usa la geometría completa de cada arista, no solo su punto medio.
            aristas_cerca = []
            for ar in aristas:
                coords_ar = ar.get("coordenadas") or [
                    [nodos[ar["source"]]["lon"], nodos[ar["source"]]["lat"]],
                    [nodos[ar["target"]]["lon"], nodos[ar["target"]]["lat"]],
                ]
                pts_ar = [proyectar(tr, c[0], c[1]) for c in coords_ar]
                d_ar = distancia_entre_lineas(pts_ar, pts_proy)
                if d_ar <= 500.0:
                    aristas_cerca.append({
                        "id": ar["id"],
                        "distancia_m": round(d_ar, 1),
                        "buffer_privacidad": bool(d_ar <= UMBRAL_PRIVACIDAD_M)
                    })
            s["aristas_cercanas"] = aristas_cerca
        else:
            s["longitud_km"] = 0.0
            p_pt = proyectar(tr, s["coordenadas"][0], s["coordenadas"][1])
            s["nodos_cercanos"] = [
                {"id": nid, "distancia_m": round(float(np.linalg.norm(p_pt - p_nodo)), 1)}
                for nid, p_nodo in xy_nodos.items()
                if float(np.linalg.norm(p_pt - p_nodo)) <= 500.0
            ]
            s["aristas_cercanas"] = []


def main():
    nodos = leer_json(NODOS_PATH, "nodos")
    aristas = leer_json(ARISTAS_PATH, "aristas")
    senderos = parsear_kml(KML_PATH)
    cruzar_senderos(senderos, nodos, aristas)

    documento = {
        "meta": {
            "fuente": "Senderos Oficiales Parque Pumalín (KML Google My Maps)",
            "archivo_kml": ruta_repo(KML_PATH),
            "nodos_origen": ruta_repo(NODOS_PATH),
            "aristas_origen": ruta_repo(ARISTAS_PATH),
            "crs_metrico": CRS_METRICO,
            "umbral_privacidad_m": UMBRAL_PRIVACIDAD_M,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_elementos": len(senderos),
            "regla_privacidad": (
                f"Si un tramo de vuelo está a <= {UMBRAL_PRIVACIDAD_M:.0f} m del sendero, "
                "se marca buffer_privacidad = true para restringir la captura en horas de uso público. "
                "La distancia se mide entre las geometrías completas del tramo y del sendero."
            )
        },
        "senderos": senderos
    }

    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito: {SALIDA} ({len(senderos)} elementos procesados)")


if __name__ == "__main__":
    main()