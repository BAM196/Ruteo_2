# amenaza_meteo.json

Condiciones de Open-Meteo en cada una de las 48 cámaras para la ventana de la mañana, cuando se vuela. Lo genera `Amenazas/extraer_meteo.py`.

## Ventana

Son 3 horas desde la primera hora completa que empieza 60 minutos después del amanecer. Los dos valores están en `Motor/config/mision.yaml`. La imagen térmica se toma poco después del amanecer, antes de que el suelo se caliente (Chang et al., 2025).

## Modos

- **Pronóstico (sin fecha):** la próxima mañana, con el pronóstico por hora de la Weather Forecast API, incluida la probabilidad de lluvia (`precipitation_probability`).
- **Histórico (`--fecha AAAA-MM-DD`):** esa mañana, con la Historical Weather API (reanálisis).

## Cómo se usa

Por cámara se guarda la peor hora de la ventana. El motor calcula tres probabilidades y las combina como independientes (parámetros en `Motor/config/amenazas.yaml`):

- **Viento:** la ráfaga a 10 m se lleva a la altura de vuelo con g₈₀ = g₁₀ · 8^α, con α = 0,25, la fila "Wooded countryside, many trees" de la Tabla 6.3 de Masters (2004). Luego p = 1 − Φ((12 − g₈₀) / σ), con σ = 3,1 m/s. Es la desviación estándar del sesgo del modelo de climatología en la Tabla 2 de Harris y Kahl (2017), y se usa como peor caso.
- **Temperatura:** probabilidad de quedar fuera de −10 a 40 °C, el rango de operación del dron.
- **Lluvia:** en pronóstico, la probabilidad de lluvia de la peor hora. En histórico, 1 si llovió y 0 si no. El dron no es resistente al agua.

El clima solo se mide en las cámaras. Un tramo toma el máximo de sus dos extremos, y una base toma el de la cámara más cercana. Como es el mismo viento en todo el recorrido, el motor cuenta el clima una vez por vuelo, con el máximo del recorrido.

## meta

| Campo | Contenido |
| --- | --- |
| `fuente`, `endpoint`, `modo`, `fecha_escenario` | API usada y fecha de la mañana |
| `ventana` | Primera y última hora, y la regla |
| `variables`, `unidad_viento`, `unidad_lluvia` | Variables pedidas; viento en m/s y lluvia en mm/h |
| `resumen_ventana` | Cómo se resume la ventana en una lectura |
| `limites_dron` | 12 m/s de ráfaga y −10 a 40 °C |
| `n_lecturas`, `n_evitar` | Lecturas y cuántas tienen alguna condición fuera de los límites |

## lecturas[]

| Campo | Contenido |
| --- | --- |
| `nodo_id`, `nombre`, `lat`, `lon` | Cámara |
| `fecha`, `amanecer` | Día de la ventana y hora del amanecer |
| `temperatura`, `temperatura_min`, `temperatura_max` | Promedio, mínima y máxima de la ventana (°C) |
| `humedad` | Humedad relativa promedio (%) |
| `viento`, `rafaga` | Viento y ráfaga máximos a 10 m (m/s) |
| `precipitacion_mm`, `lluvia_mm_h` | Lluvia acumulada y la hora más lluviosa |
| `prob_lluvia` | Mayor probabilidad de lluvia de la ventana (%), solo en pronóstico |
| `horas` | Horas de la ventana con datos |
| `evitar`, `motivo` | Si alguna condición queda fuera de los límites del dron, y cuál |

## Tablas

`meteo_alertas` guarda una fila por lectura, con todas estas columnas. `meteo_alertas_nodo` y `meteo_alertas_arista` la cruzan con la cámara y con los tramos que tocan esa cámara.
