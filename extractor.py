import os
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client

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


# ---------------------------------------------------------------------------
# Schema de salida esperado
# ---------------------------------------------------------------------------

EXPECTED_FIELDS = {"cliente", "fecha", "total", "id_documento"}


# ---------------------------------------------------------------------------
# Cliente global (inicializado bajo demanda)
# ---------------------------------------------------------------------------

_settings: Optional[Settings] = None
_ai_client: Optional[OpenAI] = None
_db_client: Optional[Client] = None


def _init() -> None:
    global _settings, _ai_client, _db_client
    if _settings is not None:
        return
    _settings = Settings()
    _settings.validate()
    _ai_client = OpenAI(api_key=_settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    _db_client = create_client(_settings.supabase_url, _settings.supabase_key)
    log.info("Clientes inicializados correctamente")


# ---------------------------------------------------------------------------
# Extracción con IA + reintentos
# ---------------------------------------------------------------------------

def extraer(texto: str) -> dict:
    _init()
    last_error = None

    for attempt in range(1, _settings.max_retries + 1):
        try:
            log.info("Extracción — intento %d/%d", attempt, _settings.max_retries)
            response = _ai_client.chat.completions.create(
                model=_settings.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": texto},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            raw = response.choices[0].message.content
            datos = json.loads(raw)
            _validar_esquema(datos)
            _normalizar(datos)
            log.info("Extracción exitosa: %s", datos)
            return datos

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

def guardar(datos: dict) -> dict:
    _init()
    try:
        resultado = _db_client.table("documentos_legales").insert(datos).execute()
        log.info("Insertado en Supabase: %s", datos.get("id_documento"))
        return resultado.data[0] if resultado.data else datos
    except Exception as e:
        log.error("Error al insertar en Supabase: %s", e)
        raise


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def procesar_documento(texto: str) -> dict:
    datos = extraer(texto)
    guardar(datos)
    return datos


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
