# bases.json

Lugares desde donde el operador puede volar el dron, y qué se ve desde cada uno. Lo genera `Infraestructura/generar_bases.py` con el DEM, los tramos y los senderos.

## Candidatas

Las candidatas son puntos a los que se llega a pie:

- **La posición de cada cámara:** CONAF las instala y revisa caminando.
- **Un punto cada 100 m sobre los senderos oficiales.**
- **Un punto cada 100 m en la caminata entre dos cámaras** a 2,7 km o menos. Es el recorrido que hace quien revisa ambas.

Se guardan solo las que quedan a 1.359 m o menos de alguna cámara. Ese alcance es R_op − r_b, donde R_op = 1.500 m es el radio de operación de la DAN 151 y r_b = 141 m es la media diagonal del bloque de muestreo de 200 × 200 m.

## Línea de vista

La DAN 151 define la línea de vista como una recta entre el operador y el dron. Se calcula sobre el DEM:

- **Ojo del operador:** a 1,7 m sobre la superficie.
- **Claro alrededor de la base:** se supone que el operador está en un claro o en un sendero, así que los primeros 60 m no cortan la vista.
- **Una cámara se puede atender desde la base** si queda dentro del alcance y los 25 puntos de su bloque de muestreo son visibles.
- **Un tramo es volable desde la base** si todo su perfil queda a 1.500 m o menos y ningún punto queda tapado por un cerro.

## meta

`regla_candidatas`, `radio_operacion_m`, `media_diagonal_bloque_m`, `alcance_camara_m`, `ojo_operador_m`, `claro_operador_m`, `regla_visibilidad`, `enlaces_por_base`, los conteos por tipo y `camaras_sin_base` (cámaras que ninguna base deja a la vista).

## bases[]

| Campo | Contenido |
| --- | --- |
| `id` | El id de la cámara si la base es una cámara; 100000 o más en los otros casos |
| `tipo` | `camara`, `sendero` o `camino_camaras` |
| `nodo_id`, `sendero_id`, `entre_camaras` | De dónde sale la candidata |
| `nombre`, `lon`, `lat`, `elevacion_m` | Ubicación |
| `camaras[]` | Cámaras a ≤ alcance: `camara_id`, `distancia_m`, `bloque_visible` y `fraccion_visible` |
| `enlaces[]` | Tramos directos desde la base a sus 4 nodos más cercanos y a cada cámara que atiende, con su perfil (`largo_3d_m`, `ascenso_ida_m`, `ascenso_vuelta_m`, `despeje_min_m`, `puntos`) |
| `aristas_visibles` | Tramos de la red volables desde esa base |
| `aristas_bloqueadas[]` | Tramos dentro del radio que no se pueden volar desde la base: `arista_id` y `motivo` (`linea_de_vista` o `altura`) |

Las tablas son `bases`, `base_camara`, `base_enlace` y `base_arista_visible`.
