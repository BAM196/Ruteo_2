# traslados_bases.json

Tiempo real de traslado entre las bases de los sectores. Lo genera `Infraestructura/traslados_bases.py`, que consulta el servidor público de OSRM (caminos de OpenStreetMap).

## Regla

El traslado total es el tiempo en auto entre las dos bases más la caminata desde el punto de camino más cercano a cada base, a 3 km/h. Solo se miden pares de bases a 15 km o menos en línea recta.

OSRM no ve los accesos por mar ni el estado real de los senderos; esos casos hay que confirmarlos con CONAF.

El motor usa estos tiempos para agrupar varios sectores cercanos en una misma mañana (`motor/capacidad.py`). Si el archivo no existe, usa la línea recta a pie.

## meta

`fuente`, `regla`, `limitacion`, `n_bases`, `n_pares`, `pares_sin_camino` y `bases_a_mas_de_2_km_de_un_camino`.

## pares[]

`base_i`, `base_j`, `recta_km`, `auto_km`, `auto_min`, `pie_base_i_m`, `pie_base_j_m` y `total_min`.
