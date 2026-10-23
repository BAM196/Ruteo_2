# amenaza_meteo.json

Focos con puntos de amenaza de la actividad climática (temperatura, humedad, viento) solicitados por medio de la API (Weather Forecast API)

## Justificación Técnica

Las condciciones climáticas afectan directamente la toma de muestras y el estado del dispositivo, causando imágenes poco claras y daños a la aeronave, llevando a rutas incompletas y perdida de equipo.

## Regla de Peso y Penalización

- **Umbral de territorialidad:** $3000\text{ m}$ alrededor del avistamiento.
- Si un tramo o cámara cae a $\le 3000\text{ m}$:
  - `evitar = true`
  - `costo_resiliente_km = costo_km + 3000`
- Al igual que en NASA FIRMS, el Dijkstra de fase 2 utiliza solo `costo_km`, dejando `costo_resiliente_km` para la heurística resiliente de fase 3.

## meta

`fuente`: Open-Meteo API
`endpoint`: https://api.open-meteo.com/v1/forecast
`generado`: `2026-10-20T00:09:49+00:00`
`umbral_amenaza_m`: 1000.0,

## alertas_meteorologicas[]

`nodo_id`: nodo afectado
`fecha`: tiempo del evento
`temperatura`: temperatura ambiente
`humedad`: humedad del ambiente
`viento`: velocidad del viento a nivel de vuelo
`geom`: `lat`, `lon`

## nodos_afectados[], aristas_afectadas[]

Nodo: `nodo_id`, `fecha`, `temperatura`, `humedad`, `viento`, `geom`

arista: `alerta_id`, `source`, `target`, `distancia_m`, `costo_km`, `costo_resiliente_km`, `evitar`
