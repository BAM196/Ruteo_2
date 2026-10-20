```python
import os
import urllib.request
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent

# Carpeta data al mismo nivel que la carpeta del script
DATA_DIR = RAIZ / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CSV_DESCARGADO = DATA_DIR / "Pumalme_Especies_Descargado.csv"
CSV_SALIDA = DATA_DIR / "fauna_filtrada.csv"

URL_DATASET = (
    "https://simbio.mma.gob.cl/Especies/DownloadCSV?Type=Advanced&"
    "Advanced.FiltroVigencia=1&Advanced.KingdomId=7&"
    "Advanced.PhylumId=&Advanced.ClassId=&Advanced.OrderId=&"
    "Advanced.FamilyId=&Advanced.GenusId=&Advanced.RegionId=&"
    "Advanced.ProvinciaId=&Advanced.ComunaId=&"
    "Advanced.CategoriaConservacionId=&"
    "Advanced.OrigenesSeleccionados=1&"
    "Advanced.OrigenesSeleccionados=2&"
    "Advanced.OrigenesSeleccionados=3&"
    "Advanced.InvasorasSeleccionadas=1&"
    "Advanced.InvasorasSeleccionadas=2&"
    "Advanced.InvasorasSeleccionadas=3&"
    "Advanced.EndemicasSeleccionadas=1&"
    "Advanced.EndemicasSeleccionadas=2&"
    "Advanced.EndemicasSeleccionadas=3"
)

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


def descargar_fauna(url, destino):
    print("Descargando catálogo de especies desde SIMBIO...")

    try:
        solicitud = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
            destino.write_bytes(respuesta.read())

        print(f"Descarga guardada en: {destino}")
        return True

    except Exception as error:
        print(f"Error durante la descarga: {error}")
        return False


def limpiar_encabezados(df):
    # Quitar espacios, asteriscos y espacios invisibles de los encabezados
    df.columns = [
        str(columna)
        .replace("\ufeff", "")
        .replace("*", "")
        .strip()
        for columna in df.columns
    ]

    return df


if descargar_fauna(URL_DATASET, CSV_DESCARGADO):
    try:
        # Leer CSV separado por punto y coma
        animales_data = pd.read_csv(
            CSV_DESCARGADO,
            sep=";",
            encoding="utf-8-sig",
            dtype=str
        )

        animales_data = limpiar_encabezados(animales_data)

        # Encabezados esperados en el catálogo
        columna_cientifica = "Nombre Cinetífico"
        columna_comun = "Nombre Común"
        columna_estado = "Estado de Conservación vigente"

        # Comprobar que exista la columna científica
        if columna_cientifica not in animales_data.columns:
            raise ValueError(
                "No se encontró la columna 'Nombre Cinetífico'.\n"
                f"Columnas encontradas: {animales_data.columns.tolist()}"
            )

        # Limpiar espacios en los valores
        animales_data[columna_cientifica] = (
            animales_data[columna_cientifica]
            .fillna("")
            .str.strip()
        )

        # Filtrar las 10 especies solicitadas
        animales_data = animales_data[
            animales_data[columna_cientifica].isin(ESPECIES_OBJETIVO)
        ].copy()

        # Seleccionar las columnas existentes en el CSV
        columnas_deseadas = [
            "Reino",
            "Filo/División",
            "Clase",
            "Orden",
            "Familia",
            "Género",
            "Nombre Cinetífico",
            "Nombre Común",
            "Estado de Conservación vigente",
            "Origen respecto de Chile",
            "URL Ficha",
        ]

        columnas_finales = [
            columna
            for columna in columnas_deseadas
            if columna in animales_data.columns
        ]

        animales_data = animales_data[columnas_finales]

        # Guardar el resultado filtrado
        animales_data.to_csv(
            CSV_SALIDA,
            sep=";",
            index=False,
            encoding="utf-8-sig"
        )

        print("\n--- Especies encontradas ---")
        if animales_data.empty:
            print("No se encontraron especies de la lista en el catálogo.")
        else:
            print(animales_data.to_string(index=False))

        # Mostrar las especies que no aparecieron en el catálogo
        encontradas = set(
            animales_data[columna_cientifica].dropna().str.strip()
        )
        faltantes = set(ESPECIES_OBJETIVO) - encontradas

        if faltantes:
            print("\nEspecies no encontradas:")
            for especie in sorted(faltantes):
                print(f"- {especie}")

        print(f"\nTotal de especies encontradas: {len(encontradas)}")
        print(f"Total de registros guardados: {len(animales_data)}")
        print(f"Archivo de salida: {CSV_SALIDA}")

    except Exception as error:
        print(f"Error al procesar el archivo: {error}")
```