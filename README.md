<div align="center">

```
██████╗  █████╗ ████████╗ █████╗ ██████╗ ██╗  ██╗██████╗ ██╗   ██╗
██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗██╔══ ╗╚██╗██╔╝██╔══██╗╚██╗ ██╔╝
██║  ██║███████║   ██║   ███████║██████╔╝ ╚███╔╝ ██████╔╝ ╚████╔╝ 
██║  ██║██╔══██║   ██║   ██╔══██║██╔══  ╗ ██╔██╗ ██╔═══╝   ╚██╔╝  
██████╔╝██║  ██║   ██║   ██║  ██║██████╔╝██╔╝ ██╗██║        ██║   
╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝        ╚═╝

```

**Extracción inteligente de datos en documentos legales · IA + Supabase**

[![Groq](https://img.shields.io/badge/Groq-Llama_3-FF6600?style=flat-square&logo=groq)](https://groq.com)
[![Supabase](https://img.shields.io/badge/Supabase-Database-3ECF8E?style=flat-square&logo=supabase)](https://supabase.com)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python)](https://python.org)
[![Licencia](https://img.shields.io/badge/Licencia-MIT-green?style=flat-square)](LICENSE)
[![Hecho por](https://img.shields.io/badge/by-ChrizDev-8A2BE2?style=flat-square)](https://github.com/ChrizDev)

---

**Transforma contratos, facturas y recibos en datos estructurados al instante.**
Sin OCR, sin plantillas, sin reglas manuales. Solo pega el texto y la IA extrae: cliente, fecha, total e ID del documento.

</div>

---

## ✨ Funcionalidades

| Característica | Descripción |
|---|---|
| **🤖 IA Legal** | Groq (GPT-OSS 20B) entrenado vía prompt para extraer datos legales con precisión |
| **📂 Múltiples formatos** | PDF, DOCX, TXT — arrastra o selecciona, el texto se extrae automáticamente |
| **🔒 Anonimización** | Datos sensibles (tarjetas, contraseñas, direcciones) → `[PROTEGIDO]` |
| **💾 Persistencia** | Los datos viajan directo a Supabase — listos para analítica o RAG |
| **📤 Exportación** | Descarga los resultados en CSV o JSON con un clic |
| **📋 Historial** | Todas las extracciones se acumulan en sesión |
| **🎨 Interfaz nativa** | App de escritorio Windows con dark mode, sin depender de un navegador |
| **📦 Ejecutable portátil** | Compila a un solo `.exe` — sin Python, sin dependencias |

---

## 🧠 Arquitectura

```
┌────────────────────────────────────────────────────────────┐
│                    DataExPY Desktop App                     │
│  ┌──────────────┐          ┌──────────────────────────┐    │
│  │  Entrada      │          │  Resultados               │    │
│  │  · Texto      │          │  · Cliente  · Fecha      │    │
│  │  · PDF/DOCX   │  ──────→ │  · Total    · ID Doc     │    │
│  │  · TXT        │   Groq   │  · Export CSV/JSON       │    │
│  └──────────────┘          └──────────┬───────────────┘    │
└───────────────────────────────────────┼────────────────────┘
                                        │
                              ┌─────────▼─────────┐
                              │   Supabase DB      │
                              │  documentos_legales│
                              └───────────────────┘
```

**Flujo de datos:**
1. Cargas un documento o pegas texto
2. Se envía a **Groq** con un prompt especializado en datos legales
3. La IA devuelve un JSON estructurado con los 4 campos
4. Los datos se **validan, normalizan y guardan** en Supabase
5. La UI muestra los resultados y permite exportarlos

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
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 🎯 Uso

### Cargar un documento

1. **Pega texto** directamente en el área de texto, o
2. Haz clic en **"Seleccionar archivo"** y elige un PDF, DOCX o TXT

### Extraer datos

3. Presiona **"Extraer datos"**
4. La IA procesa el documento en segundos
5. Los campos aparecen en las tarjetas de la derecha

### Exportar

6. Usa los botones **CSV** o **JSON** para descargar los resultados
7. El historial acumula todas las extracciones de la sesión

---

## 🔬 Ejemplo

### Entrada

```
CONTRATO DE PRESTACIÓN DE SERVICIOS

Entre: CARLOS ANDRÉS RAMÍREZ, identificado con cédula...
Fecha del contrato: 15 de marzo de 2026
Valor total del servicio: $2.850.000 COP
Número de referencia: CONT-2026-0891
...
```

### Salida

```json
{
  "cliente": "CARLOS ANDRÉS RAMÍREZ",
  "fecha": "2026-03-15",
  "total": 2850000.0,
  "id_documento": "CONT-2026-0891"
}
```

---

## 🛡️ Seguridad

- **Las credenciales nunca están en el código fuente**
- `Settings.validate()` verifica formato de keys al arrancar
- Anonimización automática de datos sensibles (`[PROTEGIDO]`)
- `response_format: json_object` fuerza a la IA a responder solo JSON
- Validación estricta del esquema devuelto antes de guardar

---

## 📦 Stack tecnológico

| Tecnología | Propósito |
|---|---|
| [Groq](https://groq.com) | Inferencia ultrarrápida en LPU — modelo GPT-OSS 20B |
| [Supabase](https://supabase.com) | Base de datos PostgreSQL + API REST |
| [customtkinter](https://github.com/TomSchimansky/CustomTkinter) | UI nativa moderna con dark mode |
| [PyInstaller](https://pyinstaller.org) | Empaquetado en ejecutable portátil |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Gestión segura de configuración |

---

## 🧩 API (uso programático)

```python
from extractor import extraer, guardar, procesar_documento

# Extraer datos de un texto
datos = extraer("Cliente: Juan Pérez, Total: $1.500.000, ID: FAC-001")
print(datos)
# → {"cliente": "Juan Pérez", "total": 1500000.0, ...}

# Guardar en Supabase
guardar(datos)

# O todo en uno
procesar_documento("...texto del documento...")
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

**DataExPY by ChrizDev** · Transformando datos legales con inteligencia artificial

⭐ Si te es útil, regálame una estrella. Reporta issues con cariño.

</div>
