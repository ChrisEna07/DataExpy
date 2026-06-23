# Manual de Usuario — DataExPY by ChrizDev

> Extracción inteligente de datos en documentos legales con IA.

---

## 1. Requisitos

- Windows 10 / 11 (64 bits)
- 500 MB de espacio libre
- Conexión a Internet
- Credenciales de API (Groq + Supabase) en archivo `.env`

---

## 2. Instalación

### Opción A: Ejecutable portátil

1. Descarga `DataExPY.exe` desde la última release
2. Crea un archivo `.env` en la misma carpeta del `.exe`:

```env
GROQ_API_KEY="gsk_tu_key_aqui"
SUPABASE_URL="https://tu-proyecto.supabase.co"
SUPABASE_KEY="sb_secret_tu_key_aqui"
```

3. Ejecuta `DataExPY.exe`

### Opción B: Desde código fuente

```powershell
pip install -r requirements.txt
python main.py
```

---

## 3. Interfaz

```
┌──────────────────────────────────────────────────────────────┐
│  ⚖️  DataExPY  by ChrizDev                                   │
│               Extracción inteligente de documentos legales    │
├──────────────────────────┬───────────────────────────────────┤
│  📄 Entrada              │  📋 Resultados                    │
│  ┌────────────────────┐  │  ┌──────┐ ┌──────┐ ┌──────┐      │
│  │ Pega texto aquí...  │  │  👤     │ 📅    │ 💰    │      │
│  └────────────────────┘  │  │ Juan  │2026..│$1.5M │      │
│  [📎 Seleccionar] [🔍]   │  └──────┘ └──────┘ └──────┘      │
│  🖼️ preview (imágenes)   │  [CSV] [JSON] [PDF]               │
│                          │  [📄 Transcripción] [🔍 Buscar]   │
│                          │  📚 Historial                     │
├──────────────────────────┴───────────────────────────────────┤
│  ✅ Listo                                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Cómo usar

### 4.1 Cargar un documento

| Formato | Método |
|---|---|
| Texto plano | Pega directamente en el área de texto |
| PDF / DOCX / TXT | Botón "Seleccionar archivo" |
| Imagen (JPG/PNG) | Botón "Seleccionar archivo" — se muestra preview |

### 4.2 Extraer datos

1. Presiona **"Extraer datos"**
2. La IA procesa el documento (si es imagen, primero la transcribe con OCR)
3. Los campos aparecen en las tarjetas de resultados:
   - **Cliente** — nombre completo
   - **Fecha** — formato AAAA-MM-DD
   - **Total** — valor numérico sin símbolos
   - **ID Documento** — número de referencia

### 4.3 Ver transcripción

- Botón **"Ver transcripción"** → ventana con el texto completo extraído del documento
- Útil para verificar que la IA leyó correctamente todo el contenido

### 4.4 Buscar en el documento

- Botón **"Buscar en documento"** → abre el buscador inteligente

**Funcionalidades del buscador:**
- **Barra de búsqueda**: escribe cualquier término
- **Keywords sugeridas**: haz clic en C.C., NIT, Dirección, Teléfono, Email, etc.
- **Resultados**: muestra cada coincidencia con contexto (texto antes/después) y número de línea
- **"Extraer como campo personalizado"**: toma el término buscado y usa IA para extraer su valor del documento completo. El campo se agrega al resultado actual.

### 4.5 Exportar resultados

| Botón | Formato | Contenido |
|---|---|---|
| **CSV** | `.csv` | Campos estructurados (cliente, fecha, total, id) |
| **JSON** | `.json` | Campos + transcripción completa + datos de auditoría |
| **PDF** | `.pdf` | Reporte de conformidad profesional con resumen |

---

## 5. Ejemplo completo

**Entrada (texto):**
```
CONTRATO DE PRESTACIÓN DE SERVICIOS
Entre: CARLOS ANDRÉS RAMÍREZ
Fecha: 15 de marzo de 2026
Valor: $2.850.000 COP
Referencia: CONT-2026-0891
```

**Resultado:**
| Campo | Valor |
|---|---|
| Cliente | CARLOS ANDRÉS RAMÍREZ |
| Fecha | 2026-03-15 |
| Total | 2850000.0 |
| ID Documento | CONT-2026-0891 |

**Reporte PDF generado:**
```
┌─────────────────────────────────────┐
│  DataExPY by ChrizDev               │
│  Reporte de conformidad             │
│                                     │
│  Fecha de procesamiento: 2026-06-23 │
│  ID Documento: CONT-2026-0891       │
│  Cliente: CARLOS ANDRÉS RAMÍREZ     │
│  Total: $2,850,000.00               │
│  Procesado por: usuario@PC-01       │
│  Estado: COMPLETADO                 │
└─────────────────────────────────────┘
```

---

## 6. Solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| "Configuración incompleta" | Falta `.env` o credenciales incorrectas | Verificar `.env` en la misma carpeta |
| "Extracción fallida" | API key inválida o modelo no disponible | Verificar `GROQ_API_KEY` en https://console.groq.com |
| "Error al insertar en Supabase" | Credenciales de BD incorrectas | Verificar `SUPABASE_URL` y `SUPABASE_KEY` |
| La imagen no se procesa | Formato no soportado | Usar JPG o PNG |
| La transcripción está vacía | Imagen muy borrosa o ilegible | Verificar calidad de la imagen |

---

## 7. Datos de auditoría

Cada documento procesado registra automáticamente:

- `procesado_por`: usuario@máquina (ej: `maria@PC-ABOGADOS`)
- `status`: COMPLETADO, ERROR o PENDIENTE
- `procesado_en`: timestamp ISO del momento del procesamiento

Estos datos se guardan en Supabase y se incluyen en el reporte PDF.
