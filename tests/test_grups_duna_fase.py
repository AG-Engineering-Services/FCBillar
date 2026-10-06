"""El dia, el club i els jugadors de cada grup, també abans que es jugui.

La federació publica els grups d'una fase amb el sorteig: quin dia es juguen, a
quin club i qui hi ha. És l'única manera de dir a algú quan, on i contra qui
juga la ronda que ve, i fins ara es llegia i es llençava.

El cas que més importa és el que abans no es desava: un torneig sortejat que
encara no ha començat. `desa` rebutjava tota divisió sense partides, perquè una
divisió buida vol dir que no s'ha sabut llegir; però una divisió amb grups i
sense partides no és buida.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from fcbillar.individuals import Divisio, Fase, Grup, Membre, Partida, desa, llegeix
from tests.test_individuals_open import ClientFals as PortalFals
from tests.test_publish_lliga_retirada import ClientFals as NuvolFals

PREVIA = 815


def _sortejada() -> Divisio:
    """Una prèvia amb dos grups sortejats i cap partida jugada."""
    return Divisio(
        torneig_id_extern=216,
        divisio_id_extern=455,
        nom="TRES BANDES INDIVIDUAL - 1A DIVISIÓ",
        fases=[Fase(PREVIA, "PRÈVIA", "grups", 1)],
        membres=[
            Membre(PREVIA, "Grup A", 5303, "ROCA, ANNA"),
            Membre(PREVIA, "Grup A", 5303, "PUIG, BERNAT"),
            Membre(PREVIA, "Grup B", 5304, "SERRA, CARLA"),
        ],
        grups=[
            Grup(PREVIA, "Grup A", 5303, "C.B.BANYOLES", date(2026, 10, 3)),
            Grup(PREVIA, "Grup B", 5304, "C.B.SANT ADRIÀ", date(2026, 10, 3)),
        ],
    )


def _partida(local: str, visitant: str) -> Partida:
    return Partida(
        fase_id_extern=PREVIA,
        grup_nom="Grup A",
        data=date(2026, 10, 3),
        jugador1=local,
        caramboles1=30,
        serie1=4,
        jugador2=visitant,
        caramboles2=20,
        serie2=3,
        entrades=25,
        arbitre=None,
        estat=None,
    )


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    return ensure_schema(tmp_path / "t.db")


def test_llegir_un_torneig_en_treu_el_dia_i_el_club_de_cada_grup() -> None:
    d = llegeix(PortalFals(), 217, "OPEN LLIURE PUNT D'ATAC")[0]
    assert d.grups, "la pàgina de la fase porta la taula de grups"
    assert all(g.data is not None for g in d.grups)
    assert {g.fase_id_extern for g in d.grups} <= {f.fase_id_extern for f in d.fases}


def test_es_desa_un_torneig_sortejat_que_encara_no_ha_comencat(conn) -> None:
    desa(conn, _sortejada(), "2026-2027")

    grups = conn.execute(
        "SELECT grup_nom, club_organitzador, data FROM torneig_grups ORDER BY grup_nom"
    ).fetchall()
    assert [tuple(g) for g in grups] == [
        ("Grup A", "C.B.BANYOLES", "2026-10-03"),
        ("Grup B", "C.B.SANT ADRIÀ", "2026-10-03"),
    ]
    assert conn.execute("SELECT COUNT(*) FROM torneig_fase_grups").fetchone()[0] == 3


def test_desar_sense_partides_no_esborra_les_que_hi_havia(conn) -> None:
    """Si el que ha fallat és llegir les partides, les d'abans s'han de quedar."""
    amb = _sortejada()
    amb = Divisio(
        torneig_id_extern=amb.torneig_id_extern,
        divisio_id_extern=amb.divisio_id_extern,
        nom=amb.nom,
        fases=amb.fases,
        membres=amb.membres,
        grups=amb.grups,
        partides=[_partida("ROCA, ANNA", "PUIG, BERNAT")],
    )
    desa(conn, amb, "2026-2027")
    desa(conn, _sortejada(), "2026-2027")
    assert conn.execute("SELECT COUNT(*) FROM torneig_partides").fetchone()[0] == 1


def test_sense_partides_ni_grups_segueix_sense_desar_se(conn) -> None:
    buida = Divisio(torneig_id_extern=216, divisio_id_extern=455, nom="BUIDA")
    with pytest.raises(ValueError, match="No esborro"):
        desa(conn, buida, "2026-2027")


class NuvolSenseColumnesNoves(NuvolFals):
    """Un núvol on encara no s'ha aplicat la migració: rebutja `places`."""

    def table(self, nom: str):
        taula = super().table(nom)
        upsert = taula.upsert

        def _upsert(files: list[dict], **k):
            if nom == "open_fases" and files and "places" in files[0]:
                raise RuntimeError("PGRST204: Could not find the 'places' column")
            return upsert(files, **k)

        taula.upsert = _upsert  # type: ignore[method-assign]
        return taula


def test_les_fases_porten_la_regla_i_les_places(conn, tmp_path, monkeypatch) -> None:
    desa(conn, _sortejada(), "2026-2027")
    conn.execute("UPDATE torneig_fases SET regla = 'el primer de cada grup', places = 2")
    conn.commit()
    conn.close()
    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: NuvolFals(magatzem))

    cloud_sync.publish_open_fases(db_path=tmp_path / "t.db")

    (fase,) = magatzem["open_fases"]
    assert fase["places"] == 2
    assert fase["regla"] == "el primer de cada grup"


def test_si_el_nuvol_encara_no_te_les_columnes_les_fases_es_publiquen_igual(
    conn, tmp_path, monkeypatch
) -> None:
    desa(conn, _sortejada(), "2026-2027")
    conn.close()
    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: NuvolSenseColumnesNoves(magatzem))

    counts = cloud_sync.publish_open_fases(db_path=tmp_path / "t.db")

    assert counts["open_fases"] == 1
    assert "places" not in magatzem["open_fases"][0]


def test_es_publiquen_tots_els_del_grup_hagin_jugat_o_no(conn, tmp_path, monkeypatch) -> None:
    desa(conn, _sortejada(), "2026-2027")
    open_id = conn.execute("SELECT id FROM torneigs_individuals").fetchone()[0]
    conn.close()

    magatzem: dict[str, list[dict]] = {
        # D'abans que el torneig es renumerés: ha de marxar.
        "open_grups": [{"open_id": open_id + 1, "fase_id": PREVIA, "grup_nom": "Grup A"}]
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: NuvolFals(magatzem))

    counts = cloud_sync.publish_open_grups(db_path=tmp_path / "t.db")

    files = {f["grup_nom"]: f for f in magatzem["open_grups"] if f["open_id"] == open_id}
    assert set(files) == {"Grup A", "Grup B"}
    assert files["Grup A"]["club_organitzador"] == "C.B.BANYOLES"
    assert files["Grup A"]["data"] == "2026-10-03"
    assert [j["jugador"] for j in files["Grup A"]["jugadors"]] == ["ROCA, ANNA", "PUIG, BERNAT"]
    assert {f["open_id"] for f in magatzem["open_grups"]} == {open_id}
    assert counts == {"open_grups": 2, "open_grups_retirats": 1}
