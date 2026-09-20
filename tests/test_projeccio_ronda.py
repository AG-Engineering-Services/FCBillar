"""La ronda següent, projectada mentre la federació no la publiqui.

Quan s'acaba una pre-prèvia ja se sap qui passa —la regla és al PDF del sorteig i
l'ordre entre grups es calcula— però la federació tarda dies a publicar com queden
repartits. Això es projecta, i la publicació oficial el substitueix.

El que és exacte i el que no:

    qui passa    la regla del PDF + la classificació publicada    EXACTE
    quin bombo   del nombre de places i la mida de grup           EXACTE
    quin grup    el repartiment que fem aquí                      PROJECCIÓ

L'última no es pot encertar: el sorteig de la federació és geogràfic. Per això la
prova d'aquest fitxer és que **els bombos** quedin bé, no el grup concret.
"""

from __future__ import annotations

import sqlite3

import pytest

from fcbillar import projeccio_ronda as PR
from fcbillar.db.migrations import ensure_schema
from fcbillar.individuals import projecta_ronda_seguent


def test_de_quina_ronda_ve_cadascuna() -> None:
    assert PR.ronda_seguent("PRE-PRÈVIA") == "PRÈVIA"
    assert PR.ronda_seguent("PRÈVIA") == "FINAL"
    assert PR.ronda_seguent("PRE-PRE-PRÈVIA") == "PRE-PRÈVIA"
    # De la final no en ve cap altra, i d'una fase que no és cap ronda tampoc.
    assert PR.ronda_seguent("FINAL") is None
    assert PR.ronda_seguent("FASE VUITENS") is None


def test_cada_grup_rep_un_de_cada_bombo() -> None:
    """És l'única cosa del sorteig que es pot saber abans que es faci."""
    files = PR.projecta([f"J{i:02}" for i in range(1, 19)])
    assert len(files) == 18
    per_grup: dict[str, list[int]] = {}
    for f in files:
        per_grup.setdefault(f.grup_projectat, []).append(f.bombo)
    assert len(per_grup) == 6, "18 jugadors de tres en tres són sis grups"
    for grup, bombos in per_grup.items():
        assert sorted(bombos) == [1, 2, 3], f"{grup} no té un de cada bombo: {bombos}"


def test_els_bombos_son_trams_del_ranquing() -> None:
    files = PR.projecta([f"J{i:02}" for i in range(1, 19)])
    per_bombo: dict[int, list[int]] = {}
    for f in files:
        per_bombo.setdefault(f.bombo, []).append(f.posicio)
    assert per_bombo[1] == list(range(1, 7))
    assert per_bombo[2] == list(range(7, 13))
    assert per_bombo[3] == list(range(13, 19))


def test_va_en_serpentina() -> None:
    """El primer del bombo 2 acompanya l'ÚLTIM del bombo 1, no el primer.

    Sense la serpentina, el grup A s'enduria el millor de cada bombo i el F el
    pitjor de cada un: sis grups de dificultat molt diferent.
    """
    files = {f.posicio: f.grup_projectat for f in PR.projecta([f"J{i:02}" for i in range(1, 19)])}
    assert files[1] == "Grup A" and files[6] == "Grup F"
    assert files[7] == "Grup F" and files[12] == "Grup A"
    assert files[13] == "Grup A" and files[18] == "Grup F"


def test_els_que_sobren_no_queden_fora() -> None:
    """Amb 20 i grups de tres surten sis grups i dos de quatre, no ningú al carrer."""
    files = PR.projecta([f"J{i:02}" for i in range(1, 21)])
    assert len(files) == 20
    assert len({f.grup_projectat for f in files}) == 6


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    c = ensure_schema(tmp_path / "t.db")
    c.execute("INSERT INTO temporades (id, nom) VALUES (1, '2026-2027')")
    c.execute(
        "INSERT INTO torneigs_individuals (id, torneig_id_extern, divisio_id_extern, nom, "
        "temporada_id) VALUES (1, 216, 455, 'TRES BANDES INDIVIDUAL - 1A DIVISIÓ', 1)"
    )
    c.commit()
    return c


def _fase(c, fase_id, nom, ordre, regla=None, places=None):
    c.execute(
        "INSERT INTO torneig_fases (id, torneig_id, fase_id_extern, nom, tipus, ordre, regla, places) "
        "VALUES (?, 1, ?, ?, 'grups', ?, ?, ?)",
        (fase_id, 800 + fase_id, nom, ordre, regla, places),
    )


def _membres(c, fase_id, quants, complet=True):
    """`quants` jugadors repartits de tres en tres, amb la seva posició de grup."""
    for i in range(quants):
        grup = f"Grup {chr(ord('A') + i // 3)}"
        pos = (i % 3) + 1 if complet else None
        c.execute(
            "INSERT INTO torneig_fase_grups (fase_id, grup_nom, jugador_nom, ordre, "
            "posicio_grup, punts, mitjana, serie_major) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (fase_id, grup, f"JUGADOR {i:02}", i, pos, 4 - (i % 3) * 2, 1.0 - i / 100, 5),
        )
    c.commit()


def test_projecta_quan_la_fase_esta_jugada_i_te_regla(conn) -> None:
    _fase(
        conn,
        1,
        "PRE-PRÈVIA",
        1,
        regla="els primers de cada grup i els set millors segons",
        places=18,
    )
    _membres(conn, 1, 33)

    resum = projecta_ronda_seguent(conn, 1)
    assert resum["estat"] == "projectada"
    assert resum["ronda"] == "PRÈVIA"
    assert resum["jugadors"] == 18
    assert resum["grups"] == 6
    assert conn.execute("SELECT COUNT(*) FROM torneig_ronda_projectada").fetchone()[0] == 18


def test_no_projecta_una_fase_a_mitges(conn) -> None:
    """Una llista de classificats que demà canviarà no serveix de res."""
    _fase(conn, 1, "PRE-PRÈVIA", 1, regla="els primers de cada grup", places=11)
    _membres(conn, 1, 33, complet=False)
    assert projecta_ronda_seguent(conn, 1)["estat"] == "fase a mitges"
    assert conn.execute("SELECT COUNT(*) FROM torneig_ronda_projectada").fetchone()[0] == 0


def test_sense_la_regla_no_s_inventa_quantes_places_hi_ha(conn) -> None:
    _fase(conn, 1, "PRE-PRÈVIA", 1)  # sense regla ni places
    _membres(conn, 1, 33)
    assert projecta_ronda_seguent(conn, 1)["estat"] == "sense regla"
    assert conn.execute("SELECT COUNT(*) FROM torneig_ronda_projectada").fetchone()[0] == 0


def test_quan_la_federacio_publica_la_ronda_la_projeccio_se_retira(conn) -> None:
    """És així com se substitueix: no cal esborrar-la a mà.

    La ingesta desa els grups de debò a `torneig_fase_grups` i la projecció, que
    només valia mentre no hi fossin, se'n va tota sola a la passada següent.
    """
    _fase(
        conn,
        1,
        "PRE-PRÈVIA",
        1,
        regla="els primers de cada grup i els set millors segons",
        places=18,
    )
    _membres(conn, 1, 33)
    assert projecta_ronda_seguent(conn, 1)["estat"] == "projectada"

    # La federació publica la PRÈVIA.
    _fase(conn, 2, "PRÈVIA", 2)
    _membres(conn, 2, 18)

    resum = projecta_ronda_seguent(conn, 1)
    # La projecció de la PRÈVIA se'n va perquè ja hi ha els grups de debò.
    assert resum["retirades"] == 18
    assert conn.execute("SELECT COUNT(*) FROM torneig_ronda_projectada").fetchone()[0] == 0
    # I `estat` diu què passa amb la ronda que ve ARA, que és la FINAL: no es
    # projecta perquè el seu PDF de sorteig encara no existeix. Les dues coses són
    # certes i totes dues s'han de poder llegir.
    assert resum["estat"] == "sense regla"


def test_es_projecta_la_ronda_nova_quan_te_regla(conn) -> None:
    """Publicada la PRÈVIA i llegit el seu PDF, el que es projecta és la FINAL."""
    _fase(
        conn,
        1,
        "PRE-PRÈVIA",
        1,
        regla="els primers de cada grup i els set millors segons",
        places=18,
    )
    _membres(conn, 1, 33)
    projecta_ronda_seguent(conn, 1)

    _fase(conn, 2, "PRÈVIA", 2, regla="els dos primers de cada grup", places=12)
    _membres(conn, 2, 18)

    resum = projecta_ronda_seguent(conn, 1)
    assert resum["retirades"] == 18, "la de la PRÈVIA, que ja és publicada"
    assert resum["estat"] == "projectada"
    assert resum["ronda"] == "FINAL"
    assert resum["jugadors"] == 12
    rondes = {r[0] for r in conn.execute("SELECT DISTINCT ronda FROM torneig_ronda_projectada")}
    assert rondes == {"FINAL"}, "no hi pot quedar cap projecció de la PRÈVIA"
