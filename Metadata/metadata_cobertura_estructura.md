# metadata_cobertura.json

Clase de cobertura de suelo en cada nodo de `nodosv2.json`, según ESA WorldCover 10 m 2021 v200. Lo genera `Metadata/extraer_worldcover.py`, que lee directamente el COG público del bucket `esa-worldcover` en AWS, sin cuenta ni credenciales.

## Uso

La restricción "Volar solo sobre bosque" excluye los nodos cuya clase no es 10 (cobertura arbórea). El sistema no bloquea ninguna clase por defecto.

## meta

| Campo | Contenido |
| --- | --- |
| `fuente`, `acceso`, `registro`, `tiles`, `banda` | Dataset, cómo se descarga y qué tile se leyó |
| `cita` | Zanaga et al. (2022), doi:10.5281/zenodo.7254221 |
| `clases` | Código de WorldCover con su nombre en inglés y español |
| `nodos_por_clase` | Conteo de nodos por clase |
| `uso` | Cómo usa el sistema esta metadata |

## registros[]

| Campo | Contenido |
| --- | --- |
| `nodo_id`, `nombre`, `lat`, `lon` | Nodo |
| `landcover_code`, `landcover_clase`, `landcover_clase_es` | Clase de WorldCover |
| `nota_pixel` | Aviso cuando el píxel de 10 m cae en agua aunque la cámara esté en la orilla |

La tabla `metadata_cobertura` guarda estos campos y la elevación de `metadata_dem.json`.
