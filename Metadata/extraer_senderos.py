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

            # Distancia a aristas
            aristas_cerca = []
            for ar in aristas:
                p_a = xy_nodos[ar["source"]]
                p_b = xy_nodos[ar["target"]]
                mid = (p_a + p_b) / 2.0
                d_ar = min(
                    distancia_punto_a_segmento(mid, pts_proy[i], pts_proy[i+1])
                    for i in range(len(pts_proy)-1)
                )
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
                "se marca buffer_privacidad = true para restringir la captura en horas de uso público."
            )
        },
        "senderos": senderos
    }

    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito: {SALIDA} ({len(senderos)} elementos procesados)")


if __name__ == "__main__":
    main()