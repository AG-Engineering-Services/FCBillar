"""Un campionat que s'està jugant no té classificació final, i no se n'ha de publicar.

`open_classifications` és la classificació FINAL d'un torneig: d'ella pengen el
palmarès de la fitxa, el de c3b i la pàgina del torneig, i totes tres llegeixen
«1r, 2n, 3r» com un podi.

`torneig_participants.posicio` sempre en porta una, perquè és el rànquing de la
ronda que s'ha jugat —i ha de ser-hi, que és el que ensenya la pàgina del
campionat—, o sigui que publicar-la sense mirar res converteix una PRE-PRÈVIA en
un campionat guanyat. El 20/09/2026 el palmarès deia que en Corominas havia guanyat
la 1a divisió i l'Ametller hi era segon amb una pre-prèvia jugada.
"""

from __future__ import annotations

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals


def _torneig(conn, tid: int, nom: str, temporada_id: int, fases: list[tuple[int, str]]) -> None:
    conn.execute(
        "INSERT INTO torneigs_individuals "
        "(id, torneig_id_extern, divisio_id_extern, nom, temporada_id) VALUES (?,?,?,?,?)",
        (tid, tid, tid, nom, temporada_id),
    )
    for ordre, nom_fase in fases:
        conn.execute(
            "INSERT INTO torneig_fases (torneig_id, fase_id_extern, nom, ordre, tipus) "
            "VALUES (?,?,?,?,'grups')",
            (tid, tid * 100 + ordre, nom_fase, ordre),
        )


@pytest.fixture
def conn(tmp_path):
    """Quatre torneigs: dos d'ara (un a mitges, un acabat) i dos de la temporada passada."""
    c = ensure_schema(tmp_path / "t.db")
    c.execute("INSERT INTO temporades (id, nom) VALUES (1, '2025-2026')")
    c.execute("INSERT INTO temporades (id, nom) VALUES (2, '2026-2027')")

    # Ara: una pre-prèvia jugada i res més. S'està jugant.
    _torneig(c, 100, "TRES BANDES INDIVIDUAL - 1A DIVISIÓ", 2, [(1, "PRE-PRÈVIA")])
    # Ara: acabat, amb el nom que la federació posa a l'última ronda.
    _torneig(c, 101, "OPEN LLIURE PUNT D'ATAC", 2, [(1, "PRÈVIA"), (2, "FASE FINAL")])
    # La temporada passada: acabat, i l'última fase no és cap ronda de la seqüència.
    _torneig(c, 10, "TRES BANDES - 3A DIVISIÓ", 1, [(1, "PRÈVIA"), (2, "QUALIFICACIÓ")])
    # La temporada passada: només se'n van ingerir les fases de grups.
    _torneig(c, 11, "OPEN TRES BANDES SANTS", 1, [(1, "PRE-PRÈVIA"), (2, "PRÈVIA")])
    c.commit()
    return c


def test_nomes_el_de_la_temporada_en_curs_a_mitges(conn) -> None:
    assert cloud_sync._torneigs_en_joc(conn) == {100}


def test_l_ultima_fase_manda_i_no_el_conjunt(conn) -> None:
    """El de 3a divisió de la 2025-26 té PRÈVIA i no té FINAL, i està acabat.

    Mirant el conjunt de fases sortiria «en joc»: hi ha la prèvia i no la final.
    El que ho diu és l'última fase, «QUALIFICACIÓ», que vol dir «aquí s'acaba».
    """
    assert 10 not in cloud_sync._torneigs_en_joc(conn)


def test_un_open_acabat_sense_els_quadres_ingerits_no_hi_cau(conn) -> None:
    """De la 2025-26 n'hi ha quatre així, i el palmarès no els pot perdre."""
    assert 11 not in cloud_sync._torneigs_en_joc(conn)


def test_sense_cap_fase_no_se_n_sap_res(conn) -> None:
    """Els 287 campionats històrics no tenen fases: es publiquen com sempre."""
    conn.execute(
        "INSERT INTO torneigs_individuals "
        "(id, torneig_id_extern, divisio_id_extern, nom, temporada_id) "
        "VALUES (900, 900, 900, 'CAMPIONAT CATALUNYA HISTÒRIC LLIURE', 1)"
    )
    conn.commit()
    assert 900 not in cloud_sync._torneigs_en_joc(conn)


def test_la_classificacio_publicada_d_un_torneig_a_mitges_es_retira(tmp_path, monkeypatch) -> None:
    """I el que ja s'hagués publicat se n'ha d'anar, que si no es queda al núvol."""
    db = tmp_path / "t.db"
    c = ensure_schema(db)
    c.execute("INSERT INTO temporades (id, nom) VALUES (2, '2026-2027')")
    _torneig(c, 100, "TRES BANDES INDIVIDUAL - 1A DIVISIÓ", 2, [(1, "PRE-PRÈVIA")])
    c.execute("INSERT INTO players (id, fcb_id, nom) VALUES (1, '1', 'COROMINAS FRANCH, ESTEVE')")
    c.execute(
        "INSERT INTO torneig_participants (torneig_id, player_id, posicio) VALUES (100, 1, 1)"
    )
    c.commit()
    c.close()

    magatzem: dict[str, list[dict]] = {
        "opens": [{"open_id": 100}],
        "open_classifications": [{"open_id": 100, "posicio": 1, "player_fcb_id": "1"}],
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    counts = cloud_sync.publish_opens(db_path=db)

    assert counts["open_classifications"] == 0, "no se n'ha de publicar cap"
    assert magatzem["open_classifications"] == [], "i la que hi havia se n'ha d'anar"
