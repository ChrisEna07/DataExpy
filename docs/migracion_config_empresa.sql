-- =============================================================
-- Migración: Tabla configuraciones_empresa (White Label)
-- =============================================================
-- Creado: 2026-06-23
-- Descripción: Almacena la configuración de personalización
--   del reporte PDF para cada instalación/cliente.
--   Solo una fila (singleton) ya que es una configuración
--   global de la instalación.
-- =============================================================

CREATE TABLE IF NOT EXISTS configuraciones_empresa (
    id BIGSERIAL PRIMARY KEY,
    empresa_nombre TEXT NOT NULL DEFAULT 'DataExPY',
    logo_base64 TEXT,                          -- Logo codificado en base64 (PNG/JPG)
    color_primario TEXT DEFAULT '#0f3460',     -- Color primario en hex (ej: #0f3460)
    actualizado_por TEXT,                      -- Usuario@Host que hizo el cambio
    actualizado_en TIMESTAMPTZ DEFAULT NOW()   -- Fecha de última modificación
);

-- Índice único parcial para garantizar singleton (solo una fila activa)
CREATE UNIQUE INDEX IF NOT EXISTS idx_config_unica
    ON configuraciones_empresa ((true));

-- =============================================================
-- Uso:
--   1. Ejecuta esta migración en la consola SQL de Supabase
--      (SQL Editor → New Query → pegar → Run)
--   2. La app creará/actualizará la fila automáticamente al
--      guardar configuración desde el modal ⚙ Config
-- =============================================================
