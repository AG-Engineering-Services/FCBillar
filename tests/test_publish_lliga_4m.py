"""La Lliga de 4 Modalitats es publica a les seves taules, i només a les seves.

La federació juga dues lligues per equips cada temporada. La de Tres Bandes ja es
publicava, a `lliga_groups`, `lliga_standings`, `lliga_encontres` i
`lliga_partides`, i qui les llegeix —l'app del club i /lliga— no filtra per
lliga. Posar-hi la de 4 Modalitats al costat els barrejaria les dues.

Per això va a `lliga4m_*`, que són les mateixes quatre taules amb un altre nom, i
les omplen les mateixes funcions amb un altre destí. El que es prova aquí és la
frontera: cap de les dues publicacions no escriu ni esborra a les taules de
l'altra, i la nova no fa res si no té on escriure o no té res a dir.
"""

from __future__ import annotations

import copy
import sqlite3

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals, TaulaFalsa, _classificacio

TAULES_3B = ("lliga_groups", "lliga_standings", "lliga_encontres", "lliga_partides")
TAULES_4M = ("lliga4m_groups", "lliga4m_standings", "lliga4m_encontres", "lliga4m_partides")

#: Una acta de 4 Modalitats: quatre partides, una de cada modalitat.
ACTA_4M = [
    (1, "SÁNCHEZ MARTÍNEZ, PASCUAL", 30, "HERNÁNDEZ PARRA, ANTONI", 22, 40),
    (2, "GASCÓN REYES, RAFAEL", 150, "ESPINASA SÁNCHEZ, JOAN", 98, 20),
    (3, "PASTOR RIVAS, MANUEL", 100, "MAS CANADELL, CÉSAR", 100, 25),
    (4, "MEGIAS NAVAS, MATEU", 41, "NAVARRO CARMONA, JOAN ANT.", 60, 30),
]


def _encontre(
    conn, eid, lliga, divisio, grup, jornada, extern, temporada, resultat, local=1, visitant=2
) -> None:
    pml, pmv, ppl, ppv = resultat or (None, None, None, None)
    conn.execute(
        """
        INSERT INTO encontres_lliga
            (id, lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern, data,
             temporada_id, equip_local_id, equip_visitant_id, p_match_local,
             p_match_visitant, p_parcials_local, p_parcials_visitant)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (eid, lliga, divisio, grup, jornada, extern, "2026-10-03", temporada, local, visitant,
         pml, pmv, ppl, ppv),
    )  # fmt: skip


def _acta(conn, eid, partides) -> None:
    for mod, j1, c1, j2, c2, ent in partides:
        conn.execute(
            """INSERT INTO lliga_pending_partides
               (encontre_lliga_id, modalitat_codi, competicio, data, player1_nom,
                caramboles1, serie1, player2_nom, caramboles2, serie2, entrades)
               VALUES (?, ?, 'LLIGA', '2026-10-03', ?, ?, NULL, ?, ?, NULL, ?)""",
            (eid, mod, j1, c1, j2, c2, ent),
        )


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """Les dues lligues de la 2026-27 i la de 4 Modalitats de l'any abans.

    De cada una de les d'enguany, un encontre jugat amb la seva acta; de la de 4
    Modalitats, a més, un de la jornada següent que encara no s'ha jugat.
    """
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2025-2026')")
    conn.execute("INSERT INTO temporades (id, nom) VALUES (2, '2026-2027')")
    for i, nom in enumerate(("C.B.MATARÓ", "C.B.LLEIDA"), start=1):
        conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (?,?,?)", (i, nom, nom))
        conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (?,?,'A')", (i, i))
    for lliga, divisio, grup in ((38, 159, 343), (39, 163, 350), (37, 153, 325)):
        for g, nom in ((0, "HONOR"), (grup, "UNIC")):
            conn.execute(
                "INSERT INTO lliga_noms (lliga_id, divisio_id, grup_id, nom) VALUES (?,?,?,?)",
                (lliga, divisio, g, nom),
            )
    _encontre(conn, 500, 38, 159, 343, 2790, 11656, 2, (3, 0, 6, 2))
    _acta(conn, 500, [(1, *p[1:]) for p in ACTA_4M])
    _encontre(conn, 600, 39, 163, 350, 2900, 12001, 2, (3, 0, 5, 3))
    _acta(conn, 600, ACTA_4M)
    _encontre(conn, 601, 39, 163, 350, 2901, None, 2, None, local=2, visitant=1)
    _encontre(conn, 700, 37, 153, 325, 2700, 11001, 1, (1, 1, 4, 4))
    _acta(conn, 700, ACTA_4M)
    conn.commit()
    conn.close()

    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    monkeypatch.setattr(cloud_sync, "LLIGA_3B_ID", 38)
    monkeypatch.setattr(cloud_sync, "LLIGA_4M_ID", 39)
    # La classificació oficial respon de tots els grups que se li demanen, de la
    # lliga que sigui: sense això no es retiraria res i no es provaria la frontera.
    monkeypatch.setattr(
        cloud_sync,
        "_fetch_official_lliga_standings",
        lambda claus, prog, lliga=38: {
            c: [_classificacio(1, "C.B.MATARÓ A", 3), _classificacio(2, "C.B.LLEIDA A", 0)]
            for c in claus
        },
    )
    return db, magatzem


def _publica_3b(db) -> None:
    cloud_sync.publish_lliga(db_path=db)
    cloud_sync.publish_lliga_encontres(db_path=db)


def test_la_4m_va_a_les_seves_taules_i_no_toca_les_de_tres_bandes(entorn) -> None:
    db, magatzem = entorn
    _publica_3b(db)
    # Una fila de Tres Bandes que «sobraria» si la retirada de 4M hi arribés.
    magatzem["lliga_standings"].append(
        {"lliga_id": 39, "divisio_id": 163, "grup_id": 350, "equip": "NO EM TOQUIS", "posicio": 9}
    )
    abans = copy.deepcopy({t: magatzem[t] for t in TAULES_3B})

    counts = cloud_sync.publish_lliga_4m(db_path=db)

    assert {t: magatzem[t] for t in TAULES_3B} == abans, "la 4M ha tocat les taules de 3B"
    assert counts["lliga4m_groups"] == 1 and counts["lliga4m_standings"] == 2
    assert counts["lliga4m_encontres"] == 2 and counts["lliga4m_partides"] == 4

    assert {f["lliga_id"] for f in magatzem["lliga4m_groups"]} == {39}
    assert {f["lliga_id"] for f in magatzem["lliga4m_standings"]} == {39}
    primer = next(f for f in magatzem["lliga4m_standings"] if f["posicio"] == 1)
    assert (primer["equip"], primer["punts"], primer["ppf"], primer["ppc"]) == (
        "C.B.MATARÓ A",
        3,
        5,
        3,
    )
    assert primer["car_f"] == 30 + 150 + 100 + 41, "les caramboles de les quatre modalitats"

    encontres = {f["encontre_id"]: f for f in magatzem["lliga4m_encontres"]}
    assert 12001 in encontres and encontres[12001]["gols_local"] == 3
    # El que encara no s'ha jugat hi va igualment, amb la clau provisional.
    pendent = next(f for k, f in encontres.items() if k != 12001)
    assert pendent["encontre_id"] == 10_000_000 + 2901 * 100 + 1
    assert pendent["gols_local"] is None and pendent["equip_local"] == "C.B.LLEIDA A"

    partides = sorted(magatzem["lliga4m_partides"], key=lambda f: f["ordre"])
    assert [f["modalitat_codi"] for f in partides] == [1, 2, 3, 4], "una partida per modalitat"
    assert {f["encontre_id"] for f in partides} == {12001}


def test_la_de_tres_bandes_no_escriu_ni_esborra_a_les_de_4m(entorn) -> None:
    db, magatzem = entorn
    cloud_sync.publish_lliga_4m(db_path=db)
    abans = copy.deepcopy({t: magatzem[t] for t in TAULES_4M})

    _publica_3b(db)

    assert {t: magatzem[t] for t in TAULES_4M} == abans, "la 3B ha tocat les taules de 4M"
    assert {f["lliga_id"] for f in magatzem["lliga_groups"]} == {38}
    assert {f["lliga_id"] for f in magatzem["lliga_standings"]} == {38}
    assert {f["encontre_id"] for f in magatzem["lliga_encontres"]} == {11656}
    assert {f["modalitat_codi"] for f in magatzem["lliga_partides"]} == {1}


def test_retira_el_que_sobra_nomes_a_les_seves_taules_i_de_la_seva_lliga(entorn) -> None:
    db, magatzem = entorn
    vell = {"lliga_id": 39, "divisio_id": 163, "grup_id": 350, "equip": "NOM ANTIC", "posicio": 3}
    passada = {"lliga_id": 37, "divisio_id": 153, "grup_id": 325, "equip": "C.B.LLEIDA A"}
    magatzem["lliga4m_standings"] = [dict(vell), dict(passada)]
    # Un encontre amb la clau d'abans a la mateixa divisió, i un d'una altra.
    magatzem["lliga4m_encontres"] = [
        {"encontre_id": 99, "divisio_id": 163, "grup_id": 350},
        {"encontre_id": 11001, "divisio_id": 153, "grup_id": 325},
    ]
    magatzem["lliga4m_partides"] = [
        {"encontre_id": 99, "ordre": 1},
        {"encontre_id": 11001, "ordre": 1},
        {"encontre_id": 12001, "ordre": 5},  # l'acta en tenia cinc i ara quatre
    ]
    # Les mateixes claus a Tres Bandes: no són seves i s'hi han de quedar.
    magatzem["lliga_standings"] = [dict(vell)]
    magatzem["lliga_encontres"] = [{"encontre_id": 99, "divisio_id": 163, "grup_id": 350}]

    counts = cloud_sync.publish_lliga_4m(db_path=db)

    equips = {(f["lliga_id"], f["equip"]) for f in magatzem["lliga4m_standings"]}
    assert (39, "NOM ANTIC") not in equips, "el nom vell de la lliga en curs se'n va"
    assert (37, "C.B.LLEIDA A") in equips, "la temporada passada no es toca"
    assert counts["lliga4m_standings_retirades"] == 1
    assert "retirades" not in counts, "es trepitjaria amb la de Tres Bandes a publish-cloud"

    ids = {f["encontre_id"] for f in magatzem["lliga4m_encontres"]}
    assert 99 not in ids and 11001 in ids
    assert counts["lliga4m_encontres_retirats"] == 1
    claus = {(f["encontre_id"], f["ordre"]) for f in magatzem["lliga4m_partides"]}
    assert (99, 1) not in claus and (12001, 5) not in claus and (11001, 1) in claus

    assert magatzem["lliga_standings"] == [vell]
    assert magatzem["lliga_encontres"] == [{"encontre_id": 99, "divisio_id": 163, "grup_id": 350}]


def test_una_temporada_passada_es_publica_amb_la_seva_temporada(entorn) -> None:
    """La lliga 37 és de la 2025-26, que no és la temporada més nova de la taula."""
    db, magatzem = entorn
    counts = cloud_sync.publish_lliga_4m(db_path=db, lliga_id=37)

    assert counts["lliga4m_encontres"] == 1 and counts["lliga4m_partides"] == 4
    assert {f["encontre_id"] for f in magatzem["lliga4m_encontres"]} == {11001}
    assert {f["lliga_id"] for f in magatzem["lliga4m_standings"]} == {37}
    assert all(t not in magatzem for t in TAULES_3B)


class ClientSenseLes4M(ClientFals):
    """El Data API d'abans d'aplicar la 0030: de `lliga4m_*` no en sap res."""

    def table(self, nom: str) -> TaulaFalsa:
        if nom.startswith("lliga4m_"):
            raise RuntimeError(
                "{'code': 'PGRST205', 'message': \"Could not find the table "
                f"'fcbillar.{nom}' in the schema cache\"}}"
            )
        return super().table(nom)


def test_si_el_data_api_no_coneix_les_taules_avisa_i_no_publica_res(entorn, monkeypatch) -> None:
    db, magatzem = entorn
    _publica_3b(db)
    abans = copy.deepcopy(magatzem)
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientSenseLes4M(magatzem))
    avisos: list[str] = []

    res = cloud_sync.publica_si_hi_es(
        "lliga4m",
        lambda: cloud_sync.publish_lliga_4m(db_path=db),
        lambda nivell, msg: avisos.append(msg) if nivell == "warn" else None,
    )

    assert res == {"lliga4m": -1}, "ha de dir que no ha publicat, no fer veure que sí"
    assert any("lliga4m" in a for a in avisos)
    assert magatzem == abans, "sense taules no s'ha d'haver escrit enlloc"


def test_si_nomes_en_falta_una_tampoc_s_omplen_les_altres(entorn, monkeypatch) -> None:
    """Les respostes del Data API alternen mentre el cache d'esquemes no convergeix."""
    db, magatzem = entorn

    class NomesFaltenLesPartides(ClientFals):
        def table(self, nom: str) -> TaulaFalsa:
            if nom == "lliga4m_partides":
                raise RuntimeError("PGRST205")
            return super().table(nom)

    monkeypatch.setattr(cloud_sync, "get_client", lambda: NomesFaltenLesPartides(magatzem))
    with pytest.raises(RuntimeError, match="PGRST205"):
        cloud_sync.publish_lliga_4m(db_path=db)
    assert not any(magatzem.get(t) for t in TAULES_4M)


def test_si_la_bd_local_no_en_sap_res_no_publica_ni_retira(entorn, monkeypatch) -> None:
    db, magatzem = entorn
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM lliga_pending_partides WHERE encontre_lliga_id IN (600, 601)")
    conn.execute("DELETE FROM encontres_lliga WHERE lliga_id = 39")
    conn.execute("DELETE FROM lliga_noms WHERE lliga_id = 39")
    conn.commit()
    conn.close()
    magatzem["lliga4m_standings"] = [
        {"lliga_id": 39, "divisio_id": 163, "grup_id": 350, "equip": "C.B.MATARÓ A", "posicio": 1}
    ]
    magatzem["lliga4m_encontres"] = [{"encontre_id": 12001, "divisio_id": 163, "grup_id": 350}]
    abans = copy.deepcopy(magatzem)

    def _no_s_ha_de_cridar():
        raise AssertionError("sense res a dir no s'ha d'obrir ni el client")

    monkeypatch.setattr(cloud_sync, "get_client", _no_s_ha_de_cridar)
    avisos: list[str] = []
    res = cloud_sync.publish_lliga_4m(db_path=db, on_progress=lambda n, m: avisos.append(m))

    assert res == {}
    assert magatzem == abans
    assert any("no sap res" in a for a in avisos)
