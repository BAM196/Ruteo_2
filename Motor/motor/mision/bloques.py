import numpy as np

from .. import grafo
from ..config import parametros_mision
from ..grafo import _TR

_INV = None


def _a_geo(x, y):
    global _INV
    if _INV is None:
        from pyproj import Transformer

        _INV = Transformer.from_crs(grafo.CRS_METRICO, "EPSG:4326", always_xy=True)
    return _INV.transform(x, y)


def puntos(lon: float, lat: float, m: dict | None = None) -> list:
    m = m or parametros_mision()
    x, y = _TR.transform(lon, lat)
    lado = m["puntos_por_lado"]
    off = (np.arange(lado) - (lado - 1) / 2) * m["separacion"]
    salida = []
    for fila, dy in enumerate(off):
        orden = off if fila % 2 == 0 else off[::-1]
        for dx in orden:
            lo, la = _a_geo(x + dx, y + dy)
            salida.append([round(lo, 6), round(la, 6), m["altura"]])
    return salida


def cuadrado(lon: float, lat: float, m: dict | None = None) -> list:
    m = m or parametros_mision()
    x, y = _TR.transform(lon, lat)
    h = m["lado_bloque"] / 2
    esquinas = [(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h), (x - h, y - h)]
    return [[round(c, 6) for c in _a_geo(a, b)] for a, b in esquinas]


def geojson_bloques(esc, camaras: list, m: dict | None = None) -> dict:
    m = m or parametros_mision()
    feats = []
    for c in camaras:
        n = esc.nodos[c]
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [cuadrado(n["lon"], n["lat"], m)]},
                      "properties": {"camara_id": c, "nombre": n.get("nombre"), "puntos": m["puntos_por_lado"] ** 2,
                                     "lado_m": m["lado_bloque"], "altura_m": m["altura"]}})
    return {"type": "FeatureCollection", "features": feats}
