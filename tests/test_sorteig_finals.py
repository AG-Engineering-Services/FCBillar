"""Els sortejos de les finals i els del quadre 47/2 també es llegeixen.

Dos filtres en deixaven fora documents publicats, i tots dos pel nom:

- Només s'obrien les pàgines del sitemap amb `previ` o `grups` al nom, i les de
  les finals es diuen «final-tres-bandes-honor».
- La categoria del gestor de fitxers havia de començar per `individuals-`, i la
  del quadre es diu `individual-quadre-47-2`, sense la essa.

I un cop dins, el full d'una final no és el d'una prèvia: no té «Grup X (seu)»
amb els jugadors a sota, sinó un horari i una taula «Rànquing inicial».

Les fixtures són del 2026-10-08: el sitemap de documents i els PDF de dues
finals, la de Quadre 47/2 d'Honor i la de Tres Bandes de 1a.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fcbillar import sorteig_fase as S
from fcbillar.db.migrations import ensure_schema

FIXTURES = Path(__file__).parent / "fixtures"
SITEMAP = (FIXTURES / "nou" / "wp_sitemap_documents_2026_10.xml").read_text(encoding="utf-8")
FINAL_QUADRE = FIXTURES / "sorteig" / "final-quadre-47-2-divisio-honor.pdf"
FINAL_3B_1A = FIXTURES / "sorteig" / "final-tres-bandes-1a-divisio-26-27.pdf"

URL_QUADRE = (
    "https://fcbillar.cat/download/63/individual-quadre-47-2/232637/"
    "final-quadre-47-2-divisio-honor.pdf"
)
URL_3B = (
    "https://fcbillar.cat/download/11/individuals-tres-bandes/232705/"
    "final-tres-bandes-1a-divisio-26-27.pdf"
)
URL_CALENDARI = "https://fcbillar.cat/download/36/calendari/232324/calendari-fcb-2026-27-v-2.pdf"
URL_OPEN = (
    "https://fcbillar.cat/download/33/opens/232494/grups-previa-open-banda-b-c-granollers.pdf"
)


# ---------------- quines pàgines s'obren ----------------


def _slugs_acceptats() -> set[str]:
    import re

    return {
        u.rstrip("/").rsplit("/", 1)[-1]
        for u in re.findall(r"<loc>([^<]+)</loc>", SITEMAP)
        if S.es_pagina_de_sorteig(u)
    }


def test_les_pagines_de_les_finals_s_obren() -> None:
    acceptats = _slugs_acceptats()
    assert {
        "final-tres-bandes-honor",
        "final-tres-bandes-1a-divisio-26-27",
        "final-tres-bandes-2a-divisio-26-27",
        "final-quadre-47-2-divisio-honor",
        "final-quadre-47-2-1a-divisio",
    } <= acceptats


def test_les_que_ja_s_obrien_segueixen_obrint_se() -> None:
    acceptats = _slugs_acceptats()
    assert {
        "previes-3-bandes-honor",
        "previes-tres-bandes-1a-divisio",
        "previa-tres-bandes-2a-divisio",
        "pre-previes-tres-bandes-1a-divisio",
        "pre-previes-tres-bandes-2a-divisio",
    } <= acceptats


def test_la_classificacio_final_no_es_cap_sorteig() -> None:
    """És a la mateixa categoria que els sortejos, i parla d'una final."""
    acceptats = _slugs_acceptats()
    assert "classificacio-final-quadre-47-2-honor-26-27" not in acceptats
    assert "classificacio-final-quadre-47-2-1a-divisio-26-27" not in acceptats
    assert "2627-openlliurepuntatac-classificaciofinal" not in acceptats
    # Ni el que no parla de cap fase.
    assert "divisions-quadre-47-2-temporada-2026-27" not in acceptats
    assert "calendari-fcb-2026-27-v-2" not in acceptats


# ---------------- quins PDF s'agafen ----------------


@pytest.mark.parametrize(
    ("categoria", "modalitat"),
    [
        ("individuals-tres-bandes", "Tres bandes"),
        ("individual-quadre-47-2", "Quadre 47/2"),
        ("individuals-quadre-47-2", "Quadre 47/2"),
        ("individual-lliure", "Lliure"),
        ("individuals-una-que-no-coneixem", ""),
    ],
)
def test_la_modalitat_surt_de_la_categoria_amb_essa_o_sense(categoria, modalitat) -> None:
    assert S.modalitat_de_categoria(categoria) == modalitat


class Resposta:
    def __init__(self, text: str = "", content: bytes = b"") -> None:
        self.text, self.content = text, content


class WebFals:
    """El sitemap i dues pàgines de document, amb els enllaços com els du el web."""

    def __init__(self) -> None:
        self.demanades: list[str] = []
        base = "https://fcbillar.cat/wpfd_file"
        self._pagines = {
            S.SITEMAP: (
                "<urlset>"
                f"<url><loc>{base}/final-quadre-47-2-divisio-honor/</loc></url>"
                f"<url><loc>{base}/final-tres-bandes-1a-divisio-26-27/</loc></url>"
                f"<url><loc>{base}/classificacio-final-quadre-47-2-honor-26-27/</loc></url>"
                f"<url><loc>{base}/grups-previa-open-banda/</loc></url>"
                f"<url><loc>{base}/calendari-fcb-2026-27-v-2/</loc></url>"
                "</urlset>"
            ),
            # Cada pàgina enllaça el seu document i, a la barra lateral, el calendari.
            f"{base}/final-quadre-47-2-divisio-honor/": f'<a href="{URL_QUADRE}">a</a>'
            f'<a href="{URL_CALENDARI}">c</a>',
            f"{base}/final-tres-bandes-1a-divisio-26-27/": f'<a href="{URL_3B}">a</a>',
            f"{base}/grups-previa-open-banda/": f'<a href="{URL_OPEN}">a</a>',
        }
        self._pdfs = {URL_QUADRE: FINAL_QUADRE, URL_3B: FINAL_3B_1A}

    def get(self, url: str) -> Resposta:
        self.demanades.append(url)
        if url in self._pdfs:
            return Resposta(content=self._pdfs[url].read_bytes())
        return Resposta(text=self._pagines[url])


def test_descobreix_troba_les_finals_i_el_quadre() -> None:
    web = WebFals()
    publicats = S.descobreix(web)

    assert [(p.nom_fitxer, p.categoria, p.modalitat) for p in publicats] == [
        ("final-quadre-47-2-divisio-honor.pdf", "individual-quadre-47-2", "Quadre 47/2"),
        ("final-tres-bandes-1a-divisio-26-27.pdf", "individuals-tres-bandes", "Tres bandes"),
    ]
    # La pàgina de la classificació final ni s'obre.
    assert not any("classificacio" in u for u in web.demanades)


# ---------------- el full d'una final ----------------


def test_la_final_del_quadre_es_llegeix_sencera() -> None:
    sorteig = S.llegeix(FINAL_QUADRE)

    assert sorteig.ronda == "FINAL"
    assert sorteig.titol == "Final QUADRE 47/2 HONOR"
    assert [(j.jugador, j.club, j.grup) for j in sorteig.jugadors] == [
        ("TUSET MALLOL, CARLES", "S.B.F.MOLINS", "A"),
        ("GARRIGA LLOVET, SERGI", "S.E.CASAL CERVERA", "B"),
        ("VILALTA PARÉ, VALENTÍ", "C.B.SANTS", "B"),
        ("MORENO CORTÉS, ARMAND", "C.B.LLEIDA", "A"),
        ("VIDAL GIBERT, JOAN", "C.B.TARRAGONA", "A"),
        ("GASSÓ CHUMILLAS, JORDI", "B.C.GRANOLLERS", "B"),
        # El club d'aquesta fila surt una línia més amunt que el nom, al PDF.
        ("PALLISA GONZÁLEZ, JOSEP", "C.B.SANT ADRIÀ", "B"),
        ("ESPINASA SÁNCHEZ, JOAN", "B.C.GRANOLLERS", "A"),
    ]


def test_la_final_de_tres_bandes_amb_els_noms_centrats() -> None:
    """Aquí el nom no comença a cap `x` fixa, i el número va en una altra línia."""
    sorteig = S.llegeix(FINAL_3B_1A)

    assert sorteig.ronda == "FINAL"
    assert {j.grup: 0 for j in sorteig.jugadors}.keys() == {"A", "B"}
    assert len(sorteig.jugadors) == 8
    per_nom = {j.jugador: (j.club, j.grup) for j in sorteig.jugadors}
    assert per_nom["COROMINAS FRANCH, ESTEVE"] == ("C.B.BANYOLES", "A")
    assert per_nom["GUERRERO GONZÁLEZ, MIQUEL A."] == ("C.B.SANT ADRIÀ", "B")
    assert per_nom["MARTÍN LIMA, MELCHOR"] == ("S.B. LA GRAN PENYA", "B")
    assert per_nom["HERNÁNDEZ LÓPEZ, JONATAN"] == ("C.B.SANT ADRIÀ", "A")


def test_el_titol_d_una_final_casa_amb_la_seva_fase_i_no_amb_la_previa() -> None:
    titol = S.llegeix(FINAL_3B_1A).titol
    assert S.casa_amb_fase(titol, "1A DIVISIÓ", "FINAL")
    assert not S.casa_amb_fase(titol, "1A DIVISIÓ", "PRÈVIA")
    assert not S.casa_amb_fase(titol, "2A DIVISIÓ", "FINAL")


def test_una_final_no_porta_regla_i_no_es_cap_avis(tmp_path, monkeypatch) -> None:
    """Una final no classifica per a res: que no en tingui no s'ha de dir cada nit."""
    monkeypatch.setenv("FCB_CACHE_DIR", str(tmp_path / "cache"))
    conn = ensure_schema(tmp_path / "t.db")

    n, avisos = S.desa_regles(conn, WebFals())

    assert n == 0
    assert avisos == []


# ---------------- el club d'una final, que ve amb prefix ----------------


def test_el_club_amb_el_prefix_equivocat_es_resol_pel_nom(tmp_path) -> None:
    """El full de la final d'Honor escriu «C.B.GRANOLLERS» de «B.C.GRANOLLERS»."""
    from fcbillar import afiliacions as A
    from fcbillar.db.repository import Repository
    from fcbillar.models import Club

    repo = Repository(ensure_schema(tmp_path / "t.db"))
    for nom in ("B.C.GRANOLLERS", "C.B.OLESA", "BC OLESA"):
        repo.upsert_club(Club(fcb_id=nom, nom=nom))
    cens = [r[0] for r in repo.conn.execute("SELECT nom FROM clubs")]

    assert A.resol_club(repo, "C.B.GRANOLLERS", cens) == "B.C.GRANOLLERS"
    # El que ja és al cens es resol com sempre, sense passar pel sufix.
    assert A.resol_club(repo, "C.B.OLESA", cens) == "C.B.OLESA"
    # I el que casaria amb dos clubs segueix sense triar-se.
    assert A.resol_club(repo, "S.B.OLESA", cens) is None
