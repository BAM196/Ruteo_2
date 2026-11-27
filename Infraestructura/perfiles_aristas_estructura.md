# perfiles_aristas.json

Perfil de cada tramo de `aristasv2.json` sobre el terreno. Lo genera `Infraestructura/perfiles_aristas.py` con el DEM de `data/dem_pumalin.tif`. Así los tramos dejan de ser rectas planas: se vuelan a 80 m sobre la superficie y siguen el relieve.

## Reglas

1. **Muestreo:** cada tramo se muestrea cada 30 m, la resolución del DEM.
2. **Altura de vuelo:** los extremos se vuelan a 80 m sobre la superficie, la altura que validaron Chang et al. (2025) con el mismo dron.
3. **Densificación:** si la recta entre dos puntos pasa a menos de c_min sobre la superficie, o a más de 120 m (el techo de la DAN 151), se agrega un punto intermedio a 80 m sobre la superficie. Se usan los menos puntos posibles.
4. **Despeje mínimo:** c_min = error del DEM (4 m) + error de altura del dron (0,5 m) + margen por árboles más altos que el promedio del píxel (20 m) = 24,5 m.
5. **Bloqueo:** el tramo queda bloqueado si en un solo paso de 30 m el desnivel supera 120 − c_min. Para mantener el despeje habría que volar sobre el techo legal; pasa en acantilados.

El bloqueo por línea de vista depende de la base desde donde se vuela, así que está en `bases.json`.

## meta

`fuente`, `dem`, `aristas_origen`, `altura_vuelo_m`, `techo_m`, `despeje_minimo_m`, `regla_despeje`, `paso_muestreo_m`, `regla_densificacion`, `regla_bloqueo`, `n_aristas`, `n_densificadas` y `n_bloqueadas`.

## perfiles[]

| Campo | Contenido |
| --- | --- |
| `arista_id`, `source`, `target` | Tramo |
| `bloqueada`, `motivo` | Si se puede volar, y por qué no |
| `largo_2d_m`, `largo_3d_m` | Largo en planta y largo real volado |
| `ascenso_ida_m`, `ascenso_vuelta_m` | Subida acumulada de `source` a `target` y en sentido contrario |
| `despeje_min_m`, `altura_max_sobre_superficie_m` | Menor y mayor altura sobre la superficie del perfil final |
| `superficie_min_m`, `superficie_max_m` | Rango del terreno bajo el tramo |
| `densificada`, `n_puntos` | Si se agregaron puntos y cuántos tiene el perfil |
| `puntos` | `[lon, lat, altura sobre el nivel del mar]` de cada punto del vuelo |

## Uso en el motor

El tiempo de un tramo es largo / v_c + subida / v_sub, con v_c = 9 m/s y v_sub = 6 m/s según la ficha DJI. Depende del sentido. La tabla `arista_perfil` guarda estos campos con la geometría 3D.
