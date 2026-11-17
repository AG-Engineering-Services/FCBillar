"""Desa a les taules `ext_*` el que han llegit els lectors de cada font."""

from __future__ import annotations

from fcbillar.externes.model import Resultat


def _iso(d) -> str | None:
    return d.isoformat() if d is not None else None


def desa(conn, resultat: Resultat) -> tuple[int, int]:
    """Desa un esdeveniment amb les seves partides o totals.

    Reemplaça el que hi hagués del mateix esdeveniment: tornar a llegir una font
    no duplica res, i si la font ha corregit una partida, la correcció mana.
    Retorna (partides, totals) desats.
    """
    e = resultat.esdeveniment
    with conn:
        conn.execute("DELETE FROM ext_partides WHERE font = ? AND esdeveniment = ?", (e.font, e.id))
        conn.execute("DELETE FROM ext_totals WHERE font = ? AND esdeveniment = ?", (e.font, e.id))
        conn.execute(
            """INSERT INTO ext_esdeveniments
                   (font, id, nom, modalitat, ambit, tipus, temporada, data_inici, data_fi, lloc, url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (font, id) DO UPDATE SET
                   nom = excluded.nom, modalitat = excluded.modalitat, ambit = excluded.ambit,
                   tipus = excluded.tipus, temporada = excluded.temporada,
                   data_inici = excluded.data_inici, data_fi = excluded.data_fi,
                   lloc = excluded.lloc, url = excluded.url""",
            (
                e.font,
                e.id,
                e.nom,
                e.modalitat,
                e.ambit,
                e.tipus,
                e.temporada,
                _iso(e.data_inici),
                _iso(e.data_fi),
                e.lloc,
                e.url,
            ),
        )
        conn.executemany(
            """INSERT INTO ext_partides
                   (font, esdeveniment, ordre, data, fase, grup,
                    jugador1, nacio1, caramboles1, entrades1, serie1, punts1,
                    jugador2, nacio2, caramboles2, entrades2, serie2, punts2)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    e.font,
                    e.id,
                    p.ordre,
                    _iso(p.data or e.data_inici),
                    p.fase,
                    p.grup,
                    p.jugador1,
                    p.nacio1,
                    p.caramboles1,
                    p.entrades1,
                    p.serie1,
                    p.punts1,
                    p.jugador2,
                    p.nacio2,
                    p.caramboles2,
                    p.entrades2,
                    p.serie2,
                    p.punts2,
                )
                for p in resultat.partides
            ],
        )
        # Un mateix nom dues vegades en una classificació (rar, però passa en
        # PDF mal fets): es queda la primera fila, que és la de millor posició.
        vistos: set[str] = set()
        files = []
        for t in resultat.totals:
            if t.jugador in vistos:
                continue
            vistos.add(t.jugador)
            files.append(
                (
                    e.font,
                    e.id,
                    t.jugador,
                    t.federacio,
                    t.posicio,
                    t.jugades,
                    t.guanyades,
                    t.empatades,
                    t.perdudes,
                    t.caramboles,
                    t.entrades,
                    t.serie,
                )
            )
        conn.executemany(
            """INSERT INTO ext_totals
                   (font, esdeveniment, jugador, federacio, posicio, jugades, guanyades,
                    empatades, perdudes, caramboles, entrades, serie)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            files,
        )
    return len(resultat.partides), len(files)
