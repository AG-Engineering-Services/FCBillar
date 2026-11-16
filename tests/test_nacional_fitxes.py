from fcbillar.nacional_fitxes import Candidat, JugadorCens, JugadorRfeb, candidats


def _cens(*noms: str) -> list[JugadorCens]:
    return [JugadorCens(fcb_id=str(i), nom=n, club="C.B.X") for i, n in enumerate(noms)]


def _rfeb(nom: str) -> list[JugadorRfeb]:
    return [JugadorRfeb(nom=nom, equip="EQUIP", divisio="honor")]


def _ids(trobats: list[Candidat]) -> list[str]:
    return [c.cens.nom for c in trobats]


def test_nom_castella_contra_nom_catala():
    trobats = candidats(_rfeb("José Mª Mas Canadell"), _cens("MAS CANADELL, JOSEP Mª"))
    assert _ids(trobats) == ["MAS CANADELL, JOSEP Mª"]


def test_mateix_nom_sense_accents():
    trobats = candidats(_rfeb("Jordi Garriga Comas"), _cens("GARRIGA COMAS, JORDI"))
    assert len(trobats) == 1


def test_un_sol_cognom_no_val():
    assert candidats(_rfeb("Sergio Martínez"), _cens("MARTÍNEZ AVILÉS, SERGIO")) == []


def test_cognoms_iguals_i_nom_diferent_no_val():
    assert candidats(_rfeb("César Mas Canadell"), _cens("MAS CANADELL, JOSEP Mª")) == []


def test_cognoms_que_no_quadren_no_val():
    cens = _cens("HERNÁNDEZ SÁNCHEZ, FRANCISCO")
    assert candidats(_rfeb("Francisco Hernández Hernández"), cens) == []


def test_inicial_del_segon_nom():
    cens = _cens("PARERAS MÉNDEZ, JUAN CARLOS")
    assert len(candidats(_rfeb("Juan C. Pareras Méndez"), cens)) == 1
    assert candidats(_rfeb("Juan J. Pareras Méndez"), cens) == []


def test_segon_nom_que_nomes_te_un_dels_dos():
    assert len(candidats(_rfeb("Carlos Chacón López"), _cens("CHACÓN LÓPEZ, CARLOS J."))) == 1


def test_cognom_amb_guionet():
    cens = _cens("SAINZ-PARDO PRADO, DANIEL")
    assert len(candidats(_rfeb("Daniel Sainz-Pardo Prado"), cens)) == 1


def test_homonims_surten_tots():
    cens = _cens("PUIG FERRER, JOAN", "PUIG FERRER, JUAN")
    assert len(candidats(_rfeb("Juan Puig Ferrer"), cens)) == 2
