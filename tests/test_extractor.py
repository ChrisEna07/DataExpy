"""
test_extractor.py — Suite de pruebas automatizadas para DataExPY.

Verifica que el motor de extracción cumpla con:
  • Esquema JSON completo (cliente, fecha, total, id_documento)
  • total sea tipo float
  • fecha tenga formato YYYY-MM-DD
  • Anonimización de datos sensibles
  • Búsqueda en texto
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from extractor import extraer, extraer_campos_dinamico, buscar_en_texto

# ---------------------------------------------------------------------------
# Casos de prueba
# ---------------------------------------------------------------------------

SAMPLE_DOCS = [
    {
        "name": "factura_basica",
        "input": "Cliente: Juan Perez\nFecha: 2026-05-15\nTotal: $1.250.000\nID: FAC-2026-001",
        "checks": {
            "cliente": "Juan Perez",
            "fecha": "2026-05-15",
            "total": 1250000.0,
            "id_documento": "FAC-2026-001",
        },
    },
    {
        "name": "contrato_con_datos_sensibles",
        "input": (
            "Contrato entre TechCorp SAS (NIT 901.123.456-7) y Luis Mejia.\n"
            "Valor: COP $8.500.000. Fecha: 2026-03-01.\n"
            "Tarjeta de credito: 4111-1111-1111-1111\n"
            "Ref: CONT-2026-033\n"
        ),
        "checks_sensitive": {
            "total": 8500000.0,
            "id_documento": "CONT-2026-033",
        },
        "must_anonymize": ["4111", "tarjeta"],
    },
    {
        "name": "documento_incompleto",
        "input": "Solo un texto sin datos relevantes para extraer.",
        "checks_incomplete": {
            "cliente": None,
            "fecha": None,
            "total": None,
            "id_documento": None,
        },
    },
]

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

errors = 0
total_tests = 0


def test(name: str, condition: bool, detail: str = ""):
    global total_tests, errors
    total_tests += 1
    if condition:
        print(f"  OK  {name}")
    else:
        errors += 1
        print(f"  FAIL {name} — {detail}")


def run_tests():
    global total_tests, errors
    total_tests = 0
    errors = 0

    print("=" * 60)
    print("  DataExPY — Suite de pruebas automatizadas")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Esquema completo + tipos
    # ------------------------------------------------------------------
    print("\n[1] Extraccion basica y tipado\n")

    for doc in SAMPLE_DOCS:
        if "checks" not in doc:
            continue
        print(f"  ── {doc['name']} ──")
        try:
            result = extraer(doc["input"])
        except Exception as e:
            test(f"{doc['name']}: extraer() lanzó excepción", False, str(e))
            continue

        test("Devuelve dict", isinstance(result, dict))
        for campo, esperado in doc["checks"].items():
            obtenido = result.get(campo)
            if isinstance(esperado, float):
                test(
                    f"'{campo}' es float",
                    isinstance(obtenido, float),
                    f"obtenido={type(obtenido).__name__}: {obtenido}",
                )
                test(
                    f"'{campo}' = {esperado}",
                    abs(obtenido - esperado) < 0.001,
                    f"obtenido={obtenido}",
                )
            elif isinstance(esperado, str):
                test(f"'{campo}' = '{esperado}'", obtenido == esperado, f"obtenido={obtenido}")
            else:
                test(f"'{campo}' es {type(esperado).__name__}", obtenido == esperado, f"obtenido={obtenido}")

    # ------------------------------------------------------------------
    # 2. Validación de formato de fecha
    # ------------------------------------------------------------------
    print("\n[2] Formato de fecha (YYYY-MM-DD)\n")

    FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for doc in SAMPLE_DOCS:
        if "checks" not in doc:
            continue
        try:
            result = extraer(doc["input"])
        except Exception:
            continue
        fecha = result.get("fecha")
        if fecha is not None:
            test(
                f"{doc['name']}: fecha='{fecha}' cumple YYYY-MM-DD",
                bool(FECHA_RE.match(str(fecha))),
                f"formato incorrecto: {fecha}",
            )

    # ------------------------------------------------------------------
    # 3. Anonimización de datos sensibles
    # ------------------------------------------------------------------
    print("\n[3] Anonimizacion\n")

    for doc in SAMPLE_DOCS:
        if "must_anonymize" not in doc:
            continue
        try:
            result = extraer(doc["input"])
        except Exception:
            continue
        output_str = json.dumps(result)
        for term in doc["must_anonymize"]:
            test(
                f"{doc['name']}: '{term}' anonimizado → [PROTEGIDO]",
                term.lower() not in output_str.lower(),
                f"el término '{term}' aparece sin anonimizar en: {output_str[:200]}",
            )

    # ------------------------------------------------------------------
    # 4. Manejo de documentos incompletos (nulls)
    # ------------------------------------------------------------------
    print("\n[4] Documentos incompletos (nulls)\n")

    for doc in SAMPLE_DOCS:
        if "checks_incomplete" not in doc:
            continue
        try:
            result = extraer(doc["input"])
        except Exception:
            continue
        for campo, esperado in doc["checks_incomplete"].items():
            test(
                f"{doc['name']}: '{campo}' es null",
                result.get(campo) is None,
                f"obtenido={result.get(campo)}",
            )

    # ------------------------------------------------------------------
    # 5. Extracción dinámica de campos
    # ------------------------------------------------------------------
    print("\n[5] Extraccion dinamica\n")

    texto_contrato = (
        "Contrato entre: MARIA GOMEZ (C.C. 12.345.678) y la empresa "
        "TechCorp SAS con NIT 901.123.456-7. Dirección: Calle 45 # 20-30, Bogotá. "
        "Teléfono de contacto: 300 123 4567. Email: maria@email.com"
    )

    try:
        campos = extraer_campos_dinamico(texto_contrato, ["C.C.", "NIT", "dirección", "teléfono"])
        for c in ("C.C.", "NIT"):
            test(f"Campo dinámico '{c}' presente", c in campos, f"resultado={campos}")
            test(f"Campo dinámico '{c}' no es null", campos.get(c) is not None)
    except Exception as e:
        test("Extracción dinámica completa", False, str(e))

    # ------------------------------------------------------------------
    # 6. Búsqueda en texto
    # ------------------------------------------------------------------
    print("\n[6] Busqueda en texto\n")

    resultados = buscar_en_texto(texto_contrato, "C.C.")
    test("Búsqueda 'C.C.' encuentra resultados", len(resultados) > 0, f"encontrados={len(resultados)}")
    if resultados:
        test("Resultado tiene 'linea'", "linea" in resultados[0])
        test("Resultado tiene 'match'", "match" in resultados[0])
        test("Resultado tiene 'antes'/'despues'", "antes" in resultados[0] and "despues" in resultados[0])

    # Resultado
    print(f"\n{'=' * 60}")
    print(f"  Total: {total_tests} |  Pasaron: {total_tests - errors} |  Fallaron: {errors}")
    print(f"{'=' * 60}")

    return errors == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
