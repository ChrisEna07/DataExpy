import os
import json
import io
import csv
import sys
import threading
import queue
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from pypdf import PdfReader
from docx import Document
from PIL import Image, ImageTk

from extractor import (
    extraer,
    guardar,
    procesar_imagen,
    procesar_con_transcripcion,
    transcribir_imagen,
    extraer_campos_dinamico,
    buscar_en_texto,
    generar_reporte_pdf,
    AUDIT_PROCESADO_POR,
    registrar_accion,
    Settings,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

APP_NAME = "DataExPY by ChrizDev"
VERSION = "1.0.0"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# ---------------------------------------------------------------------------
# Estilos / constantes
# ---------------------------------------------------------------------------

COLOR_BG = "#1a1a2e"
COLOR_CARD = "#16213e"
COLOR_ACCENT = "#0f3460"
COLOR_TEXT = "#e0e0e0"
COLOR_LABEL = "#8899aa"
COLOR_SUCCESS = "#22c55e"
COLOR_ERROR = "#ef4444"

# ---------------------------------------------------------------------------
# Utilidades de archivos
# ---------------------------------------------------------------------------

def extraer_texto_pdf(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _pdf_a_jpeg_bytes(path: str, dpi: int = 200) -> list[tuple[bytes, str]]:
    """Convierte cada página de un PDF a JPEG bytes con MIME image/jpeg."""
    import fitz
    pages = []
    doc = fitz.open(path)
    for i in range(len(doc)):
        pix = doc[i].get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("jpeg")
        pages.append((img_bytes, "image/jpeg"))
    doc.close()
    return pages


def _ocr_pdf(path: str) -> str:
    """Procesa un PDF escaneado (sin texto) con OCR vía Groq Visión.
    Limita a las primeras 3 páginas para evitar rate limiting (429)."""
    import time as _time
    paginas = _pdf_a_jpeg_bytes(path)
    MAX_PAGINAS = min(len(paginas), 3)
    textos = []
    for i in range(MAX_PAGINAS):
        img_bytes, mime = paginas[i]
        texto = transcribir_imagen(img_bytes, mime)
        textos.append(texto)
        if i < MAX_PAGINAS - 1:
            _time.sleep(2)  # pausa entre páginas para respetar rate limit
    if len(paginas) > MAX_PAGINAS:
        textos.append(f"[{len(paginas) - MAX_PAGINAS} páginas restantes omitidas. "
                       "Usa 'Ver transcripción' si necesitas el documento completo.]")
    return "\n\n".join(textos)


def extraer_texto_docx(path: str) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def leer_archivo(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        texto = extraer_texto_pdf(path)
        if not texto or len(texto.strip()) < 10:
            # PDF escaneado (sin texto) → degradación elegante a OCR
            return _ocr_pdf(path)
        return texto
    elif ext == ".docx":
        return extraer_texto_docx(path)
    elif ext == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"Formato no soportado: {ext}")


def es_imagen(path: str) -> bool:
    return Path(path).suffix.lower() in (".jpg", ".jpeg", ".png")


def leer_imagen(path: str) -> tuple[bytes, str]:
    ext = Path(path).suffix.lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return f.read(), mime


def validar_config() -> str | None:
    try:
        s = Settings()
        s.validate()
        return None
    except RuntimeError as e:
        return str(e)


# ---------------------------------------------------------------------------
# Componentes UI
# ---------------------------------------------------------------------------

class CardFrame(ctk.CTkFrame):
    """Tarjeta para mostrar un campo extraído."""
    def __init__(self, master, label, value, icon="", **kwargs):
        super().__init__(master, fg_color=COLOR_CARD, corner_radius=10, **kwargs)
        self.pack(fill="x", padx=5, pady=4)

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=(10, 4))

        ctk.CTkLabel(
            inner, text=f"{icon} {label}",
            font=("Segoe UI", 10), text_color=COLOR_LABEL,
        ).pack(anchor="w")

        self.valor_label = ctk.CTkLabel(
            inner, text=str(value) if value is not None else "—",
            font=("Segoe UI", 16, "bold"), text_color=COLOR_TEXT,
        )
        self.valor_label.pack(anchor="w", pady=(0, 8))

    def actualizar(self, value):
        self.valor_label.configure(text=str(value) if value is not None else "—")


class HeaderFrame(ctk.CTkFrame):
    """Encabezado de la aplicación."""
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=COLOR_ACCENT, corner_radius=0, height=70, **kwargs)
        self.pack(fill="x")
        self.pack_propagate(False)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(expand=True, fill="both", padx=25)

        ctk.CTkLabel(
            container, text="⚖️  DataExPY",
            font=("Segoe UI", 22, "bold"), text_color="white",
        ).pack(side="left")

        ctk.CTkLabel(
            container, text="by ChrizDev",
            font=("Segoe UI", 11), text_color="#aabbcc",
        ).pack(side="left", padx=(8, 0), pady=(6, 0))

        ctk.CTkLabel(
            container, text="Extracción inteligente de documentos legales",
            font=("Segoe UI", 11), text_color="#99aabb",
        ).pack(side="right")


class StatusBar(ctk.CTkFrame):
    """Barra de estado inferior."""
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=COLOR_ACCENT, corner_radius=0, height=30, **kwargs)
        self.pack(fill="x", side="bottom")
        self.pack_propagate(False)

        self.label = ctk.CTkLabel(
            self, text="✅ Listo",
            font=("Segoe UI", 10), text_color="#ccdddd",
        )
        self.label.pack(side="left", padx=15)

    def set(self, texto: str, ok: bool = True):
        prefix = "🟢" if ok else "🔴"
        self.label.configure(text=f"{prefix} {texto}")


# ---------------------------------------------------------------------------
# Toast notifications (auto-dismiss)
# ---------------------------------------------------------------------------

class Toast(ctk.CTkFrame):
    """Notificación tipo toast animada, posicionada en la esquina superior derecha."""
    def __init__(self, master, mensaje: str, tipo: str = "success", duracion: int = 3000):
        colores = {"success": "#22c55e", "error": "#ef4444", "info": "#3b82f6"}
        iconos = {"success": "✔", "error": "✘", "info": "ℹ"}
        bg = colores.get(tipo, "#22c55e")
        icon = iconos.get(tipo, "✔")
        super().__init__(master, fg_color=bg, corner_radius=10)

        self.label = ctk.CTkLabel(
            self, text=f" {icon}  {mensaje}",
            font=("Segoe UI", 12), text_color="white",
            padx=16, pady=8,
        )
        self.label.pack()

        self.place(relx=0.98, rely=0.04, anchor="ne")
        self.lift()
        self.after(duracion, self._fade_out)

    def _fade_out(self):
        try:
            self.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Modal de búsqueda en documento
# ---------------------------------------------------------------------------

KEYWORD_SUGERIDAS = [
    "C.C.", "NIT", "Cédula", "Pasaporte", "Dirección",
    "Teléfono", "Email", "Correo", "Celular",
    "Cliente", "Proveedor", "Contratante", "Contratista",
    "Fecha", "Total", "Subtotal", "IVA", "Descuento",
    "ID", "Factura", "Contrato", "Referencia",
    "Banco", "Cuenta", "Firma", "Cargo",
]


class BusquedaModal(ctk.CTkToplevel):
    def __init__(self, master, texto_documento: str, on_extraer_campo=None):
        super().__init__(master)
        self.texto = texto_documento
        self.on_extraer_campo = on_extraer_campo
        self._resultados_actuales: list[dict] = []

        self.transient(master)
        self.grab_set()
        self.focus_set()

        self.title("🔍 Buscar en documento")
        self.geometry("750x580")
        self.minsize(600, 400)

        # Centrar
        self.after(100, lambda: self._centrar())

        self._build_ui()

    def _centrar(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//3}")

    def _build_ui(self):
        # Buscador
        busca_frame = ctk.CTkFrame(self, fg_color="transparent")
        busca_frame.pack(fill="x", padx=15, pady=(15, 8))

        self.entry_busqueda = ctk.CTkEntry(
            busca_frame, placeholder_text="Escribe lo que buscas...",
            font=("Segoe UI", 13), height=38,
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            border_width=1, border_color="#334155",
        )
        self.entry_busqueda.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_busqueda.bind("<Return>", lambda e: self._ejecutar_busqueda())

        ctk.CTkButton(
            busca_frame, text="Buscar", command=self._ejecutar_busqueda,
            fg_color="#22c55e", hover_color="#16a34a",
            font=("Segoe UI", 12, "bold"), height=38, width=100,
            text_color="white",
        ).pack(side="right")

        # Keywords sugeridas
        ctk.CTkLabel(
            self, text="Palabras clave sugeridas:",
            font=("Segoe UI", 11), text_color=COLOR_LABEL,
        ).pack(anchor="w", padx=15, pady=(0, 6))

        keywords_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=60,
        )
        keywords_frame.pack(fill="x", padx=15, pady=(0, 10))

        for kw in KEYWORD_SUGERIDAS:
            btn = ctk.CTkButton(
                keywords_frame, text=kw,
                command=lambda k=kw: self._click_keyword(k),
                fg_color=COLOR_ACCENT, hover_color="#1a5276",
                font=("Segoe UI", 11), height=28,
                width=len(kw) * 9 + 20,
            )
            btn.pack(side="left", padx=3, pady=2)

        # Resultados
        ctk.CTkLabel(
            self, text="Resultados:",
            font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=15, pady=(0, 4))

        self.resultados_text = ctk.CTkTextbox(
            self, wrap="word",
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            font=("Consolas", 11), corner_radius=8,
            border_width=1, border_color="#334155",
            state="disabled",
        )
        self.resultados_text.pack(fill="both", expand=True, padx=15, pady=(0, 8))

        # Botón extraer campo
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=15, pady=(0, 12))

        self.btn_extraer_campo = ctk.CTkButton(
            action_frame, text="➕ Extraer como campo personalizado",
            command=self._extraer_como_campo,
            fg_color="#0f3460", hover_color="#1a5276",
            font=("Segoe UI", 12), height=36,
            state="disabled",
        )
        self.btn_extraer_campo.pack(side="left", padx=(0, 8), fill="x", expand=True)

        ctk.CTkButton(
            action_frame, text="Cerrar", command=self.destroy,
            fg_color="#ef4444", hover_color="#dc2626",
            font=("Segoe UI", 12), height=36, width=100,
        ).pack(side="right")

    def _click_keyword(self, kw: str):
        self.entry_busqueda.delete(0, "end")
        self.entry_busqueda.insert(0, kw)
        self._ejecutar_busqueda()

    def _ejecutar_busqueda(self):
        query = self.entry_busqueda.get().strip()
        if not query:
            return

        self._resultados_actuales = buscar_en_texto(self.texto, query)

        self.resultados_text.configure(state="normal")
        self.resultados_text.delete("1.0", "end")

        if not self._resultados_actuales:
            self.resultados_text.insert("end", "🔍 Sin resultados.\n")
            self.btn_extraer_campo.configure(state="disabled")
        else:
            self.resultados_text.insert(
                "end",
                f"🔍 {len(self._resultados_actuales)} ocurrencia(s) de '{query}':\n\n",
            )
            for r in self._resultados_actuales:
                antes = r["antes"][-40:].rjust(40) if r["antes"] else ""
                despues = r["despues"][:40].ljust(40) if r["despues"] else ""
                linea = (
                    f"  ── Línea {r['linea']} ──\n"
                    f"  ...{antes}[{r['match']}]{despues}...\n\n"
                )
                self.resultados_text.insert("end", linea)

            self.resultados_text.see("1.0")
            self.btn_extraer_campo.configure(state="normal")

        self.resultados_text.configure(state="disabled")

    def _extraer_como_campo(self):
        query = self.entry_busqueda.get().strip()
        if not query or not self._resultados_actuales:
            return

        # Usar IA para extraer el campo del documento completo
        try:
            resultado = extraer_campos_dinamico(self.texto, [query])
            valor = resultado.get(query)
            if valor:
                if self.on_extraer_campo:
                    self.on_extraer_campo(query, valor)
                self.resultados_text.configure(state="normal")
                self.resultados_text.insert(
                    "end",
                    f"\n✅ Campo '{query}' extraído: {valor}\n",
                )
                self.resultados_text.configure(state="disabled")
            else:
                messagebox.showinfo(
                    "Sin valor",
                    f"No se encontró un valor claro para '{query}'.\n"
                    "Revisa los resultados manualmente.",
                )
        except Exception as e:
            messagebox.showerror("Error", f"Error al extraer campo:\n{e}")


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------

class DataExPYApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME}  v{VERSION}")
        self.geometry("1100x720")
        self.minsize(900, 600)

        # Centrar en pantalla
        self.after(100, self._centrar)

        self.historial: list[dict] = []
        self.ultimo_resultado: dict | None = None
        self.transcripcion_actual: str | None = None
        self.imagen_bytes: bytes | None = None
        self.imagen_mime: str | None = None

        # Cola asíncrona para comunicación hilo→UI
        self.task_queue: queue.Queue = queue.Queue()
        self.after(100, self._check_queue)

        self._validar_conf()
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------------------

    def _centrar(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 3
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _validar_conf(self):
        error = validar_config()
        if error:
            messagebox.showerror(
                "Configuración incompleta",
                f"{error}\n\nRevisa tu archivo .env",
            )

    def _build_ui(self):
        # Header
        HeaderFrame(self)

        # Cuerpo principal
        body = ctk.CTkFrame(self, fg_color=COLOR_BG)
        body.pack(fill="both", expand=True, padx=15, pady=(10, 0))

        body.grid_columnconfigure(0, weight=1, uniform="col")
        body.grid_columnconfigure(1, weight=1, uniform="col")
        body.grid_rowconfigure(0, weight=1)

        # --- Panel izquierdo: entrada ---
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))

        self._build_panel_entrada(left)

        # --- Panel derecho: resultados ---
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        self._build_panel_resultados(right)

        # --- Barra de estado ---
        self.status_bar = StatusBar(self)

    def _build_panel_entrada(self, parent):
        ctk.CTkLabel(
            parent, text="📄 Entrada del documento",
            font=("Segoe UI", 14, "bold"), text_color=COLOR_TEXT,
        ).pack(anchor="w", pady=(0, 8))

        # Área de texto
        self.text_input = ctk.CTkTextbox(
            parent, height=220,
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            font=("Consolas", 12), corner_radius=8,
            border_width=1, border_color="#334155",
        )
        self.text_input.pack(fill="x", pady=(0, 8))
        self.text_input.insert("1.0", "Pega aquí el contenido del documento legal...")

        # Vista previa de imagen
        self.img_preview_label = ctk.CTkLabel(
            parent, text="",
            fg_color="transparent",
        )

        self.img_path_label = ctk.CTkLabel(
            parent, text="",
            font=("Segoe UI", 10), text_color=COLOR_LABEL,
        )

        # Botones
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            btn_frame, text="📎  Seleccionar archivo",
            command=self._seleccionar_archivo,
            fg_color=COLOR_ACCENT, hover_color="#1a5276",
            font=("Segoe UI", 12), height=38,
        ).pack(side="left", padx=(0, 8))

        self.btn_extraer = ctk.CTkButton(
            btn_frame, text="🔍  Extraer datos",
            command=self._extraer_datos,
            fg_color="#22c55e", hover_color="#16a34a",
            font=("Segoe UI", 12, "bold"), height=38,
            text_color="white",
        )
        self.btn_extraer.pack(side="left", fill="x", expand=True)

        # Labels de archivo cargado
        self.archivo_label = ctk.CTkLabel(
            parent, text="",
            font=("Segoe UI", 10), text_color=COLOR_LABEL,
        )
        self.archivo_label.pack(anchor="w")

    def _build_panel_resultados(self, parent):
        ctk.CTkLabel(
            parent, text="📋 Resultados",
            font=("Segoe UI", 14, "bold"), text_color=COLOR_TEXT,
        ).pack(anchor="w", pady=(0, 8))

        # Status badge
        self.status_badge = ctk.CTkLabel(
            parent, text="🟡 Sin procesar",
            font=("Segoe UI", 10), text_color="#94a3b8",
        )
        self.status_badge.pack(anchor="w", pady=(0, 6))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            parent, fg_color="#334155", progress_color="#22c55e",
            height=6, corner_radius=3,
        )
        self.progress_bar.pack(fill="x", pady=(0, 10))
        self.progress_bar.set(0)

        # Cards de resultados
        self.cards_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.cards_frame.pack(fill="x")

        self.card_cliente = CardFrame(self.cards_frame, "Cliente", "—", "👤")
        self.card_fecha = CardFrame(self.cards_frame, "Fecha", "—", "📅")
        self.card_total = CardFrame(self.cards_frame, "Total", "—", "💰")
        self.card_id = CardFrame(self.cards_frame, "ID Documento", "—", "🔖")

        # Botones de exportación
        exp_frame = ctk.CTkFrame(parent, fg_color="transparent")
        exp_frame.pack(fill="x", pady=(12, 0))

        ctk.CTkButton(
            exp_frame, text="📥  Exportar CSV", command=self._exportar_csv,
            fg_color="#1e293b", hover_color="#334155",
            font=("Segoe UI", 12), height=36,
        ).pack(side="left", padx=(0, 8), fill="x", expand=True)

        ctk.CTkButton(
            exp_frame, text="📥  Exportar JSON", command=self._exportar_json,
            fg_color="#1e293b", hover_color="#334155",
            font=("Segoe UI", 12), height=36,
        ).pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.btn_reporte = ctk.CTkButton(
            exp_frame, text="📄  Reporte PDF", command=self._exportar_pdf,
            fg_color="#1e293b", hover_color="#334155",
            font=("Segoe UI", 12), height=36,
        )
        self.btn_reporte.pack(side="left", fill="x", expand=True)

        # Botones de transcripción, búsqueda y vista previa
        tools_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tools_frame.pack(fill="x", pady=(10, 0))

        self.btn_transcripcion = ctk.CTkButton(
            tools_frame, text="📄  Ver transcripción",
            command=self._abrir_transcripcion,
            fg_color="#1e293b", hover_color="#334155",
            font=("Segoe UI", 12), height=34,
            state="disabled",
        )
        self.btn_transcripcion.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.btn_buscar = ctk.CTkButton(
            tools_frame, text="🔍  Buscar en documento",
            command=self._abrir_busqueda,
            fg_color="#1e293b", hover_color="#334155",
            font=("Segoe UI", 12), height=34,
            state="disabled",
        )
        self.btn_buscar.pack(side="left", fill="x", expand=True)

        self.btn_preview = ctk.CTkButton(
            tools_frame, text="👁️  Ver original",
            command=self._abrir_previsualizacion,
            fg_color="#1e293b", hover_color="#334155",
            font=("Segoe UI", 12), height=34,
            state="disabled",
        )
        self.btn_preview.pack(side="left", padx=(8, 0), fill="x", expand=True)

        # Historial
        ctk.CTkLabel(
            parent, text="📚 Historial",
            font=("Segoe UI", 14, "bold"), text_color=COLOR_TEXT,
        ).pack(anchor="w", pady=(15, 5))

        self.historial_text = ctk.CTkTextbox(
            parent, height=150,
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            font=("Consolas", 11), corner_radius=8,
            border_width=1, border_color="#334155",
            state="disabled",
        )
        self.historial_text.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _seleccionar_archivo(self):
        path = filedialog.askopenfilename(
            title="Seleccionar documento",
            filetypes=[
                ("Todos los documentos", "*.pdf *.docx *.txt *.jpg *.jpeg *.png"),
                ("PDF", "*.pdf"), ("Word", "*.docx"), ("Texto", "*.txt"),
                ("Imágenes", "*.jpg *.jpeg *.png"),
            ],
        )
        if not path:
            return

        # Resetear estado de imagen
        self.imagen_bytes = None
        self.imagen_mime = None
        self.img_preview_label.pack_forget()
        self.img_path_label.pack_forget()

        if es_imagen(path):
            try:
                data, mime = leer_imagen(path)
                self.imagen_bytes = data
                self.imagen_mime = mime

                # Mostrar preview
                img = Image.open(path)
                img.thumbnail((280, 200))
                tk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self.img_preview_label.configure(image=tk_img, text="")
                self.img_preview_label.pack(pady=(0, 6))
                self.img_path_label.configure(
                    text=f"🖼️ {Path(path).name} (imagen)",
                    text_color="#94a3b8",
                )
                self.img_path_label.pack(anchor="w")
                self.text_input.delete("1.0", "end")
                self.status_bar.set(f"Imagen cargada: {Path(path).name}")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo leer la imagen:\n{e}")
                self.status_bar.set("Error al leer imagen", ok=False)
        else:
            try:
                texto = leer_archivo(path)
                self.text_input.delete("1.0", "end")
                self.text_input.insert("1.0", texto)
                self.archivo_label.configure(
                    text=f"📄 {Path(path).name} ({len(texto):,} caracteres)",
                    text_color="#94a3b8",
                )
                # Detectar si fue OCR
                ocr_msg = " (OCR automático)" if Path(path).suffix.lower() == ".pdf" and len(texto.strip()) < 100 else ""
                self.status_bar.set(f"Archivo cargado: {Path(path).name}{ocr_msg}")
                registrar_accion("CARGAR_DOCUMENTO", estado="EXITO", archivo=Path(path).name)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo leer el archivo:\n{e}")
                self.status_bar.set("Error al leer archivo", ok=False)

    def _mostrar_toast(self, mensaje: str, tipo: str = "success"):
        try:
            Toast(self, mensaje, tipo)
        except Exception:
            pass

    def _extraer_datos(self):
        # Prioridad: imagen cargada > texto manual
        if self.imagen_bytes:
            self.btn_extraer.configure(state="disabled", text="⏳ Analizando imagen...")
            self.status_bar.set("Procesando imagen con Groq Visión...")
            self.progress_bar.set(0.2)
            self.status_badge.configure(text="🟡 Procesando...", text_color="#eab308")
            threading.Thread(target=self._procesar_imagen, daemon=True).start()
            return

        texto = self.text_input.get("1.0", "end").strip()
        if not texto or texto == "Pega aquí el contenido del documento legal...":
            messagebox.showwarning("Sin contenido", "Ingresa texto o carga un archivo primero.")
            return

        self.btn_extraer.configure(state="disabled", text="⏳ Procesando...")
        self.status_bar.set("Procesando con Groq...")
        self.progress_bar.set(0.2)
        self.status_badge.configure(text="🟡 Procesando...", text_color="#eab308")

        threading.Thread(target=self._procesar, args=(texto,), daemon=True).start()

    def _check_queue(self):
        """Procesa mensajes del hilo secundario en el hilo principal (UI)."""
        try:
            while True:
                msg = self.task_queue.get_nowait()
                tipo = msg.get("tipo")

                if tipo == "progreso":
                    self.progress_bar.set(msg["valor"])
                elif tipo == "resultado":
                    self.ultimo_resultado = msg.get("datos")
                    self.transcripcion_actual = msg.get("texto", "")
                    if self.ultimo_resultado:
                        self.ultimo_resultado["_timestamp"] = datetime.now().strftime("%H:%M:%S")
                        self.historial.append(self.ultimo_resultado)
                    self._mostrar_resultado(self.ultimo_resultado or {})
                    self.status_bar.set(msg.get("status_msg", "Listo"))
                    self._mostrar_toast(msg.get("toast_msg", "Completado"), "success")
                elif tipo == "error":
                    self.status_bar.set(msg.get("status_msg", "Error"), False)
                    self._mostrar_toast(msg.get("toast_msg", "Error"), "error")
                    messagebox.showerror("Error", msg.get("detail", "Error desconocido"))
                elif tipo == "habilitar":
                    self._habilitar_boton()
        except queue.Empty:
            pass
        self.after(100, self._check_queue)

    def _procesar(self, texto: str):
        try:
            self.task_queue.put({"tipo": "progreso", "valor": 0.4})
            datos = extraer(texto)
            self.task_queue.put({"tipo": "progreso", "valor": 0.7})
            guardar(datos)

            self.task_queue.put({
                "tipo": "resultado",
                "datos": datos,
                "texto": texto,
                "status_msg": "Documento procesado y guardado en Supabase",
                "toast_msg": "Documento procesado con éxito",
            })
        except Exception as e:
            self.task_queue.put({
                "tipo": "error",
                "status_msg": f"Error: {e}",
                "toast_msg": f"Error: {e}",
                "detail": f"Error durante el procesamiento:\n{e}",
            })
        finally:
            self.task_queue.put({"tipo": "habilitar"})

    def _procesar_imagen(self):
        try:
            self.task_queue.put({"tipo": "progreso", "valor": 0.4})
            datos = procesar_con_transcripcion(self.imagen_bytes, self.imagen_mime)
            self.task_queue.put({"tipo": "progreso", "valor": 0.8})

            resultado = {
                k: v for k, v in datos.items() if k != "transcripcion_completa"
            }
            transcripcion = datos.get("transcripcion_completa", "")

            self.task_queue.put({
                "tipo": "resultado",
                "datos": resultado,
                "texto": transcripcion,
                "status_msg": "Imagen procesada y guardada en Supabase",
                "toast_msg": "Imagen procesada con éxito",
            })
        except Exception as e:
            self.task_queue.put({
                "tipo": "error",
                "status_msg": f"Error: {e}",
                "toast_msg": f"Error: {e}",
                "detail": f"Error al procesar imagen:\n{e}",
            })
        finally:
            self.task_queue.put({"tipo": "habilitar"})

    def _mostrar_resultado(self, datos: dict):
        self.card_cliente.actualizar(datos.get("cliente"))
        self.card_fecha.actualizar(datos.get("fecha"))
        total = datos.get("total")
        if total is not None:
            self.card_total.actualizar(f"${total:,.2f}")
        else:
            self.card_total.actualizar(None)
        self.card_id.actualizar(datos.get("id_documento"))

        # Status badge verde
        self.status_badge.configure(text="🟢 Procesado", text_color="#22c55e")

        # Activar botones si hay transcripción
        if self.transcripcion_actual:
            self.btn_transcripcion.configure(state="normal")
            self.btn_buscar.configure(state="normal")
            self.btn_preview.configure(state="normal")

        # Actualizar historial
        self._actualizar_historial()

    def _actualizar_historial(self):
        self.historial_text.configure(state="normal")
        self.historial_text.delete("1.0", "end")
        for h in reversed(self.historial):
            ts = h.get("_timestamp", "")
            total_str = f"${h['total']:,.2f}" if h.get("total") is not None else "—"
            linea = (
                f"[{ts}]  "
                f"Cliente: {h.get('cliente') or '—'}  |  "
                f"Fecha: {h.get('fecha') or '—'}  |  "
                f"Total: {total_str}  |  "
                f"ID: {h.get('id_documento') or '—'}"
            )
            self.historial_text.insert("end", linea + "\n" + "-" * 80 + "\n")
        self.historial_text.configure(state="disabled")

    def _habilitar_boton(self):
        self.btn_extraer.configure(state="normal", text="🔍  Extraer datos")

    def _abrir_transcripcion(self):
        if not self.transcripcion_actual:
            return
        win = ctk.CTkToplevel(self)
        win.transient(self)
        win.grab_set()
        win.focus_set()
        win.title("📄 Transcripción completa del documento")
        win.geometry("750x550")
        win.minsize(500, 300)

        txt = ctk.CTkTextbox(
            win, wrap="word",
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            font=("Consolas", 12), corner_radius=8,
        )
        txt.pack(fill="both", expand=True, padx=15, pady=15)
        txt.insert("1.0", self.transcripcion_actual)
        txt.configure(state="disabled")

        ctk.CTkButton(
            win, text="Cerrar", command=win.destroy,
            fg_color=COLOR_ACCENT, hover_color="#1a5276",
            font=("Segoe UI", 12), height=36,
        ).pack(pady=(0, 12))

    def _abrir_busqueda(self):
        if not self.transcripcion_actual:
            return
        BusquedaModal(self, self.transcripcion_actual, self._on_campo_extraido)

    def _abrir_previsualizacion(self):
        """Modal con el texto original del documento."""
        if not self.transcripcion_actual:
            return
        win = ctk.CTkToplevel(self)
        win.transient(self)
        win.grab_set()
        win.focus_set()
        win.title("👁️ Documento original")
        win.geometry("800x600")
        win.minsize(500, 300)

        container = ctk.CTkFrame(win, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(
            container, text="Documento original",
            font=("Segoe UI", 14, "bold"), text_color=COLOR_TEXT,
        ).pack(anchor="w", pady=(0, 8))

        txt = ctk.CTkTextbox(
            container, wrap="word",
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            font=("Consolas", 12), corner_radius=8,
        )
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", self.transcripcion_actual)
        txt.configure(state="disabled")

    def _on_campo_extraido(self, nombre_campo: str, valor):
        if not self.ultimo_resultado:
            return
        self.ultimo_resultado[nombre_campo] = valor
        messagebox.showinfo(
            "Campo extraído",
            f"'{nombre_campo}' guardado en resultados.\n"
            "Exporta el JSON para verlo.",
        )

    def _exportar_pdf(self):
        if not self.ultimo_resultado:
            messagebox.showinfo("Sin datos", "No hay resultados para exportar.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"reporte_{datetime.now():%Y%m%d_%H%M%S}.pdf",
        )
        if not path:
            return
        try:
            datos = dict(self.ultimo_resultado)
            if self.transcripcion_actual:
                datos["transcripcion_completa"] = self.transcripcion_actual
            generar_reporte_pdf(datos, path)
            self.status_bar.set(f"Reporte PDF generado: {Path(path).name}")
            registrar_accion("GENERAR_PDF", estado="EXITO", archivo=Path(path).name)
        except Exception as e:
            registrar_accion("GENERAR_PDF", estado="FALLO", error=str(e))
            messagebox.showerror("Error", f"Error al generar PDF:\n{e}")
            self.status_bar.set("Error al generar PDF", ok=False)

    def _exportar_csv(self):
        if not self.ultimo_resultado:
            messagebox.showinfo("Sin datos", "No hay resultados para exportar.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"extract_{datetime.now():%Y%m%d_%H%M%S}.csv",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=self.ultimo_resultado.keys())
            w.writeheader()
            w.writerow(self.ultimo_resultado)
        self.status_bar.set(f"Exportado a CSV: {Path(path).name}")
        registrar_accion("EXPORTAR_CSV", estado="EXITO", archivo=Path(path).name)

    def _exportar_json(self):
        if not self.ultimo_resultado:
            messagebox.showinfo("Sin datos", "No hay resultados para exportar.")
            return
        export = dict(self.ultimo_resultado)
        if self.transcripcion_actual:
            export["transcripcion_completa"] = self.transcripcion_actual
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"extract_{datetime.now():%Y%m%d_%H%M%S}.json",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, ensure_ascii=False)
        self.status_bar.set(f"Exportado a JSON: {Path(path).name}")
        registrar_accion("EXPORTAR_JSON", estado="EXITO", archivo=Path(path).name)

    def _on_close(self):
        """Confirma salida si hay documentos procesados o proceso activo."""
        from tkinter import messagebox as _mb
        tiene_resultados = self.ultimo_resultado is not None
        tiene_historial = len(self.historial) > 0
        procesando = self.btn_extraer.cget("text") != "🔍  Extraer datos"

        if procesando:
            _mb.showwarning("Proceso en curso", "Hay una extracción en progreso. Espera a que termine.")
            return

        if tiene_resultados or tiene_historial:
            respuesta = _mb.askyesno(
                "Confirmar salida",
                "Tienes documentos procesados. ¿Seguro que quieres salir?\n"
                "Los datos no exportados se perderán.",
                icon="warning",
            )
            if not respuesta:
                return

        registrar_accion("CERRAR_APLICACION", estado="EXITO")
        self.destroy()
        sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = DataExPYApp()
    app.mainloop()
