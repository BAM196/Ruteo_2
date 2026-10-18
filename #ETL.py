#ETL 
import pandas as pd
import numpy as np
import requests
import geopandas as gpd
from shapely.geometry import LineString, Point

from shapely.geometry import Point, LineString
from scipy.spatial import KDTree
import numpy as np


# Descargar el archivo de ocurrencias desde GBIF (Global Biodiversity Information Facility)

#link de descarga del archivo de ocurrencias (zip)
# https://gbif-chile.mma.gob.cl/ipt/archive.do?r=fotomonitoreo_conaf_2021&v=1.9

#response = requests.get('https://api.gbif.org/v1/occurrence/download/request/0000000-0000000-000-0000000-0000000')


df = pd.read_csv('occurrence.txt', sep='\t', low_memory=False)
#locality: parque nacional pumalín Douglas Tompkins

# Seleccionar las columnas clave: ID, localidad, latitud y longitud
columnas_interes = ['occurrenceID', 'decimalLatitude', 'decimalLongitude', 'locality']
df_filtrado = df[columnas_interes].copy()

nombre_localidad = "Parque Nacional Pumalín Douglas Tompkins"
df_filtrado = df_filtrado[df_filtrado['locality'] == nombre_localidad]

# Eliminar filas que no tengan coordenadas válidas
df_filtrado = df_filtrado.dropna(subset=['decimalLatitude', 'decimalLongitude'])

# Eliminar cámaras duplicadas
df_camaras = df_filtrado.drop_duplicates(subset=['decimalLatitude', 'decimalLongitude'])

# Guardar el resultado en un nuevo CSV limpio
df_camaras.to_csv('coordenadas_camaras.csv', index=False, encoding='utf-8')

print(f"¡Listo! Se extrajeron {len(df_camaras)} ubicaciones únicas con coordenadas.")
# ----------------------------------------------------------------------------------------------------------

lat_min, lat_max = -42.8136, -42.5464  
lon_min, lon_max = -72.6554, -72.5657

#df_centro = df[
#    (df['decimalLatitude'] >= lat_min) & 
#    (df['decimalLatitude'] <= lat_max) & 
#    (df['decimalLongitude'] >= lon_min) & 
#    (df['decimalLongitude'] <= lon_max)
#].copy()
df_centro = df[
    df['decimalLatitude'].between(lat_min, lat_max)
    & df['decimalLongitude'].between(lon_min, lon_max)
].copy()
print(f"Puntos filtrados en el centro: {len(df_centro)}")

# Eliminar puntos con coordenadas idénticas
df_centro = df_centro.drop_duplicates(
    subset=["decimalLongitude", "decimalLatitude"]
).reset_index(drop=True)
print("Puntos únicos:", len(df_centro))

#-----------------------------------------------------------------------------------------------------------
# Proyectar a un sistema métrico (ej. UTM Zona 19S para Chile) para medir distancias reales en metros ¿¿¿

gdf_puntos = gpd.GeoDataFrame(
    df_centro,
    geometry=gpd.points_from_xy(
        df_centro["decimalLongitude"],
        df_centro["decimalLatitude"]
    ),
    crs="EPSG:4326"
).to_crs("EPSG:32718")

coords = np.column_stack([
    gdf_puntos.geometry.x,
    gdf_puntos.geometry.y
])

# Extraer coordenadas 
coords = np.array([(p.x, p.y) for p in gdf_puntos.geometry])
tree = KDTree(coords)

# Si K_VECINOS = 2, cada cámara se conectará con sus 2 vecinos más cercanos, creando múltiples rutas ramificadas.
K_VECINOS = 2 
tree = KDTree(coords)

k = min(K_VECINOS + 1, len(coords))
distancias, indices = tree.query(coords, k=k)


# Solo en k = 1
#if k == 1:
#    distancias = distancias[:, np.newaxis]
#    indices = indices[:, np.newaxis]

pares = set()

for i in range(len(coords)):
    for j in range(1, k):
        idx = int(indices[i, j])
        distancia = float(distancias[i, j])

        # Evitar el mismo punto y las distancias cero
        if idx == i or distancia <= 0:
            continue

        # Evitar conexiones duplicadas
        par = tuple(sorted((i, idx)))
        pares.add(par)

registros = []

for origen, destino in sorted(pares):
    linea = LineString([
        coords[origen],
        coords[destino]
    ])

    registros.append({
        "source": origen,
        "target": destino,
        "distance_m": linea.length,
        "geometry": linea
    })

gdf_rutas = gpd.GeoDataFrame(
    registros,
    geometry="geometry",
    crs="EPSG:32718"
)



# Validar y exportar a GeoJSON
# --------------------------------------------------
if not gdf_rutas.empty:
    gdf_rutas = gdf_rutas[
        (gdf_rutas["distance_m"] > 0)
        & gdf_rutas.geometry.is_valid
    ].copy()

    gdf_rutas = gdf_rutas.to_crs("EPSG:4326")

    gdf_rutas.to_file(
        "rutas_centro_multiples.geojson",
        driver="GeoJSON"
    )

print("Conexiones generadas:", len(gdf_rutas))
print(
    "Líneas de longitud cero:",
    (gdf_rutas.to_crs("EPSG:32718").length == 0).sum()
)
print("Archivo generado: rutas_centro_multiples.geojson")


#todo a sql
#pip install geopandas sqlalchemy "psycopg[binary]" geoalchemy2






# Guardar el resultado en formato GeoJSON para abrirlo directamente en QGIS
#gdf_rutas = gpd.GeoDataFrame(geometry=lineas, crs="EPSG:32719").to_crs("EPSG:4326")
#gdf_rutas.to_file('rutas_centro_multiples.geojson', driver='GeoJSON')

#print("¡Proceso finalizado! Archivo 'rutas_centro_multiples.geojson' creado con éxito.")

# Cargar tus puntos / carga en orden del csv
#df = pd.read_csv('coordenadas_camaras.csv')

# Ordenar por columna /de secuencia
# df = df.sort_values(by='decimalLatitude')

#
# 
# 
#  Crear una lista de objetos Point respetando el orden
#puntos = [Point(xy) for xy in zip(df['decimalLongitude'], df['decimalLatitude'])]

# Crear el LineString uniendo los puntos secuencialmente
#if len(puntos) >= 2:
#    linea = LineString(puntos)
#    
#    # 4. Crear un GeoDataFrame para la línea
#    gdf_linea = gpd.GeoDataFrame(geometry=[linea], crs="EPSG:4326")
#    
#    # Guardar como archivo vectorial (GeoJSON o Shapefile)
#    gdf_linea.to_file('trayecto_camaras.geojson', driver='GeoJSON')
#    print("¡LineString creado con éxito!")
#else:
#    print("Se necesitan al menos 2 puntos para crear una línea.")