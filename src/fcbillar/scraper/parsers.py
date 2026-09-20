"""Parsers de les pàgines de competició de la FCB.

Reescrits l'agost de 2026 per al web nou (vegeu `docs/canvi-web-fcb-2026.md`).
El portal va passar d'una graella feta a mà —`section.three.fourths.padded`,
`div.row.box.info`, `div.two.ninths`— a targetes Bootstrap amb taules normals,
totes iguals. Per això aquí gairebé no hi ha selectors: la feina de trobar les
taules la fa `taules.py` i cada funció només diu què vol dir cada columna.

Els **contractes no han canviat**: els mateixos dataclasses i les mateixes
signatures que abans, perquè el pipeline no s'hagi d'assabentar del canvi de
web més enllà de les URLs que demana.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from fcbillar.models import Player, RankingEntry
from fcbillar.scraper.taules import (
    Taula,
    decimal,
    enter,
    normalitza,
    parell,
    taula_amb,
    taules,
    taules_amb,
)

log = logging.getLogger(__name__)


# --------------------------- ids dins dels enllaços ---------------------------
#
# Al web nou l'identificador ja no és mai al text: sempre és a l'href. Aquestes
# expressions són l'únic lloc del mòdul que depèn de com la federació escriu
# les URLs.

_RE_JUGADOR = re.compile(r"idjugador=(\d+)")
_RE_RANKING_DADES = re.compile(
    r"rankings/(llistat|historial)-dades\?idranking=(\d+)&idmodalitat=(\d+)"
)

_RE_LLIGA_DIVISIONS = re.compile(r"lligues/divisions/(\d+)")
_RE_LLIGA_GRUPS = re.compile(r"lligues/grups/(\d+)/(\d+)")
_RE_LLIGA_JORNADES = re.compile(r"lligues/jornades/(\d+)/(\d+)/(\d+)")
_RE_LLIGA_ENCONTRES = re.compile(r"lligues/encontres/(\d+)/(\d+)/(\d+)/(\d+)")
_RE_LLIGA_PARTIDES = re.compile(r"lligues/partides/(\d+)/(\d+)/(\d+)/(\d+)/(\d+)")
_RE_LLIGA_PARTICIPANTS = re.compile(r"lligues/participants/(\d+)/(\d+)")

_RE_IND_DIVISIONS = re.compile(r"individuals/divisions/(\d+)")
_RE_IND_FASES = re.compile(r"individuals/fases/(\d+)/(\d+)")
_RE_IND_GRUPS = re.compile(r"individuals/grups/(\d+)/(\d+)/(\d+)")
_RE_IND_KO = re.compile(r"individuals/partides-eliminatories/(\d+)/(\d+)/(\d+)")
_RE_IND_PARTIDES_GRUP = re.compile(r"individuals/partides-grup/(\d+)/(\d+)/(\d+)/(\d+)")

_RE_COPA_GRUPS = re.compile(r"copa/grups/(\d+)/(\d+)")
_RE_COPA_ENCGRUP = re.compile(r"copa/encontres-grup/(\d+)/(\d+)/(\d+)")
_RE_COPA_PARTIDES = re.compile(r"copa/partides-grup/(\d+)/(\d+)/(\d+)/(\d+)/(\d+)/(\d+)")

# "NOM JUGADOR (4 / 30 / 3)" — sèrie major, caramboles i punts a la fitxa de copa.
_RE_COPA_JUGADOR = re.compile(r"^(.*?)\s*\(\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*\)\s*$")


def _primer(regex: re.Pattern[str], enllacos: list[str]) -> re.Match[str] | None:
    for href in enllacos:
        m = regex.search(href)
        if m is not None:
            return m
    return None


def _parteix_encontre(text: str) -> tuple[str, str]:
    """'C.B. SANTS "A" - SB FOMENT MOLINS "A"' -> els dos equips.

    Cap club del cens federatiu porta ' - ' al nom, però si algun dia n'hi ha
    un ho volem saber en comptes de partir-lo malament en silenci.
    """
    parts = text.split(" - ")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    if len(parts) > 2:
        log.warning("Encontre amb més d'un separador, parteixo pel primer: %r", text)
        return parts[0].strip(), " - ".join(parts[1:]).strip()
    return text.strip(), ""


class _SkipRow(Exception):
    """Fila que no podem interpretar — la saltem en silenci."""


# ======================================================================
# RÀNQUINGS
# ======================================================================


@dataclass
class RankingParseResult:
    """Resultat de parsejar una pàgina de rànquing."""

    num_seq: int
    modalitat_codi_fcb: int
    players: list[Player]
    entries: list[RankingEntry]


def parse_ranking(html: str, num_seq: int, modalitat_codi_fcb: int) -> RankingParseResult:
    """Parseja un rànquing (`llistat-dades` o `historial-dades`).

    Columnes: `# | Jugador | MJ | MR | Rang | C | E | P / PT | Def | Partides`.
    L'fcb_id del jugador surt de l'enllaç «Partides» de la fila; sense ell la
    fila no ens serveix de res i la saltem.

    MJ és la mitjana del jugador i MR la dels contraris. El rànquing vigent
    publica cinc decimals i l'històric només tres.
    """
    taula = taula_amb(html, "Jugador", "MJ", "Rang")
    if taula is None:
        raise ValueError("No s'ha trobat la taula del rànquing")

    players: list[Player] = []
    entries: list[RankingEntry] = []
    vistos: set[str] = set()

    for fila in taula:
        m = _RE_JUGADOR.search(fila.enllac() or "")
        if m is None:
            log.debug("Fila de rànquing sense enllaç de partides: %r", fila["Jugador"])
            continue
        fcb_id = m.group(1)
        punts, punts_totals = fila.parell("P / PT")

        if fcb_id not in vistos:
            players.append(Player(fcb_id=fcb_id, nom=fila["Jugador"]))
            vistos.add(fcb_id)

        entries.append(
            RankingEntry(
                ranking_num_seq=num_seq,
                ranking_modalitat=modalitat_codi_fcb,
                player_fcb_id=fcb_id,
                posicio=fila.enter("#"),
                mitjana_general=fila.decimal("MJ"),
                mitjana_particular=None,
                partides=None,
                extras={
                    "mitjana_contraris": fila.decimal("MR"),
                    "rang": fila.decimal("Rang"),
                    "caramboles": fila.enter("C"),
                    "entrades": fila.enter("E"),
                    "punts": punts,
                    "punts_totals": punts_totals,
                    "definitiva": fila["Def"].strip().lower() == "si",
                },
            )
        )

    return RankingParseResult(
        num_seq=num_seq,
        modalitat_codi_fcb=modalitat_codi_fcb,
        players=players,
        entries=entries,
    )


@dataclass(frozen=True)
class CurrentRankingInfo:
    modalitat_codi_fcb: int
    num_seq: int
    format_url: str  # 'llistat' (vigent) o 'historial'


@dataclass(frozen=True)
class HistorialEntry:
    """Una data de rànquing amb el número de seqüència de cada modalitat."""

    data: date
    rankings: dict[int, tuple[str, int]]  # modalitat_codi_fcb -> (format_url, num_seq)


@dataclass(frozen=True)
class HomeRankingsResult:
    data_ranking: date | None  # data del darrer rànquing calculat
    rankings: list[CurrentRankingInfo]


@dataclass(frozen=True)
class RankingsIndex:
    """L'índex sencer de `/frontend/rankings/llistat`.

    Al web antic el rànquing vigent i l'historial eren dues pàgines diferents,
    i totes dues demanaven login. Ara són dues taules de la mateixa pàgina
    pública, així que una sola descàrrega ens diu tot el que hi ha publicat.
    """

    data_vigent: date | None
    vigents: list[CurrentRankingInfo]
    historial: list[HistorialEntry]


def _files_de_rankings(taula: Taula) -> list[tuple[date | None, dict[int, tuple[str, int]]]]:
    out: list[tuple[date | None, dict[int, tuple[str, int]]]] = []
    for fila in taula:
        per_modalitat: dict[int, tuple[str, int]] = {}
        for href in fila.enllacos():
            m = _RE_RANKING_DADES.search(href)
            if m is None:
                continue
            vigencia, num_seq, modalitat = m.group(1), int(m.group(2)), int(m.group(3))
            per_modalitat[modalitat] = (vigencia, num_seq)
        if per_modalitat:
            out.append((fila.data("Data"), per_modalitat))
    return out


def parse_rankings_index(html: str) -> RankingsIndex:
    """Parseja `/frontend/rankings/llistat`: el vigent i els quinze anteriors."""
    vigents: list[CurrentRankingInfo] = []
    data_vigent: date | None = None
    historial: list[HistorialEntry] = []

    for taula in taules_amb(html, "Data"):
        for data, per_modalitat in _files_de_rankings(taula):
            es_vigent = any(v == "llistat" for v, _ in per_modalitat.values())
            if es_vigent:
                data_vigent = data_vigent or data
                vigents.extend(
                    CurrentRankingInfo(modalitat_codi_fcb=mod, num_seq=num, format_url=vigencia)
                    for mod, (vigencia, num) in sorted(per_modalitat.items())
                )
            elif data is not None:
                historial.append(HistorialEntry(data=data, rankings=per_modalitat))

    return RankingsIndex(data_vigent=data_vigent, vigents=vigents, historial=historial)


def parse_home_current_rankings(html: str) -> HomeRankingsResult:
    """Els rànquings vigents, tal com els demanava la portada del jugador."""
    index = parse_rankings_index(html)
    return HomeRankingsResult(data_ranking=index.data_vigent, rankings=index.vigents)


def parse_ranking_historial(html: str) -> list[HistorialEntry]:
    """Els rànquings anteriors, de més nou a més antic."""
    return parse_rankings_index(html).historial


# ======================================================================
# PARTIDES D'UN JUGADOR
# ======================================================================


@dataclass(frozen=True)
class RawGameRow:
    """Una partida tal com surt a `rankings/{vigencia}-partides`.

    El portal només dona noms; no exposa l'fcb_id del contrincant. El pipeline
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
    """Parseja les partides puntuables d'un jugador en un rànquing.

    Abans era una sola taula amb separadors de categoria; ara són tres
    targetes —Lliga, Individual i Copa— i la competició és el títol de cada
    targeta. Les columnes es repeteixen (`P` i `C` surten dues vegades), així
    que aquí llegim per posició:

        Data | Local | P | C | Visitant | P | C | E
    """
    result = PartidesParseResult()
    for taula in taules_amb(html, "Data", "Local", "Visitant"):
        competicio = (taula.titol or "").strip().upper()
        if not competicio:
            continue
        for fila in taula:
            if len(fila) < 8:
                continue
            data_val = fila.data(0)
            if data_val is None:
                log.debug("Salto partida sense data a %s", competicio)
                continue
            row = RawGameRow(
                data_partida=data_val,
                competicio=competicio,
                local_nom=fila[1],
                local_punts=fila.enter(2),
                local_caramboles=fila.enter(3),
                visitant_nom=fila[4],
                visitant_punts=fila.enter(5),
                visitant_caramboles=fila.enter(6),
                entrades=fila.enter(7),
            )
            result.rows.append(row)
            result.noms.add(row.local_nom)
            result.noms.add(row.visitant_nom)
    return result


# ======================================================================
# LLIGA
# ======================================================================


@dataclass(frozen=True)
class LligaDivisio:
    lliga_id: int
    divisio_id: int
    nom: str


@dataclass(frozen=True)
class LligaGrup:
    lliga_id: int
    divisio_id: int
    grup_id: int
    nom: str  # "GRUP A", "HONOR FINAL", ...
    club_responsable: str | None = None


@dataclass(frozen=True)
class LligaJornadaLink:
    lliga_id: int
    divisio_id: int
    grup_id: int
    jornada_id: int
    nom: str  # "Jornada 01"
    data: date | None


@dataclass(frozen=True)
class LligaEncontre:
    """Un enfrontament d'una jornada, jugat o no.

    `encontre_id` és `None` mentre no s'hagi jugat, i no és cap mancança de la
    pàgina: la federació no dona identificador a un encontre fins que algú
    n'introdueix el resultat, i llavors la fila estrena enllaç. Fins aleshores
    l'enfrontament existeix igualment —hi surt amb els dos equips, l'estat
    «Oberta» i els punts a zero— i és l'única cosa que identifica la parella.

    Saltar-se'ls, que és el que es feia, deixava la jornada mig buida a la web:
    de la primera d'Honor Grup A en sortien dos encontres de quatre.
    """

    lliga_id: int
    divisio_id: int
    grup_id: int
    jornada_id: int
    encontre_id: int | None
    equip_local: str
    p_parcials_local: int | None
    p_match_local: int | None
    equip_visitant: str
    p_parcials_visitant: int | None
    p_match_visitant: int | None
    #: 'Finalitzada', 'Oberta', 'Pendent'… tal com l'escriu la federació.
    estat: str = ""


@dataclass(frozen=True)
class LligaClassificacioRow:
    posicio: int
    equip: str  # text tal qual: 'C.B. CANET "B"', 'S.B. GEiEG', ...
    pm: int  # punts de match (OFICIALS, amb penalització ja restada)
    pp: int | None  # punts parcials (desempat oficial)
    j: int | None  # partides jugades


@dataclass(frozen=True)
class LligaPartidaRow:
    data_partida: date | None
    modalitat: str  # "Tres bandes", "Lliure", ...
    local_nom: str
    local_caramboles: int | None
    local_serie_major: int | None
    local_punts: int | None
    visitant_nom: str
    visitant_caramboles: int | None
    visitant_serie_major: int | None
    visitant_punts: int | None
    entrades: int | None
    arbitre: str | None
    assistencia: str | None
    #: 'Tancada', 'Pendent'… El web antic no ho deia i el nou sí.
    estat: str = ""


def parse_lliga_divisions(html: str) -> list[LligaDivisio]:
    """Divisions d'una lliga. L'id surt de l'enllaç als grups."""
    taula = taula_amb(html, "Divisió")
    if taula is None:
        return []
    out: list[LligaDivisio] = []
    for fila in taula:
        m = _primer(_RE_LLIGA_GRUPS, fila.enllacos())
        if m is None:
            continue
        out.append(
            LligaDivisio(
                lliga_id=int(m.group(1)),
                divisio_id=int(m.group(2)),
                nom=fila["Divisió"],
            )
        )
    return out


def parse_lliga_grups(html: str) -> list[LligaGrup]:
    """Grups d'una divisió, amb el club que els organitza."""
    taula = taula_amb(html, "Grup")
    if taula is None:
        return []
    out: list[LligaGrup] = []
    for fila in taula:
        m = _primer(_RE_LLIGA_JORNADES, fila.enllacos())
        if m is None:
            continue
        out.append(
            LligaGrup(
                lliga_id=int(m.group(1)),
                divisio_id=int(m.group(2)),
                grup_id=int(m.group(3)),
                nom=fila["Grup"],
                club_responsable=fila["Organitzador"] or None,
            )
        )
    return out


def parse_lliga_jornades(html: str) -> list[LligaJornadaLink]:
    """Jornades d'un grup, amb la data prevista."""
    taula = taula_amb(html, "Jornada", "Data")
    if taula is None:
        return []
    out: list[LligaJornadaLink] = []
    for fila in taula:
        m = _primer(_RE_LLIGA_ENCONTRES, fila.enllacos())
        if m is None:
            continue
        out.append(
            LligaJornadaLink(
                lliga_id=int(m.group(1)),
                divisio_id=int(m.group(2)),
                grup_id=int(m.group(3)),
                jornada_id=int(m.group(4)),
                nom=fila["Jornada"],
                data=fila.data("Data"),
            )
        )
    return out


def parse_lliga_encontres(
    html: str, *, lliga_id: int = 0, divisio_id: int = 0, grup_id: int = 0, jornada_id: int = 0
) -> list[LligaEncontre]:
    """Tots els enfrontaments d'una jornada, jugats o no.

    Els jugats porten enllaç al detall i d'allà surten els cinc identificadors.
    Els que encara no s'han jugat no en porten cap —vegeu `LligaEncontre`—, i
    per això cal dir-li de quina jornada és la pàgina: sense els paràmetres, un
    encontre obert no es pot situar i se salta.

    Es demanen com a paràmetres i no s'endevinen de la pàgina perquè la pàgina
    no ho diu: el títol de la targeta és «Jornada 1» i prou. Qui la baixa sí que
    ho sap, que és qui n'ha muntat la URL.
    """
    taula = taula_amb(html, "Encontre")
    if taula is None:
        return []
    out: list[LligaEncontre] = []
    for fila in taula:
        local, visitant = _parteix_encontre(fila["Encontre"])
        if not local or not visitant:
            continue
        m = _primer(_RE_LLIGA_PARTIDES, fila.enllacos())
        if m is not None:
            claus = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
            encontre_id: int | None = int(m.group(5))
            pp_local, pp_visitant = fila.parell("Punts Parcials")
            pm_local, pm_visitant = fila.parell("Punts de Match")
        else:
            claus = (lliga_id, divisio_id, grup_id, jornada_id)
            encontre_id = None
            if not all(claus):
                continue
            # La federació escriu «0 / 0» als encontres que no s'han jugat, i
            # això no és un resultat: és un lloc per posar-n'hi un. Desar-hi el
            # zero els faria semblar empats a zero —que a més no existeixen, els
            # punts de matx van 3/0 o 1/1— i els comptaria com a jugats a
            # qualsevol suma. És el mateix error que el 0 als equips que la v15
            # va haver de desfer.
            #
            # El senyal és l'enllaç i no el text de l'estat: l'enllaç apareix
            # exactament quan algú ha introduït el resultat.
            pp_local = pp_visitant = pm_local = pm_visitant = None
        out.append(
            LligaEncontre(
                lliga_id=claus[0],
                divisio_id=claus[1],
                grup_id=claus[2],
                jornada_id=claus[3],
                encontre_id=encontre_id,
                equip_local=local,
                p_parcials_local=pp_local,
                p_match_local=pm_local,
                equip_visitant=visitant,
                p_parcials_visitant=pp_visitant,
                p_match_visitant=pm_visitant,
                estat=fila["Estat"] if fila.te("Estat") else "",
            )
        )
    return out


def parse_lliga_classificacio(html: str) -> list[LligaClassificacioRow]:
    """Classificació d'un grup: PM són els punts oficials, amb penalitzacions."""
    taula = taula_amb(html, "Equip", "PM")
    if taula is None:
        return []
    out: list[LligaClassificacioRow] = []
    for i, fila in enumerate(taula, start=1):
        pm = fila.enter("PM")
        if pm is None:
            continue
        # La columna de posició no té títol; si falta, val l'ordre de la taula.
        posicio = fila.enter(0)
        out.append(
            LligaClassificacioRow(
                posicio=posicio if posicio is not None else i,
                equip=fila["Equip"],
                pm=pm,
                pp=fila.enter("PP"),
                j=fila.enter("J"),
            )
        )
    return out


@dataclass(frozen=True)
class LligaEncontreDetall:
    """El detall d'un encontre: qui hi jugava i les partides una per una.

    Els noms dels equips surten de les CAPÇALERES de la taula, que és on la
    federació els posa: la primera columna es titula «C.B. SANT BOI "A"» i la
    segona «B.C. GRANOLLERS "B"». Val la pena tenir-los perquè permeten
    comprovar que la pàgina que hem baixat és la de l'encontre que demanàvem.
    """

    equip_local: str
    equip_visitant: str
    partides: list[LligaPartidaRow]


def parse_lliga_encontre_detall(html: str) -> LligaEncontreDetall | None:
    """Detall d'un encontre de lliga: sèrie major, caramboles, entrades i punts.

    Aquesta pàgina va retornar HTTP 500 des del canvi de web d'agost de 2026
    fins al setembre, i durant aquell temps el parser es va escriure a cegues
    contra la forma que tenien les taules de partides d'individuals i de copa:

        Local | SM | Caramboles | Visitant | SM | Caramboles | Entrades | …

    No és aquesta. Quan la federació la va arreglar —i la va arreglar per a
    totes les temporades, o sigui que el 500 era seu— la taula va resultar ser:

        <equip local> | <equip visitant> | SM/Caramboles | SM/Caramboles |
        Entrades | Modalitat | Estat | <punts>

    És a dir: els equips són les capçaleres, cada resultat ve aparellat dins
    d'una sola cel·la («4 / 27» = sèrie major 4, 27 caramboles) i l'última
    columna, que no té títol, són els punts de la partida («2 / 0», «1 / 1» si
    han empatat). No hi surt ni la data, ni l'àrbitre, ni l'assistència: el web
    antic els donava i el nou no. Els deixem a `None` i el pipeline hi posa els
    de l'encontre.

    La modalitat SÍ que hi és, i per partida, que és com ha de ser: a la lliga
    de 4 Modalitats cada partida d'un encontre juga una modalitat diferent.
    """
    for taula in taules(html):
        caps = [normalitza(c) for c in taula.capcaleres]
        parells = [i for i, c in enumerate(caps) if c in ("sm caramboles", "sm cara")]
        if len(parells) < 2 or "entrades" not in caps:
            continue
        i_local, i_visitant = parells[0], parells[1]
        # Els jugadors van a les dues primeres columnes, les que porten el nom
        # de l'equip per títol; no es busquen per nom perquè el títol ÉS l'equip.
        out: list[LligaPartidaRow] = []
        for fila in taula:
            if len(fila) <= i_visitant:
                continue
            sm_l, car_l = fila.parell(i_local)
            sm_v, car_v = fila.parell(i_visitant)
            punts_l, punts_v = (None, None)
            # Els punts són l'última columna i no tenen capçalera.
            if len(fila) > len(caps) - 1 and not caps[-1]:
                punts_l, punts_v = fila.parell(len(caps) - 1)
            out.append(
                LligaPartidaRow(
                    data_partida=fila.data("Data") if fila.te("Data") else None,
                    modalitat=fila["Modalitat"] if fila.te("Modalitat") else "",
                    local_nom=fila[0],
                    local_serie_major=sm_l,
                    local_caramboles=car_l,
                    local_punts=punts_l,
                    visitant_nom=fila[1],
                    visitant_serie_major=sm_v,
                    visitant_caramboles=car_v,
                    visitant_punts=punts_v,
                    entrades=fila.enter("Entrades"),
                    arbitre=None,
                    assistencia=None,
                    estat=fila["Estat"] if fila.te("Estat") else "",
                )
            )
        return LligaEncontreDetall(
            equip_local=taula.capcaleres[0] if taula.capcaleres else "",
            equip_visitant=taula.capcaleres[1] if len(taula.capcaleres) > 1 else "",
            partides=out,
        )
    return None


def parse_lliga_partides(html: str) -> list[LligaPartidaRow]:
    """Només les partides del detall d'un encontre. Vegeu `parse_lliga_encontre_detall`."""
    detall = parse_lliga_encontre_detall(html)
    return detall.partides if detall else []


@dataclass(frozen=True)
class LligaOberta:
    """Una lliga del llistat: la temporada en joc, una per modalitat.

    El llistat només ensenya les lligues vives. Les tancades continuen
    accessibles pel seu id —la 36 i la 37 són les de 2025-26— però ja no hi
    surten, o sigui que d'aquí no se n'obté l'històric.
    """

    lliga_id: int
    nom: str
    modalitat: str
    data_limit: date | None  # límit d'inscripció
    estat: str  # 'Inscripció', 'Activa'…


def parse_lligues_llistat(html: str) -> tuple[list[LligaOberta], list[str]]:
    """Les lligues obertes, i les files que no s'han sabut llegir.

    Les dues coses juntes a posta. Una fila sense l'enllaç de divisions se salta,
    i si només es tornés la llista, un canvi de marcatge que n'afectés unes
    quantes donaria un resultat curt que sembla bo: no és buit, o sigui que els
    guardians del buit no salten, i qui el faci servir com a llista completa del
    que segueix obert n'esborrarà les que hi falten.

    Qui necessiti l'autoritat ha de mirar que no n'hi hagi cap de descartada.
    """
    taula = taula_amb(html, "Lliga", "Estat")
    if taula is None:
        return [], []
    out: list[LligaOberta] = []
    descartades: list[str] = []
    for fila in taula:
        m = _primer(_RE_LLIGA_DIVISIONS, fila.enllacos())
        if m is None:
            descartades.append(fila["Lliga"] if fila.te("Lliga") else "(fila sense nom)")
            continue
        out.append(
            LligaOberta(
                lliga_id=int(m.group(1)),
                nom=fila["Lliga"],
                modalitat=fila["Modalitat"] if fila.te("Modalitat") else "",
                data_limit=fila.data("Data límit inscripció")
                if fila.te("Data límit inscripció")
                else None,
                estat=fila["Estat"],
            )
        )
    return out, descartades


@dataclass(frozen=True)
class LligaEquipInscrit:
    """Un equip inscrit a una lliga, amb el club a què pertany.

    Pàgina nova: al web antic el club de cada equip s'havia de deduir del nom.
    """

    club: str
    equip: str
    #: Id de club de la federació, per demanar-ne els jugadors inscrits. Només
    #: surt a l'enllaç «Veure inscrits», que la pàgina posa un cop per club.
    club_id_extern: int | None = None


def parse_lliga_inscripcions(html: str) -> list[LligaEquipInscrit]:
    """Els equips inscrits a una lliga.

    El club només s'escriu a la **primera** fila de cada club; les altres el
    porten buit, com una cel·la fusionada que no ho és. Per això s'arrossega:
    filtrar les files sense club deixaria fora el segon equip de cada club i
    una llista de 93 equips en tornaria 38, sense dir-ho.

    Aquesta forma és de setembre de 2026, quan la federació hi va afegir el
    botó «Veure inscrits». Fins llavors cada fila repetia el club.
    """
    taula = taula_amb(html, "Club", "Equip")
    if taula is None:
        return []
    out: list[LligaEquipInscrit] = []
    club = ""
    club_id: int | None = None
    for fila in taula:
        if fila["Club"]:
            club = fila["Club"]
            m = _primer(_RE_LLIGA_PARTICIPANTS, fila.enllacos())
            club_id = int(m.group(2)) if m else None
        if not club or not fila["Equip"]:
            continue
        out.append(LligaEquipInscrit(club=club, equip=fila["Equip"], club_id_extern=club_id))
    return out


@dataclass(frozen=True)
class LligaJugadorInscrit:
    """Un jugador que un club inscriu a una lliga.

    La federació no en dona l'identificador: aquesta pàgina només porta el nom
    tal com l'escriu ella, «COGNOMS, NOM», que és per on es lliga amb
    `players.nom` —igual que el llistat de divisions de l'individual.
    """

    jugador: str
    #: La mitjana del rànquing vigent de la modalitat. `0.0` per a qui no hi és.
    mitjana: float | None
    #: Ve d'un altre club. La federació ho marca amb una etiqueta al nom.
    fitxatge: bool
    #: Ordre a la llista, que és de més mitjana a menys.
    posicio: int


#: Com la federació marca qui ve d'un altre club: `<span>(Fitxatge)</span>`.
_RE_FITXATGE = re.compile(r"\(\s*fitxatge\s*\)", re.IGNORECASE)


def parse_lliga_participants(html: str) -> list[LligaJugadorInscrit]:
    """Els jugadors inscrits d'un club, de `lligues/participants/{lliga}/{club}`.

    La taula té dues columnes i només una porta nom: la mitjana va a una
    capçalera buida. Per això es llegeixen per posició i no per nom de columna.
    """
    for taula in taules(html):
        capcaleres = [normalitza(h) for h in taula.capcaleres]
        if "jugador" not in capcaleres or len(capcaleres) != 2:
            continue
        i_jug = capcaleres.index("jugador")
        i_mit = 1 - i_jug
        out: list[LligaJugadorInscrit] = []
        for fila in taula:
            if len(fila) < 2:
                continue
            brut = fila[i_jug]
            nom = _RE_FITXATGE.sub("", brut).strip()
            if not nom:
                continue
            out.append(
                LligaJugadorInscrit(
                    jugador=nom,
                    mitjana=fila.decimal(i_mit),
                    fitxatge=bool(_RE_FITXATGE.search(brut)),
                    posicio=len(out) + 1,
                )
            )
        return out
    return []


# ======================================================================
# INDIVIDUALS (opens i campionats de Catalunya)
# ======================================================================


@dataclass(frozen=True)
class TorneigIndividual:
    torneig_id_extern: int
    nom: str


@dataclass(frozen=True)
class IndividualDivisio:
    torneig_id: int
    divisio_id_extern: int
    nom: str
    classif_href: str | None = None


@dataclass(frozen=True)
class IndividualFaseLink:
    torneig_id: int
    fase_id_extern: int
    nom: str  # "PRÈVIA", "QUARTS", "FINAL", etc.
    tipus: str  # "grups" o "ko"
    href: str  # URL per descarregar les partides d'aquesta fase


@dataclass(frozen=True)
class IndividualGrupMembre:
    """Assignació d'un jugador a un grup dins d'una fase de grups."""

    jugador_nom: str
    grup_nom: str


@dataclass(frozen=True)
class IndividualParticipant:
    posicio: int
    jugador_nom: str
    club: str | None
    partides_jugades: int | None
    punts: int | None
    caramboles: int | None
    entrades: int | None
    mitjana_general: float | None
    mitjana_particular: float | None
    serie_max: int | None


def parse_individuals_torneigs_list(html: str) -> list[TorneigIndividual]:
    """Torneigs de la temporada en curs."""
    taula = taula_amb(html, "Torneig")
    if taula is None:
        return []
    out: list[TorneigIndividual] = []
    for fila in taula:
        m = _primer(_RE_IND_DIVISIONS, fila.enllacos())
        if m is None:
            continue
        out.append(
            TorneigIndividual(torneig_id_extern=int(m.group(1)), nom=fila["Torneig"].upper())
        )
    return out


def parse_individuals_divisions(html: str) -> list[IndividualDivisio]:
    """Divisions (o categories) d'un torneig individual.

    `classif_href` es queda buit: la classificació final va desaparèixer amb
    el canvi de web i ja no hi ha cap enllaç que hi porti.
    """
    taula = taula_amb(html, "Divisió")
    if taula is None:
        return []
    out: list[IndividualDivisio] = []
    for fila in taula:
        m = _primer(_RE_IND_FASES, fila.enllacos())
        if m is None:
            continue
        out.append(
            IndividualDivisio(
                torneig_id=int(m.group(1)),
                divisio_id_extern=int(m.group(2)),
                nom=fila["Divisió"].upper(),
            )
        )
    return out


def parse_individuals_fases(html: str) -> list[IndividualFaseLink]:
    """Fases d'una divisió: primer les de grups, després les eliminatòries."""
    out: list[IndividualFaseLink] = []
    for taula in taules(html):
        cols = {normalitza(c) for c in taula.capcaleres}
        if "fase" in cols:
            regex, tipus, columna = _RE_IND_GRUPS, "grups", "Fase"
        elif "eliminatoria" in cols:
            regex, tipus, columna = _RE_IND_KO, "ko", "Eliminatòria"
        else:
            continue
        for fila in taula:
            href = fila.enllac()
            if href is None:
                continue
            m = regex.search(href)
            if m is None:
                continue
            out.append(
                IndividualFaseLink(
                    torneig_id=int(m.group(1)),
                    fase_id_extern=int(m.group(3)),
                    nom=fila[columna].upper(),
                    tipus=tipus,
                    href=href,
                )
            )
    return out


def parse_individuals_grups_membership(html: str) -> list[IndividualGrupMembre]:
    """Quin jugador juga a quin grup dins d'una fase de grups."""
    taula = taula_amb(html, "Jugador", "Grup")
    if taula is None:
        return []
    return [
        IndividualGrupMembre(jugador_nom=fila["Jugador"], grup_nom=fila["Grup"])
        for fila in taula
        if fila["Jugador"] and fila["Grup"]
    ]


@dataclass(frozen=True)
class IndividualGrupLink:
    """Un grup d'una fase, amb l'id que fa falta per demanar-ne les partides."""

    grup_id_extern: int
    nom: str  # 'Grup A'
    club_organitzador: str | None
    #: El dia que es juga el grup. És l'única data que dona el portal per a una
    #: partida d'individual: la taula de partides no en porta cap.
    data: date | None


def parse_individuals_grups(html: str) -> list[IndividualGrupLink]:
    """Els grups d'una fase amb el seu identificador.

    La pàgina d'una fase de grups en porta DUES taules: aquesta, amb un grup per
    fila, i la de participants, que diu qui juga a quin grup i que llegeix
    `parse_individuals_grups_membership`.

    L'id del grup no surt escrit enlloc: només és a l'enllaç d'aquesta fila. Per
    això sense aquest parser les partides dels grups són inabastables, encara
    que la pàgina que les serveix funcioni.
    """
    taula = taula_amb(html, "Grup", "Data partits")
    if taula is None:
        return []
    out: list[IndividualGrupLink] = []
    for fila in taula:
        m = _primer(_RE_IND_PARTIDES_GRUP, fila.enllacos())
        if m is None:
            continue
        out.append(
            IndividualGrupLink(
                grup_id_extern=int(m.group(4)),
                nom=fila["Grup"],
                club_organitzador=fila["Club organitzador"] or None
                if fila.te("Club organitzador")
                else None,
                data=fila.data("Data partits"),
            )
        )
    return out


@dataclass(frozen=True)
class IndividualPartidaRow:
    """Una partida d'un grup o d'una eliminatòria d'un torneig individual.

    Aquestes taules són més riques que les del rànquing: hi ha sèrie major,
    entrades i àrbitre. No hi ha data: la posa la fase.
    """

    local_nom: str
    local_serie_major: int | None
    local_caramboles: int | None
    visitant_nom: str
    visitant_serie_major: int | None
    visitant_caramboles: int | None
    entrades: int | None
    arbitre: str | None
    estat: str | None


def parse_individuals_partides(html: str) -> list[IndividualPartidaRow]:
    """Partides d'un grup (`partides-grup`) o d'una eliminatòria.

    Les dues pàgines fan servir exactament la mateixa taula. Les files on el
    local i el visitant són el mateix jugador amb tot a zero no són partides:
    són els buits que deixa un grup incomplet.
    """
    out: list[IndividualPartidaRow] = []
    for taula in taules_amb(html, "Local", "Visitant", "Entrades"):
        for fila in taula:
            if len(fila) < 7:
                continue
            local, visitant = fila[0], fila[3]
            caramboles_local, caramboles_visitant = fila.enter(2), fila.enter(5)
            if local == visitant and not caramboles_local and not caramboles_visitant:
                continue
            out.append(
                IndividualPartidaRow(
                    local_nom=local,
                    local_serie_major=fila.enter(1),
                    local_caramboles=caramboles_local,
                    visitant_nom=visitant,
                    visitant_serie_major=fila.enter(4),
                    visitant_caramboles=caramboles_visitant,
                    entrades=fila.enter("Entrades"),
                    arbitre=fila["Àrbitre"] or None,
                    estat=fila["Estat"] or None if fila.te("Estat") else None,
                )
            )
    return out


@dataclass(frozen=True)
class IndividualGrupClassifRow:
    """Una línia de la classificació d'un grup, tal com la publica la federació.

    La `posicio` no s'escriu a la pàgina: és l'ordre de la fila, i la federació
    ja les dona ordenades (punts, i a igualtat de punts la mitjana). Tres
    jugadors amb dos punts cadascun al Grup F de la pre-prèvia de 1a surten
    ordenats per mitjana, i és així com es desempaten.
    """

    posicio: int
    jugador_nom: str
    punts: int | None
    mitjana: float | None
    #: Només a les eliminatòries: aquella taula porta caramboles i entrades.
    caramboles: int | None = None
    entrades: int | None = None


def parse_individuals_grup_classificacio(html: str) -> list[IndividualGrupClassifRow]:
    """Com ha quedat un grup: qui, amb quants punts i amb quina mitjana.

    Aquesta taula és a la mateixa pàgina que les partides del grup
    (`partides-grup`) i no la llegia ningú, tot i ser l'única cosa que diu qui
    s'ha classificat. La ingesta d'individuals deduïa la classificació del
    quadre —quina fase havia jugat cadascú i qui va guanyar l'última partida—,
    que serveix per a un open acabat i no serveix de res per a un campionat a
    mitges: al setembre de 2026 el campionat de Catalunya de tres bandes només
    havia jugat la prèvia i la pre-prèvia, i del que en calia era justament
    això: l'ordre dins de cada grup.

    Els punts són 2 per victòria i 1 per empat; la mitjana és la del grup, i és
    buida per a qui no hi ha jugat cap partida.
    """
    out: list[IndividualGrupClassifRow] = []
    for taula in taules(html):
        cols = {normalitza(c) for c in taula.capcaleres}
        if "jugador" not in cols or "punts" not in cols:
            continue
        # La taula de la fase de grups porta «Mitjana»; la d'eliminatòries,
        # «Promig» amb caramboles i entrades. Totes dues valen.
        if not ({"mitjana", "promig"} & cols):
            continue
        for i, fila in enumerate(taula, start=1):
            nom = fila["Jugador"]
            if not nom:
                continue
            out.append(
                IndividualGrupClassifRow(
                    posicio=i,
                    jugador_nom=nom,
                    punts=fila.enter("Punts"),
                    mitjana=fila.decimal("Mitjana") if fila.te("Mitjana") else fila.decimal("Promig"),
                    caramboles=fila.enter("Caramboles") if fila.te("Caramboles") else None,
                    entrades=fila.enter("Entrades") if fila.te("Entrades") else None,
                )
            )
        return out
    return out


def parse_individuals_classificaciofinal(html: str) -> list[IndividualParticipant]:
    """Classificació final d'un torneig individual.

    OBSOLET: `/ca/individuals/classificaciofinal/…` va desaparèixer amb el web
    nou i no té substitut. Es manté per poder rellegir l'HTML que ja tenim
    arxivat, i per si la federació la torna a publicar. La classificació de la
    temporada en curs s'ha de calcular a partir dels grups i les eliminatòries.
    """
    taula = taula_amb(html, "Jugador")
    if taula is None:
        return []
    out: list[IndividualParticipant] = []
    for i, fila in enumerate(taula, start=1):
        if len(fila) < 10:
            continue
        posicio = fila.enter(0)
        out.append(
            IndividualParticipant(
                posicio=posicio if posicio is not None else i,
                jugador_nom=fila[1],
                club=fila[2] or None,
                partides_jugades=fila.enter(3),
                punts=fila.enter(4),
                caramboles=fila.enter(5),
                entrades=fila.enter(6),
                mitjana_general=decimal(fila[7]),
                mitjana_particular=decimal(fila[8]),
                serie_max=fila.enter(9),
            )
        )
    return out


# ======================================================================
# CLUBS (ara al WordPress)
# ======================================================================


@dataclass(frozen=True)
class ClubOficial:
    nom: str
    telefon: str | None = None
    email: str | None = None
    direccio: str | None = None
    web: str | None = None


def parse_clubs_listing(html: str) -> list[ClubOficial]:
    """Llistat oficial de clubs.

    Ha passat de la intranet al WordPress i hi ha guanyat telèfon, correu,
    adreça i web, que abans no teníem enlloc.
    """
    taula = taula_amb(html, "CLUB")
    if taula is None:
        raise ValueError("No s'ha trobat la taula de clubs")
    out: list[ClubOficial] = []
    for fila in taula:
        nom = fila["CLUB"]
        if not nom:
            continue
        out.append(
            ClubOficial(
                nom=nom,
                telefon=fila["TELÈFON"] or None,
                email=fila["EMAIL"] or None,
                direccio=fila["DIRECCIÓ"] or None,
                web=fila.enllac("WEB") or fila["WEB"] or None,
            )
        )
    return out


# ======================================================================
# COPA — edició → jornades → grups → encontres → partides
# ======================================================================


@dataclass(frozen=True)
class CopaJornadaLink:
    edicio_id: int
    jornada: int
    nom: str


@dataclass(frozen=True)
class CopaGrupLink:
    edicio_id: int
    jornada: int
    grup_id: int
    nom: str


@dataclass(frozen=True)
class CopaClassifRow:
    posicio: int
    equip: str
    punts: int | None
    parcials: int | None
    mitjana: float | None


@dataclass(frozen=True)
class CopaEncontreLink:
    edicio_id: int
    jornada: int
    grup_id: int
    enc_id_extern: int
    team_a_extern: int
    team_b_extern: int
    equip_local: str
    equip_visitant: str
    p_match_local: int | None
    p_match_visitant: int | None


@dataclass(frozen=True)
class CopaGrupData:
    grup_nom: str
    classificacio: list[CopaClassifRow]
    encontres: list[CopaEncontreLink]


@dataclass(frozen=True)
class CopaPartidaRow:
    ordre: int
    local_nom: str
    local_caramboles: int | None
    local_serie: int | None
    visitant_nom: str
    visitant_caramboles: int | None
    visitant_serie: int | None
    entrades: int | None
    punts_local: int | None
    punts_visitant: int | None


def parse_copa_jornades(html: str) -> list[CopaJornadaLink]:
    """Jornades d'una edició de copa."""
    taula = taula_amb(html, "Fase")
    if taula is None:
        return []
    out: list[CopaJornadaLink] = []
    vistes: set[int] = set()
    for fila in taula:
        m = _primer(_RE_COPA_GRUPS, fila.enllacos())
        if m is None:
            continue
        jornada = int(m.group(2))
        if jornada in vistes:
            continue
        vistes.add(jornada)
        out.append(CopaJornadaLink(edicio_id=int(m.group(1)), jornada=jornada, nom=fila["Fase"]))
    return out


def parse_copa_grups(html: str) -> list[CopaGrupLink]:
    """Grups d'una jornada de copa."""
    taula = taula_amb(html, "Grup")
    if taula is None:
        return []
    out: list[CopaGrupLink] = []
    vistos: set[int] = set()
    for fila in taula:
        m = _primer(_RE_COPA_ENCGRUP, fila.enllacos())
        if m is None:
            continue
        grup_id = int(m.group(3))
        if grup_id in vistos:
            continue
        vistos.add(grup_id)
        out.append(
            CopaGrupLink(
                edicio_id=int(m.group(1)),
                jornada=int(m.group(2)),
                grup_id=grup_id,
                nom=fila["Grup"],
            )
        )
    return out


def parse_copa_encontresgrup(html: str) -> CopaGrupData:
    """Classificació i encontres d'un grup de copa.

    La posició ja no és una columna: la dona l'ordre de la taula, que és el
    mateix criteri que fa servir el portal per pintar-la.
    """
    classif: list[CopaClassifRow] = []
    grup_nom = ""

    taula_classif = taula_amb(html, "Equip", "Punts")
    if taula_classif is not None:
        grup_nom = (taula_classif.titol or "").split(" - ")[0].strip()
        for i, fila in enumerate(taula_classif, start=1):
            classif.append(
                CopaClassifRow(
                    posicio=i,
                    equip=fila["Equip"],
                    punts=fila.enter("Punts"),
                    parcials=fila.enter("Parcials"),
                    mitjana=fila.decimal("Mitjana"),
                )
            )

    encontres: list[CopaEncontreLink] = []
    taula_enc = taula_amb(html, "Local", "Resultat", "Visitant")
    if taula_enc is not None:
        if not grup_nom:
            grup_nom = (taula_enc.titol or "").split(" - ")[0].strip()
        for fila in taula_enc:
            m = _primer(_RE_COPA_PARTIDES, fila.enllacos())
            if m is None:
                continue
            # El resultat de copa s'escriu "3 - 0", no "3 / 0".
            pm_local, pm_visitant = parell(fila["Resultat"], sep="-")
            encontres.append(
                CopaEncontreLink(
                    edicio_id=int(m.group(1)),
                    jornada=int(m.group(2)),
                    grup_id=int(m.group(3)),
                    enc_id_extern=int(m.group(4)),
                    team_a_extern=int(m.group(5)),
                    team_b_extern=int(m.group(6)),
                    equip_local=fila["Local"],
                    equip_visitant=fila["Visitant"],
                    p_match_local=pm_local,
                    p_match_visitant=pm_visitant,
                )
            )

    return CopaGrupData(grup_nom=grup_nom, classificacio=classif, encontres=encontres)


def _jugador_copa(text: str) -> tuple[str, int | None, int | None, int | None]:
    """'BORT CARIÑENA, SALVADOR (4 / 30 / 3)' → nom, sèrie, caramboles, punts."""
    m = _RE_COPA_JUGADOR.match(text.strip())
    if m is None:
        return text.strip(), None, None, None
    return m.group(1).strip(), enter(m.group(2)), enter(m.group(3)), enter(m.group(4))


def parse_copa_partides(html: str) -> list[CopaPartidaRow]:
    """Partides individuals d'un encontre de copa.

    Cada cel·la de jugador porta la seva estadística entre parèntesis, en
    l'ordre que diu la capçalera: `Local SM/Caramboles/Punts`.
    """
    taula = taula_amb(html, "Entrades")
    if taula is None:
        return []
    out: list[CopaPartidaRow] = []
    for i, fila in enumerate(taula, start=1):
        if len(fila) < 3:
            continue
        local, serie_l, caram_l, punts_l = _jugador_copa(fila[0])
        visitant, serie_v, caram_v, punts_v = _jugador_copa(fila[1])
        if not local and not visitant:
            continue
        out.append(
            CopaPartidaRow(
                ordre=i,
                local_nom=local,
                local_caramboles=caram_l,
                local_serie=serie_l,
                visitant_nom=visitant,
                visitant_caramboles=caram_v,
                visitant_serie=serie_v,
                entrades=fila.enter("Entrades"),
                punts_local=punts_l,
                punts_visitant=punts_v,
            )
        )
    return out
