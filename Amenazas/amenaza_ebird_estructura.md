# amenaza_ebird.json

Avistamientos de aves grandes o territoriales cerca de la red, consultados en la API 2.0 de eBird (The Cornell Lab of Ornithology). Lo genera `Amenazas/extraer_ebird.py`.

## Qué aves y por qué

Se guardan las rapaces, las carroñeras, las gaviotas y los queltehues: aguiluchos, halcones, caranchos, tiuques, búhos, cóndores, jotes y gaviotas. Pueden atacar o chocar con el dron. Además, el dron puede perturbarlas, y eso va contra el objetivo de conservación (Vas et al., 2015).

## Modos

- **Reciente (sin fecha):** observaciones de los últimos 14 días. El parque mide 107 km de norte a sur y la API busca a lo más 50 km de un punto, así que se consulta desde dos puntos y se juntan los resultados.
- **Histórico (`--fecha AAAA-MM-DD`):** observaciones de la Región de Los Lagos (`CL-LL`) en los 14 días que terminan en esa fecha.

Sin `EBIRD_API_KEY` en `.env`, el archivo existente se mantiene sin cambios.

## Cómo se usa

El motor calcula la probabilidad de falla con esta fórmula (parámetros en `Motor/config/amenazas.yaml`):

$$p_i = p_0 \cdot f_{recencia} \cdot \max\left(0,\ 1 - \frac{d}{R}\right), \qquad p = 1 - (1 - p_i)^n, \qquad R = 100\ \text{m} + r_{mov}$$

- **100 m:** distancia de despegue que recomiendan Vas et al. (2015) para no perturbar aves.
- **r_mov:** cuánto se desplaza un ave. Es el promedio, ponderado por registros, del desplazamiento típico de las aves que eBird registra en el parque. Lo calcula `calcular_r_mov.py`.
- **p₀ = 0,5:** se sabe que hay aves, pero no si van a reaccionar al dron.
- **f_recencia:** vale 1 el día del avistamiento y 0 a los 14 días.
- **n:** cantidad de aves del registro. El término (1 − p_i)ⁿ da la probabilidad de que al menos una reaccione.

## meta

| Campo | Contenido |
| --- | --- |
| `fuente`, `endpoint`, `modo`, `fecha_escenario`, `region` | Origen y modo de la consulta |
| `dias_atras`, `puntos_consulta`, `radio_consulta_km` | Ventana y puntos desde donde se consultó |
| `filtro`, `generos` | Qué aves se guardan |
| `umbral_amenaza_m` | Radio R con que se listan los nodos y tramos cercanos |
| `n_avistamientos`, `n_nodos_afectados`, `n_aristas_afectadas` | Conteos |

## avistamientos[]

| Campo | Contenido |
| --- | --- |
| `id` | Lista de eBird y especie (`subId:speciesCode`), único por especie |
| `lista` | Identificador de la lista (`subId`) |
| `cientifico`, `comun` | Especie |
| `fecha_obs`, `cantidad`, `localidad` | Cuándo, cuántas aves y dónde |
| `lat`, `lon` | Ubicación de la lista (la del observador, no la del ave) |
| `nodos_dentro_umbral`, `aristas_dentro_umbral` | Nodos y tramos a R o menos |
