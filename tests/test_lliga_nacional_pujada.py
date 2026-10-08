"""El botó de pujar documents de la Lliga Nacional: què és cada PDF i on va."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fcbillar import lliga_nacional as LN

NACIONAL = Path(__file__).parent / "fixtures" / "nacional"
AVUI = date(2026, 10, 8)


def test_una_jornada_va_al_seu_lloc_amb_el_seu_numero(tmp_path):
    r = LN.reconeix_i_desa(NACIONAL / "liga_nal_1_j1_2627.pdf", "1", tmp_path, AVUI)
    assert (r.tipus, r.temporada, r.divisio) == ("jornada", "2026-2027", "1")
    assert r.fitxer == "2026-2027/1/liga_nal_1_j1.pdf"
    assert (tmp_path / r.fitxer).read_bytes() == (NACIONAL / "liga_nal_1_j1_2627.pdf").read_bytes()
    assert "Jornada 1" in r.resum


def test_tornar_a_pujar_la_mateixa_jornada_no_fa_una_segona_copia(tmp_path):
    for _ in range(2):
        LN.reconeix_i_desa(NACIONAL / "liga_nal_1_j1_2627.pdf", "1", tmp_path, AVUI)
    assert [p.name for p in (tmp_path / "2026-2027" / "1").iterdir()] == ["liga_nal_1_j1.pdf"]


def test_el_calendari_es_reconeix_sol(tmp_path):
    r = LN.reconeix_i_desa(NACIONAL / "calendari_1_2627.pdf", "1", tmp_path, AVUI)
    assert (r.tipus, r.fitxer) == ("calendari", "2026-2027/1/calendari.pdf")
    assert "14 jornades" in r.resum


def test_una_divisio_que_no_existeix_no_desa_res(tmp_path):
    with pytest.raises(ValueError):
        LN.reconeix_i_desa(NACIONAL / "liga_nal_1_j1_2627.pdf", "tercera", tmp_path, AVUI)
    assert list(tmp_path.iterdir()) == []


def test_un_pdf_que_no_es_de_la_lliga_no_desa_res(tmp_path):
    # El calendari d'un grup de la lliga CATALANA: un PDF de debò, però no d'aquí.
    alie = Path(__file__).parent / "fixtures" / "calendari_lliga_2627_1a_grupA.pdf"
    with pytest.raises(LN.FormatDesconegut):
        LN.reconeix_i_desa(alie, "1", tmp_path, AVUI)
    assert not any(tmp_path.rglob("*.*"))


def test_de_l_orden_de_fuerza_nomes_en_queda_el_csv(tmp_path, monkeypatch):
    """L'original porta telèfons i correus: no s'ha de copiar enlloc."""
    original = tmp_path / "pas" / "orden de fuerza.pdf"
    original.parent.mkdir()
    original.write_bytes(b"%PDF-1.4 telefon 600000000 president@club.example")
    alineacions = [
        LN.Alineacio(grup="B", equip="C.B. SANT ADRIA", ordre=1, jugador="Un Jugador"),
        LN.Alineacio(grup="B", equip="C.B. SANT ADRIA", ordre=2, jugador="Un Altre"),
    ]

    def cap(_cami):
        raise LN.FormatDesconegut("no ho és")

    monkeypatch.setattr(LN, "llegeix_jornada", cap)
    monkeypatch.setattr(LN, "llegeix_classificacio_de_jugadors", cap)
    monkeypatch.setattr(LN, "llegeix_calendari", cap)
    monkeypatch.setattr(LN, "llegeix_alineacions", lambda _cami: alineacions)

    fonts = tmp_path / "fonts"
    r = LN.reconeix_i_desa(original, "1", fonts, AVUI)

    assert (r.tipus, r.fitxer) == ("alineacions", "2026-2027/1/alineacions.csv")
    desats = [p for p in fonts.rglob("*") if p.is_file()]
    assert [p.name for p in desats] == ["alineacions.csv"]
    text = desats[0].read_text(encoding="utf-8")
    assert "Un Jugador" in text
    assert "600000000" not in text and "@" not in text
