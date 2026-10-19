# metadata_gee.json

Clase de cobertura de suelo en cada cámara de `nodosv2.json`, junto con las especies que esa cámara fotografió.

El mapa es ESA WorldCover 10 m 2021 v200. En Google Earth Engine es `ESA/WorldCover/v200/2021`. Cita: Zanaga et al. (2022), doi:10.5281/zenodo.7254221.

`modo_extraccion` dice cómo se leyó: `gee` con cuenta de Earth Engine, o `cog` con el GeoTIFF público del mismo mapa.

En las 48 cámaras hay 43 de bosque, 1 de pastizal y 4 de agua. En bosque, el pudú aparece en 30 cámaras, la güiña en 23 y el puma en 9. La vaca tiene más fotos (5050 en 5 cámaras), así que no se prioriza por cantidad de fotos.

## Códigos

| Código | Clase |
| --- | --- |
| 10 | Cobertura arbórea |
| 20 | Matorral |
| 30 | Pastizal |
| 40 | Cultivo |
| 50 | Zona construida |
| 60 | Suelo desnudo o vegetación escasa |
| 70 | Nieve y hielo |
| 80 | Cuerpo de agua permanente |
| 90 | Humedal herbáceo |
| 95 | Manglar |
| 100 | Musgo y liquen |

## Preferencia

Si el usuario pide solo bosque, las cámaras con código distinto de 10 quedan fuera de esa consulta.

Si no pide nada, no se prohíbe ninguna clase. Se marca `priorizar` solo en la clase con más cámaras de pudú, güiña, puma, culpeo o quique. Con estos datos es la 10. El Dijkstra de esta fase no usa esa marca: su costo sigue siendo `costo_km`.

## registros[]

- `nodo_id`: id de la cámara en `nodosv2.json`.
- `nombre`, `lat`, `lon`, `codigos_estacion`: la misma cámara.
- `landcover_code`, `landcover_clase`, `landcover_clase_es`: clase del píxel de 10 m.
- `especies`: especies de esa cámara. Cada una trae `cientifico`, `comun` y `registros`.
- `tiene_especie_objetivo`: hay pudú, güiña, puma, culpeo o quique.
- `tiene_especie_invasora`: hay visón, liebre, perro o vaca.
- `clase_prioritaria_default`: la clase es la prioritaria.
- `preferencia_default`: `priorizar` o `sin_prioridad`.
- `restriccion_default`: `null`. Por defecto no se excluye ninguna cámara.
- `nota_pixel`: en agua, el píxel de 10 m puede ser el fiordo y la cámara estar en la orilla. No se borra.

## meta

- `modo_extraccion`, `dataset_gee`, `banda`, `cita`: de dónde sale la clase.
- `especies_objetivo`, `especies_invasoras`: las listas de arriba.
- `clases_prioritarias_default`: códigos marcados para priorizar.
- `preferencias_default`, `ejemplo_restriccion_usuario`: la regla de la sección anterior, en texto.
- `resumen_por_clase`: cuántas cámaras hay de cada clase y qué especies salieron ahí.
- `clases`: el diccionario de códigos.
