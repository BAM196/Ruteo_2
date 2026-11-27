import math
from pathlib import Path

import numpy as np
import yaml
from pyproj import Transformer

RAIZ = Path(__file__).resolve().parent.parent
MISION_YAML = RAIZ / "Motor" / "config" / "mision.yaml"
CRS_METRICO = "EPSG:32718"
A_METRICO = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
A_GEO = Transformer.from_crs(CRS_METRICO, "EPSG:4326", always_xy=True)


def valor(x):
    return x["valor"] if isinstance(x, dict) and "valor" in x else x


def parametros() -> dict:
    cfg = yaml.safe_load(MISION_YAML.read_text(encoding="utf-8"))
    op, dron, mu = cfg["operacion"], cfg["dron"], cfg["muestreo"]
    lado = (valor(mu["puntos_por_lado"]) - 1) * valor(mu["separacion_m"])
    p = {
        "r_op": float(valor(op["radio_operacion_m"])),
        "altura": float(valor(op["altura_vuelo_m"])),
        "techo": float(valor(op["techo_m"])),
        "ojo": float(valor(op["ojo_operador_m"])),
        "claro": float(valor(op["claro_operador_m"])),
        "paso": float(valor(op["paso_perfil_m"])),
        "c_min": float(valor(op["error_dem_m"]) + valor(dron["error_vertical_m"]) + valor(op["margen_arboles_m"])),
        "lado_bloque": float(lado),
        "puntos_por_lado": int(valor(mu["puntos_por_lado"])),
        "separacion": float(valor(mu["separacion_m"])),
    }
    p["r_b"] = lado / 2 * math.sqrt(2)
    p["alcance"] = p["r_op"] - p["r_b"]
    return p


class DEM:
    def __init__(self, path: Path, paso: float = 30.0):
        import rasterio

        with rasterio.open(path) as src:
            geo = src.read(1).astype("float32")
            t = src.transform
            oeste, sur, este, norte = src.bounds
        geo[np.isnan(geo)] = 0.0
        esquinas_x, esquinas_y = A_METRICO.transform([oeste, este, oeste, este], [sur, sur, norte, norte])
        self.x0, self.y0 = min(esquinas_x), max(esquinas_y)
        self.dx, self.dy = paso, -paso
        ancho = int((max(esquinas_x) - self.x0) / paso) + 1
        alto = int((self.y0 - min(esquinas_y)) / paso) + 1
        gx = self.x0 + (np.arange(ancho) + 0.5) * paso
        gy = self.y0 - (np.arange(alto) + 0.5) * paso
        mx, my = np.meshgrid(gx, gy)
        lon, lat = A_GEO.transform(mx.ravel(), my.ravel())
        col = ((np.asarray(lon) - t.c) / t.a).astype(int)
        fila = ((np.asarray(lat) - t.f) / t.e).astype(int)
        dentro = (col >= 0) & (col < geo.shape[1]) & (fila >= 0) & (fila < geo.shape[0])
        z = np.zeros(mx.size, dtype="float32")
        z[dentro] = geo[fila[dentro], col[dentro]]
        self.z = z.reshape(mx.shape)

    def altura(self, x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        col = np.clip(((x - self.x0) / self.dx).astype(int), 0, self.z.shape[1] - 1)
        fila = np.clip(((y - self.y0) / self.dy).astype(int), 0, self.z.shape[0] - 1)
        return self.z[fila, col]


def a_metrico(lon, lat):
    x, y = A_METRICO.transform(lon, lat)
    return np.asarray(x, dtype=float), np.asarray(y, dtype=float)


def a_geo(x, y):
    lon, lat = A_GEO.transform(x, y)
    return np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)


def muestrear_linea(coords_xy: np.ndarray, paso: float):
    xs, ys, ss = [coords_xy[0, 0]], [coords_xy[0, 1]], [0.0]
    acum = 0.0
    for (xa, ya), (xb, yb) in zip(coords_xy[:-1], coords_xy[1:]):
        largo = math.hypot(xb - xa, yb - ya)
        n = max(1, int(math.ceil(largo / paso)))
        for k in range(1, n + 1):
            t = k / n
            xs.append(xa + t * (xb - xa))
            ys.append(ya + t * (yb - ya))
            ss.append(acum + t * largo)
        acum += largo
    return np.array(xs), np.array(ys), np.array(ss)


def perfil(dem: DEM, coords_xy: np.ndarray, p: dict) -> dict:
    xs, ys, ss = muestrear_linea(coords_xy, p["paso"])
    sup = dem.altura(xs, ys)
    m = len(xs) - 1
    alt = sup + p["altura"]
    banda = p["techo"] - p["c_min"]
    escalon = np.abs(np.diff(sup))
    if len(escalon) and escalon.max() > banda:
        k = int(np.argmax(escalon))
        return {"bloqueada": True,
                "motivo": (f"desnivel de {escalon[k]:.0f} m en {ss[k + 1] - ss[k]:.0f} m: "
                           f"exige pasar los {p['techo']:.0f} m sobre la superficie"),
                "largo_2d_m": float(ss[-1])}

    puntos = [0]
    i = 0
    while i < m:
        j_ok = i + 1
        for j in range(m, i + 1, -1):
            k = np.arange(i + 1, j)
            linea = alt[i] + (alt[j] - alt[i]) * (ss[k] - ss[i]) / (ss[j] - ss[i])
            despeje = linea - sup[k]
            if despeje.min() >= p["c_min"] and despeje.max() <= p["techo"]:
                j_ok = j
                break
        puntos.append(j_ok)
        i = j_ok

    idx = np.array(puntos)
    alt_p = alt[idx]
    linea_total = np.interp(ss, ss[idx], alt_p)
    despeje = linea_total - sup
    dz = np.diff(alt_p)
    ds = np.diff(ss[idx])
    lon, lat = a_geo(xs[idx], ys[idx])
    return {
        "bloqueada": False,
        "motivo": None,
        "largo_2d_m": float(ss[-1]),
        "largo_3d_m": float(np.sum(np.hypot(ds, dz))),
        "ascenso_ida_m": float(np.sum(np.clip(dz, 0, None))),
        "ascenso_vuelta_m": float(np.sum(np.clip(-dz, 0, None))),
        "despeje_min_m": float(despeje.min()),
        "altura_max_sobre_superficie_m": float(despeje.max()),
        "superficie_min_m": float(sup.min()),
        "superficie_max_m": float(sup.max()),
        "densificada": len(idx) > 2,
        "n_puntos": int(len(idx)),
        "puntos": [[round(float(a), 6), round(float(b), 6), round(float(c), 1)]
                   for a, b, c in zip(lon, lat, alt_p)],
        "muestras_xy": (xs, ys, linea_total),
    }


def linea_de_vista(dem: DEM, ojo_xyz, objetivos_xyz: np.ndarray, p: dict) -> np.ndarray:
    ox, oy, oz = ojo_xyz
    tx, ty, tz = objetivos_xyz[:, 0], objetivos_xyz[:, 1], objetivos_xyz[:, 2]
    dist = np.hypot(tx - ox, ty - oy)
    n = int(np.ceil(dist.max() / p["paso"])) if len(dist) else 0
    if n <= 1:
        return np.ones(len(tx), dtype=bool)
    t = (np.arange(1, n) / n)[None, :]
    px = ox + (tx[:, None] - ox) * t
    py = oy + (ty[:, None] - oy) * t
    pz = oz + (tz[:, None] - oz) * t
    d = dist[:, None] * t
    sup = dem.altura(px, py)
    revisar = (d > p["claro"]) & (d < dist[:, None] - p["paso"] / 2)
    corta = revisar & (sup > pz)
    return ~corta.any(axis=1)


def bloque(dem: DEM, x, y, p: dict) -> np.ndarray:
    lado = p["puntos_por_lado"]
    off = (np.arange(lado) - (lado - 1) / 2) * p["separacion"]
    filas = []
    for fila, dy in enumerate(off):
        orden = off if fila % 2 == 0 else off[::-1]
        for dx in orden:
            filas.append((x + dx, y + dy))
    pts = np.array(filas)
    z = dem.altura(pts[:, 0], pts[:, 1]) + p["altura"]
    return np.column_stack([pts, z])
