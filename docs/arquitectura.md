# Arquitectura de DataExPY by ChrizDev

> Documento de arquitectura del sistema de extracción inteligente de documentos legales.

---

## 1. Diagrama de flujo

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         USUARIO (Interfaz gráfica)                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  customtkinter Desktop App  (main.py)                                │  │
│  │                                                                      │  │
│  │  ┌──────────────┐   ┌──────────────┐   ┌────────────────────────┐   │  │
│  │  │ Panel        │   │ Panel        │   │ Modal                  │   │  │
│  │  │ Entrada      │──▶│ Resultados   │   │ Búsqueda               │   │  │
│  │  │ · Texto      │   │ · Cards      │   │ · Keywords             │   │  │
│  │  │ · Archivos   │   │ · Exportar   │   │ · Resultados c/contexto│   │  │
│  │  │ · Imágenes   │   │ · Historial  │   │ · Extraer campo        │   │  │
│  │  └──────┬───────┘   └──────┬───────┘   └────────────────────────┘   │  │
│  └─────────┼──────────────────┼──────────────────────────────────────────┘  │
└────────────┼──────────────────┼─────────────────────────────────────────────┘
             │                  │
             ▼                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         CAPA DE NEGOCIO (extractor.py)                      │
│                                                                             │
│  ┌────────────────┐    ┌──────────────┐    ┌──────────────────────┐        │
│  │  extraer()      │    │ procesar_    │    │  transcribir_imagen()│        │
│  │  (texto → JSON) │    │ con_         │    │  (bytes → texto)     │        │
│  │                 │    │ transcripcion│    │                      │        │
│  │  extraer_       │    │ (bytes →     │    │  extraer_campos_     │        │
│  │  imagen()       │    │  datos + txt)│    │  dinamico()          │        │
│  │  (b64 → JSON)   │    └──────┬───────┘    │  (texto+campos→dict) │        │
│  └────────┬────────┘           │            └──────────────────────┘        │
│           │                    │                                            │
│           ▼                    ▼                                            │
│  ┌────────────────────────────────────────────┐                            │
│  │  _validar_esquema() + _normalizar()        │                            │
│  │  (QA interno: tipos, formato, valores)     │                            │
│  └────────────────────────────────────────────┘                            │
│           │                                                                │
│           ▼                                                                │
│  ┌────────────────────────────────────────────┐                            │
│  │  _enriquecer_audit()                       │                            │
│  │  (procesado_por, status, timestamp)        │                            │
│  └────────────────────────────────────────────┘                            │
│           │                                                                │
│           ▼                                                                │
│  ┌────────────────────────────────────────────┐                            │
│  │  guardar()                                  │                            │
│  │  (INSERT en Supabase)                      │                            │
│  └────────────────────────────────────────────┘                            │
│                                                                             │
│  ┌────────────────────────────────────────────┐                            │
│  │  generar_reporte_pdf()                     │                            │
│  │  (fpdf2 → PDF de conformidad)              │                            │
│  └────────────────────────────────────────────┘                            │
│                                                                             │
│  ┌────────────────────────────────────────────┐                            │
│  │  buscar_en_texto()                         │                            │
│  │  (regex → ocurrencias con contexto)        │                            │
│  └────────────────────────────────────────────┘                            │
└────────────────────────────────────────────────────────────────────────────┘
             │                                │
             ▼                                ▼
┌─────────────────────────┐    ┌──────────────────────────────┐
│   API Externa: Groq     │    │   Base de Datos: Supabase    │
│                         │    │                              │
│  ┌───────────────────┐  │    │  ┌────────────────────────┐  │
│  │ GPT-OSS 20B       │  │    │  │ documentos_legales    │  │
│  │ (extracción texto) │  │    │  │ · id (BIGSERIAL)     │  │
│  ├───────────────────┤  │    │  │ · cliente (TEXT)      │  │
│  │ Llama 4 Scout     │  │    │  │ · fecha (DATE)        │  │
│  │ (visión / OCR)    │  │    │  │ · total (NUMERIC)     │  │
│  └───────────────────┘  │    │  │ · id_documento (TEXT) │  │
│                         │    │  │ · transcripcion_      │  │
│  Endpoint:              │    │  │   completa (TEXT)     │  │
│  api.groq.com/openai/v1 │    │  │ · procesado_por (TEXT)│  │
│                         │    │  │ · status (TEXT)       │  │
│  Modelo texto:          │    │  │ · procesado_en        │  │
│  openai/gpt-oss-20b     │    │  │   (TIMESTAMPTZ)       │  │
│                         │    │  │ · created_at          │  │
│  Modelo visión:         │    │  │   (TIMESTAMPTZ)       │  │
│  meta-llama/llama-4-    │    │  └────────────────────────┘  │
│  scout-17b-16e-instruct │    │                              │
│                         │    │  SDK: supabase-py            │
│  SDK: openai-python     │    │                              │
│  (compatible Groq)      │    │  URL + Key via .env          │
│  Key via .env           │    │                              │
└─────────────────────────┘    └──────────────────────────────┘
```

---

## 2. Componentes del sistema

### 2.1 Interfaz de usuario (`main.py`)

| Componente | Tecnología | Propósito |
|---|---|---|
| Ventana principal | `customtkinter.CTk` | Contenedor principal con dos paneles |
| HeaderFrame | `CTkFrame` | Barra superior con logo y título |
| CardFrame | `CTkFrame` | Tarjeta visual para cada campo extraído |
| StatusBar | `CTkFrame` | Barra inferior con indicador de estado |
| BusquedaModal | `CTkToplevel` | Modal de búsqueda con keywords y resultados |
| File dialog | `tkinter.filedialog` | Selector de archivos nativo de Windows |

### 2.2 Motor de extracción (`extractor.py`)

| Función | Entrada | Salida | Modelo IA |
|---|---|---|---|
| `extraer()` | `str` (texto) | `dict` | GPT-OSS 20B |
| `extraer_imagen()` | `str` (base64) + `str` (mime) | `dict` | Llama 4 Scout |
| `transcribir_imagen()` | `bytes` + `str` (mime) | `str` (texto) | Llama 4 Scout |
| `extraer_campos_dinamico()` | `str` (texto) + `list[str]` | `dict` | GPT-OSS 20B |
| `buscar_en_texto()` | `str` + `str` (query) | `list[dict]` | Ninguno (regex) |
| `guardar()` | `dict` | `dict` | — |
| `generar_reporte_pdf()` | `dict` + `str` (path) | `str` (path) | — |

### 2.3 Validación y QA

| Función | Validación |
|---|---|
| `_validar_esquema()` | Verifica que el JSON tenga los 4 campos obligatorios |
| `_normalizar()` | `total` → float, `id_documento` → string |
| `Settings.validate()` | Verifica credenciales y formato de API key |
| `tests/test_extractor.py` | Suite automatizada: tipos, formato fecha, anonimización, búsqueda |

### 2.4 Auditoría

Cada documento procesado incluye:
- `procesado_por`: `{usuario}@{hostname}` (identifica quién y desde dónde)
- `status`: `COMPLETADO` / `ERROR` / `PENDIENTE`
- `procesado_en`: timestamp ISO 8601

---

## 3. Flujo de datos detallado

### 3.1 Documento de texto

```
Texto → extraer() → _validar_esquema() → _normalizar()
→ _enriquecer_audit() → guardar() → Supabase
```

### 3.2 Imagen (foto, captura, escaneo)

```
Imagen → transcribir_imagen() → texto completo
→ extraer() → _validar_esquema() → _normalizar()
→ _enriquecer_audit() → guardar() → Supabase
```

### 3.3 Búsqueda

```
Query → buscar_en_texto(texto, query)
→ lista de {match, antes, despues, posicion, linea}
→ mostrar en BusquedaModal
→ (opcional) extraer_campos_dinamico() → valor → agregar a resultado
```

---

## 4. Seguridad

- **Credenciales**: almacenadas en `.env`, excluidas vía `.gitignore`
- **API key**: validación de formato (`gsk_*`) al arrancar
- **Anonimización**: datos sensibles → `[PROTEGIDO]` antes de guardar
- **Respuesta IA**: `response_format: json_object` evita respuestas malformadas
- **Validación estricta**: esquema JSON verificado antes de persistir

---

## 5. Despliegue

```powershell
# Desarrollo
pip install -r requirements.txt
python main.py

# Tests
python tests/test_extractor.py

# Build .exe
build_exe.bat
# → dist/DataExPY.exe (portátil, ~80 MB)
```

---

## 6. Dependencias

| Librería | Versión | Uso |
|---|---|---|
| `openai` | ≥1.30 | Cliente Groq API |
| `supabase` | ≥2.5 | Conexión a Base de Datos |
| `customtkinter` | ≥5.2 | UI de escritorio |
| `pillow` | ≥10.0 | Procesamiento de imágenes |
| `pypdf` | ≥4.0 | Extracción de PDFs |
| `python-docx` | ≥1.1 | Extracción de Word |
| `fpdf2` | ≥2.8 | Generación de PDF de reporte |
| `python-dotenv` | ≥1.0 | Carga de variables de entorno |
| `pyinstaller` | ≥6.0 | Build de ejecutable (dev) |
