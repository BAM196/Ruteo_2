import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
SALIDA = AQUI / "fauna.json"
ARCHIVO_FUENTE = RAIZ / "data" / "Pumal237n Douglas Tompkins - Especies.csv"

ESPECIES_OBJETIVO = [
    "Buteo ventralis",
    "Campephilus magellanicus",
    "Cephalorhynchus eutropia",
    "Cygnus melancoryphus",
    "Falco peregrinus",
    "Leopardus guigna",
    "Lontra provocax",
    "Lycalopex culpaeus",
    "Pudu puda",
    "Tursiops truncatus",
]

COLUMNAS = {
    "Reino": "reino",
    "Filo o División": "filo",
    "Clase": "clase",
    "Orden": "orden",
    "Familia": "familia",
    "Género": "genero",
    "Nombre Científico": "nombre_cientifico",
    "Nombre Común": "nombre_comun",
    "Estado de conservación": "estado_conservacion",
    "Origen respecto de Chile": "origen_chile",
    "Inventario Especies": "url_ficha",
}


def limpiar_encabezados(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [
        str(columna).replace("\ufeff", "").replace("*", "").strip()
        for columna in df.columns
    ]
    return df


def main():
    if not ARCHIVO_FUENTE.exists():
        raise SystemExit(f"No existe el archivo de fauna: {ARCHIVO_FUENTE}")

    try:
        animales = pd.read_csv(ARCHIVO_FUENTE, dtype=str, keep_default_na=False)
    except pd.errors.ParserError as error:
        raise SystemExit(
            f"No se pudo interpretar el archivo CSV de fauna: {error}"
        ) from error

    animales = limpiar_encabezados(animales)
    columna_cientifica = "Nombre Científico"
    if columna_cientifica not in animales.columns:
        raise SystemExit(
            f"No se encontró la columna '{columna_cientifica}'. "
            f"Columnas encontradas: {animales.columns.tolist()}"
        )

    animales[columna_cientifica] = (
        animales[columna_cientifica].fillna("").str.strip()
    )
    animales = animales[
        animales["Reino"].str.strip().eq("Animalia")
        & animales[columna_cientifica].isin(ESPECIES_OBJETIVO)
    ].copy()

    animales = animales.reindex(columns=COLUMNAS.keys(), fill_value="").fillna("")
    registros = [
        {
            COLUMNAS[columna]: str(valor).strip()
            for columna, valor in registro.items()
        }
        for registro in animales.to_dict(orient="records")
    ]
    encontradas = {r["nombre_cientifico"] for r in registros}
    faltantes = sorted(set(ESPECIES_OBJETIVO) - encontradas)
    documento = {
        "meta": {
            "fuente": "Inventario de especies del Parque Nacional Pumalín Douglas Tompkins",
            "archivo_fuente": ARCHIVO_FUENTE.relative_to(RAIZ).as_posix(),
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "criterio": (
                "Especies del reino Animalia seleccionadas para el proyecto "
                "y presentes en el inventario local."
            ),
            "especies_objetivo": ESPECIES_OBJETIVO,
            "especies_no_encontradas": faltantes,
            "n_especies_encontradas": len(encontradas),
            "n_registros": len(registros),
        },
        "especies": registros,
    }
    SALIDA.write_text(
        json.dumps(documento, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Especies encontradas: {len(encontradas)} de {len(ESPECIES_OBJETIVO)}")
    if faltantes:
        print("Especies no encontradas:")
        for especie in faltantes:
            print(f"- {especie}")
    print(f"Registros guardados: {len(registros)}")
    print(f"Archivo de salida: {SALIDA}")


if __name__ == "__main__":
    main()
