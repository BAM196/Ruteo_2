# amenaza_firms.json

Focos de NASA FIRMS sobre las cámaras de `nodosv2.json`, con un margen de 0,05° alrededor. El sensor es VIIRS Suomi-NPP y la ventana es de 5 días, el máximo de una consulta.

Si un foco cae junto a una cámara, esa estación no se visita mientras siga activo: no se espera fauna ahí. Cero focos es un resultado válido. La consulta del 19 de octubre de 2026, y la primera semana de febrero de 2023 a 2026, dieron 0 focos en esta caja.

## Radio y peso

El punto de FIRMS es el centro de un píxel de 375 m, no la llama (Schroeder et al., 2014, Remote Sensing of Environment 143, 85-96). El radio usado es 1000 m: cubre ese píxel y el entorno de la cámara. En el informe 1 el foco más cercano estaba a unos 16 km y no quedaba definido desde qué distancia sí afecta.

Dentro de ese radio la fauna no se asume disponible. Tras el fuego persiste en parches no quemados, no en lo recién quemado (Robinson et al., 2013, Journal of Applied Ecology 50, 1321-1329). 1000 m es la regla de este trabajo, no una distancia única para todas las especies.

Si el foco está a 1000 m o menos del tramo:

- `evitar = true`
- `costo_resiliente_km = costo_km + 1000`

Ese costo no entra al Dijkstra de esta fase. `pgr_dijkstra` usa solo `costo_km`. Lo penalizado queda para la fase 3. La misma regla marca la cámara en `nodos_afectados`.

## meta

- `fuente`, `source`, `endpoint`: NASA FIRMS y el sensor.
- `bbox`, `margen_grados`: rectángulo consultado.
- `day_range`, `fecha`: días de la consulta. `fecha` vacía significa los días más recientes.
- `umbral_amenaza_m`: 1000.
- `penalizacion_km`: 1000, los kilómetros que se suman al tramo afectado.
- `regla_peso`: la regla de arriba, en una frase.
- `n_focos`, `n_nodos_afectados`, `n_aristas_afectadas`: conteos.
- `resultado`: `con_focos` o `sin_focos_en_area`.

## focos[]

- `id`, `lat`, `lon`.
- `acq_date`, `acq_time`: fecha y hora UTC. La hora viene como `HHMM`.
- `satellite`, `confidence` (`l`, `n` o `h`), `frp` (MW), `daynight` (`D` o `N`), `bright_ti4`.
- `nodo_mas_cercano`: `{id, distancia_m}`, aunque quede lejos.
- `nodos_dentro_umbral`, `aristas_dentro_umbral`: los que caen en los 1000 m.

## nodos_afectados[] y aristas_afectadas[]

Cámara: `nodo_id`, `distancia_min_m`, `focos`, `evitar`, `motivo`.

Tramo: `arista_id`, `source`, `target`, `distancia_min_m`, `costo_km`, `costo_resiliente_km`, `evitar`, `focos`.
