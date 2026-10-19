# nodosv2.json

Cada nodo es una cámara de fotomonitoreo CONAF en el Parque Nacional Pumalín. Sale de `occurrence.txt` (GBIF Chile). La misma latitud y longitud se agrupa en una sola cámara, con las especies que registró.

La cámara está donde CONAF la instaló. La ruta del dron visita esas estaciones.

## meta

- `fuente`, `area`: origen de los puntos y el parque.
- `filtro_localidad`: texto usado para quedarse con Pumalín.
- `bbox`: `"none"` usa el parque completo. Un recorte va como `oeste,sur,este,norte`.
- `k_vecinos`, `max_arista_m`: con qué se armaron las aristas.
- `crs`: coordenadas en grados (WGS84). `crs_metrico`: UTM 18S, para medir metros.
- `n_nodos`, `n_aristas`: conteos.
- `nota_grafo`: el grafo es no dirigido.

## nodos[]

- `id`: número fijo, de 1 a n, ordenado por latitud y longitud.
- `nombre`: estación, por ejemplo `Camara AC103`.
- `lat`, `lon`: grados decimales.
- `codigos_estacion`: códigos CONAF de esa cámara.
- `localidad`: parque.
- `n_registros`: fotos de esa cámara en el archivo.
- `anios`: años de esas fotos.
- `especies[]`: `cientifico`, `comun` y `registros`.

En el archivo original, `coordinateUncertaintyInMeters` vale 1000 en todas las filas. La misma cámara repite la coordenada exacta en cientos de fotos, así que el nodo usa esa coordenada.
