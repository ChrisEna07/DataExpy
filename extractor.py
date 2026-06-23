import os
import re
import json
import logging
import time
import socket
import platform
import getpass
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

import base64

from dotenv import load_dotenv
from supabase import create_client, Client
from llm_client import (
    obtener_respuesta_llm,
    obtener_respuesta_vision,
    CIRCUIT_BREAKER_TEXTO,
    CIRCUIT_BREAKER_VISION,
    CircuitBreakerOpen,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("extractor")


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    supabase_key: str = field(default_factory=lambda: os.getenv("SUPABASE_KEY", ""))
    groq_model: str = "openai/gpt-oss-20b"
    groq_vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    max_retries: int = 3
    retry_delay: float = 2.0

    def validate(self) -> None:
        missing = []
        if not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        elif not self.groq_api_key.startswith("gsk_"):
            missing.append(
                "GROQ_API_KEY con formato incorrecto (debe empezar con 'gsk_'). "
                "Consigue una key en https://console.groq.com/keys"
            )
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_key:
            missing.append("SUPABASE_KEY")
        if missing:
            raise RuntimeError(
                f"Faltan variables de entorno: {', '.join(missing)}. "
                "Revisa tu archivo .env"
            )


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------

AUDIT_USER = getpass.getuser() or os.getenv("USERNAME", "unknown")
AUDIT_HOST = socket.gethostname()
AUDIT_PROCESADO_POR = f"{AUDIT_USER}@{AUDIT_HOST}"

# Handler de archivo para auditoría estructurada
_AUDIT_LOG_PATH = None
_audit_logger = logging.getLogger("auditoria")
_audit_logger.setLevel(logging.INFO)
_audit_logger.propagate = False


def _init_audit_log() -> None:
    global _AUDIT_LOG_PATH
    if _audit_logger.handlers:
        return
    from pathlib import Path
    _AUDIT_LOG_PATH = Path(__file__).resolve().parent / "auditoria.log"
    handler = logging.FileHandler(str(_AUDIT_LOG_PATH), encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | Usuario: %(user)s | Accion: %(message)s"
    ))
    _audit_logger.addHandler(handler)


def registrar_accion(accion: str, estado: str = "EXITO", **extra) -> None:
    _init_audit_log()
    identidad = f"{AUDIT_USER}@{AUDIT_HOST}"
    extra_str = f" | {json.dumps(extra, ensure_ascii=False)}" if extra else ""
    _audit_logger.info(
        "%s - Estado: %s%s",
        accion, estado, extra_str,
        extra={"user": identidad},
    )


def _enriquecer_audit(datos: dict, status: str = "COMPLETADO") -> dict:
    datos["procesado_por"] = AUDIT_PROCESADO_POR
    datos["status"] = status
    datos["procesado_en"] = datetime.now().isoformat()
    datos["log_detalles"] = {
        "usuario": AUDIT_USER,
        "host": AUDIT_HOST,
        "identidad": AUDIT_PROCESADO_POR,
        "accion": "PROCESAR_DOCUMENTO",
        "estado": status,
    }
    return datos


# ---------------------------------------------------------------------------
# Prompt Maestro
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Actúa como un Analista de Datos Senior especializado en LegalTech.
Tu objetivo es transformar documentos legales no estructurados (textos, contratos,
facturas, recibos) en datos estructurados de alta calidad.

REGLAS:
1. Devuelve ÚNICAMENTE un objeto JSON válido, sin texto adicional.
2. Usa este esquema exacto:
   {"cliente": "Nombre completo", "fecha": "AAAA-MM-DD", "total": 0.0, "id_documento": "Código"}
3. Si un dato no existe en el texto, usa null (no lo inventes).
4. Si detectas información sensible (tarjetas, contraseñas, direcciones privadas),
   reemplázala por '[PROTEGIDO]'.
5. El campo 'total' debe ser float, sin símbolos de moneda ni separadores de miles."""


VISION_SYSTEM_PROMPT = """Actúa como un experto en OCR y Análisis de Documentos.
Analiza la imagen adjunta y extrae la información solicitada.

Si la imagen es borrosa o ilegible, indica 'Calidad insuficiente' en el campo cliente.

Extrae el texto utilizando visión computacional.

REGLAS:
1. Devuelve EXCLUSIVAMENTE un JSON válido con este esquema exacto:
   {"cliente": "Nombre completo", "fecha": "AAAA-MM-DD", "total": 0.0, "id_documento": "Código"}
2. Si un dato no existe en el texto, usa null (no lo inventes).
3. Si detectas información sensible (tarjetas, contraseñas, direcciones privadas),
   reemplázala por '[PROTEGIDO]'.
4. El campo 'total' debe ser float, sin símbolos de moneda ni separadores de miles.
5. Si detectas que es un documento escaneado, ignora el ruido visual y enfócate en los datos contables."""


TRANSCRIBE_PROMPT = """Transcribe TODO el texto visible en esta imagen con la máxima precisión posible.
Devuelve EXCLUSIVAMENTE el texto transcrito, sin comentarios, ni análisis, ni JSON.
Respeta el formato original, saltos de línea y estructura del documento."""

EXTRACT_FIELDS_PROMPT = """Actúa como un extractor de datos. Dado el texto de un documento legal,
extrae ÚNICAMENTE los campos solicitados y devuélvelos como JSON.

REGLAS:
1. Responde solo con un JSON válido, sin texto adicional.
2. Usa los nombres de campo exactos que se te piden.
3. Si un dato no existe, usa null.
4. Si hay datos sensibles (tarjetas, contraseñas), usa '[PROTEGIDO]'.
5. Números deben ir como strings a menos que sean montos (float).

Documento:
{texto}

Campos solicitados: {campos_json}"""


# ---------------------------------------------------------------------------
# Schema de salida esperado
# ---------------------------------------------------------------------------

EXPECTED_FIELDS = {"cliente", "fecha", "total", "id_documento"}


# ---------------------------------------------------------------------------
# Cliente global (inicializado bajo demanda)
# ---------------------------------------------------------------------------

_settings: Optional[Settings] = None
_db_client: Optional[Client] = None


def _init() -> None:
    global _settings, _db_client
    if _settings is not None:
        return
    _settings = Settings()
    _settings.validate()
    _db_client = create_client(_settings.supabase_url, _settings.supabase_key)
    log.info("Clientes inicializados correctamente")


# ---------------------------------------------------------------------------
# Extracción con IA + reintentos
# ---------------------------------------------------------------------------

def extraer(texto: str) -> dict:
    _init()
    last_error = None
    es_largo = len(texto) > 50000

    for attempt in range(1, _settings.max_retries + 1):
        try:
            log.info("Extracción — intento %d/%d", attempt, _settings.max_retries)

            def _call():
                return obtener_respuesta_llm(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=texto,
                    es_largo=es_largo,
                    response_format={"type": "json_object"},
                    temperatura=0.0,
                )

            raw = CIRCUIT_BREAKER_TEXTO.call(_call)
            datos = json.loads(raw)
            _validar_esquema(datos)
            _normalizar(datos)
            log.info("Extracción exitosa: %s", datos)
            return datos

        except CircuitBreakerOpen as e:
            log.warning("Circuit Breaker abierto (intento %d): %s", attempt, e)
            last_error = e
            if attempt < _settings.max_retries:
                time.sleep(_settings.retry_delay * attempt * 2)
        except json.JSONDecodeError as e:
            log.warning("JSON inválido (intento %d): %s", attempt, e)
            last_error = e
        except (KeyError, TypeError, ValueError) as e:
            log.warning("Esquema inválido (intento %d): %s", attempt, e)
            last_error = e
        except Exception as e:
            log.warning("Error en API (intento %d): %s", attempt, e)
            last_error = e

        if attempt < _settings.max_retries:
            time.sleep(_settings.retry_delay * attempt)

    msg = f"Extracción fallida tras {_settings.max_retries} intentos"
    if last_error:
        msg += f". Último error: {last_error}"
    log.error(msg)
    raise RuntimeError(msg) from last_error


# ---------------------------------------------------------------------------
# Validación y normalización
# ---------------------------------------------------------------------------

def _validar_esquema(datos: dict) -> None:
    if not isinstance(datos, dict):
        raise TypeError("La respuesta no es un diccionario")
    missing = EXPECTED_FIELDS - set(datos.keys())
    if missing:
        raise ValueError(f"Faltan campos en la respuesta: {missing}")
    for k in datos:
        if k not in EXPECTED_FIELDS:
            log.warning("Campo extra en respuesta: %s", k)


def _normalizar(datos: dict) -> None:
    # total → float
    if datos["total"] is not None:
        datos["total"] = float(str(datos["total"]).replace(",", "").replace("$", "").replace("€", ""))
    # id_documento → string
    if datos["id_documento"] is not None:
        datos["id_documento"] = str(datos["id_documento"])


# ---------------------------------------------------------------------------
# Persistencia en Supabase
# ---------------------------------------------------------------------------

def guardar(datos: dict, status: str = "COMPLETADO") -> dict:
    _init()
    datos = _enriquecer_audit(datos, status)
    try:
        resultado = _db_client.table("documentos_legales").insert(datos).execute()
        log.info("Insertado en Supabase: %s | status: %s", datos.get("id_documento"), status)
        registrar_accion("PROCESAR_DOCUMENTO", estado=status, id_documento=datos.get("id_documento"))
        return resultado.data[0] if resultado.data else datos
    except Exception as e:
        registrar_accion("PROCESAR_DOCUMENTO", estado="FALLO", error=str(e))
        log.error("Error al insertar en Supabase: %s", e)
        raise


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def procesar_documento(texto: str) -> dict:
    datos = extraer(texto)
    guardar(datos, status="COMPLETADO")
    return datos


# ---------------------------------------------------------------------------
# Extracción desde imagen (visión)
# ---------------------------------------------------------------------------

def extraer_imagen(base64_image: str, mime_type: str = "image/jpeg") -> dict:
    _init()
    last_error = None
    import base64
    image_bytes = base64.b64decode(base64_image)

    for attempt in range(1, _settings.max_retries + 1):
        try:
            log.info("Extracción visión — intento %d/%d", attempt, _settings.max_retries)

            def _call():
                return obtener_respuesta_vision(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    system_prompt=VISION_SYSTEM_PROMPT,
                    text_prompt="Extrae los datos de la imagen en formato JSON.",
                    max_tokens=1024,
                )

            raw = CIRCUIT_BREAKER_VISION.call(_call)
            datos = json.loads(raw)
            _validar_esquema(datos)
            _normalizar(datos)
            log.info("Extracción visión exitosa: %s", datos)
            return datos

        except CircuitBreakerOpen as e:
            log.warning("Circuit Breaker visión abierto (intento %d): %s", attempt, e)
            last_error = e
            if attempt < _settings.max_retries:
                time.sleep(_settings.retry_delay * attempt * 2)
        except json.JSONDecodeError as e:
            log.warning("JSON inválido (intento %d): %s", attempt, e)
            last_error = e
        except (KeyError, TypeError, ValueError) as e:
            log.warning("Esquema inválido (intento %d): %s", attempt, e)
            last_error = e
        except Exception as e:
            log.warning("Error en API visión (intento %d): %s", attempt, e)
            last_error = e

        if attempt < _settings.max_retries:
            time.sleep(_settings.retry_delay * attempt)

    msg = f"Extracción de imagen fallida tras {_settings.max_retries} intentos"
    if last_error:
        msg += f". Último error: {last_error}"
    log.error(msg)
    raise RuntimeError(msg) from last_error


def procesar_imagen(file_bytes: bytes, mime_type: str) -> dict:
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    datos = extraer_imagen(b64, mime_type)
    guardar(datos, status="COMPLETADO")
    return datos


# ---------------------------------------------------------------------------
# Transcripción completa (OCR con IA)
# ---------------------------------------------------------------------------

def transcribir_imagen(file_bytes: bytes, mime_type: str) -> str:
    _init()
    last_error = None

    for attempt in range(1, _settings.max_retries + 1):
        try:
            log.info("Transcripción — intento %d/%d", attempt, _settings.max_retries)

            def _call():
                return obtener_respuesta_vision(
                    image_bytes=file_bytes,
                    mime_type=mime_type,
                    system_prompt=TRANSCRIBE_PROMPT,
                    text_prompt="Transcribe todo el texto del documento.",
                    max_tokens=4096,
                )

            texto = CIRCUIT_BREAKER_VISION.call(_call).strip()
            if not texto:
                raise ValueError("Transcripción vacía")
            log.info("Transcripción exitosa (%d caracteres)", len(texto))
            return texto

        except CircuitBreakerOpen as e:
            log.warning("Circuit Breaker transcripción abierto (intento %d): %s", attempt, e)
            last_error = e
            if attempt < _settings.max_retries:
                time.sleep(_settings.retry_delay * attempt * 2)
        except Exception as e:
            log.warning("Transcripción fallida (intento %d): %s", attempt, e)
            last_error = e

        if attempt < _settings.max_retries:
            time.sleep(_settings.retry_delay * attempt)

    raise RuntimeError(f"Transcripción fallida tras {_settings.max_retries} intentos") from last_error


# ---------------------------------------------------------------------------
# Extracción dinámica de campos
# ---------------------------------------------------------------------------

def extraer_campos_dinamico(texto: str, campos: list[str]) -> dict:
    _init()
    if not campos:
        return {}

    prompt = EXTRACT_FIELDS_PROMPT.format(
        texto=texto,
        campos_json=json.dumps(campos, ensure_ascii=False),
    )

    for attempt in range(1, _settings.max_retries + 1):
        try:
            log.info("Extracción dinámica — intento %d/%d: %s", attempt, _settings.max_retries, campos)

            def _call():
                return obtener_respuesta_llm(
                    system_prompt="Eres un extractor de datos. Responde solo con JSON.",
                    user_prompt=prompt,
                    response_format={"type": "json_object"},
                    temperatura=0.0,
                )

            raw = CIRCUIT_BREAKER_TEXTO.call(_call)
            datos = json.loads(raw)
            log.info("Extracción dinámica exitosa: %s", datos)
            return datos

        except CircuitBreakerOpen as e:
            log.warning("Circuit Breaker abierto (intento %d): %s", attempt, e)
            last_error = e
            if attempt < _settings.max_retries:
                time.sleep(_settings.retry_delay * attempt * 2)
        except Exception as e:
            log.warning("Extracción dinámica fallida (intento %d): %s", attempt, e)
            last_error = e

        if attempt < _settings.max_retries:
            time.sleep(_settings.retry_delay * attempt)

    raise RuntimeError(f"Extracción dinámica fallida tras {_settings.max_retries} intentos") from last_error


# ---------------------------------------------------------------------------
# Búsqueda de texto en documento
# ---------------------------------------------------------------------------

def buscar_en_texto(texto: str, query: str, contexto: int = 60) -> list[dict]:
    if not texto or not query:
        return []

    resultados = []
    for match in re.finditer(re.escape(query), texto, re.IGNORECASE):
        start = max(0, match.start() - contexto)
        end = min(len(texto), match.end() + contexto)
        antes = texto[start:match.start()]
        despues = texto[match.end():end]
        resultados.append({
            "match": match.group(),
            "antes": antes.strip(),
            "despues": despues.strip(),
            "posicion": match.start(),
            "linea": texto[:match.start()].count("\n") + 1,
        })

    return resultados


# ---------------------------------------------------------------------------
# Procesar documento con transcripción completa
# ---------------------------------------------------------------------------

def procesar_con_transcripcion(file_bytes: bytes, mime_type: str) -> dict:
    transcripcion = transcribir_imagen(file_bytes, mime_type)
    datos = extraer(transcripcion)
    datos["transcripcion_completa"] = transcripcion
    guardar(datos, status="COMPLETADO")
    return datos


# ---------------------------------------------------------------------------
# Reporte PDF de conformidad
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Configuración de empresa (White Label)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_EMPRESA = {
    "empresa_nombre": "DataExPY",
    "logo_base64": None,
    "color_primario": "#0f3460",
}


def _cargar_config_empresa() -> dict:
    """Carga la configuración de empresa desde Supabase. Devuelve dict con valores por defecto si no existe."""
    _init()
    try:
        resultado = _db_client.table("configuraciones_empresa").select("*").limit(1).execute()
        if resultado.data:
            row = resultado.data[0]
            return {
                "empresa_nombre": row.get("empresa_nombre", _DEFAULT_CONFIG_EMPRESA["empresa_nombre"]),
                "logo_base64": row.get("logo_base64"),
                "color_primario": row.get("color_primario", _DEFAULT_CONFIG_EMPRESA["color_primario"]),
            }
    except Exception as e:
        log.warning("No se pudo cargar config_empresa: %s", e)
    return dict(_DEFAULT_CONFIG_EMPRESA)


def _guardar_config_empresa(config: dict) -> bool:
    """Guarda/actualiza la configuración de empresa en Supabase. Solo una fila (singleton)."""
    _init()
    try:
        # Ver si ya existe una fila
        existente = _db_client.table("configuraciones_empresa").select("id").limit(1).execute()
        payload = {
            "empresa_nombre": config.get("empresa_nombre", _DEFAULT_CONFIG_EMPRESA["empresa_nombre"]),
            "logo_base64": config.get("logo_base64"),
            "color_primario": config.get("color_primario", _DEFAULT_CONFIG_EMPRESA["color_primario"]),
            "actualizado_por": AUDIT_PROCESADO_POR,
            "actualizado_en": datetime.now().isoformat(),
        }
        if existente.data:
            row_id = existente.data[0]["id"]
            _db_client.table("configuraciones_empresa").update(payload).eq("id", row_id).execute()
        else:
            _db_client.table("configuraciones_empresa").insert(payload).execute()
        log.info("Configuración de empresa guardada: %s", payload["empresa_nombre"])
        return True
    except Exception as e:
        log.error("Error al guardar config_empresa: %s", e)
        return False


# ---------------------------------------------------------------------------
# Reporte PDF de conformidad (versión profesional)
# ---------------------------------------------------------------------------

_logo_cache = None


def _get_logo_path() -> str | None:
    """Devuelve la ruta al logo del proyecto, o None si no existe."""
    from pathlib import Path
    for p in [
        Path(__file__).resolve().parent / "assets" / "logo.png",
        Path(__file__).resolve().parent / "logo.png",
    ]:
        if p.exists():
            return str(p)
    return None


def _dibujar_logo_defecto(pdf, x: float, y: float, size: float = 12):
    """Dibuja un círculo con 'D' como logo por defecto."""
    pdf.set_fill_color(15, 40, 96)
    pdf.set_draw_color(15, 40, 96)
    cx, cy = x + size / 2, y + 2
    r = size / 2
    pdf.circle(cx, cy, r)
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", int(size * 0.45))
    pdf.text(cx - size * 0.13, cy + size * 0.18, "D")


def _hash_datos(datos: dict) -> str:
    """SHA-256 del JSON de datos para el QR de validación."""
    import hashlib
    limpio = {k: v for k, v in datos.items() if k not in ("transcripcion_completa", "_timestamp")}
    raw = json.dumps(limpio, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _sanear_texto(texto: str) -> str:
    reemplazos = {
        "\u2014": "-", "\u2013": "-",
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2026": "...", "\u00a0": " ",
        "\u00bf": "?", "\u00a1": "!",
    }
    for old, new in reemplazos.items():
        texto = texto.replace(old, new)
    return texto


def _cargar_logo_personalizado(config_empresa: dict | None, pdf, size_mm: float = 30):
    """Insertar el logo de la empresa desde base64, o dibujar el logo por defecto."""
    if not config_empresa:
        _dibujar_logo_defecto(pdf, 160, 10, 12)
        return
    b64 = config_empresa.get("logo_base64")
    if b64:
        try:
            from io import BytesIO
            import base64
            img_bytes = base64.b64decode(b64)
            logo_tmp = BytesIO(img_bytes)
            pdf.image(logo_tmp, x=160, y=10, w=size_mm)
            return
        except Exception as e:
            log.warning("Logo personalizado inválido: %s", e)
    _dibujar_logo_defecto(pdf, 160, 10, 12)


def generar_reporte_pdf(datos: dict, output_path: str, config_empresa: dict = None) -> str:
    from fpdf import FPDF
    from pathlib import Path

    if config_empresa is None:
        config_empresa = _DEFAULT_CONFIG_EMPRESA

    FONT_DIR = Path(__file__).resolve().parent / "fonts"
    FONT_PATH = FONT_DIR / "arial.ttf"

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=18)

    # Fuente
    FONT_NAME = "Helvetica"
    if FONT_PATH.exists():
        pdf.add_font("UniFont", "", str(FONT_PATH), uni=True)
        pdf.add_font("UniFont", "B", str(FONT_PATH), uni=True)
        FONT_NAME = "UniFont"

    def w(texto: str) -> str:
        return _sanear_texto(str(texto)) if FONT_NAME == "Helvetica" else str(texto)

    # -----------------------------------------------------------------------
    # Header: logo (esquina superior derecha) + nombre empresa + subtítulo
    # -----------------------------------------------------------------------
    _cargar_logo_personalizado(config_empresa, pdf)

    # Color primario desde config
    hex_color = config_empresa.get("color_primario", "#0f3460")
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)

    pdf.set_font(FONT_NAME, "B", 22)
    pdf.set_text_color(r, g, b)
    pdf.cell(0, 12, w(config_empresa.get("empresa_nombre", "DataExPY")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT_NAME, "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, w("Reporte de conformidad — Extraccion de documentos legales"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Línea separadora
    pdf.set_draw_color(r, g, b)
    pdf.set_line_width(0.6)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # -----------------------------------------------------------------------
    # Tabla: Identificación
    # -----------------------------------------------------------------------
    placeholder = "-"

    def _fila_tabla(label: str, value: str, bold_label: bool = True):
        label = w(label)
        value = w(str(value))
        pdf.set_fill_color(245, 245, 250)
        pdf.set_draw_color(210, 210, 220)
        x0 = 20
        col1_w = 55
        col2_w = 125
        h = 7
        y = pdf.get_y()

        # Fondo
        pdf.rect(x0, y, col1_w + col2_w, h, style="F")
        # Borde izquierdo (color primario)
        pdf.set_fill_color(r, g, b)
        pdf.rect(x0, y, 2, h, style="F")

        pdf.set_text_color(60, 60, 60)
        if bold_label:
            pdf.set_font(FONT_NAME, "B", 9)
        else:
            pdf.set_font(FONT_NAME, "", 9)
        pdf.set_xy(x0 + 5, y + 1.2)
        pdf.cell(col1_w - 5, h - 2, label)

        pdf.set_font(FONT_NAME, "", 9)
        pdf.set_text_color(r, g, b)
        pdf.set_xy(x0 + col1_w + 3, y + 1.2)
        pdf.cell(col2_w - 3, h - 2, value)

        pdf.set_y(y + h)

    pdf.set_font(FONT_NAME, "B", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 7, w("Identificacion"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    _fila_tabla("ID Documento", datos.get("id_documento") or placeholder)
    _fila_tabla("Cliente", datos.get("cliente") or placeholder)
    pdf.ln(3)

    # -----------------------------------------------------------------------
    # Tabla: Datos Contables
    # -----------------------------------------------------------------------
    pdf.set_font(FONT_NAME, "B", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 7, w("Datos contables"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    _fila_tabla("Fecha del documento", datos.get("fecha") or placeholder)
    total_str = f"${datos['total']:,.2f}" if datos.get("total") is not None else placeholder
    _fila_tabla("Total", total_str)
    pdf.ln(3)

    # -----------------------------------------------------------------------
    # Tabla: Auditoría
    # -----------------------------------------------------------------------
    pdf.set_font(FONT_NAME, "B", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 7, w("Auditoria"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    _fila_tabla("Fecha de procesamiento", datos.get("procesado_en", datetime.now().isoformat())[:19])
    _fila_tabla("Procesado por", datos.get("procesado_por", AUDIT_PROCESADO_POR))
    status_val = datos.get("status", "COMPLETADO")
    status_icon = "COMPLETADO" if status_val == "COMPLETADO" else status_val
    _fila_tabla("Estado", status_icon)
    pdf.ln(6)

    # -----------------------------------------------------------------------
    # QR de validación
    # -----------------------------------------------------------------------
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    hash_val = _hash_datos(datos)
    qr_data = f"DATEXPY:{hash_val}"

    try:
        import qrcode
        from io import BytesIO
        qr_img = qrcode.make(qr_data, box_size=2, border=1)
        qr_bytes = BytesIO()
        qr_img.save(qr_bytes, format="PNG")
        qr_bytes.seek(0)
        # Generar nombre temporal
        tmp_qr = Path(output_path).parent / f"_qr_{Path(output_path).stem}.png"
        with open(tmp_qr, "wb") as f:
            f.write(qr_bytes.getvalue())
        pdf.image(str(tmp_qr), x=160, y=pdf.get_y() - 2, w=22)
        tmp_qr.unlink(missing_ok=True)
    except Exception:
        pass

    # Texto del hash al lado del QR
    pdf.set_font(FONT_NAME, "", 7)
    pdf.set_text_color(100, 100, 100)
    pdf.set_xy(20, pdf.get_y() + 1)
    pdf.cell(130, 4, w(f"Hash de validacion: {hash_val}"))
    pdf.set_xy(20, pdf.get_y() + 4)
    pdf.cell(130, 4, w("Escanee el QR para verificar la integridad del documento."))
    pdf.ln(10)

    # -----------------------------------------------------------------------
    # Footer (se repite en cada página automáticamente)
    # -----------------------------------------------------------------------
    pdf.alias_nb_pages()
    pdf.set_y(-15)
    pdf.set_font(FONT_NAME, "", 7)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(0, 4, w(f"Generado: {datetime.now():%Y-%m-%d %H:%M}  |  Pagina {pdf.page_no()}/{{nb}}  |  Powered by DataExPY"), align="C")

    pdf.output(output_path)
    log.info("Reporte PDF generado: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            texto = fh.read()
    else:
        texto = (
            "Cliente: Maria Gomez, Fecha: 2026-06-22, "
            "Total: $500,000, ID: DOC-999"
        )

    try:
        resultado = procesar_documento(texto)
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    except Exception as e:
        log.error("Procesamiento fallido: %s", e)
        sys.exit(1)
