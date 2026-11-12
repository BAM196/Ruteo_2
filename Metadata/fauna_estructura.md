# `fauna.json`

Catálogo de especies del Parque Nacional Pumalín Douglas Tompkins, filtrado a las especies objetivo del proyecto que pertenecen al reino `Animalia`. `extraer_fauna.py` lee `data/Pumal237n Douglas Tompkins - Especies.csv` y guarda el resultado del proyecto como JSON en esta carpeta.

## Estructura principal

El documento contiene dos propiedades:

- `meta`: fuente, fecha de extracción, criterio y resumen del filtrado.
- `especies`: registros de las especies objetivo encontradas en el catálogo.

## `meta`

| Campo | Descripción |
| --- | --- |
| `fuente` | Nombre del inventario de especies. |
| `archivo_fuente` | Ruta del CSV local relativo a la raíz del proyecto. |
| `generado` | Fecha y hora UTC de la extracción, en formato ISO 8601. |
| `criterio` | Descripción del filtro aplicado. |
| `especies_objetivo` | Nombres científicos que el extractor busca en el catálogo. |
| `especies_no_encontradas` | Especies objetivo que no aparecieron en el archivo. |
| `n_especies_encontradas` | Cantidad de nombres científicos distintos encontrados. |
| `n_registros` | Cantidad de registros incluidos en `especies`. |

## `especies[]`

Cada elemento contiene la información disponible en el catálogo para una especie objetivo:

| Campo | Columna de SIMBIO | Descripción |
| --- | --- | --- |
| `reino` | Reino | Reino taxonómico. |
| `filo` | Filo o División | Filo o división taxonómica. |
| `clase` | Clase | Clase taxonómica. |
| `orden` | Orden | Orden taxonómico. |
| `familia` | Familia | Familia taxonómica. |
| `genero` | Género | Género taxonómico. |
| `nombre_cientifico` | Nombre Científico | Nombre científico tal como aparece en el catálogo. |
| `nombre_comun` | Nombre Común | Nombre común, si está disponible. |
| `estado_conservacion` | Estado de conservación | Categoría de conservación, si está disponible en el inventario. |
| `origen_chile` | — | Se conserva vacío porque el inventario local no contiene este dato. |
| `url_ficha` | Inventario Especies | Enlace a la ficha de la especie, si está disponible. |

Los valores no informados por el inventario se guardan como cadenas vacías. Se filtran las filas cuyo reino sea `Animalia` y cuyo nombre científico esté en `especies_objetivo`.

`Metadata/cargar_fauna.py` guarda el documento completo en la columna `documento` de `metadata_fauna` como `JSONB`. La tabla mantiene una sola versión del catálogo y la carga posterior reemplaza esa versión.
