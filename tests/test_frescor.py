"""La comprovació de frescor: cada pèrdua de l'auditoria, convertida en una fila que falla.

La reingesta nocturna sortia verda passés el que passés. L'auditoria del 8
d'octubre de 2026 hi va trobar vuit pèrdues que no deia ningú; aquí n'hi ha les
que es podien veure comparant el que tenim amb el que publica la federació:

- el rànquing 126 publicat el 2 d'octubre i nosaltres republicant el 124;
- `games` aturat al juliol amb competició jugada al setembre;
- una lliga del llistat que no es publica, o una jornada jugada sense resultats;
- un torneig amb partides i sense cap participant (l'Open de Mataró);
- el PDF del rànquing d'opens que desapareix del sitemap;
- un document nou de la federació que cap pas no reconeix.

Les pàgines són captures del web de la federació de l'octubre de 2026.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fcbillar import cli, en_curs, frescor
from fcbillar.config import Settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.frescor import AVIS, FALLA, NA, OK, Font, Fonts
from fcbillar.scraper import urls as U
from fcbillar.scraper.parsers import parse_lligues_llistat

FIXTURES = Path(__file__).parent / "fixtures" / "nou"


def _pagina(nom: str) -> str:
    return (FIXTURES / nom).read_text(encoding="utf-8")


RANQUINGS = _pagina("rankings_llistat_2026_10.html")  # el 126, del 2 d'octubre
LLIGUES = _pagina("lligues_llistat.html")  # 38 Tres Bandes i 39 4 Modalitats, actives
INDIVIDUALS = _pagina("individuals_llistat_2026_10.html")  # 216-219 actius, 220 en inscripció
COPA = _pagina("copa_llistat.html")  # buit
SITEMAP = _pagina("wp_sitemap_documents_2026_10.xml")  # 84 documents

AVUI = date(2026, 10, 9)
ARA = datetime(2026, 10, 9, 21, 40)


def _font(text: str | None, error: str | None = None) -> Font:
    return Font(url="https://exemple/pagina", text=text, error=error)


def _fonts(**canvis) -> Fonts:
    base = {
        "ranquings": _font(RANQUINGS),
        "lligues": _font(LLIGUES),
        "individuals": _font(INDIVIDUALS),
        "copa": _font(COPA),
        "sitemap": _font(SITEMAP),
    }
    return Fonts(**{**base, **canvis})


@pytest.fixture
def conn(tmp_path, monkeypatch):
    """Una base de dades al dia el 9 d'octubre de 2026, petita."""
    for variable in ("FCB_LLIGA_3B_ID", "FCB_LLIGA_4M_ID", "FCB_TEMPORADA"):
        monkeypatch.delenv(variable, raising=False)
    c = ensure_schema(tmp_path / "t.db")
    c.execute("INSERT INTO temporades (id, nom) VALUES (2, '2026-2027')")
    for pid, nom in ((1, "ALBA, ANNA"), (2, "BOSCH, BERNAT")):
        c.execute(
            "INSERT INTO players (id, fcb_id, nom) VALUES (?, ?, ?)", (pid, str(100 + pid), nom)
        )

    # Els cinc rànquings vigents, el 126.
    for mod_id in (1, 2, 3, 4, 5):
        c.execute(
            "INSERT INTO rankings (num_seq, modalitat_id, url, format_url, data_pub) "
            "VALUES (126, ?, 'u', 'llistat', '2026-10-02')",
            (mod_id,),
        )
    c.execute(
        "INSERT INTO games (id, data_partida, modalitat_id, player1_id, player2_id, "
        "caramboles1, caramboles2, entrades) VALUES ('g', '2026-09-27', 1, 1, 2, 40, 30, 40)"
    )

    # Les dues lligues del llistat, vistes per `ingest-lliga`.
    en_curs.desa_lligues_obertes(c, parse_lligues_llistat(LLIGUES)[0], ara=ARA)
    _jornada(c, 38, "2026-09-26", jugats=7, de=8)
    _jornada(c, 38, "2026-10-10", jugats=0, de=8)
    _jornada(c, 39, "2026-10-11", jugats=0, de=4)

    # Els quatre torneigs actius, amb partides i participants.
    for tid in (216, 217, 218, 219):
        c.execute(
            "INSERT INTO torneigs_individuals (id, torneig_id_extern, divisio_id_extern, nom, "
            "temporada_id) VALUES (?, ?, ?, ?, 2)",
            (tid, tid, tid * 2, f"TORNEIG {tid}"),
        )
        c.execute(
            "INSERT INTO torneig_partides (torneig_id_extern, divisio_id_extern, fase_id, "
            "player1_nom, caramboles1, player2_nom, caramboles2, entrades, data) "
            "VALUES (?, ?, 1, 'ALBA, ANNA', 40, 'BOSCH, BERNAT', 30, 40, '2026-10-03')",
            (tid, tid * 2),
        )
        c.execute(
            "INSERT INTO torneig_participants (torneig_id, player_id, posicio) VALUES (?, 1, 1)",
            (tid,),
        )

    c.execute("INSERT INTO copa_jornades (edicio_id, jornada, ordre, nom) VALUES (7, 26, 1, '1a')")

    for jornada, data, jugada in ((1, "2026-09-12", 1), (2, "2026-09-26", 1), (3, "2026-10-10", 0)):
        c.execute(
            "INSERT INTO nacional_encontres (temporada, divisio, grup, jornada, ordre, data, "
            "local, visitant, punts_local, punts_visitant) VALUES "
            "('2026-2027', '1', 'A', ?, 1, ?, 'A', 'B', ?, ?)",
            (jornada, data, 6 if jugada else None, 2 if jugada else None),
        )

    for font, versio in (("FCB", "V-2"), ("RFEB", "v.1.2")):
        c.execute(
            "INSERT INTO calendari_versions (font, temporada, versio, sha256, last_checked_at) "
            "VALUES (?, '2026/2027', ?, ?, '2026-10-08 22:33:19')",
            (font, versio, font),
        )
    for grup in range(12):
        c.execute(
            "INSERT INTO lliga_calendari (temporada, divisio, grup, jornada, data, local, visitant) "
            "VALUES ('2026/2027', ?, ?, 1, '2026-09-26', 'A', 'B')",
            (f"d{grup // 2}", "AB"[grup % 2] + str(grup)),
        )
    c.commit()
    return c


def _jornada(conn, lliga: int, data: str, *, jugats: int, de: int) -> None:
    for i in range(de):
        conn.execute(
            "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id, data, "
            "p_match_local, p_match_visitant) VALUES (?, 1, 1, ?, ?, ?, ?)",
            (
                lliga,
                hash((data, i)) % 10**6,
                data,
                2 if i < jugats else None,
                0 if i < jugats else None,
            ),
        )


def _fila(informe, comenca: str) -> frescor.Fila:
    trobades = [f for f in informe.files if f.familia.startswith(comenca)]
    assert len(trobades) == 1, [f.familia for f in informe.files]
    return trobades[0]


# --------------------------- tot al dia ---------------------------


def test_amb_tot_al_dia_no_falla_res(conn) -> None:
    informe = frescor.comprova(conn, _fonts(), ara=ARA)

    assert {f.familia: f.estat for f in informe.files if f.estat in (FALLA, AVIS)} == {}
    assert not informe.falla


def test_cada_familia_hi_te_la_seva_fila(conn) -> None:
    informe = frescor.comprova(conn, _fonts(), ara=ARA)

    assert [f.familia for f in informe.files] == [
        "Rànquings de mitjana",
        "Partides per jugador (games)",
        "Lliga 4 Modalitats (39)",
        "Lliga Tres bandes (38)",
        "Individuals i opens",
        "Rànquing d'opens (PDF oficial)",
        "Opens en directe (prova de fum)",
        "Copa",
        "Lliga Nacional",
        "Calendari FCB",
        "Calendari RFEB",
        "Calendaris de grup",
    ]


# --------------------------- rànquings i partides ---------------------------


def test_un_ranquing_nou_que_no_tenim_falla(conn) -> None:
    """El 2 d'octubre de 2026: la federació publica el 126 i aquí hi ha el 124."""
    conn.execute("UPDATE rankings SET num_seq = 124, data_pub = '2026-07-27'")

    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Rànquings")

    assert fila.estat == FALLA
    assert "tenim el 124, hi ha el 126" in fila.detall


def test_una_sola_modalitat_endarrerida_ja_falla(conn) -> None:
    conn.execute("UPDATE rankings SET num_seq = 124 WHERE modalitat_id = 5")

    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Rànquings")

    assert fila.estat == FALLA
    assert "Quadre 71/2" in fila.detall and "Tres Bandes" not in fila.detall


def test_si_l_index_no_es_pot_llegir_falla_i_diu_per_que(conn) -> None:
    fonts = _fonts(ranquings=_font(None, "HTTP 500 a rankings/llistat"))

    fila = _fila(frescor.comprova(conn, fonts, ara=ARA), "Rànquings")

    assert fila.estat == FALLA and "HTTP 500" in fila.detall


def test_un_ranquing_que_ha_entrat_sense_les_seves_partides_falla(conn) -> None:
    """`games` aturat al juliol amb un rànquing d'octubre i lliga jugada al setembre."""
    conn.execute("UPDATE games SET data_partida = '2026-07-26'")

    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Partides per jugador")

    assert fila.estat == FALLA
    assert "2026-07-26" in fila.nostre


# --------------------------- lliga ---------------------------


def test_una_jornada_jugada_sense_cap_resultat_falla(conn) -> None:
    """Dues setmanes després de la primera jornada, ni un resultat."""
    conn.execute("UPDATE encontres_lliga SET p_match_local = NULL WHERE lliga_id = 38")

    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Lliga Tres bandes")

    assert fila.estat == FALLA
    assert "2026-09-26" in fila.nostre


def test_la_jornada_d_aquest_cap_de_setmana_encara_no_s_espera(conn) -> None:
    """El calendari no s'escriu enlloc: el que toca surt de les dates de la federació."""
    dilluns = datetime(2026, 10, 12, 21, 40)

    fila = _fila(frescor.comprova(conn, _fonts(), ara=dilluns), "Lliga Tres bandes")

    assert fila.estat == OK
    assert "2026-09-26" in fila.nostre, "la del 10 encara té marge per pujar les actes"


def test_una_lliga_que_encara_no_ha_comencat_no_crida_al_llop(conn) -> None:
    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Lliga 4 Modalitats")

    assert fila.estat == OK
    assert "cap jornada jugada" in fila.esperat


def test_si_la_publicacio_no_segueix_el_llistat_falla(conn, monkeypatch) -> None:
    """El setembre de 2026: la federació té oberta la 38 i el web ensenya la 36."""
    monkeypatch.setenv("FCB_LLIGA_3B_ID", "36")

    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Lliga Tres bandes")

    assert fila.estat == FALLA
    assert "es publica la 36" in fila.nostre


def test_una_lliga_del_llistat_que_la_base_no_ha_vist_falla(conn) -> None:
    conn.execute("DELETE FROM lligues_obertes WHERE lliga_id = 39")

    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Lliga 4 Modalitats")

    assert fila.estat == FALLA


def test_entre_temporades_el_llistat_buit_no_es_cap_error(conn) -> None:
    buit = LLIGUES.split("<tbody>")[0] + "<tbody></tbody></table></div></div>"
    estiu = datetime(2027, 8, 26, 21, 40)

    informe = frescor.comprova(conn, _fonts(lligues=_font(buit)), ara=estiu)

    de_lliga = [f for f in informe.files if f.familia == "Lliga"]
    assert [f.estat for f in de_lliga] == [NA]
    assert not any(f.familia.startswith("Lliga Tres") for f in informe.files)


# --------------------------- individuals i opens ---------------------------


def test_un_torneig_amb_partides_i_sense_participants_falla(conn) -> None:
    """L'Open de Mataró va estar tres mesos així."""
    conn.execute("DELETE FROM torneig_participants WHERE torneig_id = 217")

    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Individuals")

    assert fila.estat == FALLA
    assert "(217)" in fila.detall


def test_un_torneig_en_inscripcio_no_s_espera(conn) -> None:
    """El 220 té inscripció oberta fins al 16 d'octubre: no hi ha res a ingerir."""
    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Individuals")

    assert fila.estat == OK
    assert fila.esperat.startswith("4 actius")


def test_si_el_llistat_perd_la_taula_falla(conn) -> None:
    fonts = _fonts(individuals=_font("<html><body>Manteniment</body></html>"))

    assert _fila(frescor.comprova(conn, fonts, ara=ARA), "Individuals").estat == FALLA


def _open_de_tres_bandes(conn, data: str) -> None:
    conn.execute(
        "INSERT INTO torneigs_individuals (id, torneig_id_extern, divisio_id_extern, nom, "
        "temporada_id) VALUES (211, 211, 447, 'OPEN TRES BANDES MATARO', 2)"
    )
    conn.execute(
        "INSERT INTO torneig_partides (torneig_id_extern, divisio_id_extern, fase_id, "
        "player1_nom, caramboles1, player2_nom, caramboles2, entrades, data) "
        "VALUES (211, 447, 1, 'ALBA, ANNA', 40, 'BOSCH, BERNAT', 30, 40, ?)",
        (data,),
    )


def test_si_el_pdf_del_ranquing_d_opens_desapareix_del_sitemap_falla(conn) -> None:
    """Ha passat dues vegades: el reanomenen i la ronda es queda provisional."""
    _open_de_tres_bandes(conn, "2026-07-18")
    sense = SITEMAP.replace("ranquing-catala-opens-3-bandes-25-26", "classificacio-circuit-25-26")

    fila = _fila(frescor.comprova(conn, _fonts(sitemap=_font(sense)), ara=ARA), "Rànquing d'opens")

    assert fila.estat == FALLA


@pytest.mark.parametrize(
    ("aplicat", "estat", "diu"),
    [(1, OK, "aplicat"), (-1, FALLA, "NO aplicat"), (0, AVIS, "ronda provisional")],
)
def test_el_que_diu_la_publicacio_del_pdf_d_opens(conn, aplicat, estat, diu) -> None:
    """Aplicat, no llegit, o provisional des de fa massa (l'open és de fa 83 dies)."""
    _open_de_tres_bandes(conn, "2026-07-18")

    informe = frescor.comprova(
        conn, _fonts(), ara=ARA, publicacio={"open_ranking_pdf_oficial": aplicat}
    )

    fila = _fila(informe, "Rànquing d'opens")
    assert fila.estat == estat
    assert diu in fila.nostre


def test_una_ronda_provisional_de_fa_pocs_dies_es_normal(conn) -> None:
    _open_de_tres_bandes(conn, "2026-10-04")

    informe = frescor.comprova(conn, _fonts(), ara=ARA, publicacio={"open_ranking_pdf_oficial": 0})

    assert _fila(informe, "Rànquing d'opens").estat == OK


# --------------------------- copa, nacional, calendari ---------------------------


def test_sense_cap_copa_oberta_no_toca(conn) -> None:
    assert _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Copa").estat == NA


def test_una_copa_oberta_que_no_hem_ingerit_falla(conn) -> None:
    oberta = COPA.replace(
        "<tbody>",
        "<tbody><tr><td>Copa Catalana 2026-27</td><td>Activa</td><td>2027-04-30</td>"
        '<td><a href="/frontend/copa/fase-grups/8">Veure</a></td></tr>',
        1,
    )
    assert "fase-grups/8" in oberta, "la captura ha de tenir un <tbody> on posar la fila"

    fila = _fila(frescor.comprova(conn, _fonts(copa=_font(oberta)), ara=ARA), "Copa")

    assert fila.estat == FALLA
    assert "8" in fila.detall


@pytest.mark.parametrize(
    ("avui", "estat"),
    [
        (datetime(2026, 10, 9, 21), OK),  # la jornada 3 és demà
        (datetime(2026, 10, 15, 21), OK),  # fa cinc dies: encara no toca
        (datetime(2026, 10, 22, 21), AVIS),  # fa dotze dies i ningú no ha pujat el PDF
        (datetime(2026, 11, 5, 21), FALLA),  # ja s'ha jugat la següent
        (
            datetime(2027, 3, 1, 21),
            AVIS,
        ),  # un forat de mesos no ha de deixar el job vermell per sempre
    ],
)
def test_la_lliga_nacional_avisa_i_despres_falla(conn, avui, estat) -> None:
    """No es baixa: algú ha de pujar el PDF. Sense això es quedava on era, en verd."""
    assert _fila(frescor.comprova(conn, _fonts(), ara=avui), "Lliga Nacional").estat == estat


def test_una_revisio_nova_del_calendari_que_no_tenim_falla(conn) -> None:
    amb_la_v3 = SITEMAP.replace("calendari-fcb-2026-27-v-2", "calendari-fcb-2026-27-v-3")

    fila = _fila(frescor.comprova(conn, _fonts(sitemap=_font(amb_la_v3)), ara=ARA), "Calendari FCB")

    assert fila.estat == FALLA
    assert fila.esperat == "2026/2027 V-3"


def test_un_calendari_que_fa_dies_que_no_es_mira_falla(conn) -> None:
    conn.execute("UPDATE calendari_versions SET last_checked_at = '2026-10-01 22:00:00'")

    informe = frescor.comprova(conn, _fonts(), ara=ARA)

    assert _fila(informe, "Calendari FCB").estat == FALLA
    assert _fila(informe, "Calendari RFEB").estat == FALLA


def test_un_calendari_de_grup_publicat_i_no_ingerit_falla(conn) -> None:
    conn.execute("DELETE FROM lliga_calendari WHERE divisio = 'd0'")

    fila = _fila(frescor.comprova(conn, _fonts(), ara=ARA), "Calendaris de grup")

    assert fila.estat == FALLA
    assert (fila.nostre, fila.esperat) == ("10 grups de la 2026/2027", "12 PDF al web")


# --------------------------- els passos del workflow ---------------------------


def test_un_pas_fallat_surt_a_la_taula_i_fa_fallar(conn) -> None:
    passos = ["ingest-ranquings\t0", "ingest-lliga\t1", "opens-directe-prova\t0"]

    informe = frescor.comprova(conn, _fonts(), ara=ARA, linies_passos=passos)

    fila = _fila(informe, "Passos de la reingesta")
    assert fila.estat == FALLA
    assert fila.detall == "ingest-lliga (exit 1)"
    assert informe.falla
    assert informe.files[0] is fila, "és el primer que es veu"


def test_la_prova_de_fum_dels_opens_en_directe_te_fila_propia(conn) -> None:
    """Exit 3: el lector no sap llegir el web i el cap de setmana no hi haurà seguiment."""
    informe = frescor.comprova(
        conn, _fonts(), ara=ARA, linies_passos=["ingest-lliga\t0", "opens-directe-prova\t3"]
    )

    assert _fila(informe, "Opens en directe").estat == FALLA
    assert _fila(informe, "Passos de la reingesta").estat == FALLA


def test_un_fitxer_de_passos_buit_vol_dir_que_no_ha_corregut_res(conn) -> None:
    informe = frescor.comprova(conn, _fonts(), ara=ARA, linies_passos=[])

    assert _fila(informe, "Passos de la reingesta").estat == FALLA


def test_amb_tots_els_passos_be_no_falla(conn) -> None:
    passos = [f"{nom}\t0" for nom in ("ingest-lliga", "opens-directe-prova", "publish-cloud")]

    informe = frescor.comprova(conn, _fonts(), ara=ARA, linies_passos=passos)

    assert not informe.falla
    assert _fila(informe, "Opens en directe").estat == OK


def test_una_comprovacio_que_peta_no_passa_per_bona(conn) -> None:
    """Si falta una taula, la fila surt com a fallada i les altres hi són igualment."""
    conn.execute("DROP TABLE nacional_encontres")

    informe = frescor.comprova(conn, _fonts(), ara=ARA)

    assert _fila(informe, "Comprovació interna").estat == FALLA
    assert _fila(informe, "Calendari FCB").estat == OK


# --------------------------- l'inventari de documents ---------------------------


def test_l_inventari_separa_el_que_es_llegeix_del_que_no_reconeix_ningu() -> None:
    documents = {d.slug: d for d in frescor.inventari(_font(SITEMAP))}

    assert len(documents) == 84
    assert documents["calendari-lliga-tres-bandes-2026-27-honor-grup-a"].classe == "ingerit"
    assert documents["calendari-fcb-2026-27-v-2"].classe == "ingerit"
    assert documents["ranquing-catala-opens-3-bandes-25-26"].classe == "ingerit"
    assert documents["final-tres-bandes-honor"].classe == "ingerit"
    assert documents["previes-3-bandes-honor"].classe == "ingerit"
    assert documents["reglament-lliga-catalana-3-bandes-26-27"].classe == "sabut"
    assert documents["grups-previa-open-banda-b-c-granollers"].classe == "sabut"
    assert documents["adjudicacio-finals-2026-27"].classe == "sabut"


def test_els_que_l_auditoria_va_trobar_a_ma_surten_com_a_nous() -> None:
    """Les classificacions finals, el quadre, els rànquings d'altres modalitats."""
    nous = {d.slug for d in frescor.inventari(_font(SITEMAP)) if d.classe == "nou"}

    assert {
        "classificacio-final-quadre-47-2-honor-26-27",
        "divisions-quadre-47-2-temporada-2026-27",
        "jugadors-lliga-4mod-26-27",
        "calendari-lliga-4modalitats-honor-26-27",
        "ranquing-catala-opens-lliure-26-27",
        "ranquing-opens-circuit-catala-femeni-3-bandes-25-26",
    } <= nous
    assert len(nous) == 20


def test_un_document_reanomenat_deixa_de_ser_reconegut() -> None:
    """El dia que canvien un nom, surt a la llista en comptes de perdre's."""
    reanomenat = SITEMAP.replace("final-tres-bandes-honor", "quadre-honor-3b")

    nous = {d.slug for d in frescor.inventari(_font(reanomenat)) if d.classe == "nou"}

    assert "quadre-honor-3b" in nous


def test_l_inventari_no_fa_fallar_res(conn) -> None:
    informe = frescor.comprova(conn, _fonts(), ara=ARA)

    assert len(informe.nous()) == 20
    assert not informe.falla


# --------------------------- el resum i la comanda ---------------------------


def test_el_resum_porta_la_taula_i_els_documents_nous(conn) -> None:
    text = frescor.markdown(frescor.comprova(conn, _fonts(), ara=ARA))

    assert text.startswith("### ✅ Frescor: tot al dia")
    assert "| ✅ OK | Rànquings de mitjana | núm. 126 a 5 modalitats |" in text
    assert "#### Documents de la federació que no llegeix cap pas (20 de 84)" in text
    # Els dels últims catorze dies, a la vista; els altres, plegats.
    recents, vells = text.split("<details>")
    assert "`jugadors-lliga-4mod-26-27` (2026-10-08)" in recents
    assert "`ranquing-catala-5-quilles-25-26`" in vells


def test_el_resum_diu_quantes_fallen(conn) -> None:
    conn.execute("UPDATE rankings SET num_seq = 124")

    text = frescor.markdown(frescor.comprova(conn, _fonts(), ara=ARA))

    assert text.startswith("### ❌ Frescor: 1 comprovacions fallen")
    assert "| ❌ FALLA | Rànquings de mitjana |" in text


class _Client:
    """Serveix les captures per l'adreça que es demana."""

    PAGINES = (
        (U.rankings_llistat(), RANQUINGS),
        (U.lligues_llistat(), LLIGUES),
        (U.individuals_llistat(), INDIVIDUALS),
        (U.copa_llistat(), COPA),
        (U.web_sitemap_documents(), SITEMAP),
    )

    def __init__(self, *_a, **_k) -> None:
        pass

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *_a) -> None:
        return None

    def fetch_html(self, url: str, **_k) -> str:
        return dict(self.PAGINES)[url]


def test_la_comanda_escriu_el_resum_i_surt_amb_error_quan_falla(
    conn, tmp_path, monkeypatch
) -> None:
    """És el que fa acabar el job en vermell."""
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    conn.execute("UPDATE rankings SET num_seq = 124")
    conn.commit()
    settings = Settings(db_path=db, cache_dir=tmp_path / "cache")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "ScraperClient", _Client)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    resum = tmp_path / "resum.md"

    res = CliRunner().invoke(cli.app, ["comprova-frescor", "--resum", str(resum)])

    assert res.exit_code == 1
    assert "❌ FALLA | Rànquings de mitjana" in resum.read_text(encoding="utf-8")


def test_la_comanda_llegeix_els_passos_i_el_resum_de_github(conn, tmp_path, monkeypatch) -> None:
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    settings = Settings(db_path=db, cache_dir=tmp_path / "cache")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "ScraperClient", _Client)
    resum = tmp_path / "github_summary.md"
    resum.write_text("### Els 16 passos han anat bé\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(resum))
    passos = tmp_path / "passos.tsv"
    passos.write_text(
        "ingest-lliga\t0\nopens-directe-prova\t0\npublish-cloud\t1\n", encoding="utf-8"
    )

    res = CliRunner().invoke(cli.app, ["comprova-frescor", "--passos", str(passos)])

    assert res.exit_code == 1, "un pas fallat fa fallar la comprovació"
    text = resum.read_text(encoding="utf-8")
    assert text.startswith("### Els 16 passos han anat bé"), "s'hi afegeix, no es trepitja"
    assert "publish-cloud (exit 1)" in text
