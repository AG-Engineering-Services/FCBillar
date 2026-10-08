"""El rànquing d'opens que es veu ha de ser el de la federació, i només aquell.

L'octubre del 2026 no ho era, per dues coses que se sumaven.

La primera: la federació va reanomenar el document del rànquing, de
«ranquing-opens-3-bandes-25-26» a «ranquing-catala-opens-3-bandes-25-26». La
cerca al sitemap anava per aquell prefix, va deixar de trobar-lo i el PDF no
s'aplicava. Qui el demana ho encaixa marcant la ronda com a provisional, i com
que l'últim open (Mataró) no té classificació final publicada, hi valia zero
punts per a tothom: en Jordi Garriga sortia amb 595 punts i en té 775.

La segona: l'upsert va per `(genere, ronda, jugador)` i ningú no treia els
jugadors que una ronda deixava de tenir. A la ronda vigent n'hi havia 33 d'una
publicació anterior, amb un altre nom de prova i llocs repetits.
"""

from __future__ import annotations

import httpx
import pytest

from fcb_opens.scraper import official_pdf as op
from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals

SITEMAP = """
<urlset>
<url><loc>https://fcbillar.cat/wpfd_file/ranquing-opens-circuit-catala-femeni-3-bandes-25-26/</loc></url>
<url><loc>https://fcbillar.cat/wpfd_file/ranquing-catala-opens-quadre-47-2-2025-26/</loc></url>
<url><loc>https://fcbillar.cat/wpfd_file/reglamentopenscatalans3bandes26-27/</loc></url>
<url><loc>https://fcbillar.cat/wpfd_file/{pagina}/</loc></url>
</urlset>
"""

#: La pàgina d'un document enllaça també el calendari, a la capçalera.
PAGINA = """
<a href="https://fcbillar.cat/download/36/calendari/232324/calendari-fcb-2026-27-v-2.pdf">cal</a>
<a href="https://fcbillar.cat/download/6/ranquings/230343/{fitxer}.pdf">baixa</a>
"""


class _WebFals:
    """Un `httpx.Client` que serveix el sitemap i les pàgines que se li donen."""

    def __init__(self, pagines: dict[str, str], demanades: list[str]) -> None:
        self._pagines, self._demanades = pagines, demanades

    def __enter__(self) -> _WebFals:
        return self

    def __exit__(self, *_a) -> None:
        return None

    def get(self, url: str, **_k):
        self._demanades.append(url)
        return type("R", (), {"text": self._pagines[url]})()


def _web(monkeypatch, pagines: dict[str, str]) -> list[str]:
    demanades: list[str] = []
    monkeypatch.setattr(httpx, "Client", lambda **_k: _WebFals(pagines, demanades))
    return demanades


@pytest.mark.parametrize(
    "nom",
    ["ranquing-opens-3-bandes-25-26", "ranquing-catala-opens-3-bandes-25-26"],
)
def test_troba_el_ranquing_es_digui_com_es_digui(monkeypatch, nom: str) -> None:
    pagina = f"https://fcbillar.cat/wpfd_file/{nom}/"
    demanades = _web(
        monkeypatch,
        {
            op.FCB_SITEMAP_DOCS: SITEMAP.format(pagina=nom),
            pagina: PAGINA.format(fitxer=nom),
        },
    )

    url = op.descobreix_ranquing_oficial()

    assert url == f"https://fcbillar.cat/download/6/ranquings/230343/{nom}.pdf"
    # Ni el femení ni les altres modalitats: no se'n demana ni la pàgina.
    assert demanades == [op.FCB_SITEMAP_DOCS, pagina]


def test_tria_la_temporada_mes_nova_encara_que_el_nom_hagi_canviat(monkeypatch) -> None:
    """Per ordre alfabètic «ranquing-opens-…-26-27» perdria contra «ranquing-catala-…-25-26»."""
    vell, nou = "ranquing-catala-opens-3-bandes-25-26", "ranquing-opens-3-bandes-26-27"
    sitemap = SITEMAP.format(pagina=vell) + (
        f"<url><loc>https://fcbillar.cat/wpfd_file/{nou}/</loc></url>"
    )
    _web(
        monkeypatch,
        {
            op.FCB_SITEMAP_DOCS: sitemap,
            f"https://fcbillar.cat/wpfd_file/{vell}/": PAGINA.format(fitxer=vell),
            f"https://fcbillar.cat/wpfd_file/{nou}/": PAGINA.format(fitxer=nou),
        },
    )

    assert op.descobreix_ranquing_oficial().endswith(f"/{nou}.pdf")


def test_sense_ranquing_de_tres_bandes_ho_diu(monkeypatch) -> None:
    _web(monkeypatch, {op.FCB_SITEMAP_DOCS: SITEMAP.format(pagina="reglament-5-quilles-25-26")})

    with pytest.raises(LookupError, match="rànquing d'opens"):
        op.descobreix_ranquing_oficial()


# ── Les files que sobren dins d'una ronda ────────────────────────────────────


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """Un sol open amb dos classificats, i el PDF oficial que no es troba."""
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2025-2026')")
    conn.execute(
        "INSERT INTO torneigs_individuals (id, torneig_id_extern, divisio_id_extern, nom, "
        "temporada_id) VALUES (7, 196, 431, 'OPEN TRES BANDES SANT ADRIÀ', 1)"
    )
    for pid, fcb, nom, posicio in ((1, "100", "ROCA, ANNA", 1), (2, "200", "PUIG, BERNAT", 2)):
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?, ?, ?)", (pid, fcb, nom))
        conn.execute(
            "INSERT INTO torneig_participants (torneig_id, player_id, posicio, club_text) "
            "VALUES (7, ?, ?, 'C.B.PROVA')",
            (pid, posicio),
        )
    conn.commit()
    conn.close()

    def no_hi_es(*_a, **_k):
        raise LookupError("sense PDF")

    monkeypatch.setattr(op, "descobreix_ranquing_oficial", no_hi_es)
    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    return db, magatzem


def _fila(genere: str, ronda: int, fcb: str) -> dict:
    return {"genere": genere, "ronda": ronda, "player_fcb_id": fcb, "punts": 125}


def test_qui_ja_no_es_a_la_ronda_se_n_va(entorn) -> None:
    db, magatzem = entorn
    magatzem["open_ranking"] = [
        _fila("general", 1, "999"),  # d'una publicació anterior: ja no hi és
        _fila("femeni", 1, "999"),  # un altre rànquing: no és cosa d'aquesta publicació
    ]

    counts = cloud_sync.publish_open_ranking(db_path=db)

    queden = {(f["genere"], f["ronda"], f["player_fcb_id"]) for f in magatzem["open_ranking"]}
    assert queden == {("general", 1, "100"), ("general", 1, "200"), ("femeni", 1, "999")}
    assert counts["files_retirades"] == 1


def test_si_no_es_pot_llegir_el_nuvol_no_s_esborra_res() -> None:
    class NoRespon:
        def table(self, _nom: str):
            raise ConnectionError("no respon")

    avisos: list[str] = []
    fora = cloud_sync._retira_files_sobrants(
        NoRespon(), "general", [_fila("general", 1, "100")], lambda _n, m: avisos.append(m)
    )

    assert fora == 0
    assert "no s'ha pogut llegir" in avisos[0]


def test_nomes_es_toquen_les_rondes_publicades() -> None:
    """Una ronda que aquesta publicació no ha escrit no és seva per buidar."""
    magatzem = {"open_ranking": [_fila("general", 1, "999"), _fila("general", 2, "999")]}

    fora = cloud_sync._retira_files_sobrants(
        ClientFals(magatzem), "general", [_fila("general", 1, "100")], lambda *_a: None
    )

    assert fora == 1
    assert magatzem["open_ranking"] == [_fila("general", 2, "999")]
