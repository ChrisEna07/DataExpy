import os
import json
import io
import csv
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from pypdf import PdfReader
from docx import Document

from extractor import extraer, guardar, Settings

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PAGE_TITLE = "LegalExtract AI"
PAGE_ICON = "⚖️"

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Estilos personalizados
# ---------------------------------------------------------------------------

st.markdown(
    """
<style>
    /* Header */
    .app-header {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        color: white;
    }
    .app-header h1 { margin: 0; font-size: 1.8rem; font-weight: 700; }
    .app-header p { margin: 0.3rem 0 0; opacity: 0.8; font-size: 0.95rem; }

    /* Tarjetas de resultado */
    .result-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1rem;
    }
    .result-card .label { font-size: 0.75rem; text-transform: uppercase; color: #64748b; letter-spacing: 0.05em; }
    .result-card .value { font-size: 1.1rem; font-weight: 600; color: #0f172a; margin-top: 0.1rem; }

    /* Sidebar */
    .sidebar-status { padding: 0.5rem 0; }
    .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
    .status-dot.ok { background: #22c55e; }
    .status-dot.err { background: #ef4444; }

    /* Botones */
    .stDownloadButton button {
        background: #1e293b !important;
        color: white !important;
        border: none !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 0.5rem; }
    .stTabs [data-baseweb="tab"] { border-radius: 6px 6px 0 0; padding: 0.5rem 1rem; }

    /* Footer */
    .app-footer { text-align: center; color: #94a3b8; font-size: 0.8rem; margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #e2e8f0; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Helpers de sesión
# ---------------------------------------------------------------------------

def init_session():
    if "historial" not in st.session_state:
        st.session_state.historial = []
    if "config_valida" not in st.session_state:
        st.session_state.config_valida = _check_config()


def _check_config() -> bool:
    try:
        s = Settings()
        s.validate()
        return True
    except RuntimeError:
        return False


# ---------------------------------------------------------------------------
# Extracción de texto desde archivos
# ---------------------------------------------------------------------------

def extraer_texto_pdf(file) -> str:
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extraer_texto_docx(file) -> str:
    doc = Document(file)
    return "\n".join(p.text for p in doc.paragraphs)


def leer_archivo(uploaded_file) -> str:
    ext = Path(uploaded_file.name).suffix.lower()
    if ext == ".pdf":
        return extraer_texto_pdf(uploaded_file)
    elif ext == ".docx":
        return extraer_texto_docx(uploaded_file)
    elif ext == ".txt":
        return uploaded_file.read().decode("utf-8")
    else:
        st.error(f"Formato no soportado: {ext}")
        return ""


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar():
    with st.sidebar:
        st.markdown(
            "<div style='font-size:3rem; text-align:center; margin-bottom:0.5rem;'>⚖️</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"### {PAGE_TITLE}")
        st.markdown("---")

        # Estado de conexión
        st.markdown("#### Estado del Sistema")
        ok = st.session_state.config_valida
        dot = "🟢" if ok else "🔴"
        label = "Configuración válida" if ok else "Falta .env o credenciales"
        st.markdown(f"{dot} {label}")

        if not ok:
            st.warning(
                "Crea un archivo `.env` en la raíz con:\n\n"
                "```\nGROQ_API_KEY=...\nSUPABASE_URL=...\nSUPABASE_KEY=...\n```"
            )

        st.markdown("---")
        st.markdown("#### Instrucciones")
        st.markdown(
            """
1. **Pega texto** o **sube un archivo** (PDF, DOCX, TXT)
2. La IA extrae: *cliente, fecha, total, id_documento*
3. Los datos se guardan en **Supabase**
4. Exporta los resultados en **CSV** o **JSON**
        """
        )
        st.markdown("---")
        st.markdown("#### Datos sensibles")
        st.info(
            "La IA anonimiza automáticamente tarjetas, "
            "contraseñas y direcciones privadas → `[PROTEGIDO]`"
        )

        # Botón para limpiar historial
        if st.session_state.historial:
            st.markdown("---")
            if st.button("🗑️ Limpiar historial", use_container_width=True):
                st.session_state.historial = []
                st.rerun()


# ---------------------------------------------------------------------------
# Panel de entrada
# ---------------------------------------------------------------------------

def render_input():
    tab_texto, tab_archivo = st.tabs(["📝 Texto manual", "📎 Subir archivo"])

    texto = ""

    with tab_texto:
        texto = st.text_area(
            "Pega el contenido del documento legal:",
            height=220,
            placeholder=(
                "Ej: Cliente: María Gómez\n"
                "Fecha de emisión: 15/03/2026\n"
                "Total facturado: $ 1.250.000\n"
                "Referencia: FAC-2026-0421"
            ),
        )
        cols = st.columns([1, 5])
        btn_texto = cols[0].button("🔍 Extraer", type="primary", key="btn_texto")

    with tab_archivo:
        uploaded = st.file_uploader(
            "Selecciona un documento",
            type=["pdf", "docx", "txt"],
            help="Archivos PDF, Word o texto plano",
        )
        if uploaded:
            with st.status("Leyendo archivo...", expanded=False) as status:
                texto = leer_archivo(uploaded)
                if texto:
                    st.code(texto[:800] + ("..." if len(texto) > 800 else ""), language="text")
                    status.update(label=f"✅ {uploaded.name} cargado", state="complete")
                else:
                    status.update(label="❌ Error al leer archivo", state="error")

        btn_archivo = st.button("🔍 Extraer", type="primary", key="btn_archivo", disabled=not texto)

    return texto, (btn_texto or btn_archivo)


# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------

def render_resultado(datos: dict):
    cols = st.columns(4)
    labels = {
        "cliente": "Cliente",
        "fecha": "Fecha",
        "total": "Total",
        "id_documento": "ID Documento",
    }
    icons = {"cliente": "👤", "fecha": "📅", "total": "💰", "id_documento": "🔖"}

    for i, campo in enumerate(labels):
        val = datos.get(campo)
        display = val if val is not None else "—"
        with cols[i]:
            st.markdown(
                f"""
                <div class="result-card">
                    <div class="label">{icons[campo]} {labels[campo]}</div>
                    <div class="value">{display}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_exportacion(datos: dict):
    _, col_csv, col_json, _ = st.columns([3, 2, 2, 3])
    with col_csv:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=datos.keys())
        w.writeheader()
        w.writerow(datos)
        st.download_button(
            "📥 CSV",
            data=buf.getvalue(),
            file_name=f"extract_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_json:
        st.download_button(
            "📥 JSON",
            data=json.dumps(datos, indent=2, ensure_ascii=False),
            file_name=f"extract_{datetime.now():%Y%m%d_%H%M%S}.json",
            mime="application/json",
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------

def render_historial():
    if not st.session_state.historial:
        return

    st.markdown("---")
    st.markdown("### 📋 Historial de extracciones")

    # Tabla
    data = []
    for h in st.session_state.historial:
        data.append(
            {
                "Cliente": h.get("cliente") or "—",
                "Fecha": h.get("fecha") or "—",
                "Total": f"${h['total']:,.2f}" if h.get("total") is not None else "—",
                "ID Documento": h.get("id_documento") or "—",
                "Hora": h.get("_timestamp", ""),
            }
        )

    st.dataframe(data, use_container_width=True, hide_index=True)

    # Exportar todo
    if st.button("📥 Exportar historial completo (JSON)", use_container_width=True):
        export = [
            {k: v for k, v in h.items() if not k.startswith("_")}
            for h in st.session_state.historial
        ]
        st.download_button(
            "📥 Descargar historial",
            data=json.dumps(export, indent=2, ensure_ascii=False),
            file_name=f"historial_{datetime.now():%Y%m%d_%H%M%S}.json",
            mime="application/json",
        )


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------

def main():
    init_session()
    render_sidebar()

    # Header
    st.markdown(
        """
        <div class="app-header">
            <h1>⚖️ LegalExtract AI</h1>
            <p>Extracción inteligente de datos en documentos legales · Groq (Llama-3) + Supabase</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.config_valida:
        st.error(
            "⚠️ **Configuración incompleta.** Crea un archivo `.env` en la raíz del proyecto "
            "con `GROQ_API_KEY`, `SUPABASE_URL` y `SUPABASE_KEY`. "
            "Revisa la barra lateral para más detalles."
        )
        return

    texto, btn_clicked = render_input()

    if btn_clicked and texto.strip():
        with st.spinner("🤖 Analizando documento con Groq (Llama-3)..."):
            try:
                datos = extraer(texto)
                guardar(datos)

                datos["_timestamp"] = datetime.now().strftime("%H:%M:%S")
                st.session_state.historial.append(datos)

                st.success("✅ Documento procesado y guardado en Supabase")
                render_resultado(datos)
                render_exportacion(datos)

            except Exception as e:
                st.error(f"❌ Error durante el procesamiento: {e}")

    elif btn_clicked and not texto.strip():
        st.warning("✏️ Ingresa texto o sube un archivo antes de extraer.")

    render_historial()

    # Footer
    st.markdown(
        "<div class='app-footer'>LegalExtract AI · Datos anonimizados automáticamente · "
        "Powered by Groq Llama-3 & Supabase</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
