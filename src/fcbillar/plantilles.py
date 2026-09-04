"""De qui està fet cada club, estimat.

La federació no publica les plantilles. Publica qui té llicència a cada club
—que ho tenim a `players.club_id`—, però aquella llista inclou gent que fa anys
que no juga, i no diu qui alinearà cada equip.

L'estimació és la que va acordar el club: hi entra qui **ha jugat la lliga
aquesta temporada o l'anterior**, o qui **consta al llistat de divisions del
campionat individual d'aquesta temporada**. La primera condició agafa qui és en
actiu; la segona, qui s'acaba d'inscriure i encara no ha jugat res.

De quin club és cadascú ho diu el llistat de divisions, no el cens. El cens el té
on el vam veure per última vegada, i qui ha fitxat en un altre lloc hi segueix
constant fins que hi torni a jugar; el llistat és el document de la temporada que
comença.

És una estimació i s'ha de dir. A la interfície va marcada com a «estimat»:
ningú no ha de creure's que això és una alineació oficial.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

#: Per què hi és cada jugador. Va a la fila perquè es pugui explicar.
MOTIU_JUGAT = "ha jugat"
MOTIU_INSCRIT = "inscrit a l'individual"


#: D'on surt la mitjana de cadascú.
FONT_RANQUING = "rànquing"
FONT_DIVISIONS = "divisions"


@dataclass(frozen=True)
class Jugador:
    club: str
    #: Buit per a qui encara no té fitxa nostra: acaba de federar-se i no ha
    #: jugat res, o sigui que no ha aparegut mai en cap partida.
    player_fcb_id: str | None
    jugador: str
    #: La millor que en tenim. `None` si no en tenim cap.
    mitjana: float | None
    #: D'on surt: del rànquing oficial o del llistat de divisions.
    mitjana_font: str | None
    motiu: str


def temporades_recents(conn, quantes: int = 2) -> list[int]:
    """Les temporades amb encontres de lliga més recents.

    Es miren les que tenen encontres i no totes: `temporades` en porta de
    buides, i «l'anterior» ha de voler dir l'anterior que es va jugar.
    """
    return [
        r[0]
        for r in conn.execute(
            """
            SELECT e.temporada_id
            FROM encontres_lliga e JOIN temporades t ON t.id = e.temporada_id
            WHERE e.temporada_id IS NOT NULL
            GROUP BY e.temporada_id
            ORDER BY t.nom DESC
            LIMIT ?
            """,
            (quantes,),
        )
    ]


def plantilles(conn, ranking_id: int, temporada_inscrits: str) -> list[Jugador]:
    """Els jugadors que es poden esperar a cada club, amb la seva mitjana."""
    conn.row_factory = sqlite3.Row
    temps = temporades_recents(conn)
    # Sense cap temporada amb encontres no hi ha ningú que «hagi jugat», però la
    # meitat dels inscrits de la regla sí que existeix i s'ha de mirar igualment.
    marques = ",".join("?" * len(temps))
    jugat = (
        {
            r[0]
            for r in conn.execute(
                f"""
                SELECT g.player1_id FROM games g
                  JOIN encontres_lliga e ON e.id = g.encontre_lliga_id
                 WHERE e.temporada_id IN ({marques})
                UNION
                SELECT g.player2_id FROM games g
                  JOIN encontres_lliga e ON e.id = g.encontre_lliga_id
                 WHERE e.temporada_id IN ({marques})
                """,
                (*temps, *temps),
            )
        }
        if temps
        else set()
    )
    inscrits = {
        r[0]
        for r in conn.execute(
            "SELECT p.id FROM inscrits_individual i JOIN players p ON p.nom = i.jugador "
            "WHERE i.temporada = ?",
            (temporada_inscrits,),
        )
    }
    mitjanes = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT player_id, mitjana_general FROM ranking_entries WHERE ranking_id = ?",
            (ranking_id,),
        )
    }
    # Qui encara no és al rànquing general -perquè no ha començat a jugar- sí
    # que té mitjana al llistat de divisions: és la que la federació li assigna
    # per repartir-lo per categories, i és l'única que en tenim.
    del_pdf = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT p.id, i.mitjana FROM inscrits_individual i JOIN players p ON p.nom = i.jugador "
            "WHERE i.temporada = ?",
            (temporada_inscrits,),
        )
    }

    # De quin club és cadascú AQUESTA temporada. `players.club_id` diu el del
    # cens, que és on el vam veure l'última vegada: qui ha fitxat en un altre lloc
    # hi segueix constant fins que hi torni a jugar. El llistat de divisions és el
    # document de la temporada que comença, i per tant mana ell. Són 30 jugadors
    # del 26/27, un d'ells cap a casa (Ferran Rodríguez, de Llinars a Banyoles).
    club_del_pdf = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT jugador, club FROM inscrits_individual WHERE temporada = ?",
            (temporada_inscrits,),
        )
    }

    out: list[Jugador] = []
    vistos: set[str] = set()
    for r in conn.execute(
        "SELECT p.id, p.fcb_id, p.nom, c.nom AS club FROM players p "
        "JOIN clubs c ON c.id = p.club_id"
    ):
        if r["id"] in jugat:
            motiu = MOTIU_JUGAT
        elif r["id"] in inscrits:
            motiu = MOTIU_INSCRIT
        else:
            continue
        mitjana, font = mitjanes.get(r["id"]), FONT_RANQUING
        if mitjana is None:
            mitjana, font = del_pdf.get(r["id"]), FONT_DIVISIONS
        out.append(
            Jugador(
                club=club_del_pdf.get(r["nom"]) or r["club"],
                player_fcb_id=r["fcb_id"],
                jugador=r["nom"],
                mitjana=mitjana,
                mitjana_font=font if mitjana is not None else None,
                motiu=motiu,
            )
        )
        vistos.add(r["nom"])

    # Qui s'acaba de federar consta al llistat de divisions i no té fila a
    # `players`: no ha jugat mai res, i per aquí no hi passa. Deixar-lo fora
    # seria buidar de la plantilla justament qui la regla dels inscrits volia
    # agafar, i sense dir-ho. Del PDF en surt el club i la mitjana; el `fcb_id`
    # arribarà el dia que jugui.
    for r in conn.execute(
        "SELECT club, jugador, mitjana FROM inscrits_individual WHERE temporada = ?",
        (temporada_inscrits,),
    ):
        # Per nom i prou. Amb (club, nom) qui hagi canviat de club sortiria dos
        # cops: el cens encara el té a l'antic i el PDF ja el posa al nou.
        if r["jugador"] in vistos:
            continue
        vistos.add(r["jugador"])
        out.append(
            Jugador(
                club=r["club"],
                player_fcb_id=None,
                jugador=r["jugador"],
                mitjana=r["mitjana"],
                mitjana_font=FONT_DIVISIONS if r["mitjana"] is not None else None,
                motiu=MOTIU_INSCRIT,
            )
        )
    # Per club i, dins de cada club, de més mitjana a menys. Qui no en té va al
    # final: encara no ha jugat prou per tenir-ne, no és que jugui malament.
    out.sort(key=lambda j: (j.club, -(j.mitjana or 0.0), j.jugador))
    return out


def desa(conn, jugadors: list[Jugador], temporada: str) -> int:
    """Desa les plantilles estimades. Reemplaça les de la temporada.

    No es desa el buit: una llista buida voldria dir que el càlcul no ha trobat
    ningú, i sobreescriure-hi el que hi ha seria canviar una estimació per un
    silenci.
    """
    if not jugadors:
        raise ValueError(
            "Cap jugador a les plantilles. No esborro les que hi ha per posar-hi el buit."
        )
    conn.execute("DELETE FROM club_plantilles WHERE temporada = ?", (temporada,))
    conn.executemany(
        "INSERT INTO club_plantilles "
        "(temporada, club, player_fcb_id, jugador, mitjana, mitjana_font, motiu) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (temporada, j.club, j.player_fcb_id, j.jugador, j.mitjana, j.mitjana_font, j.motiu)
            for j in jugadors
        ],
    )
    conn.commit()
    return len(jugadors)
