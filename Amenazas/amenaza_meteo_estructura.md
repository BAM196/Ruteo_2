# amenaza_meteo.json

Condiciones meteorológicas actuales en cada cámara, obtenidas de la API de Open-Meteo (Weather Forecast API, sin clave). Lo genera `Amenazas/extraer_meteo.py` y lo carga `Amenazas/cargar_meteo.py`.

## Por qué es una amenaza

El viento, la temperatura y la lluvia limitan el vuelo del dron. La ficha del DJI Mavic 3T da estos límites:

- **Viento:** 12 m/s como máximo.
- **Temperatura:** operación de −10 a 40 °C.
- **Lluvia:** no declara clasificación IP, así que no es resistente al agua.

En la fase 3 la lectura se convierte en una probabilidad de falla (`Motor/motor/probabilidades.py`, parámetros en `Motor/config/amenazas.yaml`).

## Variables pedidas a la API

Son las mismas que se citan en el informe:

| Variable de Open-Meteo | Campo en el JSON | Unidad |
| --- | --- | --- |
| `temperature_2m` | `temperatura` | °C |
| `relative_humidity_2m` | `humedad` | % |
| `wind_speed_10m` | `viento` | m/s (se pide `wind_speed_unit=ms`; por defecto la API entrega km/h) |
| `wind_gusts_10m` | `rafaga` | m/s |
| `precipitation` | `precipitacion_mm` | mm acumulados en el intervalo (15 min) |

Se hace una sola consulta con las coordenadas de las 48 cámaras.

## meta

| Campo | Significado |
| --- | --- |
| `fuente`, `endpoint` | API consultada |
| `generado` | Fecha y hora UTC de la consulta |
| `variables` | Lista de variables pedidas |
| `unidades_api` | Unidades que devolvió la API (`current_units`), como evidencia de que el viento viene en m/s |
| `unidad_viento`, `unidad_lluvia` | Unidades del JSON: `m/s` y `mm/h` |
| `intervalo_s` | Duración del intervalo de la lectura actual (900 s) |
| `limites_fabricante` | `v_max_ms`, `temperatura_min_c` y `temperatura_max_c`, leídos de `Motor/config/amenazas.yaml` |
| `regla_evitar` | Cuándo se marca `evitar = true` |
| `n_lecturas`, `n_evitar` | Lecturas guardadas y cuántas superan los límites del fabricante |

## lecturas[]

| Campo | Significado |
| --- | --- |
| `nodo_id`, `nombre`, `lat`, `lon` | Cámara consultada |
| `fecha` | Hora local de la lectura (`current.time`) |
| `temperatura`, `humedad`, `viento`, `rafaga` | Valores medidos (ver la tabla de unidades) |
| `precipitacion_mm` | Lluvia del intervalo, tal como la entrega la API |
| `lluvia_mm_h` | Lluvia convertida a mm/h: `precipitacion_mm × 3600 / intervalo_s` |
| `evitar` | `true` si el viento o la ráfaga supera 12 m/s, o si la temperatura sale de −10 a 40 °C |
| `motivo` | Explicación de `evitar` |

## En la base

- `meteo_alertas`: una fila por lectura, con las columnas `rafaga`, `lluvia_mm_h`, `unidad_viento` y `evitar` agregadas en la fase 3.
- `meteo_alertas_nodo`: enlaza cada lectura con su cámara.
- `meteo_alertas_arista`: enlaza cada lectura con las aristas que tocan esa cámara.
