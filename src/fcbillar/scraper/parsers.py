"""Parsers HTML per a les pàgines de l'intranet de fcbillar.cat."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup, Tag

from fcbillar.models import Player, RankingEntry

log = logging.getLogger(__name__)


# Format de l'href del link "Partides" dins de cada fila del rànquing:
#   ca/jugador/ranking/partideshome/{num_seq}/{modalitat}/{player_fcb_id}
_PARTIDES_HREF_RE = re.compile(
    r"ranking/partideshome/(\d+)/(\d+)/(\d+)"
)

# Format de l'href dels links de modalitat a l'historial:
#   ca/jugador/ranking/(data|datahome)/{num_seq}/{modalitat}
_HISTORIAL_HREF_RE = re.compile(
    r"ranking/(data|datahome)/(\d+)/(\d+)"
)


def _text(tag: Tag | None) -> str:
    return tag.get_text(strip=True) if tag is not None else ""


def _parse_float(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_int(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_punts(cell: str) -> tuple[int | None, int | None]:
    """Cel·la 'P / PT' té el format '16 / 20'."""
    parts = [p.strip() for p in cell.split("/")]
    if len(parts) != 2:
        return None, None
    return _parse_int(parts[0]), _parse_int(parts[1])


@dataclass
class RankingParseResult:
    """Resultat de parsejar una pàgina de rànquing."""

    num_seq: int
    modalitat_codi_fcb: int
    players: list[Player]
    entries: list[RankingEntry]


def parse_ranking(html: str, num_seq: int, modalitat_codi_fcb: int) -> RankingParseResult:
    """Parseja una pàgina de rànquing i retorna jugadors + entries.

    La pàgina té una taula amb columnes:
        Ranking | Jugador | MJ | MR | Rang | C | E | P / PT | Def | [Partides]

    El link "Partides" de cada fila conté el fcb_id del jugador. Si no podem
    extreure l'id, saltem la fila (només pot venir de canvis de format que
    no controlem encara).
    """
    soup = BeautifulSoup(html, "lxml")

    # La taula del rànquing viu dins de <section class="three fourths padded">.
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("No s'ha trobat la secció principal del rànquing")
    table = section.find("table")
    if table is None:
        raise ValueError("No s'ha trobat la taula del rànquing dins la secció")

    players: list[Player] = []
    entries: list[RankingEntry] = []
    seen_player_ids: set[str] = set()

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        # La primera fila és <th> (capçalera); files de dades tenen 10 <td>
        if len(cells) < 9:
            continue
        try:
            entry, player = _parse_ranking_row(cells, num_seq, modalitat_codi_fcb)
        except _SkipRow as e:
            log.debug("Salto fila: %s", e)
            continue
        if player.fcb_id not in seen_player_ids:
            players.append(player)
            seen_player_ids.add(player.fcb_id)
        entries.append(entry)

    return RankingParseResult(
        num_seq=num_seq,
        modalitat_codi_fcb=modalitat_codi_fcb,
        players=players,
        entries=entries,
    )


class _SkipRow(Exception):
    """Fila que no podem parsejar — la saltem en silenci."""


def _parse_ranking_row(
    cells: list[Tag], num_seq: int, modalitat_codi_fcb: int
) -> tuple[RankingEntry, Player]:
    # cells: [Ranking, Jugador, MJ, MR, Rang, C, E, P/PT, Def, <Partides>]
    posicio = _parse_int(_text(cells[0]))
    nom = _text(cells[1])
    mj = _parse_float(_text(cells[2]))
    mr = _parse_float(_text(cells[3]))
    rang = _parse_float(_text(cells[4]))
    caramboles = _parse_int(_text(cells[5]))
    entrades = _parse_int(_text(cells[6]))
    punts, punts_totals = _parse_punts(_text(cells[7]))
    definitiva = _text(cells[8]).strip().lower() == "si"

    # L'última cel·la conté el link "Partides" amb l'id del jugador.
    fcb_id = _extract_player_fcb_id(cells[-1])
    if fcb_id is None:
        raise _SkipRow(f"fila sense link de partides parsejable (posicio={posicio}, nom={nom!r})")

    player = Player(fcb_id=fcb_id, nom=nom)
    # MJ = mitjana del jugador; MR = mitjana dels contraris (a extras).
    # El nombre de partides no es publica al rànquing — surt a partideshome.
    entry = RankingEntry(
        ranking_num_seq=num_seq,
        ranking_modalitat=modalitat_codi_fcb,
        player_fcb_id=fcb_id,
        posicio=posicio,
        mitjana_general=mj,
        mitjana_particular=None,
        partides=None,
        extras={
            "mitjana_contraris": mr,
            "rang": rang,
            "caramboles": caramboles,
            "entrades": entrades,
            "punts": punts,
            "punts_totals": punts_totals,
            "definitiva": definitiva,
        },
    )
    return entry, player


def _extract_player_fcb_id(cell: Tag) -> str | None:
    link = cell.find("a", href=True)
    if link is None:
        return None
    m = _PARTIDES_HREF_RE.search(link["href"])
    if m is None:
        return None
    return m.group(3)  # el tercer grup és el player_fcb_id


# --------------------------- historial ---------------------------


@dataclass(frozen=True)
class HistorialEntry:
    """Una fila de l'historial: una data amb els links a cada modalitat."""

    data: date
    rankings: dict[int, tuple[str, int]]  # modalitat_codi_fcb -> (format_url, num_seq)


def parse_ranking_historial(html: str) -> list[HistorialEntry]:
    """Parseja /ca/jugador/ranking/historial.

    La taula té com a capçalera: Data | Modalitats (colspan=5), i cada fila
    de dades té una primera <td> amb la data ISO i les altres amb un <a> per
    modalitat. La URL conté el format (`data` o `datahome`), el num_seq i el
    codi de modalitat.
    """
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("No s'ha trobat la secció principal de l'historial")
    table = section.find("table")
    if table is None:
        raise ValueError("No s'ha trobat la taula d'historial")

    out: list[HistorialEntry] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        data_str = _text(cells[0])
        try:
            data_val = date.fromisoformat(data_str)
        except ValueError:
            continue  # fila no de dades
        rankings: dict[int, tuple[str, int]] = {}
        for cell in cells[1:]:
            link = cell.find("a", href=True)
            if link is None:
                continue
            m = _HISTORIAL_HREF_RE.search(link["href"])
            if m is None:
                continue
            fmt, num_seq, modalitat = m.group(1), int(m.group(2)), int(m.group(3))
            rankings[modalitat] = (fmt, num_seq)
        if rankings:
            out.append(HistorialEntry(data=data_val, rankings=rankings))
    return out


# --------------------------- partides per jugador ---------------------------


@dataclass(frozen=True)
class RawGameRow:
    """Una partida tal com surt a /jugador/ranking/partideshome/...

    El portal només dona noms; no exposa el fcb_id del contrincant. El pipeline
    és qui resol nom → fcb_id consultant la BD.
    """

    data_partida: date
    competicio: str  # 'LLIGA', 'INDIVIDUAL', 'COPA', ...
    local_nom: str
    local_punts: int | None
    local_caramboles: int | None
    visitant_nom: str
    visitant_punts: int | None
    visitant_caramboles: int | None
    entrades: int | None


@dataclass
class PartidesParseResult:
    rows: list[RawGameRow] = field(default_factory=list)
    # noms únics que apareixen a les files (per facilitar resolució a la BD)
    noms: set[str] = field(default_factory=set)


def parse_partides_jugador(html: str) -> PartidesParseResult:
    """Parseja /ca/jugador/ranking/partideshome/{num}/{mod}/{player}.

    Les files de la taula es divideixen per separadors `<tr><td colspan=8>`
    amb el nom de la categoria (LLIGA/INDIVIDUAL/COPA). Cada bloc següent va
    associat a aquesta categoria fins al pròxim separador.
    """
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.three.fourths.padded")
    if section is None:
        raise ValueError("No s'ha trobat la secció principal de partides")
    table = section.find("table")
    if table is None:
        raise ValueError("No s'ha trobat la taula de partides")

    result = PartidesParseResult()
    current_competicio: str | None = None
    for tr in table.find_all("tr"):
        # Capçalera <th>: saltar.
        if tr.find("th") is not None:
            continue
        cells = tr.find_all("td")
        if not cells:
            continue
        # Separador de categoria: única cel·la amb colspan.
        if len(cells) == 1 and cells[0].get("colspan"):
            current_competicio = _text(cells[0]).upper() or None
            continue
        # Files de dades: 8 cel·les.
        if len(cells) < 8 or current_competicio is None:
            continue
        try:
            row = _parse_partida_row(cells, current_competicio)
        except _SkipRow as e:
            log.debug("Salto fila de partides: %s", e)
            continue
        result.rows.append(row)
        result.noms.add(row.local_nom)
        result.noms.add(row.visitant_nom)
    return result


# --------------------------- home del jugador ---------------------------


_HOME_DATA_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class CurrentRankingInfo:
    modalitat_codi_fcb: int
    num_seq: int
    format_url: str  # 'data' o 'datahome'


@dataclass(frozen=True)
class HomeRankingsResult:
    data_ranking: date | None  # data del darrer rànquing calculat
    rankings: list[CurrentRankingInfo]


def parse_home_current_rankings(html: str) -> HomeRankingsResult:
    """Extreu els rànquings actuals dels boxes de la home del jugador."""
    soup = BeautifulSoup(html, "lxml")
    # Data del rànquing: dins d'un <h2>Últim ranking calculat ( YYYY-MM-DD )</h2>
    data_ranking: date | None = None
    for h2 in soup.find_all("h2"):
        m = _HOME_DATA_RE.search(h2.get_text())
        if m:
            try:
                data_ranking = date.fromisoformat(m.group(1))
                break
            except ValueError:
                continue

    out: list[CurrentRankingInfo] = []
    for link in soup.select("div.box.success a[href]"):
        m = _HISTORIAL_HREF_RE.search(link["href"])
        if m is None:
            continue
        fmt, num_seq, modalitat = m.group(1), int(m.group(2)), int(m.group(3))
        out.append(
            CurrentRankingInfo(
                modalitat_codi_fcb=modalitat, num_seq=num_seq, format_url=fmt
            )
        )
    return HomeRankingsResult(data_ranking=data_ranking, rankings=out)


def _parse_partida_row(cells: list[Tag], competicio: str) -> RawGameRow:
    data_str = _text(cells[0])
    try:
        data_val = date.fromisoformat(data_str)
    except ValueError as e:
        raise _SkipRow(f"data no parsejable: {data_str!r}") from e
    return RawGameRow(
        data_partida=data_val,
        competicio=competicio,
        local_nom=_text(cells[1]),
        local_punts=_parse_int(_text(cells[2])),
        local_caramboles=_parse_int(_text(cells[3])),
        visitant_nom=_text(cells[4]),
        visitant_punts=_parse_int(_text(cells[5])),
        visitant_caramboles=_parse_int(_text(cells[6])),
        entrades=_parse_int(_text(cells[7])),
    )
