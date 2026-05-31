-- ------------------------------------------------------------
-- schema.sql
-- Schema de la base de datos en Supabase (PostgreSQL).
--
-- Ejecutar una sola vez en el SQL Editor de Supabase:
--   Dashboard -> SQL Editor -> New query -> pegar este archivo -> Run.
--
-- Tablas:
--   1) notificaciones: destino final del pipeline (con datos cifrados).
--   2) rechazados:     auditoria de filas descartadas por etapa.
--   3) load_audit:     bitacora de cada ejecucion de la carga.
-- ------------------------------------------------------------

-- ------------------------------------------------------------
-- Tabla 1: destino final
-- ------------------------------------------------------------
create table if not exists notificaciones (
  notification_id      text primary key,
  event_id             text not null,
  event_type           text not null,
  user_id_enc          text not null,
  source_user_id_enc   text not null,
  post_id              text,
  comment_id           text,
  created_at           timestamptz not null,
  device               text not null,
  delivery_channel     text not null,
  priority             text not null,
  seen                 boolean not null,
  status               text not null,
  app_version          text not null,
  country              text not null,
  latency_ms           integer not null,
  cargado_at           timestamptz default now()
);

-- ------------------------------------------------------------
-- Tabla 2: auditoria de rechazos
-- ------------------------------------------------------------
create table if not exists rechazados (
  id                serial primary key,
  notification_id   text,
  etapa             text not null check (etapa in ('limpieza', 'validacion')),
  motivo_rechazo    text not null,
  payload_original  jsonb not null,
  rechazado_at      timestamptz default now()
);

-- ------------------------------------------------------------
-- Tabla 3: bitacora de cargas
-- ------------------------------------------------------------
create table if not exists load_audit (
  id                  serial primary key,
  fecha_carga         timestamptz default now(),
  archivo_origen      text not null,
  filas_entrada       integer not null,
  filas_insertadas    integer not null,
  filas_idempotentes  integer not null,
  total_destino       integer not null,
  cifrado             text not null
);

-- ------------------------------------------------------------
-- Indices para consultas comunes
-- ------------------------------------------------------------
create index if not exists idx_notif_status   on notificaciones(status);
create index if not exists idx_notif_country  on notificaciones(country);
create index if not exists idx_rechazados_etapa on rechazados(etapa);
