"""De qui està fet cada club, estimat.

La federació no publica plantilles. L'estimació és la que va acordar el club: hi
entra qui ha jugat la lliga aquesta temporada o l'anterior, o qui consta al
llistat de divisions del campionat individual d'aquesta.

La segona meitat de la regla existeix per a qui s'acaba de federar, i durant un
temps era justament la que no funcionava: un jugador nou surt al PDF de
divisions i encara no té fitxa nostra —no ha jugat res—, i per aquí quedava fora
de la plantilla del seu club sense que ho digués ningú.
"""

from __future__ import annotations

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.plantilles import (
    FONT_DIVISIONS,
    FONT_RANQUING,
    MOTIU_INSCRIT,
    MOTIU_JUGAT,
    desa,
    plantilles,
)

TEMPORADA = "2026/2027"


@pytest.fixture
def conn(tmp_path):
    c = ensure_schema(tmp_path / "t.db")
    for nom in ("C.B.BANYOLES", "C.B.MANRESA"):
        c.execute("INSERT INTO clubs (fcb_id, nom) VALUES (?, ?)", (nom, nom))
    c.execute("INSERT INTO temporades (nom) VALUES ('2025-2026')")
    c.execute(
        "INSERT INTO rankings "
        "(num_seq, modalitat_id, url, format_url, any_pub, mes_pub, data_pub) VALUES "
        "(124, (SELECT id FROM modalitats WHERE nom = 'Tres bandes'), '', 'historial', "
        "2026, 8, '2026-07-27')"
    )
    return c


def _ranking_id(conn) -> int:
    return conn.execute("SELECT id FROM rankings").fetchone()[0]


def _jugador(conn, nom: str, club: str) -> int:
    cid = conn.execute("SELECT id FROM clubs WHERE nom = ?", (club,)).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO players (fcb_id, nom, club_id) VALUES (?, ?, ?)", (nom, nom, cid)
    )
    return cur.lastrowid


def _rival(conn) -> int:
    """L'altra meitat de la partida. `games` en vol dos i aquí no interessa qui."""
    fila = conn.execute("SELECT id FROM players WHERE nom = 'RIVAL, UN'").fetchone()
    return fila[0] if fila else _jugador(conn, "RIVAL, UN", "C.B.MANRESA")


def _va_jugar(conn, player_id: int) -> None:
    """Una partida de lliga la temporada passada, que és el que el fa de la plantilla."""
    temp = conn.execute("SELECT id FROM temporades WHERE nom = '2025-2026'").fetchone()[0]
    conn.execute(
        "INSERT INTO encontres_lliga "
        "(id, lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern, temporada_id) "
        "VALUES (1, 38, 1, 1, 1, 1, ?) ON CONFLICT (id) DO NOTHING",
        (temp,),
    )
    conn.execute(
        "INSERT INTO games "
        "(data_partida, modalitat_id, player1_id, player2_id, encontre_lliga_id, temporada_id) "
        "VALUES ('2026-01-10', (SELECT id FROM modalitats WHERE nom = 'Tres bandes'), "
        "?, ?, 1, ?)",
        (player_id, _rival(conn), temp),
    )


def _inscrit(conn, nom: str, club: str, mitjana: float | None = 0.4) -> None:
    conn.execute(
        "INSERT INTO inscrits_individual "
        "(temporada, divisio, posicio, jugador, club, mitjana, definitiva) "
        "VALUES (?, '5ª', 1, ?, ?, ?, 1)",
        (TEMPORADA, nom, club, mitjana),
    )


def test_qui_s_acaba_de_federar_no_pot_quedar_fora(conn) -> None:
    """Surt al PDF de divisions i encara no té fitxa: és el cas que la regla volia agafar."""
    _inscrit(conn, "TRONCOSO GENES, RAFAEL", "C.B.MANRESA", 0.400)
    _va_jugar(conn, _jugador(conn, "ALGU, ALTRE", "C.B.MANRESA"))

    quins = {j.jugador: j for j in plantilles(conn, _ranking_id(conn), TEMPORADA)}

    nou = quins["TRONCOSO GENES, RAFAEL"]
    assert nou.club == "C.B.MANRESA"
    assert nou.player_fcb_id is None
    assert nou.motiu == MOTIU_INSCRIT
    assert (nou.mitjana, nou.mitjana_font) == (0.400, FONT_DIVISIONS)


def test_ningu_no_surt_dos_cops_encara_que_hagi_canviat_de_club(conn) -> None:
    """El cens el té a l'antic i el PDF ja el posa al nou: és la mateixa persona."""
    _va_jugar(conn, _jugador(conn, "QUI, CANVIA", "C.B.BANYOLES"))
    _inscrit(conn, "QUI, CANVIA", "C.B.MANRESA")

    quins = [
        j for j in plantilles(conn, _ranking_id(conn), TEMPORADA) if j.jugador == "QUI, CANVIA"
    ]
    assert len(quins) == 1


def test_la_mitjana_del_ranquing_mana_sobre_la_del_pdf(conn) -> None:
    """La del PDF és la que la federació assigna per repartir per categories."""
    pid = _jugador(conn, "JA, JUGAVA", "C.B.BANYOLES")
    _va_jugar(conn, pid)
    _inscrit(conn, "JA, JUGAVA", "C.B.BANYOLES", 0.400)
    conn.execute(
        "INSERT INTO ranking_entries (ranking_id, player_id, posicio, mitjana_general) "
        "VALUES (?, ?, 1, 0.717)",
        (_ranking_id(conn), pid),
    )

    j = next(j for j in plantilles(conn, _ranking_id(conn), TEMPORADA) if j.jugador == "JA, JUGAVA")
    assert (j.mitjana, j.mitjana_font, j.motiu) == (0.717, FONT_RANQUING, MOTIU_JUGAT)


def test_qui_no_te_mitjana_enlloc_hi_es_igualment(conn) -> None:
    """Encara no ha jugat prou per tenir-ne; això no el treu de la plantilla."""
    _va_jugar(conn, _jugador(conn, "SENSE, MITJANA", "C.B.BANYOLES"))

    j = next(
        j for j in plantilles(conn, _ranking_id(conn), TEMPORADA) if j.jugador == "SENSE, MITJANA"
    )
    assert (j.mitjana, j.mitjana_font) == (None, None)


def test_no_es_desa_el_buit_sobre_el_que_ja_hi_ha(conn) -> None:
    """Zero jugadors vol dir que el càlcul ha fallat, no que el club s'hagi buidat."""
    _inscrit(conn, "ALGU, U", "C.B.MANRESA")
    desa(conn, plantilles(conn, _ranking_id(conn), TEMPORADA), TEMPORADA)
    with pytest.raises(ValueError):
        desa(conn, [], TEMPORADA)
    assert conn.execute("SELECT COUNT(*) FROM club_plantilles").fetchone()[0] == 1


def test_desa_qui_no_te_fitxa(conn) -> None:
    """La taula ha d'admetre `player_fcb_id` buit: la clau és el nom."""
    _inscrit(conn, "TRONCOSO GENES, RAFAEL", "C.B.MANRESA")
    desa(conn, plantilles(conn, _ranking_id(conn), TEMPORADA), TEMPORADA)

    fila = conn.execute(
        "SELECT player_fcb_id, motiu FROM club_plantilles WHERE jugador = ?",
        ("TRONCOSO GENES, RAFAEL",),
    ).fetchone()
    assert tuple(fila) == (None, MOTIU_INSCRIT)
