"""Construcció d'URLs de rànquings — suporta els dos formats coneguts.

Format ANTIC (fins ~rànquing 112 de tres bandes):
    {base}/ca/jugador/ranking/data/{num_seq}/{modalitat_codi_fcb}#red

Format NOU (a partir d'un moment indeterminat entre 112 i 121):
    {base}/ca/jugador/ranking/datahome/{num_seq}/{modalitat_codi_fcb}#red

Tots dos retornen contingut equivalent. Provem `datahome` primer i fem
fallback a `data` si retorna 404 / pàgina buida.
"""

from __future__ import annotations

from typing import Literal

UrlFormat = Literal["data", "datahome"]
URL_FORMATS: tuple[UrlFormat, ...] = ("datahome", "data")


def ranking_url(base_url: str, num_seq: int, modalitat_codi_fcb: int, fmt: UrlFormat) -> str:
    base = base_url.rstrip("/")
    return f"{base}/ca/jugador/ranking/{fmt}/{num_seq}/{modalitat_codi_fcb}#red"


def all_ranking_url_candidates(
    base_url: str, num_seq: int, modalitat_codi_fcb: int
) -> list[tuple[UrlFormat, str]]:
    """Retorna els dos formats per ordre de preferència (nou primer)."""
    return [
        (fmt, ranking_url(base_url, num_seq, modalitat_codi_fcb, fmt)) for fmt in URL_FORMATS
    ]
