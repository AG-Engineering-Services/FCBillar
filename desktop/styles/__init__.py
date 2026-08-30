"""Full d'estils de l'escriptori, derivat dels tokens d'AGenginyeria.

El tema d'abans era el de fàbrica de qualsevol aplicació fosca: fons `#1f2329`,
accent `#2d6cdf`, Segoe UI i cantonades de 6 px. Ara la base la genera
`qss(FOSC)` dels estàndards —betum, Verdana, filets d'1 px, radi de 2 px, cap
degradat i cap ombra— i aquí només hi ha el que és d'aquesta aplicació: els noms
d'objecte que fa servir la interfície.

Els tokens són la font de veritat i s'importen; no se'n copia cap valor.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ESTANDARDS = Path(__file__).resolve().parents[3] / "ag-standards" / "skills" / "ag-disseny"
if str(_ESTANDARDS) not in sys.path:
    sys.path.insert(0, str(_ESTANDARDS))

from tokens import FOSC, per_familia, qss  # noqa: E402

# Família de producte: `gestio`. El vermell de l'escut de la federació és marca
# d'identitat i no es fa servir mai com a color d'acció; a l'escriptori ni tan
# sols hi surt, perquè no hi ha capçalera de marca.
TOKENS = per_familia(FOSC, "gestio")


def _propi(t) -> str:
    """Regles dels widgets que són d'aquesta aplicació i no del sistema."""
    return f"""
/* --- Barra lateral: llista, no marc. Plana i sense degradat. --- */
QListWidget#sidebar {{
    background: {t.raised};
    border: none;
    border-right: {t.hairline}px solid {t.rule};
    color: {t.ink_soft};
    padding: {t.space[1]}px 0;
    outline: none;
}}
QListWidget#sidebar::item {{
    padding: {t.space[1]}px {t.space[2]}px;
    border-radius: {t.radius}px;
    margin: 1px {t.space[1]}px;
}}
QListWidget#sidebar::item:selected {{
    background: {t.accent};
    color: {t.accent_ink};
}}
QListWidget#sidebar::item:hover:!selected {{
    background: {t.surface};
    color: {t.ink};
}}

/* Les etiquetes hereten el fons de pàgina i el pintaven damunt de la targeta,
   cosa que deixava un rectangle a dins de cada indicador. Van transparents. */
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}

/* --- Indicadors: la xifra en monoespaiada, l'etiqueta en registre tècnic. --- */
QFrame#kpiCard {{
    background: {t.surface};
    border: {t.hairline}px solid {t.rule};
    border-radius: {t.radius}px;
}}
QLabel#kpiValue {{
    font-family: {t.font_data};
    font-size: {t.size_pt + 8}pt;
    font-weight: 700;
    color: {t.ink};
}}
QLabel#kpiLabel {{
    font-family: {t.font_data};
    font-size: {t.size_pt - 2}pt;
    font-weight: 600;
    color: {t.ink_muted};
    letter-spacing: 1px;
}}

/* --- Títols. Sense adorns: el pes i l'espai ja els separen. --- */
QLabel#sectionTitle {{
    font-size: {t.size_pt + 4}pt;
    font-weight: 700;
    color: {t.ink};
}}
QLabel#subSectionTitle {{
    font-size: {t.size_pt + 1}pt;
    font-weight: 700;
    color: {t.ink_soft};
}}
QLabel#fieldLabel {{
    font-family: {t.font_data};
    font-size: {t.size_pt - 2}pt;
    font-weight: 600;
    color: {t.ink_muted};
    letter-spacing: 1px;
}}

/* --- Pestanyes: filet a sota, mai càpsules. --- */
QTabWidget::pane {{
    border: {t.hairline}px solid {t.rule};
    border-radius: {t.radius}px;
}}
QTabBar::tab {{
    background: transparent;
    color: {t.ink_muted};
    border: none;
    border-bottom: 2px solid transparent;
    padding: {t.space[1]}px {t.space[2]}px;
    margin-right: {t.space[1]}px;
}}
QTabBar::tab:selected {{
    color: {t.accent};
    border-bottom-color: {t.accent};
}}
QTabBar::tab:hover:!selected {{ color: {t.ink}; }}

/* --- Reingesta i registre: el log és sortida d'aparell, va monoespaiat. --- */
QFrame#reingestPanel {{
    background: {t.surface};
    border: {t.hairline}px solid {t.rule};
    border-radius: {t.radius}px;
}}
QLabel#reingestPanelTitle {{
    font-weight: 700;
    color: {t.ink};
}}
QPlainTextEdit#scrapingLog {{
    font-family: {t.font_data};
    background: {t.ground};
    border: {t.hairline}px solid {t.rule};
}}
QLabel#scrapingStatus {{
    font-family: {t.font_data};
    color: {t.ink_soft};
}}

/* --- Taules: densitat alta. Els nostres usuaris comparen files. --- */
QTableWidget::item {{
    padding: {t.space[0]}px {t.space[2]}px;
}}

/* --- Barres de desplaçament: filet, no relleu. --- */
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {t.ground};
    border: none;
    width: 10px;
    height: 10px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {t.rule_strong};
    border-radius: {t.radius}px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* --- Àrees de desplaçament: cap marc doble. --- */
QScrollArea, QScrollArea > QWidget > QWidget {{ border: none; }}
QSplitter::handle {{ background: {t.rule}; }}
"""


def full_estils() -> str:
    """El QSS sencer: la base del sistema més el que és d'aquesta aplicació."""
    return qss(TOKENS) + _propi(TOKENS)
