# metadata_dem.json

Elevación de cada nodo según el Copernicus DEM GLO-30. Lo genera `Metadata/extraer_dem.py`, que descarga del bucket público `copernicus-dem-30m` en AWS los tiles que cubren el parque, sin credenciales. Los recorta y guarda el raster en `data/dem_pumalin.tif`.

Ese raster lo usan después `Infraestructura/perfiles_aristas.py` y `Infraestructura/generar_bases.py`. No se sube al repositorio porque pesa unos 15 MB; `main.py` lo vuelve a descargar.

## Por qué este DEM

- **Es un modelo de superficie:** incluye el dosel del bosque, que es lo que el dron debe librar.
- **Resolución de 30 m:** la misma que el SRTM que usan Chang et al. (2025), pero más reciente.
- **Error vertical:** menor a 4 m (90 % de error lineal). Entra en el despeje mínimo c_min.

## meta

| Campo | Contenido |
| --- | --- |
| `fuente`, `acceso`, `registro`, `tiles` | Dataset, bucket y tiles descargados |
| `archivo_raster`, `bbox` | Raster recortado y su rectángulo |
| `tipo_modelo`, `error_vertical`, `unidad` | Superficie, < 4 m LE90, metros sobre el nivel del mar |
| `cita` | ESA (2024), Copernicus Global DEM, doi:10.5270/ESA-c5d3d65 |
| `n_nodos`, `n_sin_dato`, `elevacion_min_m`, `elevacion_max_m` | Resumen |

## nodos[]

`nodo_id`, `nombre`, `lon`, `lat` y `elevacion_m`.
