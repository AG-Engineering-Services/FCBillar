"""Els inscrits de cada club a la lliga, i les contradiccions de la font.

Les fixtures són captures del 2026-09-04, el dia que la federació va publicar
els jugadors de cada club (`docs/canvi-web-fcb-2026.md`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.inscrits_lliga import (
    TIPUS_DOS_CLUBS,
    TIPUS_FITXATGE_ORFE,
    TIPUS_FORA_RANQUING,
    TIPUS_SENSE_MITJANA,
    Inscrit,
    Lliga,
    clubs_sense_jugadors,
    desa,
    llegeix_clubs,
    llegeix_inscrits,
    revisa,
)
from fcbillar.scraper.parsers import (
    LligaOberta,
    parse_lliga_inscripcions,
    parse_lliga_participants,
    parse_lligues_llistat,
)

NOU = Path(__file__).parent / "fixtures" / "nou"


def fixture(nom: str) -> str:
    return (NOU / f"{nom}.html").read_text(encoding="utf-8")


class ClientFals:
    """Serveix fixtures per URL, per no tocar la xarxa."""

    def __init__(self, pagines: dict[str, str]) -> None:
        self.pagines = pagines
        self.demanades: list[str] = []

    def fetch_html(self, url: str) -> str:
        self.demanades.append(url)
        for tros, nom in self.pagines.items():
            if tros in url:
                return fixture(nom)
        raise AssertionError(f"No tinc fixture per a {url}")


CLIENT = {
    "lligues/llistat": "lligues_llistat",
    "lligues/inscripcions/38": "lligues_inscripcions_38",
    "lligues/participants/38/16": "lligues_participants_38_16",
    "lligues/participants/38/22": "lligues_participants_38_22",
}


# ---------------- parsers ----------------


def test_llistat_dona_les_lligues_obertes() -> None:
    lligues = parse_lligues_llistat(fixture("lligues_llistat"))
    assert [(x.lliga_id, x.nom) for x in lligues] == [
        (39, "Lliga Catalana 4 Modalitats"),
        (38, "Lliga Catalana Tres Bandes"),
    ]
    assert lligues[1].modalitat == "Tres bandes"
    assert lligues[1].data_limit.isoformat() == "2026-09-01"


def test_inscripcions_arrossega_el_club_de_la_fila_de_sobre() -> None:
    """El club només s'escriu al primer equip de cada club.

    Filtrar les files sense club deixava fora el segon equip i següents: dels
    93 equips de la lliga 38 en tornava 38, un per club, sense dir-ho.
    """
    equips = parse_lliga_inscripcions(fixture("lligues_inscripcions_38"))
    assert len(equips) == 93
    granollers = [e for e in equips if e.club == "B.C.GRANOLLERS"]
    assert [e.equip for e in granollers] == [
        f'B.C. GRANOLLERS "{lletra}"' for lletra in "ABCDE"
    ]
    assert {e.club_id_extern for e in granollers} == {13}


def test_participants_llegeix_mitjana_i_fitxatge() -> None:
    jugadors = parse_lliga_participants(fixture("lligues_participants_38_22"))
    assert len(jugadors) == 26
    assert jugadors[0].jugador == "CHACÓN LÓPEZ, CARLOS J."
    assert jugadors[0].mitjana == pytest.approx(0.98551)
    assert jugadors[0].posicio == 1
    fitxats = [j.jugador for j in jugadors if j.fitxatge]
    assert fitxats == ["ARNAU ABILLEIRA, ALEIX", "ARNAU FONT, RICARD"]
    # L'etiqueta no ha de quedar enganxada al nom: és per on es lliga amb
    # `players.nom`, i «ARNAU FONT, RICARD (Fitxatge)» no lligaria amb ningú.
    assert all("Fitxatge" not in j.jugador for j in jugadors)


def test_participants_dun_club_sense_fitxatges() -> None:
    jugadors = parse_lliga_participants(fixture("lligues_participants_38_16"))
    assert len(jugadors) == 25
    assert not any(j.fitxatge for j in jugadors)
    # La llista ve ordenada de més mitjana a menys, i això mana l'ordre dels
    # equips del club.
    mitjanes = [j.mitjana for j in jugadors]
    assert mitjanes == sorted(mitjanes, reverse=True)


# ---------------- descàrrega ----------------


def test_llegeix_clubs_i_inscrits_de_dos_clubs() -> None:
    client = ClientFals(CLIENT)
    oberta = LligaOberta(38, "Lliga Catalana Tres Bandes", "Tres bandes", None, "Activa")
    info = llegeix_clubs(client, oberta)
    assert info.equips == 93
    assert len(info.clubs) == 38
    assert info.clubs[16] == "C.B.BANYOLES"

    # Només dos clubs a les fixtures: la resta petaria. Es retalla a posta.
    info = Lliga(38, info.nom, {16: info.clubs[16], 22: info.clubs[22]}, info.equips)
    inscrits = llegeix_inscrits(client, info)
    assert len(inscrits) == 25 + 26
    assert sum(1 for i in inscrits if i.fitxatge) == 2
    assert {i.club for i in inscrits} == {"C.B.BANYOLES", "C.B.MONT-ROIG"}


def test_llegeix_clubs_es_planta_si_no_hi_ha_equips() -> None:
    """Una lliga buida no s'ha de confondre amb una pàgina que no sabem llegir."""
    client = ClientFals({"lligues/inscripcions/38": "lligues_llistat"})
    oberta = LligaOberta(38, "Lliga Catalana Tres Bandes", "Tres bandes", None, "Activa")
    with pytest.raises(ValueError, match="Cap equip inscrit"):
        llegeix_clubs(client, oberta)


# ---------------- revisió ----------------


def fila(club: str, jugador: str, *, fitxatge: bool = False, mitjana: float = 0.5) -> Inscrit:
    return Inscrit(
        club=club,
        club_id_extern=1,
        jugador=jugador,
        mitjana=mitjana,
        fitxatge=fitxatge,
        posicio=1,
    )


def test_un_fitxatge_ben_posat_no_es_cap_avis() -> None:
    """Qui ve d'un altre club surt dues vegades i està bé.

    Al seu club sense marca i al que se l'endú amb marca. És la forma normal
    d'un fitxatge, i confondre-la amb un error ompliria la llista de soroll.
    """
    avisos = revisa(
        [
            fila("C.B.TARRAGONA", "ARNAU ABILLEIRA, ALEIX"),
            fila("C.B.MONT-ROIG", "ARNAU ABILLEIRA, ALEIX", fitxatge=True),
        ]
    )
    assert avisos == []


def test_dos_clubs_i_cap_marca() -> None:
    avisos = revisa(
        [
            fila("C.B.2000 CERDANYOLA", "FERNÁNDEZ CALLEJÓN, ALFREDO"),
            fila("C.B.MATARÓ", "FERNÁNDEZ CALLEJÓN, ALFREDO"),
        ]
    )
    assert [a.tipus for a in avisos] == [TIPUS_DOS_CLUBS]
    assert set(avisos[0].clubs) == {"C.B.2000 CERDANYOLA", "C.B.MATARÓ"}


def test_fitxatge_sense_club_dorigen() -> None:
    avisos = revisa([fila("C.B.LLINARS", "NOGUÉS BLANCO, DAVID", fitxatge=True)])
    assert [a.tipus for a in avisos] == [TIPUS_FITXATGE_ORFE]


def test_mitjana_a_zero() -> None:
    avisos = revisa([fila("C.B.LLINARS", "NOGUÉS BLANCO, DAVID", mitjana=0.0)])
    assert [a.tipus for a in avisos] == [TIPUS_SENSE_MITJANA]


def test_mitjana_que_no_es_pot_contrastar() -> None:
    """Porta mitjana però no és al rànquing: el número no surt d'enlloc."""
    inscrits = [
        fila("BILLAR EL MASNOU", "CARMONA LÓPEZ, ANTONIO", mitjana=0.3538),
        fila("C.B.BANYOLES", "GÓMEZ AMETLLER, ALBERT", mitjana=0.57982),
    ]
    avisos = revisa(inscrits, {"GOMEZAMETLLERALBERT": 0.57982})
    assert [(a.tipus, a.jugador) for a in avisos] == [
        (TIPUS_FORA_RANQUING, "CARMONA LÓPEZ, ANTONIO")
    ]


def test_revisa_els_inscrits_de_debo() -> None:
    """Els dos clubs de les fixtures no tenen cap contradicció interna.

    Els seus dos fitxatges venen del C.B.TARRAGONA, que no és a les fixtures,
    o sigui que aquí surten com a orfes. És el comportament correcte: la
    revisió es fa sobre la llista sencera, no club a club.
    """
    client = ClientFals(CLIENT)
    oberta = LligaOberta(38, "Lliga Catalana Tres Bandes", "Tres bandes", None, "Activa")
    info = llegeix_clubs(client, oberta)
    info = Lliga(38, info.nom, {16: info.clubs[16], 22: info.clubs[22]}, info.equips)
    avisos = revisa(llegeix_inscrits(client, info))
    assert {a.tipus for a in avisos} == {TIPUS_FITXATGE_ORFE}
    assert len(avisos) == 2


# ---------------- desat ----------------


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    return ensure_schema(tmp_path / "test.db")


def test_desa_i_reemplaça(conn) -> None:
    info = Lliga(38, "Lliga Catalana Tres Bandes", {1: "C.B.BANYOLES"}, 4)
    assert desa(conn, info, [fila("C.B.BANYOLES", "A, A")], "2026/2027") == 1
    assert desa(conn, info, [fila("C.B.BANYOLES", "B, B")], "2026/2027") == 1
    files = conn.execute("SELECT jugador FROM lliga_inscrits").fetchall()
    assert [f[0] for f in files] == ["B, B"]


def test_desa_no_accepta_el_buit(conn) -> None:
    """Substituir una composició per un silenci és pitjor que deixar la d'ahir."""
    info = Lliga(38, "Lliga Catalana Tres Bandes", {1: "C.B.BANYOLES"}, 4)
    desa(conn, info, [fila("C.B.BANYOLES", "A, A")], "2026/2027")
    with pytest.raises(ValueError, match="No esborro"):
        desa(conn, info, [], "2026/2027")
    assert conn.execute("SELECT COUNT(*) FROM lliga_inscrits").fetchone()[0] == 1


def test_el_mateix_jugador_hi_cap_dues_vegades_si_son_clubs_diferents(conn) -> None:
    """La clau porta el club perquè un fitxatge és dues files de debò."""
    info = Lliga(38, "Lliga Catalana Tres Bandes", {1: "A", 2: "B"}, 2)
    n = desa(
        conn,
        info,
        [
            fila("C.B.TARRAGONA", "ARNAU ABILLEIRA, ALEIX"),
            fila("C.B.MONT-ROIG", "ARNAU ABILLEIRA, ALEIX", fitxatge=True),
        ],
        "2026/2027",
    )
    assert n == 2
    assert conn.execute("SELECT SUM(fitxatge) FROM lliga_inscrits").fetchone()[0] == 1


def test_desa_amb_el_nom_del_cens(conn) -> None:
    """La federació escriu «S.B. CORAL COLÓN» i el cens «S.B.CORAL COLÓN».

    Un espai de més trenca qualsevol consulta que lligui per nom, i la taula
    existeix justament per creuar-la amb la resta.
    """
    conn.execute("INSERT INTO clubs (fcb_id, nom) VALUES ('x', 'S.B.CORAL COLÓN')")
    info = Lliga(38, "Lliga Catalana Tres Bandes", {1: "S.B. CORAL COLÓN"}, 2)
    desa(conn, info, [fila("S.B. CORAL COLÓN", "A, A")], "2026/2027")
    assert conn.execute("SELECT club FROM lliga_inscrits").fetchone()[0] == "S.B.CORAL COLÓN"


def test_un_club_mut_no_esborra_el_que_ja_hi_havia(conn) -> None:
    """Cada club és una pàgina, i una pàgina pot fallar ella sola.

    Si es reemplacés la lliga sencera, n'hi hauria prou que un club dels 38
    tornés zero jugadors —un 500, un tall de xarxa, una llista que encara no
    han presentat— perquè la ingesta li esborrés la composició sense dir res.
    """
    info = Lliga(38, "Lliga Catalana Tres Bandes", {1: "C.B.BANYOLES", 2: "C.B.VIC"}, 2)
    desa(
        conn,
        info,
        [fila("C.B.BANYOLES", "A, A"), fila("C.B.VIC", "B, B")],
        "2026/2027",
    )
    # Segona passada: el VIC no contesta.
    desa(conn, info, [fila("C.B.BANYOLES", "C, C")], "2026/2027")
    files = dict(conn.execute("SELECT club, jugador FROM lliga_inscrits").fetchall())
    assert files == {"C.B.BANYOLES": "C, C", "C.B.VIC": "B, B"}


def test_un_club_que_marxa_de_la_lliga_si_que_sesborra(conn) -> None:
    """No callar i no ser-hi són coses diferents.

    Que un club no surti a la pàgina d'inscripcions vol dir que no hi juga, i
    aquella pàgina sí que s'ha comprovat que no ve buida.
    """
    dos = Lliga(38, "Lliga Catalana Tres Bandes", {1: "C.B.BANYOLES", 2: "C.B.VIC"}, 2)
    desa(conn, dos, [fila("C.B.BANYOLES", "A, A"), fila("C.B.VIC", "B, B")], "2026/2027")
    un = Lliga(38, "Lliga Catalana Tres Bandes", {1: "C.B.BANYOLES"}, 1)
    desa(conn, un, [fila("C.B.BANYOLES", "A, A")], "2026/2027")
    assert [r[0] for r in conn.execute("SELECT club FROM lliga_inscrits")] == ["C.B.BANYOLES"]


def test_clubs_sense_jugadors_els_anomena() -> None:
    info = Lliga(38, "Lliga Catalana Tres Bandes", {1: "C.B.BANYOLES", 2: "C.B.VIC"}, 2)
    assert clubs_sense_jugadors(info, [fila("C.B.BANYOLES", "A, A")]) == ["C.B.VIC"]
    assert clubs_sense_jugadors(info, []) == ["C.B.BANYOLES", "C.B.VIC"]
