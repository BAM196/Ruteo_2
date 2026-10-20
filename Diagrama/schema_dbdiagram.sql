-- Este archivo no crea la base, es solo para crear el diagrama en dbdiagram.io
-- geom es Point en nodos, metadata_gee y amenazas_firms, y LineString en aristas
-- La base real se crea con Diagrama/schema.sql


Table "nodos" {
  "id" INTEGER [pk]
  "nombre" TEXT [not null]
  "localidad" TEXT
  "n_registros" INTEGER
  "anios" TEXT
  "codigos_estacion" TEXT
  "point" geometry [not null]
}

Table "nodo_especie" {
  "nodo_id" INTEGER
  "cientifico" TEXT [not null]
  "comun" TEXT
  "registros" INTEGER [not null]

  Indexes {
    (nodo_id, cientifico) [pk]
  }
}

Table "aristas" {
  "id" INTEGER [pk]
  "source" INTEGER [not null]
  "target" INTEGER [not null]
  "distancia_m" DOUBLE [not null]
  "costo_km" DOUBLE [not null]
  "tipo" TEXT [not null]
  "excede_max" BOOLEAN [not null]
  "point" geometry [not null]
}

Table "metadata_gee" {
  "nodo_id" INTEGER [pk]
  "nombre" TEXT
  "landcover_code" INTEGER
  "landcover_clase" TEXT
  "landcover_clase_es" TEXT
  "tiene_especie_objetivo" BOOLEAN
  "tiene_especie_invasora" BOOLEAN
  "clase_prioritaria_default" BOOLEAN
  "preferencia_default" TEXT
  "nota_pixel" TEXT
  "point" geometry
}

Table "metadata_gee_especie" {
  "nodo_id" INTEGER
  "cientifico" TEXT [not null]
  "comun" TEXT
  "registros" INTEGER [not null]

  Indexes {
    (nodo_id, cientifico) [pk]
  }
}

Table "metadata_senderos" {
  "id" INTEGER [pk]
  "nombre" TEXT [not null]
  "tipo" TEXT [not null]
  "descripcion" TEXT
  "longitud_km" DOUBLE [not null, default: 0.0]
  "point" geometry [not null]
}

Table "metadata_senderos_nodo" {
  "sendero_id" INTEGER
  "nodo_id" INTEGER
  "distancia_m" DOUBLE [not null]

  Indexes {
    (sendero_id, nodo_id) [pk]
  }
}

Table "metadata_senderos_arista" {
  "sendero_id" INTEGER
  "arista_id" INTEGER
  "distancia_m" DOUBLE [not null]
  "buffer_privacidad" BOOLEAN [not null, default: FALSE]

  Indexes {
    (sendero_id, arista_id) [pk]
  }
}

Table "amenazas_firms" {
  "id" INTEGER [pk]
  "acq_date" DATE
  "acq_time" TEXT
  "satellite" TEXT
  "confidence" TEXT
  "frp" DOUBLE
  "daynight" TEXT
  "point" geometry [not null]
}

Table "amenazas_firms_nodo" {
  "foco_id" INTEGER
  "nodo_id" INTEGER
  "distancia_m" DOUBLE [not null]

  Indexes {
    (foco_id, nodo_id) [pk]
  }
}

Table "amenazas_firms_arista" {
  "foco_id" INTEGER
  "arista_id" INTEGER
  "source" INTEGER
  "target" INTEGER
  "distancia_m" DOUBLE [not null]
  "costo_km" DOUBLE
  "costo_resiliente_km" DOUBLE
  "evitar" BOOLEAN [not null]

  Indexes {
    (foco_id, arista_id) [pk]
  }
}

Table "meteo_alertas" {
  "id" SERIAL [pk]
  "nodo_id" INTEGER
  "fecha" DATE [not null]
  "temperatura" DOUBLE [not null]
  "humedad" DOUBLE [not null]
  "viento" DOUBLE [not null]
  "point" geometry [not null]
}

Table "meteo_alertas_nodo" {
  "alerta_id" INTEGER
  "nodo_id" INTEGER
  "distancia_m" DOUBLE [not null]

  Indexes {
    (alerta_id, nodo_id) [pk]
  }
}

Table "meteo_alertas_arista" {
  "alerta_id" INTEGER
  "arista_id" INTEGER
  "source" INTEGER
  "target" INTEGER
  "distancia_m" DOUBLE [not null]
  "costo_km" DOUBLE
  "costo_resiliente_km" DOUBLE
  "evitar" BOOLEAN [not null]

  Indexes {
    (alerta_id, arista_id) [pk]
  }
}

Table "amenazas_ebird" {
  "id" TEXT [pk]
  "especie_cientifico" TEXT [not null]
  "especie_comun" TEXT
  "fecha_obs" TIMESTAMP
  "cantidad" INTEGER
  "localidad" TEXT
  "point" geometry [not null]
}

Table "amenazas_ebird_nodo" {
  "avistamiento_id" TEXT
  "nodo_id" INTEGER
  "distancia_m" DOUBLE [not null]

  Indexes {
    (avistamiento_id, nodo_id) [pk]
  }
}

Table "amenazas_ebird_arista" {
  "avistamiento_id" TEXT
  "arista_id" INTEGER
  "source" INTEGER
  "target" INTEGER
  "distancia_m" DOUBLE [not null]
  "costo_km" DOUBLE
  "costo_resiliente_km" DOUBLE
  "evitar" BOOLEAN [not null]

  Indexes {
    (avistamiento_id, arista_id) [pk]
  }
}
