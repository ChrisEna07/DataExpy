<div align="center">

```
██████╗  █████╗ ████████╗ █████╗ ██████╗ ██╗  ██╗██████╗ ██╗   ██╗
██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗██╔════╗╚██╗██╔╝██╔══██╗╚██╗ ██╔╝
██║  ██║███████║   ██║   ███████║██████╔╝ ╚███╔╝ ██████╔╝ ╚████╔╝ 
██║  ██║██╔══██║   ██║   ██╔══██║██╔════╗ ██╔██╗ ██╔═══╝   ╚██╔╝  
██████╔╝██║  ██║   ██║   ██║  ██║██████╔╝██╔╝ ██╗██║        ██║   
╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝        ╚═╝

```
 ██████╗██╗  ██╗██████╗ ██╗███████╗██████╗ ███████╗██╗   ██╗
██╔════╝██║  ██║██╔══██╗██║╚══███╔╝██╔══██╗██╔════╝██║   ██║
██║     ███████║██████╔╝██║  ███╔╝ ██║  ██║█████╗  ██║   ██║
██║     ██╔══██║██╔══██╗██║ ███╔╝  ██║  ██║██╔══╝  ╚██╗ ██╔╝
╚██████╗██║  ██║██║  ██║██║███████╗██████╔╝███████╗ ╚████╔╝ 
 ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝╚═════╝ ╚══════╝  ╚═══╝  

```

**Extracción inteligente de documentos legales con IA · OCR · Búsqueda inteligente**

[![Groq](https://img.shields.io/badge/Groq-LLM_+_Visión-FF6600?style=flat-square&logo=groq)](https://groq.com)
[![Supabase](https://img.shields.io/badge/Supabase-Database-3ECF8E?style=flat-square&logo=supabase)](https://supabase.com)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python)](https://python.org)
[![Licencia](https://img.shields.io/badge/Licencia-MIT-green?style=flat-square)](LICENSE)
[![Hecho por](https://img.shields.io/badge/by-ChrizDev-8A2BE2?style=flat-square)](https://github.com/ChrizDev)

---

**Sube un contrato, factura o recibo — la IA lo transcribe, extrae los datos y te deja buscar cualquier campo.**

Fotos de documentos, PDFs escaneados, capturas de pantalla... o texto plano. Sin plantillas, sin reglas manuales.

</div>

---

## ✨ Funcionalidades

| Característica | Descripción |
|---|---|
| **🤖 IA Legal** | Groq (GPT-OSS 20B) + Gemini 1.5 Pro (documentos largos) + modelo de visión (Llama 4 Scout) |
| **⚡ Cliente LLM agnóstico** | `llm_client.py` — estrategia automática: Groq para velocidad, Gemini para contextos masivos (>50K chars) |
| **🛡️ Circuit Breaker** | Detección de errores 429 (rate limit): 3 fallos → pausa 30s con mensaje amigable al usuario |
| **📸 OCR con IA** | Escanea fotos de documentos, capturas de pantalla, JPG/PNG — la IA transcribe todo |
| **📂 Múltiples formatos** | PDF (texto + escaneados), DOCX, TXT, **JPG, JPEG, PNG** |
| **🔄 OCR automático en PDFs escaneados** | Si un PDF no tiene texto extraíble (<10 chars), lo convierte a imagen y aplica OCR vía IA automáticamente |
| **📄 Transcripción completa** | Botón "Ver transcripción" con el texto íntegro extraído del documento |
| **👁️ Vista previa original** | Botón "Ver original" modal con el documento completo en su estado original |
| **🔍 Buscador inteligente** | Modal con keywords sugeridas + búsqueda libre + resultados con contexto |
| **🎯 Extracción dinámica** | Busca C.C., NIT, dirección, teléfono, email, o cualquier campo y extrae su valor con IA |
| **🟢 Status badge + barra de progreso** | Indicador visual del estado del proceso y barra animada durante extracción |
| **🔔 Toast notifications** | Notificaciones animadas no bloqueantes en esquina superior derecha |
| **⚡ Cola asíncrona (queue)** | Comunicación hilo→UI vía `queue.Queue` + `_check_queue` cada 100ms — elimina el "Dejó de responder" de Windows |
| **🚪 Confirmación de salida** | Diálogo "¿Seguro que quieres salir?" si hay documentos procesados o extracción en curso |
| **🔒 Anonimización** | Datos sensibles (tarjetas, contraseñas, direcciones) → `[PROTEGIDO]` |
| **💾 Persistencia** | Los datos viajan directo a Supabase — listos para analítica o RAG |
| **📤 Exportación** | CSV, JSON o **PDF profesional** con logo, QR de validación, tabla de auditoría y pie de página |
| **📋 Historial** | Todas las extracciones se acumulan en sesión |
| **📝 Auditoría estructurada** | `auditoria.log` con timestamp, usuario (hostname), acción y estado; campo `log_detalles` en Supabase |
| **🎨 Interfaz nativa** | App de escritorio Windows con dark mode, sin depender de un navegador |
| **📦 Ejecutable portátil** | Compila a un solo `.exe` — sin Python, sin dependencias |

---

## 🧠 Arquitectura

```
┌──────────────────────────────────────────────────────────────────┐
│                       DataExPY Desktop App                        │
│  ┌──────────────────┐          ┌────────────────────────────┐    │
│  │  Entrada          │          │  Resultados                │    │
│  │  · Texto          │          │  · Cliente  · Fecha       │    │
│  │  · PDF/DOCX/TXT   │  ──────→ │  · Total    · ID Doc      │    │
│  │  · JPG/JPEG/PNG   │   Groq   │  · 📄 Transcripción      │    │
│  │  ↳ vista previa   │          │  · 🔍 Buscador + Keywords│    │
│  └────────┬─────────┘          │  · Export CSV/JSON         │    │
│           │                    └──────────┬─────────────────┘    │
│           ▼                                       │              │
│  ┌──────────────────┐                            │              │
│  │  OCR con IA      │                            │              │
│  │  (Visión → Texto)│                            │              │
│  └──────────────────┘                            │              │
└──────────────────────────────────────────────────┼──────────────┘
                                                   ▼
                                         ┌──────────────────┐
                                         │   Supabase DB     │
                                         │ documentos_legales│
                                         │ + transcripción   │
                                         └──────────────────┘
```

**Flujo de datos:**
1. Cargas texto, un PDF/DOCX o una **imagen** (foto de documento, captura de pantalla)
2. Si el PDF **no tiene texto extraíble** (<10 chars) → se renderiza a imagen con PyMuPDF y se aplica **OCR automático** (máx. 3 páginas, con pausa de 2s entre páginas para evitar rate limit)
3. Si es imagen → **OCR con IA** (Groq Visión) la transcribe a texto completo
4. El texto se envía al **cliente LLM agnóstico** (`llm_client.py`): Groq para documentos normales, Gemini 1.5 Pro si >50K caracteres
5. Los datos se **validan, normalizan y guardan** en Supabase (junto con la transcripción y `log_detalles` de auditoría)
6. Toda la comunicación hilo→UI pasa por una **cola asíncrona** (`queue.Queue`) con `_check_queue` cada 100ms, eliminando el "Dejó de responder"
7. La UI muestra resultados + botones para **ver transcripción**, **ver original** y **buscar dentro del documento**
8. El **buscador inteligente** permite buscar cualquier palabra clave (C.C., NIT, dirección, etc.) con resultados contextuales y extracción dinámica vía IA

---

## 🚀 Instalación

### Requisitos mínimos

- Windows 10 / 11 (64 bits)
- 500 MB de espacio libre
- Conexión a Internet

### Opción 1: Ejecutable portátil (recomendado)

```powershell
# 1. Descarga DataExPY.exe de la última release
# 2. Crea un archivo .env en la misma carpeta:

GROQ_API_KEY="gsk_tu_key_aqui"
SUPABASE_URL="https://tu-proyecto.supabase.co"
SUPABASE_KEY="sb_secret_tu_key_aqui"

# 3. Ejecuta DataExPY.exe
```

### Opción 2: Desde el código fuente

```powershell
# Clona el repositorio
git clone https://github.com/ChrizDev/DataExPY.git
cd DataExPY

# Crea tu archivo de configuración
copy .env.example .env
# Edita .env con tus credenciales

# Instala dependencias
pip install -r requirements.txt

# Ejecuta
python main.py
```

### Opción 3: Construir tu propio .exe

```powershell
pip install pyinstaller
build_exe.bat
# → El ejecutable estará en dist/DataExPY.exe
```

---

## ⚙️ Configuración

### Variables de entorno (`.env`)

| Variable | Descripción | Obtenla en |
|---|---|---|
| `GROQ_API_KEY` | API key de Groq (formato `gsk_...`) | [console.groq.com/keys](https://console.groq.com/keys) |
| `SUPABASE_URL` | URL de tu proyecto Supabase | [supabase.com](https://supabase.com) |
| `SUPABASE_KEY` | Service role key de Supabase | Panel → Settings → API |
| `GEMINI_API_KEY` | Opcional — para documentos largos (>50K chars) | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | Opcional |

> **⚠️ Seguridad:** El archivo `.env` está en `.gitignore`. Nunca subas credenciales al repositorio.

### Estructura de la tabla en Supabase

```sql
CREATE TABLE documentos_legales (
  id BIGSERIAL PRIMARY KEY,
  cliente TEXT,
  fecha DATE,
  total NUMERIC(12,2),
  id_documento TEXT,
  transcripcion_completa TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 🎯 Uso

### 1. Cargar un documento

| Tipo | Cómo |
|---|---|
| **Texto** | Pégalo directamente en el área de texto |
| **PDF / DOCX / TXT** | Haz clic en "Seleccionar archivo" |
| **Imagen** (JPG/PNG) | Selecciona el archivo — se muestra una **vista previa** |

### 2. Extraer datos

3. Presiona **"Extraer datos"**
4. Para imágenes: la IA primero transcribe el documento (OCR), luego extrae los campos
5. Los campos aparecen en las tarjetas de la derecha

### 3. Explorar el documento

| Botón | Qué hace |
|---|---|
| **📄 Ver transcripción** | Abre el texto completo extraído del documento |
| **👁️ Ver original** | Modal con el documento completo en su estado original |
| **🔍 Buscar en documento** | Abre el buscador inteligente con keywords |

### 4. Buscar y extraer campos personalizados

```
┌─────────────────────────────────────────┐
│  [Escribe lo que buscas...]  [Buscar]   │
│                                         │
│  Palabras clave sugeridas:              │
│  [C.C.] [NIT] [Dirección] [Teléfono]   │
│  [Email] [Cliente] [Total] [Banco]     │
│  [Factura] [Contrato] [Cédula] ...     │
│                                         │
│  Resultados:                            │
│  ┌─────────────────────────────────┐   │
│  │  3 ocurrencia(s) de 'C.C.':   │   │
│  │  ── Línea 12 ──              │   │
│  │  ...[C.C. 1234567890]...     │   │
│  │  ── Línea 45 ──              │   │
│  │  ...[C.C. 9876543210]...     │   │
│  └─────────────────────────────────┘   │
│                                         │
│  [➕ Extraer como campo personalizado]  │
└─────────────────────────────────────────┘
```

- **Haz clic en cualquier keyword** → auto-busca
- **Escribe lo que quieras** (cédula, dirección, banco, etc.)
- **"Extraer como campo"** → la IA captura el valor y lo agrega al resultado

### 5. Exportar

6. **CSV** → datos estructurados
7. **JSON** → datos + transcripción completa
8. **PDF** → reporte de conformidad profesional con:
   - Logo corporativo
   - QR de validación (hash SHA-256)
   - Tablas con datos agrupados (Identificación, Contables, Auditoría)
   - Pie de página automático con fecha y numeración

---

## 🔬 Ejemplo

### Entrada (imagen escaneada / texto)

```
REPÚBLICA DE COLOMBIA
CÉDULA DE CIUDADANÍA
Número: 1.234.567.890
Apellidos: GÓMEZ RESTREPO
Nombres: MARÍA FERNANDA
Fecha de expedición: 15-ENE-2020
```

### Salida

```json
{
  "cliente": "MARÍA FERNANDA GÓMEZ RESTREPO",
  "fecha": "2020-01-15",
  "total": null,
  "id_documento": "1.234.567.890",
  "transcripcion_completa": "REPÚBLICA DE COLOMBIA\nCÉDULA DE CIUDADANÍA\n..."
}
```

### Búsqueda

```
Buscar: "C.C." → 2 ocurrencias
  ── Línea 12 ──  ...[C.C. 1234567890]...
  ── Línea 45 ──  ...[C.C. 9876543210]...

✅ Campo 'C.C.' extraído: "1.234.567.890"
```

---

## 🛡️ Seguridad

- **Las credenciales nunca están en el código fuente**
- `Settings.validate()` verifica formato de keys al arrancar
- Anonimización automática de datos sensibles (`[PROTEGIDO]`)
- `response_format: json_object` fuerza a la IA a responder solo JSON
- Validación estricta del esquema devuelto antes de guardar
- **Circuit Breaker**: 3 errores 429 consecutivos → pausa 30s con mensaje al usuario
- **Auditoría estructurada**: archivo `auditoria.log` + campo `log_detalles` en cada registro de Supabase
- **Cola asíncrona**: toda actualización de UI desde hilos secundarios pasa por `queue.Queue` — sin race conditions

---

## 📦 Stack tecnológico

| Tecnología | Propósito |
|---|---|
| [Groq](https://groq.com) | Inferencia ultrarrápida — GPT-OSS 20B (texto) + Llama 4 Scout (visión/OCR) |
| [Gemini](https://deepmind.google/gemini/) | Fallback para documentos masivos (>50K chars) via `llm_client.py` |
| [Supabase](https://supabase.com) | Base de datos PostgreSQL + API REST |
| [customtkinter](https://github.com/TomSchimansky/CustomTkinter) | UI nativa moderna con dark mode |
| [Pillow](https://python-pillow.org) | Procesamiento y preview de imágenes |
| [PyMuPDF](https://pymupdf.readthedocs.io/) | Renderizado de PDF escaneados → imágenes para OCR |
| [fpdf2](https://pyfpdf.github.io/fpdf2/) | Generación de reportes PDF con tablas y QR |
| [qrcode](https://github.com/lincolnloop/python-qrcode) | QR de validación hash para integridad de documentos |
| [PyInstaller](https://pyinstaller.org) | Empaquetado en ejecutable portátil |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Gestión segura de configuración |

---

## 🧩 API (uso programático)

```python
from extractor import (
    extraer,                    # Texto → campos
    extraer_imagen,             # Base64 → campos
    transcribir_imagen,         # Bytes → texto completo
    extraer_campos_dinamico,    # Texto + lista de campos → valores
    buscar_en_texto,            # Texto + query → coincidencias con contexto
    procesar_con_transcripcion, # Bytes → campos + transcripción
)

# Texto → campos estructurados
datos = extraer("Cliente: Juan Pérez, Total: $1.500.000, ID: FAC-001")

# Imagen → transcripción completa
texto = transcribir_imagen(file_bytes, "image/jpeg")

# Búsqueda dentro del texto
resultados = buscar_en_texto(texto, "C.C.", contexto=60)

# Extraer campo arbitrario
campos = extraer_campos_dinamico(texto, ["C.C.", "dirección", "teléfono"])
```

---

## 🧪 Tests

```powershell
python -c "
from extractor import extraer
texto_prueba = 'Cliente: Maria Gomez, Fecha: 2026-06-22, Total: 500000, ID: DOC-999'
resultado = extraer(texto_prueba)
print(resultado)
"
```

---

## 📄 Licencia

**MIT** — Haz lo que quieras, pero da crédito.

---

<div align="center">

**DataExPY by ChrizDev** · Transformando documentos legales con inteligencia artificial

⭐ Si te es útil, regálame una estrella. Reporta issues con cariño.

</div>
