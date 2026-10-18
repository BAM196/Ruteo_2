#ejemplo de extraccion

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# Cargar datos
df = pd.read_csv('occurrence.txt', sep='\t', low_memory=False)
df = df.dropna(subset=['decimalLatitude', 'decimalLongitude'])#var extraer 

# Crear geometría de puntos a partir de longitud y latitud
geometry = [Point(xy) for xy in zip(df['decimalLongitude'], df['decimalLatitude'])]

# Crear un GeoDataFrame (tabla con datos geográficos)
gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326") # WGS84 (sistema GPS estándar) ??

# Guardar como archivo GeoJSON o GeoPackage para abrir en QGIS
gdf.to_file('camaras_fotomonitoreo.geojson', driver='GeoJSON')

print("Archivo GeoJSON creado exitosamente con todas las coordenadas georreferenciadas.")