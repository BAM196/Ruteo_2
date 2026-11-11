# resultados/

Lo genera `python -m motor.evaluacion` (en Docker: `docker compose run --rm motor python -m motor.evaluacion`). Usa la consulta de `config/consulta_ejemplo.json`: de la cámara 16 a la 22, con la arista 27 amenazada (p = 0,8) y θ = 0,5.

## ejemplo_rutas.json

La respuesta completa de `POST /api/rutas` para la consulta de ejemplo. La estructura está en `Motor/README.md`, sección API.

## tabla_rutas.csv y tabla_rutas_autonomia.csv

Una fila por técnica. La segunda tabla repite la consulta con autonomía de 7.000 m, para mostrar la diferencia entre la técnica 2 y la 3.

| Columna | Significado |
| --- | --- |
| `tecnica`, `etiqueta` | Identificador y nombre visible de la técnica |
| `nodos` | Cámaras de la ruta, en orden |
| `distancia_m` | Largo de la ruta |
| `R_analitico` | $R(P)=\prod(1-q_v)\prod(1-p_a)$. Vacío si la ruta no es factible |
| `R_montecarlo`, `ic95_inf`, `ic95_sup` | Estimación por Monte Carlo (10.000 sorteos, regla D4) y su intervalo del 95 % |
| `delta_R` | $R$ de la técnica menos $R$ de la técnica 1 |
| `costo_C` | $C(P)$, el objetivo del modelo de optimización evaluado en la ruta |
| `tiempo_ms` | Tiempo de cálculo de la técnica (`time.perf_counter`, sin la carga de datos) |
| `factible`, `mensaje` | Si cumple autonomía y restricciones, y por qué no |
| `mas_resiliente` | `True` en la técnica ganadora |

## aco_corridas.csv

30 corridas (semillas 0 a 29) por configuración (`config_mai`, `config_zhang`). Columnas: `config`, `semilla`, `costo_C`, `gap_pct` (brecha con el óptimo de Gurobi), `distancia_m`, `factible`, `nodos`, `tiempo_ms`, `iteraciones` (las que corrió antes de parar).

## aco_resumen.csv

Una fila por configuración. Columnas: `C_optimo_milp`, `C_mejor`, `C_promedio`, `C_desv`, `gap_mejor_pct`, `gap_promedio_pct`, `aciertos_optimo` (corridas que llegaron al óptimo), `tiempo_ms_promedio` y `tiempo_ms_desv`. La brecha es $(C_{ACO}-C^*)/C^*\times100$, el mismo formato que Zhang et al. (2018).

## aco_banco.csv y aco_banco_resumen.csv

Instancias de estrés para medir la brecha. No son misiones reales: son 12 pares al azar (semilla 1), 15 aristas amenazadas con p entre 0,2 y 0,9, $D_{max}$ = 60 km y 5 semillas. Cada instancia se corre por configuración, con búsqueda local (10 pasos) y sin ella.

- **Columnas del resumen:** `corridas`, `aco_sin_ruta_factible`, `gap_promedio_pct`, `gap_max_pct`, `optimos`, `tiempo_aco_ms_prom` y `tiempo_milp_ms_prom`.
- **Instancias excluidas:** las que Gurobi declara infactibles (sin ruta bajo 60 km) no entran al resumen.

## aco_sensibilidad.csv

Grilla de α, β ∈ {1, 2, 5, 8}, ρ ∈ {0,2; 0,5}, hormigas ∈ {10, 30} y q0_inicial ∈ {0; 0,5; 0,9}, con 100 iteraciones y 5 semillas cada una, sobre la base de `config_mai`. Columnas: los parámetros (incluido `q0_inicial`), `C_promedio`, `gap_promedio_pct` y `tiempo_ms_promedio`.

## aco_convergencia.csv y aco_convergencia.png

Mejor $f$ por iteración: promedio y desviación de las 30 corridas, por configuración. Una corrida que paró antes conserva su último valor. El gráfico usa eje X logarítmico.
