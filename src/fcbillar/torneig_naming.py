"""Nom i tipus canònics dels torneigs individuals (font de veritat única).

El portal escriu el nom de cada torneig de manera inconsistent entre temporades
(`VI OPEN MATARÓ "LES SANTES" - OPEN MATARÓ`, o el mateix Memorial sense la
paraula OPEN un any i amb ella un altre). Aquest mòdul centralitza dues decisions:

- `clean_torneig_nom`: treu el sufix redundant (la divisió que només repeteix el
  nom del torneig) i el "- ÚNICA"/"- DIVISIÓ ÚNICA".
- `torneig_tipus`: classifica de manera coherent en 'open' (trofeu amb nom propi)
  o 'campionat' (Campionat de Catalunya per modalitat+divisió). Independent de si
  el nom porta literalment la paraula OPEN.

S'usa a la ingesta (pipeline), a la neteja puntual de la BD i a la publicació al
cloud (cloud_sync), perquè el frontend només hagi de llegir el camp `tipus`.
"""

from __future__ import annotations

import re
import unicodedata

# Marcadors d'un trofeu amb nom propi → Open. CAMPIONAT/CATALUNYA tenen prioritat
# (un "Campionat de Catalunya" mai és un open encara que sigui a una ciutat).
_OPEN_MARKERS = ("OPEN", "MEMORIAL", "TROFEU", "CIUTAT", "GRAN PREMI", "CRITERIUM")

# Paraules genèriques que no compten com a "informació nova" al sufix d'una divisió
# a l'hora de detectar redundància (modalitats, articles, números romans buits...).
_STOP = {
    "DE",
    "DEL",
    "LA",
    "EL",
    "LES",
    "ELS",
    "I",
    "D",
    "3",
    "BANDES",
    "TRES",
    "LLIURE",
    "BANDA",
    "QUADRE",
}

_TOKEN_RE = re.compile(r"[A-Z0-9]+")
_UNICA_RE = re.compile(r"\s*-\s*(DIVISI[ÓO]\s+)?[ÚU]NICA\s*$", re.I)


def _nfd_upper(s: str) -> str:
    """Majúscules sense accents, per a comparacions robustes."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn"
    ).upper()


def _tokens(s: str) -> set[str]:
    return set(_TOKEN_RE.findall(_nfd_upper(s)))


def _is_redundant_suffix(head: str, tail: str) -> bool:
    """El sufix `tail` no aporta res respecte a `head` (tots els seus tokens
    significatius ja hi són) → és redundant i es pot treure."""
    head_tokens = _tokens(head)
    tail_tokens = {t for t in _tokens(tail) if t not in _STOP}
    return bool(tail_tokens) and tail_tokens <= head_tokens


def clean_torneig_nom(nom: str) -> str:
    """Nom de torneig sense sufix redundant ni '- ÚNICA'.

    Exemples:
      'VI OPEN MATARÓ "LES SANTES" - OPEN MATARÓ' → 'VI OPEN MATARÓ "LES SANTES"'
      'I OPEN CIUTAT DE VIC - OPEN VIC'           → 'I OPEN CIUTAT DE VIC'
      'MEMORIAL MIQUEL ESPONA - DIVISIÓ ÚNICA'    → 'MEMORIAL MIQUEL ESPONA'
      'TRES BANDES - 1A DIVISIÓ'                  → 'TRES BANDES - 1A DIVISIÓ' (intacte)
    """
    s = (nom or "").strip()
    s = _UNICA_RE.sub("", s).strip()
    if " - " in s:
        head, tail = s.rsplit(" - ", 1)
        if _is_redundant_suffix(head, tail):
            s = head.strip()
    return s


def torneig_tipus(nom: str) -> str:
    """'open' (trofeu amb nom propi) o 'campionat' (Campionat de Catalunya).

    Regla coherent entre temporades, independent de si surt la paraula OPEN:
      - Conté CAMPIONAT o CATALUNYA → 'campionat' (oficial).
      - Conté un marcador de trofeu propi (OPEN/MEMORIAL/CIUTAT/TROFEU/...) → 'open'.
      - Si no (només modalitat+divisió, p.ex. 'BANDA - HONOR') → 'campionat'.
    """
    u = _nfd_upper(nom)
    if "CAMPIONAT" in u or "CATALUNYA" in u:
        return "campionat"
    if any(m in u for m in _OPEN_MARKERS):
        return "open"
    return "campionat"
