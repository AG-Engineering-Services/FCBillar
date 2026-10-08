"""Quina lliga es publica i quina temporada és, sense cap número escrit al codi.

Fins a l'octubre de 2026 la publicació duia `LLIGA_3B_ID = 38` i `LLIGA_4M_ID =
39`, i sis comandes duien `--temporada "2026/2027"` per defecte. La ingesta ja
seguia el llistat de la federació; la publicació no. El setembre de 2026, amb la
temporada nova ja ingerida, el web va seguir ensenyant la lliga de la passada
fins que algú va canviar el número: res no fallava.

Aquí es comprova que les dues respostes surten del llistat de la federació, que
canvien soles quan el llistat canvia, i que quan no es poden saber és un error i
no un valor vell.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from fcbillar import cloud_sync, en_curs
from fcbillar.db.migrations import ensure_schema
from fcbillar.scraper.parsers import LligaOberta, parse_lligues_llistat

FIXTURES = Path(__file__).parent / "fixtures" / "nou"

TRES_BANDES = LligaOberta(
    38, "Lliga Catalana Tres Bandes", "Tres bandes", date(2026, 9, 1), "Activa"
)
QUATRE_MOD = LligaOberta(
    39, "Lliga Catalana 4 Modalitats", "4 Modalitats", date(2026, 8, 24), "Activa"
)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    for variable in ("FCB_LLIGA_3B_ID", "FCB_LLIGA_4M_ID", "FCB_TEMPORADA"):
        monkeypatch.delenv(variable, raising=False)
    return ensure_schema(tmp_path / "t.db")


def _encontre(conn, lliga: int, data: str) -> None:
    conn.execute(
        "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id, data) "
        "VALUES (?, 1, 1, ?, ?)",
        (lliga, hash(data) % 100000, data),
    )


# --------------------------- quina mena de lliga és ---------------------------


def test_la_mena_surt_del_que_diu_la_fila() -> None:
    assert en_curs.mena_de_lliga("Lliga Catalana Tres Bandes", "Tres bandes") == "3B"
    assert en_curs.mena_de_lliga("Lliga Catalana 4 Modalitats", "4 Modalitats") == "4M"
    assert en_curs.mena_de_lliga("LLIGA 3 BANDES") == "3B"
    assert en_curs.mena_de_lliga("Lliga Femenina", "Lliure") is None


def test_el_llistat_de_debo_dona_una_de_cada() -> None:
    """La captura del llistat de la federació: la 38 és la de 3B i la 39 la de 4M."""
    obertes, descartades = parse_lligues_llistat(
        (FIXTURES / "lligues_llistat.html").read_text(encoding="utf-8")
    )

    assert descartades == []
    assert {en_curs.mena_de_lliga(o.nom, o.modalitat): o.lliga_id for o in obertes} == {
        "3B": 38,
        "4M": 39,
    }


# --------------------------- quina lliga es publica ---------------------------


def test_es_publica_la_del_llistat(conn) -> None:
    en_curs.desa_lligues_obertes(conn, [QUATRE_MOD, TRES_BANDES])

    assert en_curs.lliga_en_curs(conn, "3B") == 38
    assert en_curs.lliga_en_curs(conn, "4M") == 39


def test_quan_la_federacio_obre_la_temporada_nova_canvia_sola(conn) -> None:
    """El que no va passar el setembre de 2026: la 40 substitueix la 38 sense tocar res."""
    en_curs.desa_lligues_obertes(conn, [QUATRE_MOD, TRES_BANDES], ara=datetime(2027, 6, 1, 21, 0))
    nova = LligaOberta(40, "Lliga Catalana Tres Bandes", "Tres bandes", date(2027, 9, 1), "Activa")
    nova_4m = LligaOberta(
        41, "Lliga Catalana 4 Modalitats", "4 Modalitats", date(2027, 8, 24), "Activa"
    )

    en_curs.desa_lligues_obertes(conn, [nova, nova_4m], ara=datetime(2027, 9, 5, 21, 0))

    assert en_curs.lliga_en_curs(conn, "3B") == 40
    assert en_curs.lliga_en_curs(conn, "4M") == 41


def test_a_l_estiu_segueix_sent_l_ultima_que_s_hi_va_veure(conn) -> None:
    """La federació obre la de 4 Modalitats abans que la de Tres Bandes.

    Mentre al llistat només hi ha la 41, la de Tres Bandes que s'ha d'ensenyar
    segueix sent la 38, que és l'última que s'hi va veure: no hi ha cap altra.
    """
    en_curs.desa_lligues_obertes(conn, [QUATRE_MOD, TRES_BANDES], ara=datetime(2027, 6, 1, 21, 0))
    nova_4m = LligaOberta(
        41, "Lliga Catalana 4 Modalitats", "4 Modalitats", date(2027, 8, 24), "Inscripció"
    )

    en_curs.desa_lligues_obertes(conn, [nova_4m], ara=datetime(2027, 8, 26, 21, 0))

    assert en_curs.lliga_en_curs(conn, "3B") == 38
    assert en_curs.lliga_en_curs(conn, "4M") == 41


def test_amb_dues_al_llistat_mana_la_que_esta_activa(conn) -> None:
    """La que s'acaba i la que obre inscripcions, totes dues al llistat."""
    vella = LligaOberta(38, "Lliga Catalana Tres Bandes", "Tres bandes", None, "Activa")
    nova = LligaOberta(40, "Lliga Catalana Tres Bandes", "Tres bandes", None, "Inscripció")

    en_curs.desa_lligues_obertes(conn, [nova, vella])

    assert en_curs.lliga_en_curs(conn, "3B") == 38


def test_amb_dues_d_actives_no_en_tria_cap(conn) -> None:
    en_curs.desa_lligues_obertes(
        conn,
        [
            LligaOberta(38, "Lliga Catalana Tres Bandes", "Tres bandes", None, "Activa"),
            LligaOberta(40, "Lliga Tres Bandes Veterans", "Tres bandes", None, "Activa"),
        ],
    )

    with pytest.raises(en_curs.NoDeterminat) as e:
        en_curs.lliga_en_curs(conn, "3B")

    assert "38" in str(e.value) and "40" in str(e.value)
    assert "FCB_LLIGA_3B_ID" in str(e.value), "ha de dir com es força a mà"


def test_sense_haver_vist_mai_el_llistat_falla_i_diu_que_cal_fer(conn) -> None:
    """No hi ha cap id de reserva: una base que no sap res no publica la lliga."""
    with pytest.raises(en_curs.NoDeterminat) as e:
        en_curs.lliga_en_curs(conn, "3B")

    assert "ingest-lliga" in str(e.value)


def test_una_base_d_abans_de_la_taula_es_com_una_de_buida(tmp_path) -> None:
    import sqlite3

    conn = sqlite3.connect(tmp_path / "vella.db")

    assert en_curs.lligues_vistes(conn) == []


def test_es_pot_forcar_per_l_entorn(conn, monkeypatch) -> None:
    en_curs.desa_lligues_obertes(conn, [TRES_BANDES])
    monkeypatch.setenv("FCB_LLIGA_3B_ID", "36")

    assert en_curs.lliga_en_curs(conn, "3B") == 36


def test_a_la_publicacio_mana_el_que_es_demana_i_despres_el_llistat(tmp_path, monkeypatch) -> None:
    """`lliga_id` > la constant de `cloud_sync` > el llistat de la federació."""
    monkeypatch.delenv("FCB_LLIGA_3B_ID", raising=False)
    db = tmp_path / "t.db"
    en_curs.desa_lligues_obertes(ensure_schema(db), [TRES_BANDES])

    assert cloud_sync.LLIGA_3B_ID is None, "ja no hi ha d'haver cap id escrit"
    assert cloud_sync.LLIGA_4M_ID is None
    assert cloud_sync.lliga_a_publicar("3B", None, db) == 38
    assert cloud_sync.lliga_a_publicar("3B", 34, db) == 34
    monkeypatch.setattr(cloud_sync, "LLIGA_3B_ID", 36)
    assert cloud_sync.lliga_a_publicar("3B", None, db) == 36
    # I la de 4 Modalitats, que aquesta base no ha vist mai, no s'inventa.
    with pytest.raises(en_curs.NoDeterminat):
        cloud_sync.lliga_a_publicar("4M", None, db)


# --------------------------- quina temporada és ---------------------------


def test_la_temporada_surt_del_calendari_de_les_lligues(conn) -> None:
    en_curs.desa_lligues_obertes(conn, [TRES_BANDES, QUATRE_MOD])
    _encontre(conn, 38, "2026-09-26")
    _encontre(conn, 38, "2027-04-03")
    _encontre(conn, 39, "2026-10-11")

    assert en_curs.temporada_en_curs(conn) == 2026
    assert en_curs.temporada_o_en_curs(conn, None) == "2026/2027"
    assert en_curs.amb_guio(en_curs.temporada_en_curs(conn)) == "2026-2027"


def test_al_gener_segueix_sent_la_mateixa_temporada(conn) -> None:
    """No depèn del dia que es demana: surt de les dates de la lliga."""
    en_curs.desa_lligues_obertes(conn, [TRES_BANDES], ara=datetime(2027, 1, 15, 21, 0))
    _encontre(conn, 38, "2026-09-26")

    assert en_curs.temporada_en_curs(conn) == 2026


def test_sense_calendari_encara_surt_del_limit_d_inscripcio(conn) -> None:
    """Una lliga acabada d'obrir, sense cap encontre: la inscripció es tanca a l'estiu."""
    nova = LligaOberta(
        40, "Lliga Catalana Tres Bandes", "Tres bandes", date(2027, 7, 20), "Inscripció"
    )
    en_curs.desa_lligues_obertes(conn, [nova])

    assert en_curs.temporada_en_curs(conn) == 2027


def test_amb_dues_temporades_al_llistat_mana_la_que_es_juga(conn) -> None:
    vella = LligaOberta(38, "Lliga Catalana Tres Bandes", "Tres bandes", None, "Activa")
    nova = LligaOberta(
        41, "Lliga Catalana 4 Modalitats", "4 Modalitats", date(2027, 8, 24), "Inscripció"
    )
    en_curs.desa_lligues_obertes(conn, [vella, nova])
    _encontre(conn, 38, "2026-09-26")

    assert en_curs.temporada_en_curs(conn) == 2026


def test_la_temporada_que_es_demana_no_es_toca(conn) -> None:
    assert en_curs.temporada_o_en_curs(conn, "2024/2025") == "2024/2025"


def test_sense_llistat_la_temporada_no_s_inventa(conn) -> None:
    with pytest.raises(en_curs.NoDeterminat) as e:
        en_curs.temporada_en_curs(conn)

    assert "--temporada" in str(e.value)


def test_una_lliga_sense_dates_no_dona_temporada(conn) -> None:
    en_curs.desa_lligues_obertes(
        conn, [LligaOberta(40, "Lliga Catalana Tres Bandes", "Tres bandes", None, "Inscripció")]
    )

    with pytest.raises(en_curs.NoDeterminat):
        en_curs.temporada_en_curs(conn)


def test_la_temporada_tambe_es_pot_forcar(conn, monkeypatch) -> None:
    monkeypatch.setenv("FCB_TEMPORADA", "2025/2026")

    assert en_curs.temporada_en_curs(conn) == 2025
