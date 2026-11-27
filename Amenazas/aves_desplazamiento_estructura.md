# aves_desplazamiento.json

Cálculo de r_mov, el desplazamiento típico de las aves que eBird registra en el parque. Lo genera `Amenazas/calcular_r_mov.py` a partir de `amenaza_ebird.json` y de la tabla `aves_desplazamiento.yaml`.

## Regla

$$r_{mov} = \frac{\sum_e d_e \cdot n_e}{\sum_e n_e}$$

- **d_e:** desplazamiento típico de la especie e, sacado de un estudio con GPS o de su ámbito de hogar.
- **n_e:** cantidad de registros de la especie.

eBird ubica la lista del observador y no al ave, que además se mueve kilómetros. Por eso el radio de la amenaza de aves es R = 100 m + r_mov.

- **Especies sin dato publicado verificado:** usan el valor provisional de 2 km, que es el orden de los viajes de alimentación más cortos medidos en gaviotas (Reusch et al., 2020).
- **Sensibilidad:** r_mov se reporta con 1 y 5 km (`python -m motor.evaluacion`).

## meta

| Campo | Contenido |
| --- | --- |
| `regla` | La fórmula de arriba |
| `fuente_registros`, `tabla` | De dónde salen los registros y los desplazamientos |
| `provisional_km` | Valor para especies sin dato |
| `n_especies`, `n_con_fuente`, `n_registros` | Cobertura del cálculo |
| `r_mov_km`, `r_mov_m` | Resultado. El motor lo lee en lugar del valor de `amenazas.yaml` |

## especies[]

`cientifico`, `comun`, `registros`, `desplazamiento_km`, `con_fuente` (si tiene un dato publicado), `medida` y `fuente`.
