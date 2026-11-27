import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import rasterio

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
SALIDA = AQUI / "metadata_cobertura.json"

CLASES = {
    10: ("Tree cover", "Cobertura arbórea"),
    20: ("Shrubland", "Matorral"),
    30: ("Grassland", "Pastizal"),
    40: ("Cropland", "Cultivo"),
    50: ("Built-up", "Zona construida"),
    60: ("Bare / sparse vegetation", "Suelo desnudo o vegetación escasa"),
    70: ("Snow and ice", "Nieve y hielo"),
    80: ("Permanent water bodies", "Cuerpo de agua permanente"),
    90: ("Herbaceous wetland", "Humedal herbáceo"),
    95: ("Mangroves", "Manglar"),
    100: ("Moss and lichen", "Musgo y liquen"),
}
COG_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "AWS_NO_SIGN_REQUEST": "YES",
    "GDAL_HTTP_TIMEOUT": "60",
}


def ruta_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(path)


def cargar_nodos() -> list[dict]:
    if not NODOS_PATH.exists():
        sys.exit(f"No existe {NODOS_PATH}. Primero corre Infraestructura/generar_nodos_v2.py.")
    data = json.loads(NODOS_PATH.read_text(encoding="utf-8"))
    return data["nodos"] if isinstance(data, dict) else data


def tile_worldcover(lat: float, lon: float) -> str:
    lat_ll = math.floor(lat / 3.0) * 3
    lon_ll = math.floor(lon / 3.0) * 3
    ns = "N" if lat_ll >= 0 else "S"
    ew = "E" if lon_ll >= 0 else "W"
    return f"{ns}{abs(int(lat_ll)):02d}{ew}{abs(int(lon_ll)):03d}"


def muestrear(nodos: list[dict]) -> tuple[dict[int, int], list[str]]:
    por_tile: dict[str, list[dict]] = {}
    for n in nodos:
        por_tile.setdefault(tile_worldcover(n["lat"], n["lon"]), []).append(n)
    salida = {}
    with rasterio.Env(**GDAL_ENV):
        for tile, grupo in por_tile.items():
            print(f"Leyendo tile {tile} ({len(grupo)} nodos)")
            with rasterio.open(COG_URL.format(tile=tile)) as src:
                for n, muestra in zip(grupo, src.sample([(n["lon"], n["lat"]) for n in grupo])):
                    if int(muestra[0]) != 0:
                        salida[int(n["id"])] = int(muestra[0])
    return salida, sorted(por_tile)


def main():
    nodos = cargar_nodos()
    clases, tiles = muestrear(nodos)
    registros = []
    for n in nodos:
        codigo = clases.get(int(n["id"]))
        nombre_en, nombre_es = CLASES.get(codigo, ("Sin dato", "Sin dato"))
        registros.append({
            "nodo_id": n["id"],
            "nombre": n.get("nombre"),
            "lat": n["lat"],
            "lon": n["lon"],
            "landcover_code": codigo,
            "landcover_clase": nombre_en,
            "landcover_clase_es": nombre_es,
            "nota_pixel": (
                "Píxel de agua permanente: en un parque de fiordos el píxel de 10 m "
                "puede caer en el canal aunque la cámara esté en la orilla."
                if codigo == 80 else None
            ),
        })
    conteo: dict[str, int] = {}
    for r in registros:
        conteo[r["landcover_clase_es"]] = conteo.get(r["landcover_clase_es"], 0) + 1
    print("Nodos por clase:", conteo)

    documento = {
        "meta": {
            "fuente": "ESA WorldCover 10 m 2021 v200",
            "acceso": "Bucket público esa-worldcover en AWS (COG), sin credenciales",
            "registro": "https://registry.opendata.aws/esa-worldcover-vito/",
            "tiles": [COG_URL.format(tile=t).rsplit("/", 1)[-1] for t in tiles],
            "banda": "Map",
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nodos_origen": ruta_repo(NODOS_PATH),
            "cita": (
                "Zanaga, D. et al. (2022). ESA WorldCover 10 m 2021 v200. "
                "https://doi.org/10.5281/zenodo.7254221"
            ),
            "clases": {str(k): {"en": v[0], "es": v[1]} for k, v in CLASES.items()},
            "nodos_por_clase": conteo,
            "uso": "Restricción «solo sobre bosque»: se excluyen los nodos con landcover_code distinto de 10.",
        },
        "registros": registros,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito: {ruta_repo(SALIDA)}")


if __name__ == "__main__":
    main()
