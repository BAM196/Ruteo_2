import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE_URL = "http://127.0.0.1:8000"
MOTOR_URL = "http://127.0.0.1:8001/docs"
FAUNA_CSV = ROOT / "data" / "Pumal237n Douglas Tompkins - Especies.csv"
FAUNA_JSON = ROOT / "Metadata" / "fauna.json"

EXTRACCION = (
    ("Generando nodos y aristas", [sys.executable, "Infraestructura/generar_nodos_v2.py"]),
    ("Extrayendo cobertura de suelo", [sys.executable, "Metadata/extraer_gee.py"]),
    ("Extrayendo focos de incendio (FIRMS)", [sys.executable, "Amenazas/extraer_firms.py"]),
    ("Extrayendo rutas de sendero", [sys.executable, "Metadata/extraer_senderos.py"]),
    ("Extrayendo catálogo de fauna", [sys.executable, "Metadata/extraer_fauna.py"], FAUNA_CSV),
    ("Extrayendo avistamientos de aves (eBird)", [sys.executable, "Amenazas/extraer_ebird.py"]),
    ("Extrayendo condiciones meteorológicas (Open-Meteo)", [sys.executable, "Amenazas/extraer_meteo.py"]),
)

LEVANTAR = (
    ("Levantando la base, el sitio y el motor", ["docker", "compose", "up", "-d", "--build"]),
)

CARGA = (
    ("Cargando infraestructura", [sys.executable, "Infraestructura/cargar_infraestructura.py"]),
    ("Cargando cobertura de suelo", [sys.executable, "Metadata/cargar_gee.py"]),
    ("Cargando focos de incendio (FIRMS)", [sys.executable, "Amenazas/cargar_firms.py"]),
    ("Cargando condiciones meteorológicas (Open-Meteo)", [sys.executable, "Amenazas/cargar_meteo.py"]),
    ("Cargando rutas de sendero", [sys.executable, "Metadata/cargar_senderos.py"]),
    ("Cargando catálogo de fauna", [sys.executable, "Metadata/cargar_fauna.py"], FAUNA_JSON),
    ("Cargando avistamientos de aves (eBird)", [sys.executable, "Amenazas/cargar_ebird.py"]),
)

MOTOR = (
    (
        "Calculando la probabilidad de falla por nodo y arista (punto 5)",
        ["docker", "compose", "run", "--rm", "motor", "python", "-m", "motor.probabilidades", "--cargar"],
    ),
)


def run_step(label, command, requiere=None):
    print(label)
    if requiere is not None and not requiere.exists():
        print(f"Se omite: falta {requiere.relative_to(ROOT)}.")
        return
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        print(f"Falló: {label}.")
        raise SystemExit(completed.returncode)


def esperar_base(intentos=30, pausa=2.0):
    print("Esperando a que la base acepte conexiones")
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
    for paso in EXTRACCION + LEVANTAR:
        run_step(*paso)
    esperar_base()
    for paso in CARGA + MOTOR:
        run_step(*paso)
    print(f"Listo. El mapa está en {SITE_URL} y la API del motor en {MOTOR_URL}.")


if __name__ == "__main__":
    main()
