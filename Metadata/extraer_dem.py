import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.windows import from_bounds

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
DEM_PATH = Path(os.getenv("DEM_PATH", RAIZ / "data" / "dem_pumalin.tif"))
SALIDA = AQUI / "metadata_dem.json"
MARGEN_GRADOS = float(os.getenv("DEM_MARGEN_GRADOS", "0.05"))

URL = (
    "https://copernicus-dem-30m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
    "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif"
)
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "AWS_NO_SIGN_REQUEST": "YES",
    "GDAL_HTTP_TIMEOUT": "120",
}


def ruta_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(path)


def leer_nodos() -> list[dict]:
    if not NODOS_PATH.exists():
        sys.exit(f"No existe {NODOS_PATH}. Primero corre Infraestructura/generar_nodos_v2.py.")
    data = json.loads(NODOS_PATH.read_text(encoding="utf-8"))
    return data["nodos"] if isinstance(data, dict) else data


def url_tile(lat_sw: int, lon_sw: int) -> str:
    return URL.format(ns="N" if lat_sw >= 0 else "S", lat=abs(lat_sw),
                      ew="E" if lon_sw >= 0 else "W", lon=abs(lon_sw))


def tiles(oeste, sur, este, norte) -> list[str]:
    return [url_tile(la, lo)
            for la in range(math.floor(sur), math.floor(norte) + 1)
            for lo in range(math.floor(oeste), math.floor(este) + 1)]


def recortar(urls, bounds):
    partes = []
    with rasterio.Env(**GDAL_ENV):
        for url in urls:
            print(f"Leyendo {url.rsplit('/', 1)[-1]}")
            with rasterio.open(url) as src:
                ventana = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
                ventana = ventana.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                datos = src.read(1, window=ventana)
                perfil = src.profile.copy()
                perfil.update(height=datos.shape[0], width=datos.shape[1],
                              transform=src.window_transform(ventana), driver="GTiff")
                mem = rasterio.io.MemoryFile()
                with mem.open(**perfil) as dst:
                    dst.write(datos, 1)
                partes.append(mem)
        abiertos = [m.open() for m in partes]
        mosaico, transform = merge(abiertos, bounds=bounds)
        crs = abiertos[0].crs
        for a in abiertos:
            a.close()
    return mosaico[0].astype("float32"), transform, crs


def main():
    nodos = leer_nodos()
    lons = [n["lon"] for n in nodos]
    lats = [n["lat"] for n in nodos]
    bounds = (min(lons) - MARGEN_GRADOS, min(lats) - MARGEN_GRADOS,
              max(lons) + MARGEN_GRADOS, max(lats) + MARGEN_GRADOS)
    urls = tiles(*bounds)
    dem, transform, crs = recortar(urls, bounds)
    dem[dem < -100] = np.nan

    DEM_PATH.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(DEM_PATH, "w", driver="GTiff", height=dem.shape[0], width=dem.shape[1],
                       count=1, dtype="float32", crs=crs, transform=transform,
                       compress="deflate", predictor=3, nodata=np.nan, tiled=True) as dst:
        dst.write(dem, 1)
    print(f"DEM recortado: {dem.shape[1]} × {dem.shape[0]} píxeles → {ruta_repo(DEM_PATH)}")

    with rasterio.open(DEM_PATH) as src:
        valores = [float(v[0]) for v in src.sample([(n["lon"], n["lat"]) for n in nodos])]
    registros = [{"nodo_id": n["id"], "nombre": n.get("nombre"), "lon": n["lon"], "lat": n["lat"],
                  "elevacion_m": None if math.isnan(v) else round(v, 1)}
                 for n, v in zip(nodos, valores)]
    sin_dato = sum(1 for r in registros if r["elevacion_m"] is None)
    elev = [r["elevacion_m"] for r in registros if r["elevacion_m"] is not None]

    documento = {
        "meta": {
            "fuente": "Copernicus DEM GLO-30 (modelo digital de superficie, 30 m)",
            "acceso": "Bucket público copernicus-dem-30m en AWS, sin credenciales",
            "registro": "https://registry.opendata.aws/copernicus-dem/",
            "tiles": [u.rsplit("/", 1)[-1] for u in urls],
            "archivo_raster": ruta_repo(DEM_PATH),
            "bbox": {"oeste": bounds[0], "sur": bounds[1], "este": bounds[2], "norte": bounds[3]},
            "tipo_modelo": "Superficie (DSM): incluye el dosel del bosque, que es lo que el dron debe librar",
            "error_vertical": "< 4 m (90 % linear error, absoluto)",
            "unidad": "m sobre el nivel del mar (EGM2008)",
            "cita": (
                "European Space Agency (2024). Copernicus Global Digital Elevation Model. "
                "https://doi.org/10.5270/ESA-c5d3d65"
            ),
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nodos_origen": ruta_repo(NODOS_PATH),
            "n_nodos": len(registros),
            "n_sin_dato": sin_dato,
            "elevacion_min_m": min(elev) if elev else None,
            "elevacion_max_m": max(elev) if elev else None,
        },
        "nodos": registros,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Elevación de {len(registros)} nodos ({sin_dato} sin dato). Escrito: {ruta_repo(SALIDA)}")


if __name__ == "__main__":
    main()
