"""De qui està fet cada club a la lliga, segons la federació.

Fins al setembre de 2026 això s'havia d'estimar: `plantilles.py` mirava qui
havia jugat les dues últimes temporades i qui constava al llistat de divisions
de l'individual, i ho deia clarament que era una estimació. Ara la federació ho
publica —`lligues/participants/{lliga}/{club}`, penjat del botó «Veure
inscrits» de la pàgina d'inscripcions— amb la mitjana de cadascú i una etiqueta
per als fitxatges.

## Un fitxatge surt dues vegades, i està bé

Qui ve d'un altre club apareix a **dues** llistes: a la del seu club sense cap
marca, i a la del club que se l'endú amb `(Fitxatge)`. Sembla una contradicció
—la mateixa persona inscrita a dos clubs— i no ho és: són les dues cares del
mateix fitxatge. Comprovat contra el llistat de divisions del campionat
individual 2026/2027, que és una font independent de la federació amb el club
de cada jugador: **349 de 349 vegades** el club sense marca és el que hi consta.

Per això la clau porta el club i no només el jugador.

## Què és per club i què és per equip

La pàgina és **per club**. Diu qui juga la lliga amb cada club, no a quin equip
—"A", "B", "C"…— va cadascú, encara que el club n'hi tingui cinc. Això no ho
publica ningú abans de la primera jornada.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass

from fcbillar.clubs import canonic
from fcbillar.scraper import urls as U
from fcbillar.scraper.parsers import (
    LligaOberta,
    parse_lliga_inscripcions,
    parse_lliga_participants,
    parse_lligues_llistat,
)


@dataclass(frozen=True)
class Inscrit:
    """Un jugador que un club inscriu a una lliga."""

    club: str  # nom del cens, canonicalitzat
    club_id_extern: int
    jugador: str  # 'COGNOMS, NOM', com l'escriu la federació
    mitjana: float | None
    fitxatge: bool  # ve d'un altre club
    posicio: int  # ordre a la llista del seu club


@dataclass(frozen=True)
class Lliga:
    """Una lliga oberta, del llistat d'inscripcions."""

    lliga_id: int
    nom: str
    clubs: dict[int, str]  # id de la federació → nom del club, canonicalitzat
    equips: int
    #: 'Tres bandes', '4 Modalitats'. Va a cada fila perquè les mitjanes de dues
    #: lligues no es poden comparar: són de modalitats diferents, i qui les
    #: llegeixi per ordenar jugadors ha de poder demanar-ne una de sola.
    modalitat: str = ""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s)


# --------------------------- descàrrega ---------------------------


def llegeix_lligues(client) -> tuple[list[LligaOberta], list[str]]:
    """Les lligues obertes i les files del llistat que no s'han sabut llegir.

    El llistat només ensenya les de la temporada en joc. Les descartades van amb
    la llista i no a part perquè qui la faci servir per decidir què ja no
    existeix no se les pugui deixar: una llista curta però no buida passa per
    bona i s'endú les lligues que hi falten.
    """
    return parse_lligues_llistat(client.fetch_html(U.lligues_llistat()))


def llegeix_clubs(client, oberta: LligaOberta) -> Lliga:
    """Els clubs i equips inscrits a una lliga.

    Una llista buida no és una resposta acceptable: en tornaríem una tant si la
    lliga no té ningú apuntat com si el que ha arribat és una pàgina d'error o
    un marcatge que ha canviat. Val més plantar-se que desar el buit com si fos
    la composició d'enguany.
    """
    html = client.fetch_html(U.lligues_inscripcions(oberta.lliga_id))
    equips = parse_lliga_inscripcions(html)
    if not equips:
        raise ValueError(
            f"Cap equip inscrit a {oberta.nom} ({oberta.lliga_id}). O no s'hi ha "
            f"apuntat ningú, o la federació ha tornat a canviar el marcatge."
        )
    clubs = {e.club_id_extern: canonic(e.club) for e in equips if e.club_id_extern is not None}
    if not clubs:
        raise ValueError(
            f"Els {len(equips)} equips de {oberta.nom} no porten cap enllaç «Veure "
            f"inscrits»: sense l'id de club no se'n poden demanar els jugadors."
        )
    return Lliga(
        lliga_id=oberta.lliga_id,
        nom=oberta.nom,
        clubs=clubs,
        equips=len(equips),
        modalitat=oberta.modalitat,
    )


def llegeix_inscrits(client, lliga: Lliga) -> list[Inscrit]:
    """Els jugadors de tots els clubs d'una lliga, un club per petició."""
    out: list[Inscrit] = []
    for club_id, club in sorted(lliga.clubs.items()):
        html = client.fetch_html(U.lligues_participants(lliga.lliga_id, club_id))
        for j in parse_lliga_participants(html):
            out.append(
                Inscrit(
                    club=club,
                    club_id_extern=club_id,
                    jugador=j.jugador,
                    mitjana=j.mitjana,
                    fitxatge=j.fitxatge,
                    posicio=j.posicio,
                )
            )
    return out


def clubs_sense_jugadors(lliga: Lliga, inscrits: list[Inscrit]) -> list[str]:
    """Clubs inscrits a la lliga que no han donat cap jugador.

    Pot voler dir dues coses que des d'aquí no es distingeixen: que el club
    encara no ha presentat la llista, o que la seva pàgina ha fallat. En tots
    dos casos el que hi tinguem desat es queda com està (vegeu `desa`), i qui
    crida ho ha de dir en veu alta.
    """
    amb = {i.club for i in inscrits}
    return sorted(c for c in lliga.clubs.values() if c not in amb)


# --------------------------- revisió ---------------------------

#: Un club en reclama un altre com a seu, o cap no el reclama.
TIPUS_DOS_CLUBS = "dos clubs sense fitxatge"
TIPUS_FITXATGE_ORFE = "fitxatge sense club d'origen"
TIPUS_SENSE_MITJANA = "mitjana a zero"
TIPUS_FORA_RANQUING = "fora del rànquing"


@dataclass(frozen=True)
class Avis:
    """Una fila que no es pot llegir com a bona, i per què."""

    tipus: str
    jugador: str
    clubs: tuple[str, ...]
    detall: str


def revisa(inscrits: list[Inscrit], mitjanes: dict[str, float] | None = None) -> list[Avis]:
    """Les contradiccions de la llista, sense mirar res més que la llista.

    Amb el fitxatge ben posat, cada persona té **exactament un** club que la
    reclama com a seva —la fila sense marca— i, si l'han fitxat, una segona
    fila marcada al club que se l'endú. Les tres coses que no quadren són:

    - dues files i cap de marcada: dos clubs se'l reclamen i no se sap quin és;
    - una fila marcada i cap de neta: se l'endú un club i cap no el dona;
    - mitjana a zero: la federació hi posa un 0 quan el jugador no és al
      rànquing vigent, i el zero l'envia a l'últim lloc de la llista del club.

    `mitjanes` és opcional i, si es passa —el rànquing vigent de la modalitat,
    per nom normalitzat—, s'hi afegeix qui porta mitjana però no hi surt: el
    número que li han posat no es pot contrastar amb res.
    """
    per_jugador: dict[str, list[Inscrit]] = {}
    for i in inscrits:
        per_jugador.setdefault(_norm(i.jugador), []).append(i)

    avisos: list[Avis] = []
    for files in per_jugador.values():
        nom = files[0].jugador
        propis = [f for f in files if not f.fitxatge]
        fitxats = [f for f in files if f.fitxatge]
        clubs = tuple(f.club for f in files)
        if len(propis) > 1:
            avisos.append(
                Avis(
                    TIPUS_DOS_CLUBS,
                    nom,
                    clubs,
                    f"{len(propis)} clubs se'l reclamen com a seu i cap fila no porta "
                    f"la marca de fitxatge: {', '.join(f.club for f in propis)}.",
                )
            )
        elif fitxats and not propis:
            avisos.append(
                Avis(
                    TIPUS_FITXATGE_ORFE,
                    nom,
                    clubs,
                    f"El fitxa {fitxats[0].club} però cap club no el té com a jugador "
                    f"propi. O el seu club no l'ha inscrit, o la marca sobra.",
                )
            )

    for i in inscrits:
        if not i.mitjana:
            avisos.append(
                Avis(
                    TIPUS_SENSE_MITJANA,
                    i.jugador,
                    (i.club,),
                    f"Mitjana 0 a {i.club}: queda l'últim de la llista del club.",
                )
            )
        elif mitjanes is not None and _norm(i.jugador) not in mitjanes:
            avisos.append(
                Avis(
                    TIPUS_FORA_RANQUING,
                    i.jugador,
                    (i.club,),
                    f"Porta mitjana {i.mitjana:.5f} però no surt al rànquing vigent, "
                    f"o sigui que el número no es pot contrastar.",
                )
            )

    avisos.sort(key=lambda a: (a.tipus, a.jugador))
    return avisos


# --------------------------- desat ---------------------------


def del_cens(conn: sqlite3.Connection, nom: str) -> str:
    """El nom del club tal com és al cens, per poder-hi lligar per nom.

    La federació escriu el mateix club de maneres diferents segons la pàgina
    —«S.B. CORAL COLÓN» a les inscripcions i «S.B.CORAL COLÓN» al cens— i un
    espai de més trenca qualsevol `JOIN` per nom. La resolució del repositori
    ja sap comparar sense puntuació ni accents i mirar la taula d'àlies.
    """
    from fcbillar.db.repository import Repository

    club_id = Repository(conn).resolve_club_id_by_nom(nom)
    if club_id is None:
        return canonic(nom)
    return conn.execute("SELECT nom FROM clubs WHERE id = ?", (club_id,)).fetchone()[0]


def desa(conn: sqlite3.Connection, lliga: Lliga, inscrits: list[Inscrit], temporada: str) -> int:
    """Desa els inscrits. Reemplaça **els clubs que han contestat**, no la lliga.

    Cada club és una pàgina, i una pàgina pot fallar o tornar buida ella sola.
    Si es reemplacés la lliga sencera, n'hi hauria prou que un club dels 38
    tornés zero jugadors —un 500, un tall de xarxa, una llista que encara no
    han presentat— perquè la ingesta n'esborrés la composició i la deixés en
    blanc sense dir res. La unitat que es pot substituir amb garanties és la
    mateixa que la de la font: un club.

    Del que no ha contestat no se'n toca res: val més la composició d'ahir que
    un silenci d'avui. Qui crida ho sap per `clubs_sense_jugadors` i ho ha de
    dir.

    Sí que s'esborren els clubs que ja **no estan inscrits** a la lliga: aquells
    no callen, és que han marxat, i això ho diu la pàgina d'inscripcions, que és
    l'única que hem comprovat que no ve buida.
    """
    if not inscrits:
        raise ValueError(
            f"Cap inscrit a la lliga {lliga.lliga_id}. No esborro els que hi ha "
            f"per posar-hi el buit."
        )
    cens = {c: del_cens(conn, c) for c in lliga.clubs.values()}
    for club in {i.club for i in inscrits}:
        cens.setdefault(club, del_cens(conn, club))

    # Sense llista de clubs no hi ha contra què comparar, i esborrar-ho tot
    # seria justament el que aquesta funció evita.
    inscrits_al_cens = {cens[c] for c in lliga.clubs.values()}
    if inscrits_al_cens:
        conn.execute(
            "DELETE FROM lliga_inscrits WHERE lliga_id = ? AND club NOT IN "
            f"({','.join('?' * len(inscrits_al_cens))})",
            (lliga.lliga_id, *sorted(inscrits_al_cens)),
        )
    conn.executemany(
        "DELETE FROM lliga_inscrits WHERE lliga_id = ? AND club = ?",
        [(lliga.lliga_id, cens[c]) for c in {i.club for i in inscrits}],
    )
    conn.executemany(
        "INSERT INTO lliga_inscrits (temporada, lliga_id, lliga, modalitat, club, "
        "club_id_extern, jugador, mitjana, fitxatge, posicio) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                temporada,
                lliga.lliga_id,
                lliga.nom,
                lliga.modalitat,
                cens[i.club],
                i.club_id_extern,
                i.jugador,
                i.mitjana,
                int(i.fitxatge),
                i.posicio,
            )
            for i in inscrits
        ],
    )
    conn.commit()
    return len(inscrits)


def retira_lligues_tancades(
    conn: sqlite3.Connection, temporada: str, obertes: set[int]
) -> dict[int, int]:
    """Treu els inscrits de les lligues que ja no són al llistat de la federació.

    `desa()` reconcilia una lliga que seguim ingerint, però una lliga que es
    tanca deixa de sortir al llistat i no la visitem mai més: les seves files es
    quedarien aquí per sempre, i d'aquí passarien al núvol i a la pantalla com
    si la competició encara existís.

    L'autoritat és `llegeix_lligues()`, que és el mateix llistat d'on surten les
    que sí que s'ingereixen. Va per temporada perquè el llistat també: només
    ensenya les de la temporada en joc, i les d'anys passats no s'han de tocar.

    Amb el llistat buit no s'esborra res. Que la federació no en publiqui cap no
    vol dir que s'hagin acabat totes: vol dir que la pàgina no ha contestat el
    que esperàvem, i és el mateix criteri que fa que `desa()` no desi el buit.
    """
    if not obertes:
        raise ValueError("Cap lliga oberta: no esborro els inscrits que hi ha.")

    tancades = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT lliga_id, COUNT(*) FROM lliga_inscrits WHERE temporada = ? GROUP BY lliga_id",
            (temporada,),
        )
        if r[0] not in obertes
    }
    if tancades:
        conn.executemany(
            "DELETE FROM lliga_inscrits WHERE temporada = ? AND lliga_id = ?",
            [(temporada, i) for i in tancades],
        )
        conn.commit()
    return tancades


def mitjanes_del_ranquing(conn: sqlite3.Connection, ranking_id: int) -> dict[str, float]:
    """Les mitjanes d'un rànquing per nom normalitzat, per contrastar-hi la font."""
    return {
        _norm(nom): mitjana
        for nom, mitjana in conn.execute(
            "SELECT p.nom, e.mitjana_general FROM ranking_entries e "
            "JOIN players p ON p.id = e.player_id WHERE e.ranking_id = ?",
            (ranking_id,),
        )
        if mitjana is not None
    }
