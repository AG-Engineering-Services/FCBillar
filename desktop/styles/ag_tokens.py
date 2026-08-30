# GENERAT — no editis aquest fitxer.
#
# Còpia de ag-standards/skills/ag-disseny/tokens.py, que és la font de veritat.
# Es refresca amb:
#
#     uv run python scripts/sync_tokens_ag.py --escriu
#
# Hi és perquè l'escriptori ha d'arrencar amb aquest repositori sol, sense tenir
# els estàndards al costat. Si vols canviar un color, canvia'l als estàndards,
# passa-hi l'auditoria de contrast i torna a sincronitzar.

# -*- coding: utf-8 -*-
"""Tokens visuals d'AGenginyeria per a la linia d'escriptori (PySide6 / QSS).

Mateixos valors que tokens.css. Si canvia un, canvien els dos.
Els colors de grafic estan validats amb dataviz/scripts/validate_palette.js
en els dos modes; no els toquis sense tornar-lo a executar.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tokens:
    """Paleta i mesures d'un mode. Els components no porten colors literals."""

    mode: str  # "clar" | "fosc"

    # Superficies i tinta
    surface: str
    ground: str
    raised: str
    rule: str
    rule_strong: str
    ink: str
    ink_soft: str
    ink_muted: str

    # Accent: l'unic color d'accio. Depen de la familia (veure per_familia).
    accent: str
    accent_hover: str
    accent_ink: str
    accent_soft: str   # fons tenyit de la familia; el text a sobre va en tinta normal
    focus: str

    # Estat. SEMPRE amb icona i etiqueta, mai nomes color.
    # El color d'estat es MARCA (icona, vora): li basta 3:1.
    # El text d'una pindola va en tinta normal sobre el fons _bg.
    # Quan l'estat ha de ser text, es fa servir _text, que passa AA.
    bo: str
    bo_bg: str
    bo_text: str
    avis: str
    avis_bg: str
    avis_text: str
    greu: str
    greu_bg: str
    greu_text: str
    critic: str
    critic_bg: str
    critic_text: str

    # Grafics: ordre fix, mai en cicle.
    categorica: tuple[str, ...]
    sequencial: tuple[str, ...]
    divergent: tuple[str, ...]

    # Tipografia
    # Verdana: la mes llegible en pantalla, xifres amples i clares. Es ampla,
    # per aixo la base va a 15px/10pt i no mes. Tahoma es la versio estreta.
    font: str = "Verdana, Tahoma, DejaVu Sans, sans-serif"
    font_data: str = "Consolas, Cascadia Mono, DejaVu Sans Mono, monospace"
    size_pt: float = 9.5

    # Estructura: convencions de planol
    radius: int = 2
    hairline: int = 1
    space: tuple[int, ...] = field(default=(4, 8, 12, 16, 24, 32))


CLAR = Tokens(
    mode="clar",
    surface="#FFFFFF",
    ground="#F4F6F3",
    raised="#E8EBE8",
    rule="#D6DAD6",
    rule_strong="#B8BEB9",
    ink="#161917",
    ink_soft="#4E544F",
    ink_muted="#6A716B",   # 4,61:1 sobre pagina; el bitum-500 no hi arribava
    accent="#1A5C8A",       # gestio per defecte; ferms el reassigna
    accent_hover="#123F61",
    accent_ink="#FFFFFF",
    accent_soft="#DEEAF2",
    focus="#2E7BB0",
    bo="#157A4A", bo_bg="#DCEFE4", bo_text="#157A4A",
    avis="#C08018", avis_bg="#F7EDD9", avis_text="#A16900",
    greu="#B0432A", greu_bg="#F7E4DE", greu_text="#B0432A",
    critic="#A81E12", critic_bg="#F8DEDB", critic_text="#A81E12",
    categorica=("#0F7A5A", "#B0432A", "#2A6FB0", "#C08018", "#7A4FA8"),
    sequencial=("#DDEFE8", "#A8D6C5", "#4EAE8E", "#0F7A5A", "#0B5B43", "#08402F"),
    divergent=("#B0432A", "#DFA08E", "#939A94", "#8FB4D8", "#2A6FB0"),
)

FOSC = Tokens(
    mode="fosc",
    surface="#1C201E",
    ground="#161917",
    raised="#212523",
    rule="#333833",
    rule_strong="#4E544F",
    ink="#E7EAE7",
    ink_soft="#939A94",
    ink_muted="#828A84",   # 4,64:1 sobre targeta fosca
    accent="#4A90C4",
    accent_hover="#6BA9D6",
    accent_ink="#0B1512",
    accent_soft="#172935",
    focus="#6BA9D6",
    bo="#249272", bo_bg="#12251F", bo_text="#2D9878",
    avis="#B8811F", avis_bg="#2A2113", avis_text="#B8811F",
    greu="#CB5C3E", greu_bg="#2B1A15", greu_text="#D86749",
    critic="#D64534", critic_bg="#2E1614", critic_text="#E95745",
    categorica=("#249272", "#CB5C3E", "#4380C4", "#B8811F", "#8F68BE"),
    sequencial=("#12251F", "#14503D", "#0F7A5A", "#249272", "#4EAE8E", "#A8D6C5"),
    divergent=("#CB5C3E", "#8A4433", "#6E756F", "#35597F", "#4380C4"),
)

TEMES: dict[str, Tokens] = {"clar": CLAR, "fosc": FOSC}

# Families de producte. Nomes canvia el color d'accio; tota la resta es compartida.
FAMILIES: dict[str, dict[str, dict[str, str]]] = {
    "ferms": {   # CFRoads, seguiment d'emissions
        "clar": {"accent": "#157A4A", "accent_hover": "#0E5533",
                 "accent_ink": "#FFFFFF", "accent_soft": "#DCEFE4",
                 "focus": "#1F9A5F"},
        "fosc": {"accent": "#2FA96C", "accent_hover": "#4FC088",
                 "accent_ink": "#0B1512", "accent_soft": "#12261B",
                 "focus": "#4FC088"},
    },
    "gestio": {  # contractacio, normativa, gestio
        "clar": {"accent": "#1A5C8A", "accent_hover": "#123F61",
                 "accent_ink": "#FFFFFF", "accent_soft": "#DEEAF2",
                 "focus": "#2E7BB0"},
        "fosc": {"accent": "#4A90C4", "accent_hover": "#6BA9D6",
                 "accent_ink": "#0B1512", "accent_soft": "#172935",
                 "focus": "#6BA9D6"},
    },
}


def per_familia(t: Tokens, familia: str) -> Tokens:
    """Retorna els tokens amb l'accent de la familia demanada."""
    from dataclasses import replace
    if familia not in FAMILIES:
        raise KeyError(f"familia desconeguda: {familia!r}; opcions: {list(FAMILIES)}")
    return replace(t, **FAMILIES[familia][t.mode])


def qss(t: Tokens) -> str:
    """Full d'estils Qt derivat dels tokens.

    Sense degradats, sense ombres, radi de 2 px i filets d'1 px: son les
    convencions de planol de la skill, no preferencies.
    """
    return f"""
* {{
    font-family: {t.font};
    font-size: {t.size_pt}pt;
}}
QWidget {{
    background: {t.ground};
    color: {t.ink};
}}
QFrame#card, QGroupBox {{
    background: {t.surface};
    border: {t.hairline}px solid {t.rule};
    border-radius: {t.radius}px;
}}
QGroupBox::title {{
    color: {t.ink_soft};
    subcontrol-origin: margin;
    left: {t.space[1]}px;
    padding: 0 {t.space[0]}px;
}}
QPushButton {{
    background: {t.surface};
    color: {t.ink};
    border: {t.hairline}px solid {t.rule_strong};
    border-radius: {t.radius}px;
    padding: {t.space[0]}px {t.space[2]}px;
}}
QPushButton:hover {{ background: {t.raised}; }}
QPushButton:focus {{ border-color: {t.focus}; }}
QPushButton[primary="true"] {{
    background: {t.accent};
    color: {t.accent_ink};
    border-color: {t.accent};
}}
QPushButton[primary="true"]:hover {{ background: {t.accent_hover}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: {t.surface};
    border: {t.hairline}px solid {t.rule_strong};
    border-radius: {t.radius}px;
    padding: {t.space[0]}px {t.space[1]}px;
    selection-background-color: {t.accent};
    selection-color: {t.accent_ink};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: {t.hairline}px solid {t.focus};
}}
/* Xifres alineades: monoespaiada a les vistes de dades */
QTableView, QTreeView {{
    background: {t.surface};
    alternate-background-color: {t.ground};
    gridline-color: {t.rule};
    border: {t.hairline}px solid {t.rule};
    selection-background-color: {t.accent};
    selection-color: {t.accent_ink};
    font-family: {t.font_data};
}}
QHeaderView::section {{
    background: {t.ground};
    color: {t.ink_soft};
    border: none;
    border-bottom: {t.hairline}px solid {t.rule_strong};
    padding: {t.space[0]}px {t.space[1]}px;
    font-family: {t.font};
}}
/* Barra lateral: PLANA. Cap degradat (antipatro de la skill). */
QFrame#sidebar {{
    background: {t.raised};
    border: none;
    border-right: {t.hairline}px solid {t.rule};
}}
QToolTip {{
    background: {t.surface};
    color: {t.ink};
    border: {t.hairline}px solid {t.rule_strong};
    padding: {t.space[0]}px;
}}

/* --- La signatura (R4): xip de procedencia i panell de traca ---
   Els widgets els construeix traca.py; aqui nomes hi ha el vestit.
   QSS no te text-transform ni letter-spacing: la versaleta de #agEt la fa
   traca.py en Python, no s'hi pot fer aqui. */
QLabel#agCita {{
    font-family: {t.font_data};
    font-size: {t.size_pt - 2}pt;
    color: {t.ink_muted};
    border: {t.hairline}px solid {t.rule};
    border-radius: {t.radius}px;
    padding: 0 {t.space[0]}px;
}}
QLabel#agCita[clicable="true"]:hover {{
    color: {t.ink};
    background: {t.raised};
    border-color: {t.rule_strong};
}}
QLabel#agEt {{
    font-family: {t.font_data};
    font-size: {t.size_pt - 2.5}pt;
    color: {t.ink_muted};
}}
QLabel#agTitol {{
    font-size: {t.size_pt + 1.5}pt;
    font-weight: bold;
    color: {t.ink};
}}
QLabel#agNum, QLabel#agXifra {{
    font-family: {t.font_data};
    color: {t.ink};
}}
QLabel#agXifra {{ font-size: {t.size_pt + 4}pt; font-weight: bold; }}
QLabel#agFormula {{
    font-family: {t.font_data};
    font-size: {t.size_pt - 1}pt;
    background: {t.ground};
    border: {t.hairline}px solid {t.raised};
    border-radius: {t.radius}px;
    padding: {t.space[0]}px {t.space[1]}px;
}}
QLabel#agNota {{
    font-size: {t.size_pt - 1}pt;
    color: {t.ink_muted};
}}
/* El resultat va encapcalat per l'accent: es l'unica xifra de tota la cadena
   que l'usuari havia demanat. */
QFrame#agTracaResultat {{
    background: {t.accent_soft};
    border: {t.hairline}px solid {t.accent};
    border-radius: {t.radius}px;
}}
QDialog#agTraca {{ background: {t.surface}; }}
"""


__all__ = ["CLAR", "FAMILIES", "FOSC", "TEMES", "Tokens", "per_familia", "qss"]
