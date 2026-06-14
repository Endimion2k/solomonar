"""Temă vizuală SOLOMONAR — tokens de culoare, template Plotly, paletă partide, helpers UI.

Adaptat din cdep-client, rebrand SOLOMONAR (transparența întregului aparat de stat).
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

BG = "#0b0d12"
SURFACE = "#141821"
SURFACE_2 = "#1a1f2c"
BORDER = "#232838"
TEXT = "#e6e8ee"
TEXT_DIM = "#8a92a6"
TEXT_FAINT = "#5b6478"

ACCENT = "#8b5cf6"
ACCENT_2 = "#22d3ee"
SUCCESS = "#10b981"
WARNING = "#f59e0b"
DANGER = "#ef4444"

PARTY_COLORS = {
    "psd": "#e11d48", "pnl": "#facc15", "usr": "#0ea5e9", "aur": "#fbbf24",
    "udmr": "#22c55e", "pot": "#a855f7", "sos": "#f97316", "pmp": "#a855f7",
    "pro": "#06b6d4", "alde": "#16a34a", "fd": "#3b82f6", "neafiliati": "#6b7280",
}
# încredere graf
CONF_COLORS = {"high": "#10b981", "context": "#22d3ee", "candidat": "#8a92a6"}
NEUTRAL_PALETTE = ["#8b5cf6", "#22d3ee", "#10b981", "#f59e0b", "#ef4444", "#0ea5e9",
                   "#a855f7", "#14b8a6", "#f472b6", "#eab308"]


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
        font=dict(color=TEXT, family="Inter, system-ui, sans-serif", size=13),
        colorway=NEUTRAL_PALETTE,
        xaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER),
        yaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER),
        margin=dict(l=40, r=20, t=40, b=40), hoverlabel=dict(bgcolor=SURFACE_2),
    )
    pio.templates["solomonar"] = tmpl
    pio.templates.default = "solomonar"
    st.markdown(f"""<style>
      .stApp {{ background:{BG}; color:{TEXT}; }}
      section[data-testid="stSidebar"] {{ background:{SURFACE}; border-right:1px solid {BORDER}; }}
      [data-testid="stMetric"] {{ background:{SURFACE}; border:1px solid {BORDER};
        border-radius:12px; padding:14px 16px; }}
      [data-testid="stMetricValue"] {{ color:{TEXT}; font-size:26px; }}
      [data-testid="stMetricLabel"] {{ color:{TEXT_DIM}; }}
      h1,h2,h3 {{ color:{TEXT}; letter-spacing:-.01em; }}
      .solomonar-hero {{ font-size:13px; color:{TEXT_DIM}; margin:-6px 0 14px; }}
      .stDataFrame {{ border:1px solid {BORDER}; border-radius:10px; }}
      a {{ color:{ACCENT_2}; }}
      .badge {{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:11px;
        border:1px solid {BORDER}; color:{TEXT_DIM}; }}
    </style>""", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"## {title}")
    if subtitle:
        st.markdown(f"<div class='solomonar-hero'>{subtitle}</div>", unsafe_allow_html=True)


def kpi_card(col, label: str, value: str, help: str = "") -> None:
    col.metric(label, value, help=help or None)


def sidebar_brand() -> None:
    st.sidebar.markdown(
        f"<div style='font-size:22px;font-weight:700;color:{TEXT};letter-spacing:-.02em'>"
        f"RO<span style='color:{ACCENT_2}'>MEGA</span></div>"
        f"<div style='font-size:11px;color:{TEXT_DIM};margin-bottom:8px'>"
        f"transparența aparatului de stat</div>", unsafe_allow_html=True)
