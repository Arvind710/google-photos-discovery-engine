"""Page furniture shared by the section pages — the Myntra design language
([CTX] §16): numbered PARTs, one conclusion, one visual and a one-sentence
verdict each; no tabs; Okabe-Ito colours; raw HTML only through st.html, and
every piece of user or model text escaped before it reaches it.

The Data Bank keeps its own copies (it predates this module and is verified
live); Analysis and Opportunities use these.
"""

from __future__ import annotations

import html

import plotly.graph_objects as go
import streamlit as st

from lib import nav

MUTED = "#8a8a8a"
HAIR = "rgba(128,128,128,.28)"
BLUE, SKY, ORANGE, GREEN, PINK, RED = "#0072B2", "#56B4E9", "#E69F00", "#009E73", "#CC79A7", "#D55E00"
GREY = "#BBBBBB"

esc = html.escape


def section(num: int, title: str, sub: str = "", colour: str = BLUE, slug: str = "") -> None:
    if slug:
        st.html(nav.anchor(slug))
    st.html(
        f"<div style='margin:2.4rem 0 .5rem'>"
        f"<div style='display:flex;align-items:center;gap:.7rem'>"
        f"<span style='font-size:.68rem;font-weight:800;letter-spacing:.16em;"
        f"color:{colour}'>PART {num}</span>"
        f"<span style='flex:1;height:2px;background:{colour};opacity:.3'></span></div>"
        f"<div style='font-size:1.5rem;font-weight:750;line-height:1.25;"
        f"margin:.4rem 0 .2rem'>{title}</div>"
        + (f"<div style='color:{MUTED};font-size:.93rem;line-height:1.55;"
           f"max-width:70ch'>{sub}</div>" if sub else "")
        + "</div>")


def verdict(text: str, colour: str) -> None:
    st.html(f"<div style='border-left:4px solid {colour};padding:.6rem 0 .6rem .85rem;"
            f"margin:.9rem 0 .2rem;font-size:1.02rem;line-height:1.5;max-width:80ch'>"
            f"{text}</div>")


def note(text: str) -> None:
    st.html(f"<div style='color:{MUTED};font-size:.82rem;line-height:1.5;"
            f"margin:.35rem 0 0;max-width:80ch'>{text}</div>")


def card(body: str, colour: str = HAIR, *, dim: bool = False) -> str:
    return (f"<div style='border:1px solid {HAIR};border-left:4px solid {colour};"
            f"border-radius:7px;padding:.7rem .9rem;margin:.5rem 0;"
            f"{'opacity:.62;' if dim else ''}'>{body}</div>")


def chip(text: str, colour: str) -> str:
    return (f"<span style='display:inline-block;font-size:.7rem;font-weight:700;"
            f"letter-spacing:.04em;padding:.08rem .45rem;border-radius:4px;"
            f"border:1px solid {colour};color:{colour}'>{text}</span>")


def hbar(labels: list[str], values: list[int], texts: list[str], colours, height=None) -> None:
    fig = go.Figure(go.Bar(
        x=values[::-1], y=labels[::-1], orientation="h", marker_color=colours[::-1],
        text=texts[::-1], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,}<extra></extra>"))
    fig.update_layout(height=height or 70 + 38 * len(labels), margin=dict(l=10, r=10, t=10, b=10),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      showlegend=False, yaxis=dict(showgrid=False),
                      xaxis=dict(visible=False, range=[0, max(values or [1]) * 2.3]))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def quote(span: str, cite: str) -> str:
    return (f"<div style='border-left:2px solid {HAIR};padding:.1rem 0 .1rem .7rem;"
            f"margin:.35rem 0;font-size:.86rem;line-height:1.45'>“{esc(span)}”"
            f"<span style='color:{MUTED};font-size:.74rem'> — {esc(cite)}</span></div>")
