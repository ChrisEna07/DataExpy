import os
import json
import io
import csv
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from pypdf import PdfReader
from docx import Document

from extractor import extraer, guardar, Settings

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


def extraer_texto_docx(path: str) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def leer_archivo(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return extraer_texto_pdf(path)
    elif ext == ".docx":
        return extraer_texto_docx(path)
    elif ext == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"Formato no soportado: {ext}")


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
        prefix = "✅" if ok else "❌"
        self.label.configure(text=f"{prefix} {texto}")


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

        # Vista previa del archivo cargado
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
        ).pack(side="left", fill="x", expand=True)

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
                ("Documentos", "*.pdf *.docx *.txt"),
                ("PDF", "*.pdf"), ("Word", "*.docx"), ("Texto", "*.txt"),
            ],
        )
        if not path:
            return

        try:
            texto = leer_archivo(path)
            self.text_input.delete("1.0", "end")
            self.text_input.insert("1.0", texto)
            self.archivo_label.configure(
                text=f"📄 {Path(path).name} ({len(texto):,} caracteres)",
                text_color="#94a3b8",
            )
            self.status_bar.set(f"Archivo cargado: {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el archivo:\n{e}")
            self.status_bar.set(f"Error al leer archivo", ok=False)

    def _extraer_datos(self):
        texto = self.text_input.get("1.0", "end").strip()
        if not texto or texto == "Pega aquí el contenido del documento legal...":
            messagebox.showwarning("Sin contenido", "Ingresa texto o carga un archivo primero.")
            return

        self.btn_extraer.configure(state="disabled", text="⏳ Procesando...")
        self.status_bar.set("Procesando con Groq...")

        threading.Thread(target=self._procesar, args=(texto,), daemon=True).start()

    def _procesar(self, texto: str):
        try:
            datos = extraer(texto)
            guardar(datos)
            self.ultimo_resultado = datos
            datos["_timestamp"] = datetime.now().strftime("%H:%M:%S")
            self.historial.append(datos)

            self.after(0, self._mostrar_resultado, datos)
            self.after(0, self.status_bar.set, "Documento procesado y guardado en Supabase")
        except Exception as e:
            self.after(0, self.status_bar.set, f"Error: {e}", False)
            self.after(0, messagebox.showerror, "Error", f"Error durante el procesamiento:\n{e}")
        finally:
            self.after(0, self._habilitar_boton)

    def _mostrar_resultado(self, datos: dict):
        self.card_cliente.actualizar(datos.get("cliente"))
        self.card_fecha.actualizar(datos.get("fecha"))
        total = datos.get("total")
        if total is not None:
            self.card_total.actualizar(f"${total:,.2f}")
        else:
            self.card_total.actualizar(None)
        self.card_id.actualizar(datos.get("id_documento"))

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

    def _exportar_json(self):
        if not self.ultimo_resultado:
            messagebox.showinfo("Sin datos", "No hay resultados para exportar.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"extract_{datetime.now():%Y%m%d_%H%M%S}.json",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.ultimo_resultado, f, indent=2, ensure_ascii=False)
        self.status_bar.set(f"Exportado a JSON: {Path(path).name}")

    def _on_close(self):
        self.destroy()
        sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = DataExPYApp()
    app.mainloop()
