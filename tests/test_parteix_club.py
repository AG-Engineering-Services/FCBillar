"""Separar el nom del jugador del nom del club al PDF de divisions.

El PDF no els separa de cap manera: «LUQUE MARTÍNEZ, JESÚSC.B.SANT ADRIÀ» és una
sola cadena i l'única manera de partir-la és reconèixer-hi un club del cens.

Quan el cens no porta el nom del club tal com el PDF l'escriu, el tall es queda
curt i el tros que sobra se'n va al nom del jugador. Ha passat dues vegades i
cap de les dues no la va veure el codi: catorze jugadors de la Unió Coral van
sortir com a «COGNOMS, NOM S.» i vint-i-un del Sant Adrià com a «COGNOMS, NOM
C.B.». Les dues vegades ho va veure algú mirant la pantalla.
"""

from __future__ import annotations

from fcbillar.divisions_individual import _norm, parteix_club


def _cens(*clubs: tuple[str, str]) -> list[tuple[str, str]]:
    """Les parelles (forma que es busca, club del cens), de més llarga a més curta.

    És com les prepara `llegeix`: l'ordre importa, perquè «C.B.SANT ADRIÀ» s'ha
    de provar abans que «SANT ADRIÀ».
    """
    return sorted(
        ((_norm(forma), club) for forma, club in clubs),
        key=lambda kv: -len(kv[0]),
    )


CENS = _cens(
    ("C.B.SANT ADRIÀ", "C.B.SANT ADRIÀ"),
    ("C.B.SANTS", "C.B.SANTS"),
    ("C.B.BANYOLES", "C.B.BANYOLES"),
)


def test_talla_pel_nom_sencer_del_club() -> None:
    assert parteix_club("LUQUE MARTÍNEZ, JESÚSC.B.SANT ADRIÀ", CENS) == (
        "LUQUE MARTÍNEZ, JESÚS",
        "C.B.SANT ADRIÀ",
    )


def test_un_nom_que_acaba_amb_inicial_es_valid() -> None:
    """«MIQUEL A.» és un nom de debò i no s'ha de rebutjar."""
    assert parteix_club("GUERRERO GONZÁLEZ, MIQUEL A.C.B.SANT ADRIÀ", CENS) == (
        "GUERRERO GONZÁLEZ, MIQUEL A.",
        "C.B.SANT ADRIÀ",
    )


def test_si_el_cens_nomes_te_el_nom_curt_no_es_dona_per_bo() -> None:
    """El cas del Sant Adrià: el `fcb_id` era «SANT ADRIÀ», sense el «C.B.».

    Amb aquell cens el tall deixava «...JESÚS C.B.» com a nom del jugador. Val
    més tornar `None` -i que la línia consti com a rebutjada, que atura el
    desat- que desar un nom que no casarà amb ningú i que ningú no notarà.
    """
    escurcat = _cens(("SANT ADRIÀ", "C.B.SANT ADRIÀ"))
    assert parteix_club("LUQUE MARTÍNEZ, JESÚS C.B.SANT ADRIÀ", escurcat) is None


def test_amb_les_dues_formes_al_cens_talla_per_la_llarga() -> None:
    """Que és el que ho arregla: `llegeix` rep el `fcb_id` I el nom del cens."""
    totes = _cens(("SANT ADRIÀ", "C.B.SANT ADRIÀ"), ("C.B.SANT ADRIÀ", "C.B.SANT ADRIÀ"))
    assert parteix_club("LUQUE MARTÍNEZ, JESÚS C.B.SANT ADRIÀ", totes) == (
        "LUQUE MARTÍNEZ, JESÚS",
        "C.B.SANT ADRIÀ",
    )


def test_sants_no_es_confon_amb_sant_adria() -> None:
    assert parteix_club("MARTÍN LIMA, MELCHORC.B.SANTS", CENS) == (
        "MARTÍN LIMA, MELCHOR",
        "C.B.SANTS",
    )


def test_un_club_que_no_es_al_cens_no_es_parteix() -> None:
    assert parteix_club("QUALSEVOL, U C.B.INVENTAT", CENS) is None


def test_una_linia_sense_nom_de_jugador_tampoc() -> None:
    assert parteix_club("C.B.BANYOLES", CENS) is None


def test_el_club_es_torna_amb_el_nom_del_cens_i_no_el_del_pdf() -> None:
    """El PDF escriu «S.B.LA UNIÓ CORAL» i el cens en diu «B.LA UNIÓ CORAL»."""
    cens = _cens(("S.B.LA UNIÓ CORAL", "B.LA UNIÓ CORAL"))
    assert parteix_club("SÁNCHEZ TRIGUEROS, CARLESS.B.LA UNIÓ CORAL", cens) == (
        "SÁNCHEZ TRIGUEROS, CARLES",
        "B.LA UNIÓ CORAL",
    )
