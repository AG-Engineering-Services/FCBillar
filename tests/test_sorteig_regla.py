"""La regla del sorteig, lligada a la fase que toca i llegida com està escrita.

Dos errors que es tapaven l'un a l'altre, i que van deixar la prèvia de 1a de
2026-27 amb 13 places on n'hi ha 7:

El PDF de la PRE-prèvia també casava amb la fase «PRÈVIA» —«PRE PREVIA» conté la
paraula «PREVIA»— i hi escrivia la seva regla, amb les places calculades amb els
grups de la prèvia. Normalment no es veia, perquè després el PDF de la prèvia ho
trepitjava amb la bona.

Però la regla de la prèvia de 1a no es va saber llegir: diu «e primer de cada
grup, el millor segon», amb l'article mal escrit i un «millor» en singular. Com
que una regla il·legible se saltava, el número equivocat s'hi va quedar.
"""

from __future__ import annotations

import pytest

from fcbillar.sorteig_fase import casa_amb_fase, classificats

PRE = "Pre-Prèvies 3 bandes 1a Divisió"
PREVIA = "Prèvies 3 bandes 1a Divisió"
DIVISIO = "1A DIVISIÓ"


def test_el_pdf_de_la_pre_previa_no_casa_amb_la_previa() -> None:
    assert casa_amb_fase(PRE, DIVISIO, "PRE-PRÈVIA")
    assert not casa_amb_fase(PRE, DIVISIO, "PRÈVIA")


def test_el_pdf_de_la_previa_nomes_casa_amb_la_previa() -> None:
    assert casa_amb_fase(PREVIA, DIVISIO, "PRÈVIA")
    assert not casa_amb_fase(PREVIA, DIVISIO, "PRE-PRÈVIA")


def test_amb_tres_rondes_cada_pdf_va_a_la_seva() -> None:
    titol = "Pre-Pre-Prèvies Q 47/2 4a Divisió"
    casen = [
        casa_amb_fase(titol, "4A DIVISIÓ", f) for f in ("PRE-PRE-PRÈVIA", "PRE-PRÈVIA", "PRÈVIA")
    ]
    assert casen == [True, False, False]


@pytest.mark.parametrize(
    ("regla", "grups", "places"),
    [
        # La prèvia de 1a de 2026-27, tal com és al PDF, amb l'errada i tot. El
        # jugador del club organitzador entra a la final sense passar pels grups
        # i no és cap plaça d'aquesta fase.
        (
            "Es classificaran per a la prèvia, e primer de cada grup, el millor segon "
            "i Melchor Martín del club organitzador .",
            6,
            7,
        ),
        ("el primer de cada grup i els quatre millors segons.", 14, 18),
        ("els primers de cada grup i els set millors segons", 11, 18),
        ("els dos primers de cada grup", 4, 8),
    ],
)
def test_les_places_que_surten_de_cada_regla(regla: str, grups: int, places: int) -> None:
    llegida = classificats(regla)
    assert llegida is not None
    assert llegida.places(grups) == places


def test_una_regla_que_no_parla_de_grups_no_s_inventa() -> None:
    assert classificats("passen els classificats") is None
    assert classificats(None) is None
