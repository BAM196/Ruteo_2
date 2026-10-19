# aristasv2.json

Tramos entre las cámaras de `nodosv2.json`. Los genera `generar_nodos_v2.py`.

Cada cámara se une a sus 2 vecinas más cercanas (`tipo = "knn"`). Si el grafo queda partido, se agregan los tramos mínimos para dejarlo en una sola pieza (`tipo = "conexion"`). Un tramo de más de 3 km no se borra: queda con `excede_max = true`.

`source` y `target` son el `id` del nodo, no el número de la fila.

## meta

La misma cabecera que `nodosv2.json`.

## aristas[]

- `id`: número de la arista.
- `source`, `target`: id de los dos nodos. Hay una sola fila por par.
- `distancia_m`: largo en metros.
- `costo_km`: `distancia_m / 1000`. Es el costo de `pgr_dijkstra` en esta fase. No incluye cobertura ni incendios.
- `tipo`: `knn` o `conexion`.
- `excede_max`: verdadero si el tramo supera `max_arista_m`.
- `coordenadas`: `[[lon, lat], [lon, lat]]`, para dibujar la línea.

La consulta usa el grafo sin dirección:

```sql
SELECT * FROM pgr_dijkstra(
  'SELECT id, source, target, costo_km AS cost FROM aristas',
  inicio, objetivo, directed => false
);
```
