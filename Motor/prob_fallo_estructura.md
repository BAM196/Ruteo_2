# prob_fallo.json

Probabilidad de falla de cada nodo (cámaras, waypoints y bases) y de cada tramo (incluidos los enlaces desde las bases), por amenaza y en total. Lo genera `python -m motor.probabilidades` y se carga en las tablas `prob_fallo_nodo` y `prob_fallo_arista`. Las vistas `prob_fallo_nodo_total` y `prob_fallo_arista_total` dan el total por elemento.

## Principio

Cada probabilidad es la probabilidad de que ocurra, durante el vuelo, la condición que hace fallar al dron, dado lo que miden los datos. Las fórmulas y sus fuentes están en `Motor/config/amenazas.yaml`. El detalle de cada amenaza está en los archivos `amenaza_*_estructura.md`.

## Combinación

$$q = 1 - \prod_k (1 - q_k)$$

- **Si las amenazas son independientes:** la combinación es exacta.
- **Si se correlacionan positivamente:** por ejemplo, viento e incendio. La probabilidad real de que falle alguna es menor que la calculada, así que la fórmula es una cota superior del riesgo, y nunca baja de la mayor de las q_k.
- **Tope:** la probabilidad tiene un tope de 1 − 10⁻⁶ para que −ln(1 − p) sea finito. Un elemento en el tope se excluye de las rutas.

## meta

| Campo | Contenido |
| --- | --- |
| `generado`, `principio`, `datos` | Fecha de cálculo, principio y resumen del escenario |
| `amenazas_activas`, `combinacion`, `independencia` | Qué amenazas entran y cómo se combinan |
| `cota_superior`, `nota_cota` | Tope y su efecto |
| `overrides_prob` | Probabilidades simuladas por el usuario |
| `fecha_referencia` | Fecha contra la que se mide la recencia de las aves |
| `radio_aves_m` | 100 m + r_mov |
| `parametros` | Copia de `amenazas.yaml` usada en el cálculo |

## nodos[] y aristas[]

| Campo | Contenido |
| --- | --- |
| `id` (y `source`, `target` en tramos) | Elemento |
| `p_total` | Probabilidad combinada |
| `por_amenaza` | `firms`, `meteo`, `ebird` y `escenario` (amenaza simulada) |
| `detalle` | Por amenaza: focos o avistamientos dentro del radio con su distancia y su p, o la lectura del clima con la ráfaga llevada a 80 m y la p de viento, temperatura y lluvia |
