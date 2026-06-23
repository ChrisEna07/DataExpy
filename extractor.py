import os
import re
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import base64

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
# Extracción desde imagen (visión)
# ---------------------------------------------------------------------------

def extraer_imagen(base64_image: str, mime_type: str = "image/jpeg") -> dict:
    _init()
    last_error = None
    model = _settings.groq_vision_model

    for attempt in range(1, _settings.max_retries + 1):
        try:
            log.info("Extracción visión — intento %d/%d (%s)", attempt, _settings.max_retries, model)
            response = _ai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": VISION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extrae los datos de la imagen en formato JSON.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=1024,
            )
            raw = response.choices[0].message.content
            datos = json.loads(raw)
            _validar_esquema(datos)
            _normalizar(datos)
            log.info("Extracción visión exitosa: %s", datos)
            return datos

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
    guardar(datos)
    return datos


# ---------------------------------------------------------------------------
# Transcripción completa (OCR con IA)
# ---------------------------------------------------------------------------

def transcribir_imagen(file_bytes: bytes, mime_type: str) -> str:
    _init()
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    model = _settings.groq_vision_model
    last_error = None

    for attempt in range(1, _settings.max_retries + 1):
        try:
            log.info("Transcripción — intento %d/%d (%s)", attempt, _settings.max_retries, model)
            response = _ai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": TRANSCRIBE_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Transcribe todo el texto del documento.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{b64}"
                                },
                            },
                        ],
                    },
                ],
                temperature=0.0,
                max_tokens=4096,
            )
            texto = response.choices[0].message.content.strip()
            if not texto:
                raise ValueError("Transcripción vacía")
            log.info("Transcripción exitosa (%d caracteres)", len(texto))
            return texto

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
            response = _ai_client.chat.completions.create(
                model=_settings.groq_model,
                messages=[
                    {"role": "system", "content": "Eres un extractor de datos. Responde solo con JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            datos = json.loads(response.choices[0].message.content)
            log.info("Extracción dinámica exitosa: %s", datos)
            return datos

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
