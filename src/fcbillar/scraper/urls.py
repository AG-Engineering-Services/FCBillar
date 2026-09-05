"""URLs del web de la FCB després del canvi d'agost de 2026.

El web es va partir en tres (vegeu `docs/canvi-web-fcb-2026.md`):

- `intranet.fcbillar.cat/frontend/…` — competició, **tota pública**;
- `fcbillar.cat` — WordPress: clubs, documents i PDF;
- `intranet.fcbillar.cat/{jugador,club}/login` — panells privats, que ja no
  contenen res del que ingerim.

Els rànquings van passar de rutes a paràmetres i, sobretot, de dos *formats*
de la mateixa pàgina a dos **endpoints amb significat diferent**: `llistat` és
el rànquing vigent i `historial` són els quinze anteriors. Ja no cal provar-ne
un i fer marxa enrere: la pàgina de llistat diu quin és cadascun.
"""

from __future__ import annotations

from typing import Literal

INTRANET = "https://intranet.fcbillar.cat"
WEB = "https://fcbillar.cat"

#: `llistat` = rànquing vigent · `historial` = els quinze anteriors.
Vigencia = Literal["llistat", "historial"]


def _u(base: str, *parts: object) -> str:
    return "/".join([base.rstrip("/"), *(str(p).strip("/") for p in parts)])


# --------------------------- rànquings ---------------------------


def rankings_llistat(base: str = INTRANET) -> str:
    """Índex de rànquings: el vigent i els quinze d'històric, amb la data."""
    return _u(base, "frontend/rankings/llistat")


def ranking_dades(
    num_seq: int, modalitat_codi_fcb: int, vigencia: Vigencia, base: str = INTRANET
) -> str:
    return (
        f"{_u(base, 'frontend/rankings', vigencia + '-dades')}"
        f"?idranking={num_seq}&idmodalitat={modalitat_codi_fcb}"
    )


def ranking_partides(
    num_seq: int,
    modalitat_codi_fcb: int,
    jugador_fcb_id: int | str,
    vigencia: Vigencia,
    base: str = INTRANET,
) -> str:
    return (
        f"{_u(base, 'frontend/rankings', vigencia + '-partides')}"
        f"?idranking={num_seq}&idmodalitat={modalitat_codi_fcb}"
        f"&idjugador={jugador_fcb_id}"
    )


# --------------------------- lliga ---------------------------


def lligues_llistat(base: str = INTRANET) -> str:
    return _u(base, "frontend/lligues/llistat")


def lligues_divisions(lliga: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/lligues/divisions", lliga)


def lligues_grups(lliga: int, divisio: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/lligues/grups", lliga, divisio)


def lligues_jornades(lliga: int, divisio: int, grup: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/lligues/jornades", lliga, divisio, grup)


def lligues_encontres(
    lliga: int, divisio: int, grup: int, jornada: int, base: str = INTRANET
) -> str:
    return _u(base, "frontend/lligues/encontres", lliga, divisio, grup, jornada)


def lligues_partides(
    lliga: int, divisio: int, grup: int, jornada: int, encontre: int, base: str = INTRANET
) -> str:
    """Detall d'un encontre: sèrie major, àrbitre i assistència per partida.

    ATENCIÓ: des del canvi de web retorna HTTP 500 amb tots els encontres
    provats de la temporada 2025-26. La ruta existeix (500, no 404) i els seus
    propis enllaços hi apunten, o sigui que sembla un error del portal. El
    detall equivalent de copa sí que funciona. Cal reprovar-ho quan comenci la
    lliga 2026-27.
    """
    return _u(base, "frontend/lligues/partides", lliga, divisio, grup, jornada, encontre)


def lligues_classificacio(lliga: int, divisio: int, grup: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/lligues/classificacio", lliga, divisio, grup)


def lligues_inscripcions(lliga: int, base: str = INTRANET) -> str:
    """Equips inscrits amb el seu club. No existia al web antic."""
    return _u(base, "frontend/lligues/inscripcions", lliga)


def lligues_participants(lliga: int, club: int, base: str = INTRANET) -> str:
    """Els jugadors que un club inscriu a una lliga, amb la mitjana i el fitxatge.

    Va aparèixer el setembre de 2026, penjada del botó «Veure inscrits» de la
    pàgina d'inscripcions. És la primera vegada que la federació publica de qui
    està fet cada club: fins ara ho havíem d'estimar de qui havia jugat.

    L'`id` de club és el de la federació i només surt a l'enllaç d'aquell botó,
    o sigui que aquesta pàgina no es pot demanar sense passar abans per
    `lligues_inscripcions`.

    És **per club, no per equip**: diu qui hi juga, no a quin equip (A, B, C…)
    va cadascú.
    """
    return _u(base, "frontend/lligues/participants", lliga, club)


# --------------------------- individuals (opens i catalans) ---------------------------


def individuals_llistat(base: str = INTRANET) -> str:
    return _u(base, "frontend/individuals/llistat")


def individuals_divisions(torneig: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/individuals/divisions", torneig)


def individuals_fases(torneig: int, divisio: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/individuals/fases", torneig, divisio)


def individuals_grups(torneig: int, divisio: int, fase: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/individuals/grups", torneig, divisio, fase)


def individuals_partides_grup(
    torneig: int, divisio: int, fase: int, grup: int, base: str = INTRANET
) -> str:
    return _u(base, "frontend/individuals/partides-grup", torneig, divisio, fase, grup)


def individuals_partides_eliminatories(
    torneig: int, divisio: int, eliminatoria: int, base: str = INTRANET
) -> str:
    return _u(base, "frontend/individuals/partides-eliminatories", torneig, divisio, eliminatoria)


def individuals_inscripcions(torneig: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/individuals/inscripcions", torneig)


# --------------------------- copa ---------------------------


def copa_llistat(base: str = INTRANET) -> str:
    return _u(base, "frontend/copa/llistat")


def copa_fase_grups(edicio: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/copa/fase-grups", edicio)


def copa_grups(edicio: int, jornada: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/copa/grups", edicio, jornada)


def copa_encontres_grup(edicio: int, jornada: int, grup: int, base: str = INTRANET) -> str:
    return _u(base, "frontend/copa/encontres-grup", edicio, jornada, grup)


def copa_partides_grup(
    edicio: int,
    jornada: int,
    grup: int,
    encontre: int,
    equip_a: int,
    equip_b: int,
    base: str = INTRANET,
) -> str:
    return _u(
        base, "frontend/copa/partides-grup", edicio, jornada, grup, encontre, equip_a, equip_b
    )


# --------------------------- WordPress ---------------------------


def web_clubs(base: str = WEB) -> str:
    """Llistat oficial de clubs, ara amb telèfon, correu, adreça i web."""
    return _u(base, "federacio/llistat-de-clubs-federacio-catalana-de-billar/")


def web_sitemap_documents(base: str = WEB) -> str:
    """Sitemap de Yoast amb totes les pàgines de document (calendari, PDF…).

    Substitueix el llistat paginat `/ca/docs/...` del web antic: aquí hi són
    tots d'una tirada, i cada pàgina de document porta l'enllaç directe al PDF.
    """
    return _u(base, "wpfd_file-sitemap.xml")
