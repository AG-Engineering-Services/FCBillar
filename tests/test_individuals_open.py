"""Ingesta d'un open des del web nou, i la classificació que en deduïm.

Les fixtures són de l'**OPEN LLIURE PUNT D'ATAC** (torneig 217), capturat el
2026-09-06 amb el torneig ja tancat. És un open petit i sencer —tres fases de
grups, tres eliminatòries, 44 partides— i per això serveix de prova de
regressió de tot el recorregut.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.individuals import (
    Divisio,
    Fase,
    Partida,
    classificacio,
    desa,
    llegeix,
    ranquing_fase,
)
from fcbillar.scraper.parsers import parse_individuals_grups

NOU = Path(__file__).parent / "fixtures" / "nou"

#: Una pàgina sense cap taula. Els parsers en treuen zero files, que és el que
#: ha de passar amb les fases que no tenim capturades.
BUIDA = "<html><body><div class='card'><div class='card-body'></div></div></body></html>"


def fixture(nom: str) -> str:
    return (NOU / f"{nom}.html").read_text(encoding="utf-8")


class ClientFals:
    """Serveix les fixtures que hi ha; per a la resta, una pàgina sense taules."""

    def __init__(self) -> None:
        self.demanades: list[str] = []

    def fetch_html(self, url: str, *, use_cache: bool = True) -> str:
        self.demanades.append(url)
        clau = url.split("/frontend/")[-1].replace("-", "_").replace("/", "_")
        cami = NOU / f"{clau}.html"
        return cami.read_text(encoding="utf-8") if cami.exists() else BUIDA


# ---------------- el parser que faltava ----------------


def test_els_grups_duna_fase_porten_el_seu_id() -> None:
    """L'id del grup no és enlloc més que a l'enllaç de la seva fila.

    Sense això les partides dels grups són inabastables, encara que la pàgina
    que les serveix funcioni: eren 37 de les 44 partides d'aquest open.
    """
    grups = parse_individuals_grups(fixture("individuals_grups_217_452_807"))
    assert [g.grup_id_extern for g in grups] == [5257, 5258, 5259, 5260, 5261, 5262]
    assert [g.nom for g in grups] == [f"Grup {x}" for x in "ABCDEF"]
    assert grups[0].club_organitzador == "C.B.PUNT D'ATAC"
    assert grups[0].data == date(2026, 9, 4)


def test_els_grups_dun_open_dun_altre_any() -> None:
    """La mateixa forma a l'open de Mataró de 2025-26, que és d'abans."""
    grups = parse_individuals_grups(fixture("individuals_grups_211_447_799"))
    assert [(g.grup_id_extern, g.nom) for g in grups] == [(5201, "Grup A")]


def test_una_pagina_sense_grups_no_inventa_res() -> None:
    assert parse_individuals_grups(BUIDA) == []


# ---------------- el recorregut ----------------


def test_llegeix_recorre_fases_grups_i_eliminatories() -> None:
    client = ClientFals()
    divisions = llegeix(client, 217, "OPEN LLIURE PUNT D'ATAC")
    assert len(divisions) == 1
    d = divisions[0]

    # La divisió és única: el sufix '- ÚNICA' no diu res i no s'arrossega.
    assert d.nom == "OPEN LLIURE PUNT D'ATAC"
    assert [(f.nom, f.tipus) for f in d.fases] == [
        ("PRE-PREVIA", "grups"),
        ("PRÈVIA", "grups"),
        ("FASE VUITENS", "grups"),
        ("QUARTS", "ko"),
        ("SEMIFINALS", "ko"),
        ("FINAL", "ko"),
    ]
    # De les fixtures capturades: els 18 participants de la fase de vuitens,
    # les 3 partides del seu grup A i la final.
    assert len(d.membres) == 18
    assert len(d.partides) == 4
    final = [p for p in d.partides if p.grup_nom is None]
    assert len(final) == 1
    assert final[0].jugador1 == "CARBONELL TRILLA, MATEU"
    assert (final[0].caramboles1, final[0].caramboles2, final[0].entrades) == (300, 53, 3)
    assert final[0].serie1 == 196
    assert final[0].arbitre == "A.GUTIERREZ"
    assert final[0].estat == "Finalitzada"
    # Les partides de grup hereten la data del grup; les d'eliminatòria no en tenen.
    assert {p.data for p in d.partides if p.grup_nom} == {date(2026, 9, 4)}
    assert final[0].data is None


# ---------------- la classificació deduïda ----------------


def fase(id_: int, nom: str, tipus: str, ordre: int) -> Fase:
    return Fase(fase_id_extern=id_, nom=nom, tipus=tipus, ordre=ordre)


def partida(f: int, a: str, ca: int, b: str, cb: int, ent: int = 10) -> Partida:
    return Partida(
        fase_id_extern=f,
        grup_nom=None,
        data=None,
        jugador1=a,
        caramboles1=ca,
        serie1=None,
        jugador2=b,
        caramboles2=cb,
        serie2=None,
        entrades=ent,
        arbitre=None,
        estat="Finalitzada",
    )


def quadre(*partides: Partida) -> Divisio:
    return Divisio(
        torneig_id_extern=1,
        divisio_id_extern=1,
        nom="OPEN DE PROVA",
        fases=[fase(10, "GRUPS", "grups", 1), fase(20, "SEMIFINALS", "ko", 2), fase(30, "FINAL", "ko", 3)],
        partides=list(partides),
    )


def test_el_quadre_mana_sobre_la_mitjana() -> None:
    """Qui arriba més lluny va davant, encara que jugui pitjor.

    És el que diu el reglament d'opens quan puntua: el 3r i el 4t valen igual
    perquè tots dos van caure a semifinals, hi hagin jugat com hi hagin jugat.
    """
    d = quadre(
        partida(10, "FLUIX", 100, "ALTRE", 10, ent=5),  # mitjana 20, però cau als grups
        partida(20, "CAMPIÓ", 60, "TERCER", 20),
        partida(20, "SEGON", 60, "QUART", 10),
        partida(30, "CAMPIÓ", 60, "SEGON", 40),
    )
    assert [p.jugador for p in classificacio(d)][:4] == ["CAMPIÓ", "SEGON", "TERCER", "QUART"]
    # I els dos de la semifinal perduda s'ordenen entre ells per mitjana.
    assert [p.fase_final for p in classificacio(d)][:4] == [
        "FINAL",
        "FINAL",
        "SEMIFINALS",
        "SEMIFINALS",
    ]


def test_una_partida_sense_jugar_no_compta() -> None:
    """Donar-la per zero baixaria qui encara l'ha de jugar."""
    d = quadre(
        partida(20, "A", 60, "B", 30),
        Partida(20, None, None, "C", None, None, "D", None, None, None, None, "Pendent"),
    )
    noms = [p.jugador for p in classificacio(d)]
    assert noms == ["A", "B"]


def test_la_classificacio_de_lopen_de_debo() -> None:
    """Contra el quadre real: campió, finalista i els dos semifinalistes."""
    d = quadre(
        partida(20, "CARBONELL TRILLA, MATEU", 300, "SERAROLS MONTES, JOSEP", 99),
        partida(20, "GARRIGA LLOVET, SERGI", 238, "VILALTA PARÉ, VALENTÍ", 300),
        partida(30, "CARBONELL TRILLA, MATEU", 300, "VILALTA PARÉ, VALENTÍ", 53),
    )
    assert [(p.posicio, p.jugador) for p in classificacio(d)][:2] == [
        (1, "CARBONELL TRILLA, MATEU"),
        (2, "VILALTA PARÉ, VALENTÍ"),
    ]


# ---------------- el campionat de Catalunya, a mitges ----------------


def test_el_campionat_llegeix_la_classificacio_del_grup() -> None:
    """La prèvia d'Honor del campionat de tres bandes 2026-27 (216/454/808).

    Aquesta pàgina porta, a més de les partides, la classificació del grup amb
    punts i mitjana, i no la llegia ningú. És l'única cosa que diu qui s'ha
    classificat: el PDF de la federació ho remata —«es classificaran per a la
    final els dos primers de cada grup»— però l'ordre dins del grup només és
    aquí.
    """
    d = llegeix(ClientFals(), 216, "TRES BANDES INDIVIDUAL")
    honor = next(x for x in d if "HONOR" in x.nom)
    assert [f.nom for f in honor.fases] == ["PRÈVIA"]
    fase = honor.fases[0].fase_id_extern

    # Dels quatre grups de la prèvia només tenim capturada la pàgina del Grup I.
    amb_classificacio = [m for m in honor.membres if m.posicio_grup is not None]
    assert {m.grup_nom for m in amb_classificacio} == {"Grup I"}
    grup_i = sorted(amb_classificacio, key=lambda m: m.posicio_grup)
    assert [(m.jugador, m.punts, m.mitjana) for m in grup_i] == [
        ("BENITEZ REINA, PAU", 4, 1.1442),
        ("VAN KESSEL, MARK STEFAN", 4, 1.1290),
        ("MAS CANADELL, JOSEP Mª", 2, 1.3158),
        ("HERNÁNDEZ PARRA, ANTONI", 2, 0.9333),
    ]
    # Els 16 de la prèvia hi són tots, encara que només d'un grup en sapiguem el resultat.
    assert len(honor.membres) == 16
    assert {m.grup_id_extern for m in honor.membres if m.grup_nom == "Grup I"} == {5263}

    # El rànquing de la fase: posició al grup, punts, i la mitjana per desempatar.
    ranquing = ranquing_fase(honor, fase)
    assert [(r.posicio, r.jugador) for r in ranquing] == [
        (1, "BENITEZ REINA, PAU"),
        (2, "VAN KESSEL, MARK STEFAN"),
        (3, "MAS CANADELL, JOSEP Mª"),
        (4, "HERNÁNDEZ PARRA, ANTONI"),
    ]


def test_el_ranquing_duna_fase_ordena_per_posicio_i_despres_punts() -> None:
    """Tots els primers, després tots els segons; dins de cada colla, punts i mitjana.

    És el cas de debò de la pre-prèvia de 1a divisió, on hi ha grups de tres que
    han quedat 4-2-0 i grups on el primer només fa 2 punts perquè algú no s'ha
    presentat. Sense aquest ordre no es pot dir qui passa quan la federació
    s'emporta els millors segons.
    """
    def membre(grup, jugador, pos, punts, mitjana):
        from fcbillar.individuals import Membre

        return Membre(
            fase_id_extern=99,
            grup_nom=grup,
            grup_id_extern=1,
            jugador=jugador,
            posicio_grup=pos,
            punts=punts,
            mitjana=mitjana,
        )

    d = Divisio(
        torneig_id_extern=1,
        divisio_id_extern=1,
        nom="CAMPIONAT DE PROVA",
        fases=[fase(99, "PRE-PRÈVIA", "grups", 1)],
        membres=[
            membre("Grup A", "PRIMER FLUIX", 1, 2, 0.90),
            membre("Grup A", "SEGON FLUIX", 2, 0, 0.30),
            membre("Grup B", "PRIMER FORT", 1, 4, 0.60),
            membre("Grup B", "SEGON FORT", 2, 2, 0.95),
            membre("Grup C", "SENSE JUGAR", 3, 0, None),
        ],
    )
    assert [r.jugador for r in ranquing_fase(d, 99)] == [
        "PRIMER FORT",   # 1r amb 4 punts
        "PRIMER FLUIX",  # 1r amb 2 punts, tot i tenir més mitjana
        "SEGON FORT",    # 2n amb 2 punts
        "SEGON FLUIX",   # 2n amb 0
        "SENSE JUGAR",   # 3r; hi surt, que hi era
    ]


# ---------------- el desat ----------------


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    return ensure_schema(tmp_path / "test.db")


def test_desa_lopen_sencer(conn) -> None:
    d = llegeix(ClientFals(), 217, "OPEN LLIURE PUNT D'ATAC")[0]
    n = desa(conn, d, "2026-2027")
    # Cinc jugadors: els tres del grup A de vuitens i els dos de la final.
    assert n == {"fases": 6, "grups": 6, "partides": 4, "participants": 5}

    assert conn.execute("SELECT COUNT(*) FROM torneig_fases").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM torneig_fase_grups").fetchone()[0] == 18
    assert conn.execute("SELECT COUNT(*) FROM torneig_partides").fetchone()[0] == 4
    # El campió, amb la posició deduïda i la mitjana del torneig.
    fila = conn.execute(
        "SELECT p.nom, t.posicio, t.serie_max FROM torneig_participants t "
        "JOIN players p ON p.id = t.player_id WHERE t.posicio = 1"
    ).fetchone()
    assert fila[0] == "CARBONELL TRILLA, MATEU"
    assert fila[2] == 196


def test_tornar_a_desar_no_duplica(conn) -> None:
    d = llegeix(ClientFals(), 217, "OPEN LLIURE PUNT D'ATAC")[0]
    desa(conn, d, "2026-2027")
    desa(conn, d, "2026-2027")
    assert conn.execute("SELECT COUNT(*) FROM torneig_partides").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM torneig_fases").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM torneig_fase_grups").fetchone()[0] == 18


def test_desa_no_accepta_una_divisio_sense_partides(conn) -> None:
    """Un open sencer no es pot substituir per un silenci."""
    d = llegeix(ClientFals(), 217, "OPEN LLIURE PUNT D'ATAC")[0]
    desa(conn, d, "2026-2027")
    buida = Divisio(
        torneig_id_extern=d.torneig_id_extern,
        divisio_id_extern=d.divisio_id_extern,
        nom=d.nom,
        fases=d.fases,
    )
    with pytest.raises(ValueError, match="No esborro"):
        desa(conn, buida, "2026-2027")
    assert conn.execute("SELECT COUNT(*) FROM torneig_partides").fetchone()[0] == 4
