import argparse
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE_URL = "http://127.0.0.1:8000"
MOTOR_URL = "http://127.0.0.1:8001/docs"
OCCURRENCE = ROOT / "data" / "occurrence.txt"
OCCURRENCE_ZIP = ROOT / "data" / "occurrence.zip"
FAUNA_CSV = ROOT / "data" / "Pumal237n Douglas Tompkins - Especies.csv"
FAUNA_JSON = ROOT / "Metadata" / "fauna.json"
PY = sys.executable

RED = (
    ("Generando cámaras, waypoints y tramos", [PY, "Infraestructura/generar_nodos_v2.py"]),
)

EXTRACCION = (
    ("Descargando el modelo de elevación (Copernicus GLO-30, AWS)", [PY, "Metadata/extraer_dem.py"]),
    ("Descargando la cobertura de suelo (ESA WorldCover, AWS)", [PY, "Metadata/extraer_worldcover.py"]),
    ("Extrayendo los senderos oficiales", [PY, "Metadata/extraer_senderos.py"]),
    ("Calculando el perfil de cada tramo sobre el terreno", [PY, "Infraestructura/perfiles_aristas.py"]),
    ("Generando las bases del operador y su línea de vista", [PY, "Infraestructura/generar_bases.py"]),
    ("Cruzando las especies con su categoría de conservación (RCE)", [PY, "Metadata/especies_rce.py"]),
    ("Extrayendo el catálogo de fauna del parque", [PY, "Metadata/extraer_fauna.py"], FAUNA_CSV),
    ("Extrayendo focos de incendio (NASA FIRMS)", [PY, "Amenazas/extraer_firms.py"]),
    ("Extrayendo el pronóstico de la mañana (Open-Meteo)", [PY, "Amenazas/extraer_meteo.py"]),
    ("Extrayendo avistamientos de aves (eBird)", [PY, "Amenazas/extraer_ebird.py"]),
    ("Calculando el desplazamiento de las aves (r_mov)", [PY, "Amenazas/calcular_r_mov.py"]),
)

LEVANTAR = (
    ("Levantando la base de datos, el sitio y el motor", ["docker", "compose", "up", "-d", "--build"]),
)

CARGA = (
    ("Cargando la red", [PY, "Infraestructura/cargar_infraestructura.py"]),
    ("Cargando la cobertura y la elevación", [PY, "Metadata/cargar_worldcover.py"]),
    ("Cargando los senderos", [PY, "Metadata/cargar_senderos.py"]),
    ("Cargando perfiles, bases y línea de vista", [PY, "Infraestructura/cargar_terreno.py"]),
    ("Cargando las especies y su categoría", [PY, "Metadata/cargar_especies_rce.py"]),
    ("Cargando el catálogo de fauna", [PY, "Metadata/cargar_fauna.py"], FAUNA_JSON),
    ("Cargando los focos de incendio", [PY, "Amenazas/cargar_firms.py"]),
    ("Cargando el clima", [PY, "Amenazas/cargar_meteo.py"]),
    ("Cargando las aves", [PY, "Amenazas/cargar_ebird.py"]),
)

MOTOR = (
    ("Armando los sectores, su base y su prioridad",
     ["docker", "compose", "run", "--rm", "motor", "python", "-m", "motor.mision.sectores", "--cargar"]),
    ("Calculando la probabilidad de falla por nodo y tramo",
     ["docker", "compose", "run", "--rm", "motor", "python", "-m", "motor.probabilidades", "--cargar"]),
)

OPCIONALES = (
    ("Midiendo los traslados entre bases (OSRM)", [PY, "Infraestructura/traslados_bases.py"]),
)


def run_step(label, command, requiere=None, opcional=False):
    print(f"\n» {label}")
    if requiere is not None and not requiere.exists():
        print(f"  Se omite: falta {requiere.relative_to(ROOT)}.")
        return True
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        if opcional:
            print(f"  No se pudo completar ({label}); se sigue con los datos que ya están en el repositorio.")
            return False
        print(f"  Falló: {label}.")
        raise SystemExit(completed.returncode)
    return True


def preparar_datos():
    if not OCCURRENCE.exists() and OCCURRENCE_ZIP.exists():
        print("» Descomprimiendo data/occurrence.zip")
        with zipfile.ZipFile(OCCURRENCE_ZIP) as z:
            z.extract("occurrence.txt", ROOT / "data")
    if not (ROOT / ".env").exists() and (ROOT / ".env.example").exists():
        print("Falta el archivo .env. Cópialo desde .env.example y completa las claves.")
        raise SystemExit(1)


def esperar_base(intentos=30, pausa=2.0):
    print("\n» Esperando a que la base acepte conexiones")
    try:
        import psycopg2
        from dotenv import load_dotenv
    except ImportError:
        time.sleep(10)
        return
    load_dotenv(ROOT / ".env")
    for _ in range(intentos):
        try:
            psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", "5433"),
                dbname=os.getenv("POSTGRES_DB", "gisdb"),
                user=os.getenv("POSTGRES_USER", "gisuser"),
                password=os.getenv("POSTGRES_PASSWORD"),
                connect_timeout=3,
            ).close()
            return
        except psycopg2.OperationalError:
            time.sleep(pausa)
    print("La base no respondió a tiempo.")
    raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description="Prepara los datos, levanta Docker y carga todo el sistema.")
    ap.add_argument("--sin-red", action="store_true", help="usar los nodos y tramos que ya están en el repositorio")
    ap.add_argument("--sin-extraccion", action="store_true",
                    help="no volver a descargar datos; solo levantar y cargar lo que ya está en el repositorio")
    args = ap.parse_args()

    preparar_datos()
    pasos = []
    if not args.sin_extraccion:
        pasos += ([] if args.sin_red else list(RED)) + list(EXTRACCION)
    for paso in pasos:
        run_step(*paso, opcional=paso[1][-1].startswith("Amenazas/"))
    for paso in LEVANTAR:
        run_step(*paso)
    esperar_base()
    for paso in CARGA + MOTOR:
        run_step(*paso)
    if not args.sin_extraccion:
        for paso in OPCIONALES:
            run_step(*paso, opcional=True)
    print(f"\nListo. El sitio está en {SITE_URL} y la API del motor en {MOTOR_URL}.")


if __name__ == "__main__":
    main()
