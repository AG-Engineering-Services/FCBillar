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


def test_un_sol_cognom_queda_marcat_com_a_tal():
    trobats = candidats(_rfeb("Sergio Martínez"), _cens("MARTÍNEZ AVILÉS, SERGIO"))
    assert [c.motiu for c in trobats] == ["un cognom"]


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


def _motius(trobats: list[Candidat]) -> list[tuple[str, str]]:
    return [(c.cens.nom, c.motiu) for c in trobats]


def test_cognom_abreujat():
    cens = _cens("SÁNCHEZ FERNÁNDEZ, JORGE JUAN")
    assert _motius(candidats(_rfeb("Jorge J. Sánchez Fdez."), cens)) == [
        ("SÁNCHEZ FERNÁNDEZ, JORGE JUAN", "abreujat")
    ]


def test_una_lletra_de_diferencia_en_un_cognom_llarg():
    cens = _cens("GALLÉN NÁCHER, JESÚS")
    assert _motius(candidats(_rfeb("Jesús Gallén Naches"), cens)) == [
        ("GALLÉN NÁCHER, JESÚS", "falta")
    ]


def test_una_lletra_en_un_cognom_curt_no_val():
    assert candidats(_rfeb("Pere Gil Puig"), _cens("GILI PUIG, PERE")) == []


def test_un_sol_cognom_si_al_cens_no_n_hi_ha_cap_altre():
    cens = _cens("MAS CANADELL, JOSEP Mª", "MAS CANADELL, CÉSAR")
    assert _motius(candidats(_rfeb("José Mª Mas"), cens)) == [
        ("MAS CANADELL, JOSEP Mª", "un cognom")
    ]


def test_un_sol_cognom_ambigu_no_es_proposa():
    cens = _cens("MARTÍNEZ AVILÉS, SERGIO", "MARTÍNEZ PUIG, SERGI")
    assert candidats(_rfeb("Sergio Martínez"), cens) == []


def test_dos_cognoms_que_no_casen_no_es_llegeixen_com_un_de_sol():
    assert candidats(_rfeb("Juan Pérez López"), _cens("LÓPEZ GARCIA, JUAN")) == []


def test_si_n_hi_ha_un_d_exacte_no_es_busquen_variants():
    cens = _cens("PUIG FERRER, JOAN", "PUIG FERRES, JOAN")
    assert _motius(candidats(_rfeb("Joan Puig Ferrer"), cens)) == [
        ("PUIG FERRER, JOAN", "exacte"),
        ("PUIG FERRES, JOAN", "falta"),
    ]
