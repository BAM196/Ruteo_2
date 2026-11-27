# amenaza_firms.json

Focos de incendio activos de NASA FIRMS alrededor de las cámaras de `nodosv2.json`, con un margen de 0,05°. Lo genera `Amenazas/extraer_firms.py`.

- **Sensor:** VIIRS Suomi-NPP, con píxeles de 375 m.
- **Ventana:** 5 días, el máximo que admite una consulta de la API.
- **Modo reciente (sin fecha):** consulta los últimos 5 días con el producto casi en tiempo real (`VIIRS_SNPP_NRT`).
- **Modo histórico (`--fecha AAAA-MM-DD`):** consulta los 5 días que terminan en esa fecha. Si la fecha tiene más de 60 días, usa el producto estándar (`VIIRS_SNPP_SP`), que existe desde 2012.

Cero focos es un resultado válido.

## Cómo se usa

El archivo solo lista los focos y qué nodos y tramos quedan a 1.000 m o menos de cada uno. La probabilidad de falla la calcula el motor con esta fórmula (parámetros en `Motor/config/amenazas.yaml`):

$$p = P(\text{foco real} \mid \text{confianza}) \cdot \max\left(0,\ 1 - \frac{d}{R}\right), \qquad R = 1.000\ \text{m}$$

- **Confianza nominal o alta:** P(foco real) = 0,988. El error de comisión publicado es menor a 1,2 % (Schroeder et al., 2014).
- **Confianza baja:** P(foco real) = 0,6. Es el peor valor reportado para esa clase: 40 % de detecciones erróneas.
- **Radio de 1.000 m:** el fuego puede estar a hasta 265 m del centro del píxel (media diagonal de 375 m). Los 735 m restantes son la distancia de seguridad al humo y al calor.

## meta

| Campo | Contenido |
| --- | --- |
| `fuente`, `source`, `endpoint` | NASA FIRMS, el producto usado y la URL de la API |
| `modo`, `fecha_escenario`, `desde`, `day_range` | Reciente o histórico, la fecha pedida, el primer día consultado y el largo de la ventana |
| `bbox`, `margen_grados` | Rectángulo consultado |
| `umbral_amenaza_m` | Radio con que se listan los nodos y tramos cercanos (1.000 m) |
| `regla` | La regla de arriba, en una frase |
| `n_focos`, `n_nodos_afectados`, `n_aristas_afectadas` | Conteos |
| `resultado` | `con_focos` o `sin_focos_en_area` |

## focos[]

| Campo | Contenido |
| --- | --- |
| `id`, `lat`, `lon` | Identificador y centro del píxel |
| `acq_date`, `acq_time` | Fecha y hora UTC de la pasada (`HHMM`) |
| `satellite`, `confidence`, `frp`, `daynight`, `bright_ti4` | Satélite, confianza (`l`, `n` o `h`), potencia radiativa en MW, día o noche y temperatura de brillo |
| `nodo_mas_cercano` | `{id, distancia_m}`, aunque quede lejos |
| `nodos_dentro_umbral`, `aristas_dentro_umbral` | Nodos y tramos a 1.000 m o menos |

## nodos_afectados[] y aristas_afectadas[]

- **Nodo:** `nodo_id`, `distancia_min_m`, `focos`, `evitar` y `motivo`.
- **Tramo:** `arista_id`, `source`, `target`, `distancia_min_m`, `costo_km`, `focos` y `evitar`.
