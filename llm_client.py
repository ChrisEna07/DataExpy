import os
import json
import time
import logging
from typing import Optional
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

log = logging.getLogger("llm_client")

# ---------------------------------------------------------------------------
# Circuit Breaker para manejo de errores 429
# ---------------------------------------------------------------------------

class CircuitBreakerOpen(Exception):
    pass


@dataclass
class CircuitBreaker:
    name: str = "default"
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    _failures: int = 0
    _last_failure_time: float = 0.0
    _state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN

    def call(self, fn, *args, **kwargs):
        if self._state == "OPEN":
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = "HALF_OPEN"
                log.info("CircuitBreaker[%s]: CLOSED -> HALF_OPEN", self.name)
            else:
                raise CircuitBreakerOpen(
                    f"CircuitBreaker[{self.name}] OPEN. "
                    "El sistema está procesando alta carga, tus resultados estarán listos en unos momentos."
                )

        try:
            result = fn(*args, **kwargs)
            if self._state == "HALF_OPEN":
                self._state = "CLOSED"
                self._failures = 0
                log.info("CircuitBreaker[%s]: HALF_OPEN -> CLOSED (recuperado)", self.name)
            return result
        except Exception as e:
            if _es_error_429(e):
                self._failures += 1
                self._last_failure_time = time.time()
                if self._failures >= self.failure_threshold:
                    self._state = "OPEN"
                    log.warning("CircuitBreaker[%s]: -> OPEN (%d fallos 429)", self.name, self._failures)
            raise


# ---------------------------------------------------------------------------
# Clientes LLM
# ---------------------------------------------------------------------------

GROQ_CLIENT = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

_GEMINI_CLIENT = None


def _get_gemini():
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is None:
        try:
            import google.generativeai as genai
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                _GEMINI_CLIENT = genai
            else:
                _GEMINI_CLIENT = False
        except Exception:
            _GEMINI_CLIENT = False
    return _GEMINI_CLIENT if _GEMINI_CLIENT else None


def _es_error_429(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too many requests" in msg or "rate limit" in msg


# ---------------------------------------------------------------------------
# Estrategia: decidir qué modelo usar
# ---------------------------------------------------------------------------

def obtener_respuesta_llm(
    system_prompt: str,
    user_prompt: str,
    es_largo: bool = False,
    response_format: Optional[dict] = None,
    temperatura: float = 0.0,
    max_tokens: int = 1024,
    model_override: Optional[str] = None,
) -> str:
    """
    Patrón Estrategia: decide qué proveedor/modelo usar según la entrada.
    - es_largo=True -> Gemini 1.5 Pro (contexto masivo)
    - model_override -> fuerza un modelo específico en Groq
    - default -> Groq con modelo por defecto
    """
    gemini = _get_gemini()

    if es_largo and gemini:
        try:
            log.info("Usando Gemini 1.5 Pro (documento largo)")
            model = gemini.GenerativeModel("gemini-1.5-pro")
            full_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
            response = model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            log.warning("Gemini falló, degradando a Groq: %s", e)

    # Groq (default)
    model = model_override or "openai/gpt-oss-20b"
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperatura,
        "max_tokens": max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format

    response = GROQ_CLIENT.chat.completions.create(**kwargs)
    return response.choices[0].message.content


def obtener_respuesta_vision(
    image_bytes: bytes,
    mime_type: str,
    system_prompt: str,
    text_prompt: str = "Analiza la imagen.",
    model_override: Optional[str] = None,
    max_tokens: int = 4096,
) -> str:
    """Envía una imagen a un modelo de visión."""
    import base64
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    model = model_override or "meta-llama/llama-4-scout-17b-16e-instruct"

    response = GROQ_CLIENT.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                ],
            },
        ],
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


# Circuit breakers compartidos
CIRCUIT_BREAKER_TEXTO = CircuitBreaker(name="texto")
CIRCUIT_BREAKER_VISION = CircuitBreaker(name="vision")
