# prob_fallo.json

Probabilidad de falla de cada nodo (cámara) y de cada arista (tramo de vuelo), por amenaza y total. Lo genera `Motor/motor/probabilidades.py` (punto 5) y se carga en las tablas `prob_fallo_nodo` y `prob_fallo_arista`.

```bash
docker compose run --rm motor python -m motor.probabilidades --cargar
```

## meta

| Campo | Significado |
| --- | --- |
| `generado` | Fecha y hora UTC del cálculo |
| `datos` | De dónde se leyó (`db` o `json`) y cuántos nodos, aristas, focos, avistamientos y lecturas de clima había |
| `amenazas_activas` | Amenazas que entran al cálculo (`firms`, `meteo`, `ebird`) |
| `combinacion` | Regla para combinar amenazas: `q = 1 - prod_k (1 - q_k)` (independientes) |
| `cota_superior` | 0,999999. Ninguna probabilidad la supera, para que `-ln(1-p)` sea finito. Una probabilidad en la cota equivale a excluir el elemento |
| `overrides_prob` | Probabilidades forzadas para el caso de ejemplo (vacío en la corrida normal) |
| `fecha_referencia_ebird` | Avistamiento más reciente: desde él se mide la recencia |
| `parametros` | Copia de `config/amenazas.yaml`: cada parámetro con `valor`, `fuente` y `justificacion` |
| `limitacion` | La suposición de independencia, dicha explícitamente |

## nodos[]

| Campo | Significado |
| --- | --- |
| `id` | `nodos.id` (cámara) |
| `p_total` | Probabilidad de falla total del nodo (0 a 0,999999) |
| `por_amenaza` | Probabilidad por amenaza, por ejemplo `{"firms": 0.0, "meteo": 0.12, "ebird": 0.0}`. Si hay un override, aparece `escenario` |
| `detalle.firms` | `focos_en_radio`: focos a menos de `radio_m`, con `distancia_m`, `confianza` y su `p` |
| `detalle.meteo` | `lectura` (temperatura, humedad, viento y ráfaga en m/s, lluvia en mm/h), `viento_usado` (ráfaga o viento medio), `p_viento`, `p_temperatura`, `p_lluvia` |
| `detalle.ebird` | `avistamientos_en_radio`: avistamientos a menos de `radio_m`, con `distancia_m`, `f_recencia`, `f_cantidad` y su `p` |

## aristas[]

Igual que `nodos[]`, más `source` y `target`. La distancia a un foco o avistamiento es la del punto al segmento (UTM 18S). En `detalle.meteo` va la regla `max(p_u, p_v)` con la probabilidad de cada extremo.

## Ejemplo (arista con override)

```json
{
  "id": 27, "source": 19, "target": 20, "p_total": 0.8,
  "por_amenaza": {"firms": 0.0, "meteo": 0.0, "ebird": 0.0, "escenario": 0.8},
  "detalle": {"escenario": {"nota": "probabilidad forzada (overrides_prob)"}}
}
```

## En la base

- `prob_fallo_nodo(nodo_id, amenaza, p_fallo, detalle, generado)` y `prob_fallo_arista(arista_id, amenaza, p_fallo, detalle, generado)`: una fila por elemento y amenaza.
- Vistas `prob_fallo_nodo_total` y `prob_fallo_arista_total`: la probabilidad total con `1 - EXP(SUM(LN(1 - p_fallo)))` y un JSON `por_amenaza`.
