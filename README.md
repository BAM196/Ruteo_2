# Algoritmos de Ruteo y Redes resilientes - Tarea 2

Parque Nacional Pumalín Douglas Tompkins. Cámaras de fotomonitoreo CONAF, cobertura de suelo y focos de incendio.

## Punto 0

- `Diagrama/schema.sql` crea la base desde cero.
- `Diagrama/schema_dbdiagram.sql` es el mismo esquema, simplificado, para importarlo en [dbdiagram.io](https://dbdiagram.io/) y exportar la imagen a esta carpeta.
- Las tablas de las otras metadata y amenazas se agregan a ese SQL.

## JSON y su explicación

El enunciado pide un archivo por cada JSON que diga qué significa cada campo.

- `Infraestructura/nodosv2.json` y `nodosv2_estructura.md`
- `Infraestructura/aristasv2.json` y `aristasv2_estructura.md`
- `Metadata/metadata_gee.json` y `metadata_gee_estructura.md`
- `Amenazas/amenaza_firms.json` y `amenaza_firms_estructura.md`

## Todo junto

```bash
python main.py
```

Genera nodos, cobertura y focos, levanta Docker, carga la base y deja el mapa en [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Sitio

El mapa muestra cámaras, tramos, cobertura y focos, y una ruta de `pgr_dijkstra` calculada solo con `costo_km`.

```bash
docker compose up -d
```

Queda en [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Carga

Con el contenedor arriba, con zip de data descomprimido y archivo occurrence.txt presente y `POSTGRES_PASSWORD` en `.env`:

```bash
python Infraestructura/cargar_infraestructura.py
python Metadata/cargar_gee.py
python Amenazas/cargar_firms.py
python Amenazas/cargar_meteo.py
Python Metadata/extraer_fauna.py
```
