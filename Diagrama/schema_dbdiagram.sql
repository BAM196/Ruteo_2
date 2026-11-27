-- Este archivo no crea la base, es solo para crear el diagrama en dbdiagram.io
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

Table "metadata_cobertura" {
  "nodo_id" INTEGER [pk]
  "landcover_code" INTEGER
  "landcover_clase" TEXT
  "landcover_clase_es" TEXT
  "elevacion_m" DOUBLE
  "nota_pixel" TEXT
}

Table "especie_rce" {
  "cientifico" TEXT [pk]
  "comun" TEXT
  "origen" TEXT [not null]
  "categoria_los_lagos" TEXT
  "categoria_vigente" TEXT
  "decreto" TEXT
  "peso_w" DOUBLE
  "objetivo" BOOLEAN [not null]
  "presion" BOOLEAN [not null]
  "registros" INTEGER
  "camaras" INTEGER
  "ficha" JSONB
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

Table "metadata_fauna" {
  "id" INTEGER [pk]
  "documento" JSONB [not null, note: 'fauna.json completo (meta y especies)']
  "actualizado" TIMESTAMPTZ [not null]
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
  "rafaga" DOUBLE
  "lluvia_mm_h" DOUBLE
  "unidad_viento" TEXT
  "evitar" BOOLEAN
  "temperatura_min" DOUBLE
  "temperatura_max" DOUBLE
  "precipitacion_mm" DOUBLE
  "prob_lluvia" DOUBLE
  "modo" TEXT
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

Ref: "nodo_especie"."nodo_id" > "nodos"."id" [delete: cascade]

Ref: "aristas"."source" > "nodos"."id"
Ref: "aristas"."target" > "nodos"."id"

Ref: "metadata_cobertura"."nodo_id" > "nodos"."id" [delete: cascade]

Ref: "metadata_senderos_nodo"."sendero_id" > "metadata_senderos"."id" [delete: cascade]
Ref: "metadata_senderos_nodo"."nodo_id" > "nodos"."id" [delete: cascade]
Ref: "metadata_senderos_arista"."sendero_id" > "metadata_senderos"."id" [delete: cascade]
Ref: "metadata_senderos_arista"."arista_id" > "aristas"."id" [delete: cascade]

Ref: "amenazas_firms_nodo"."foco_id" > "amenazas_firms"."id" [delete: cascade]
Ref: "amenazas_firms_nodo"."nodo_id" > "nodos"."id" [delete: cascade]
Ref: "amenazas_firms_arista"."foco_id" > "amenazas_firms"."id" [delete: cascade]
Ref: "amenazas_firms_arista"."arista_id" > "aristas"."id" [delete: cascade]

Table "prob_fallo_nodo" {
  "nodo_id" INTEGER
  "amenaza" TEXT [not null, note: 'firms, meteo, ebird o escenario']
  "p_fallo" DOUBLE [not null]
  "detalle" JSONB
  "generado" TIMESTAMPTZ [not null]

  Indexes {
    (nodo_id, amenaza) [pk]
  }
}

Table "prob_fallo_arista" {
  "arista_id" INTEGER
  "amenaza" TEXT [not null, note: 'firms, meteo, ebird o escenario']
  "p_fallo" DOUBLE [not null]
  "detalle" JSONB
  "generado" TIMESTAMPTZ [not null]

  Indexes {
    (arista_id, amenaza) [pk]
  }
}

Ref: "prob_fallo_nodo"."nodo_id" > "nodos"."id" [delete: cascade]
Ref: "prob_fallo_arista"."arista_id" > "aristas"."id" [delete: cascade]
Ref: "meteo_alertas"."nodo_id" > "nodos"."id" [delete: cascade]
Ref: "meteo_alertas_nodo"."alerta_id" > "meteo_alertas"."id" [delete: cascade]
Ref: "meteo_alertas_nodo"."nodo_id" > "nodos"."id" [delete: cascade]
Ref: "meteo_alertas_arista"."alerta_id" > "meteo_alertas"."id" [delete: cascade]
Ref: "meteo_alertas_arista"."arista_id" > "aristas"."id" [delete: cascade]

Ref: "amenazas_ebird_nodo"."avistamiento_id" > "amenazas_ebird"."id" [delete: cascade]
Ref: "amenazas_ebird_nodo"."nodo_id" > "nodos"."id" [delete: cascade]
Ref: "amenazas_ebird_arista"."avistamiento_id" > "amenazas_ebird"."id" [delete: cascade]
Ref: "amenazas_ebird_arista"."arista_id" > "aristas"."id" [delete: cascade]
Ref: "amenazas_ebird_arista"."source" > "nodos"."id"
Ref: "amenazas_ebird_arista"."target" > "nodos"."id"

Table "arista_perfil" {
  "arista_id" INTEGER [pk]
  "largo_2d_m" DOUBLE [not null]
  "largo_3d_m" DOUBLE
  "ascenso_ida_m" DOUBLE
  "ascenso_vuelta_m" DOUBLE
  "despeje_min_m" DOUBLE
  "altura_max_sobre_superficie_m" DOUBLE
  "densificada" BOOLEAN [not null]
  "bloqueada" BOOLEAN [not null]
  "motivo" TEXT
  "geom" geometry
}

Table "bases" {
  "id" INTEGER [pk]
  "tipo" TEXT [not null]
  "nodo_id" INTEGER
  "nombre" TEXT
  "sendero_id" INTEGER
  "elevacion_m" DOUBLE
  "geom" geometry [not null]
}

Table "base_camara" {
  "base_id" INTEGER
  "camara_id" INTEGER
  "distancia_m" DOUBLE [not null]
  "bloque_visible" BOOLEAN [not null]
  "fraccion_visible" DOUBLE

  Indexes {
    (base_id, camara_id) [pk]
  }
}

Table "base_enlace" {
  "id" INTEGER [pk]
  "base_id" INTEGER
  "nodo_id" INTEGER
  "distancia_m" DOUBLE [not null]
  "largo_3d_m" DOUBLE
  "ascenso_ida_m" DOUBLE
  "ascenso_vuelta_m" DOUBLE
  "despeje_min_m" DOUBLE
  "geom" geometry
}

Table "base_arista_visible" {
  "base_id" INTEGER
  "arista_id" INTEGER
  "visible" BOOLEAN [not null]
  "motivo" TEXT

  Indexes {
    (base_id, arista_id) [pk]
  }
}

Table "sectores" {
  "id" INTEGER [pk]
  "base_id" INTEGER
  "n_camaras" INTEGER [not null]
  "diametro_m" DOUBLE [not null]
  "valor_conservacion" DOUBLE
  "presion_exoticas" DOUBLE
  "prioridad" DOUBLE
  "subtitulo" TEXT
  "detalle" JSONB
  "geom" geometry
}

Table "sector_camara" {
  "sector_id" INTEGER
  "camara_id" INTEGER

  Indexes {
    (sector_id, camara_id) [pk]
  }
}

Table "campanas" {
  "id" SERIAL [pk]
  "nombre" TEXT
  "tipo" TEXT [not null]
  "modo" TEXT [not null]
  "consulta" JSONB [not null]
  "temporada" TEXT
  "fecha_inicio" DATE [not null]
  "fecha_limite" DATE [not null]
  "visitas_objetivo" INTEGER [not null]
  "estado" TEXT [not null]
  "completa" BOOLEAN [not null]
  "motivo" TEXT
  "creada" TIMESTAMPTZ [not null]
}

Table "campana_dia" {
  "id" SERIAL [pk]
  "campana_id" INTEGER
  "visita" INTEGER [not null]
  "fecha" DATE [not null]
  "estado" TEXT [not null]
  "decision" TEXT
  "r_plan" DOUBLE
  "plan" JSONB
  "actualizado" TIMESTAMPTZ [not null]
}

Ref: "arista_perfil"."arista_id" - "aristas"."id" [delete: cascade]
Ref: "bases"."nodo_id" > "nodos"."id" [delete: cascade]
Ref: "base_camara"."base_id" > "bases"."id" [delete: cascade]
Ref: "base_camara"."camara_id" > "nodos"."id" [delete: cascade]
Ref: "base_enlace"."base_id" > "bases"."id" [delete: cascade]
Ref: "base_enlace"."nodo_id" > "nodos"."id" [delete: cascade]
Ref: "base_arista_visible"."base_id" > "bases"."id" [delete: cascade]
Ref: "base_arista_visible"."arista_id" > "aristas"."id" [delete: cascade]
Ref: "sectores"."base_id" > "bases"."id"
Ref: "sector_camara"."sector_id" > "sectores"."id" [delete: cascade]
Ref: "sector_camara"."camara_id" > "nodos"."id" [delete: cascade]
Ref: "campana_dia"."campana_id" > "campanas"."id" [delete: cascade]
