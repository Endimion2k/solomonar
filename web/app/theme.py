"""Temă vizuală SOLOMONAR — tokens de culoare, template Plotly, paletă partide, helpers UI.

Adaptat din cdep-client, rebrand SOLOMONAR (transparența întregului aparat de stat).
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Aceeași paletă ca în clientul static (web/solomonar.css, tema închisă).
BG = "#0f1420"
SURFACE = "#161c2a"
SURFACE_2 = "#1c2335"
BORDER = "#283044"
TEXT = "#e7eaf0"
TEXT_DIM = "#97a1b2"
TEXT_FAINT = "#6b7588"

ACCENT = "#818cf8"
ACCENT_2 = "#5eead4"
SUCCESS = "#34d399"
WARNING = "#fbbf24"
DANGER = "#f87171"

FONT = '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif'

PARTY_COLORS = {
    "psd": "#e11d48", "pnl": "#facc15", "usr": "#0ea5e9", "aur": "#fbbf24",
    "udmr": "#22c55e", "pot": "#a855f7", "sos": "#f97316", "pmp": "#a855f7",
    "pro": "#06b6d4", "alde": "#16a34a", "fd": "#3b82f6", "neafiliati": "#6b7280",
}
# încredere graf
CONF_COLORS = {"high": SUCCESS, "context": ACCENT, "candidat": TEXT_DIM}
NEUTRAL_PALETTE = [ACCENT, ACCENT_2, WARNING, DANGER, "#38bdf8", "#c4b5fd",
                   "#2dd4bf", "#f9a8d4", "#fde68a", "#94a3b8"]


def party_color(p: str) -> str:
    return PARTY_COLORS.get((p or "").strip().lower()[:4].rstrip(), "#6b7280")


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except Exception:
        return "—"


def fmt_lei(n) -> str:
    try:
        n = float(n)
    except Exception:
        return "—"
    for div, suf in ((1e9, " mld"), (1e6, " mil"), (1e3, " mii")):
        if abs(n) >= div:
            return f"{n/div:,.1f}{suf} lei".replace(",", ".")
    return f"{n:,.0f} lei".replace(",", ".")


def fmt_pct(n) -> str:
    try:
        return f"{float(n):.1f}%"
    except Exception:
        return "—"


def apply_theme() -> None:
    tmpl = go.layout.Template()
    tmpl.layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, family=FONT, size=13),
        colorway=NEUTRAL_PALETTE,
        xaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER),
        yaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER),
        margin=dict(l=40, r=20, t=40, b=40), hoverlabel=dict(bgcolor=SURFACE_2),
    )
    pio.templates["solomonar"] = tmpl
    pio.templates.default = "solomonar"
    st.markdown(f"""<style>
      @import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500&display=swap");
      html, body, .stApp, .stApp p, .stApp label, .stApp input, .stApp button, .stApp li,
      [data-testid="stMarkdownContainer"] {{ font-family:{FONT}; }}
      .stApp {{ background:{BG}; color:{TEXT}; font-variant-numeric:tabular-nums; }}
      section[data-testid="stSidebar"] {{ background:{SURFACE}; border-right:1px solid {BORDER}; }}
      [data-testid="stMetric"] {{ background:transparent; border:0; border-top:1px solid {TEXT_FAINT};
        border-radius:0; padding:12px 0 4px; }}
      [data-testid="stMetricValue"] {{ color:{TEXT}; font-size:28px; font-weight:500; }}
      [data-testid="stMetricLabel"] {{ color:{TEXT_DIM}; }}
      h1,h2,h3,h4 {{ color:{TEXT}; font-family:{FONT}; font-weight:600; letter-spacing:-.005em; }}
      h2 {{ font-family:"IBM Plex Serif", Georgia, serif; font-weight:500; font-size:34px; }}
      .solomonar-hero {{ font-size:16px; color:{TEXT_DIM}; margin:-4px 0 20px; max-width:70ch; }}
      .stDataFrame {{ border:1px solid {BORDER}; border-radius:6px; }}
      a {{ color:{ACCENT}; }}
      .badge {{ display:inline-block; padding:1px 8px; border-radius:4px; font-size:13px;
        border:1px solid {BORDER}; color:{TEXT_DIM}; }}
    </style>""", unsafe_allow_html=True)


_NUMAR_MARE = 10_000          # sub acest prag separatorii de mii nu ajută (ani, coduri scurte)
_COLOANE_COD = ("cui", "id", "cod", "an", "idm", "idp", "nr_inregistrare")
_TIPURI_FARA_TEXT = ("link", "image", "list", "checkbox", "line_chart", "bar_chart", "progress")


def _e_text(serie) -> bool:
    """Coloană de text: `object` (pandas 2) sau tipul `str` (implicit din pandas 3)."""
    import pandas as pd

    return pd.api.types.is_object_dtype(serie) or pd.api.types.is_string_dtype(serie)


def _tip_coloana(config) -> str:
    """Tipul unei intrări din column_config („link”, „number”…); gol dacă nu e configurată."""
    if isinstance(config, dict):
        return (config.get("type_config") or {}).get("type", "")
    return ""


def tabel(df, **kw):
    """st.dataframe cu „—” în celulele goale și separatori de mii la coloanele cu numere mari.

    Coloanele care au deja `column_config` rămân neatinse.
    """
    import pandas as pd

    cfg = dict(kw.pop("column_config", None) or {})
    if kw.pop("use_container_width", None):
        kw.setdefault("width", "stretch")
    if isinstance(df, pd.DataFrame):
        df = df.copy()
        for col in df.columns:
            if pd.api.types.is_bool_dtype(df[col]):
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                e_cod = str(col).lower() in _COLOANE_COD
                if col not in cfg and not e_cod and df[col].abs().max() >= _NUMAR_MARE:
                    cfg[col] = st.column_config.NumberColumn(format="localized")
            elif _e_text(df[col]) and _tip_coloana(cfg.get(col)) not in _TIPURI_FARA_TEXT:
                df[col] = df[col].where(df[col].notna(), "—")
    return st.dataframe(df, column_config=cfg or None, **kw)


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"## {title}")
    if subtitle:
        st.markdown(f"<div class='solomonar-hero'>{subtitle}</div>", unsafe_allow_html=True)


def kpi_card(col, label: str, value: str, help: str = "") -> None:
    col.metric(label, value, help=help or None)


def sidebar_brand() -> None:
    st.sidebar.markdown(
        f"<div style='font-size:19px;font-weight:600;color:{TEXT}'>Solomonar</div>"
        f"<div style='font-size:13px;color:{TEXT_DIM};margin-bottom:8px'>{data_freshness()}</div>",
        unsafe_allow_html=True)


_LUNI = ("ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august",
         "septembrie", "octombrie", "noiembrie", "decembrie")


def data_freshness() -> str:
    """„Date din 27 septembrie 2026 (acum 53 de zile)” — din stats.json; gol dacă lipsește data."""
    from datetime import datetime, timezone

    from app import data
    raw = (data.stats() or {}).get("generat")
    try:
        gen = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return ""
    zile = (datetime.now(timezone.utc) - gen).days
    varsta = "astăzi" if zile <= 0 else "ieri" if zile == 1 else f"acum {zile} de zile"
    return f"Date din {gen.day} {_LUNI[gen.month - 1]} {gen.year} ({varsta})"
