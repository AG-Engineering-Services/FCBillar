from fcbillar import avisos
from fcbillar.avisos import Equips, Resultat, missatges, resultats_opens, seguits_de


def _partida(a, b, ca, cb, *, jugada=True, pa=2, pb=0, entrades=30):
    return {
        "player_a": a,
        "player_b": b,
        "caramboles_a": ca,
        "caramboles_b": cb,
        "punts_a": pa if jugada else 0,
        "punts_b": pb if jugada else 0,
        "entrades": entrades,
        "is_played": jugada,
    }


def _open(div, nom, modalitat, partides, ids=None):
    return {
        "fcb_division_id": div,
        "name": nom,
        "modality": modalitat,
        "payload_json": {
            "player_ids": ids or {},
            "phases": [
                {
                    "label": "PRÈVIA",
                    "groups": [{"label": "Grup A", "matches": partides}],
                    "ko_matches": [],
                }
            ],
        },
    }


IDS = {"GARRIGA COMAS, JORDI": 11, "MAS CANADELL, JOSEP": 22, "GÓMEZ AMETLLER, ALBERT": 278}


# --- Opens ----------------------------------------------------------------------


def test_opens_3b_totes_les_acabades():
    fila = _open(
        223,
        "OPEN TRES BANDES SANT ADRIA",
        "Tres Bandes",
        [
            _partida("GARRIGA COMAS, JORDI", "MAS CANADELL, JOSEP", 30, 25),
            _partida("GÓMEZ AMETLLER, ALBERT", "MAS CANADELL, JOSEP", 22, 30, pa=0, pb=2),
            _partida("GARRIGA COMAS, JORDI", "GÓMEZ AMETLLER, ALBERT", 0, 0, jugada=False),
        ],
        IDS,
    )
    rs = resultats_opens([fila])
    assert len(rs) == 2 and all(r.tipus == {"opens_3b"} for r in rs)
    assert rs[1].linia == "Grup A: Gómez Ametller 22-30 Mas Canadell (30 e.)"
    assert rs[1].url == "/opens/directe/223"


def test_opens_d_altres_modalitats_pels_jugadors_o_l_open_seguits():
    fila = _open(
        400,
        "OPEN LLIURE PUNT D'ATAC",
        "Lliure",
        [
            _partida("GARRIGA COMAS, JORDI", "MAS CANADELL, JOSEP", 30, 25),
            _partida("GÓMEZ AMETLLER, ALBERT", "MAS CANADELL, JOSEP", 30, 25),
        ],
        IDS,
    )
    assert resultats_opens([fila]) == []
    rs = resultats_opens([fila], {"j:278"})
    assert len(rs) == 1 and rs[0].tipus == frozenset() and rs[0].seguiments == {"j:278"}
    assert len(resultats_opens([fila], {"o:400"})) == 2


def test_la_clau_no_depen_de_l_ordre_dels_jugadors():
    a = resultats_opens([_open(1, "OPEN 3 BANDES X", None, [_partida("A, X", "B, Y", 1, 2)])])
    b = resultats_opens([_open(1, "OPEN 3 BANDES X", None, [_partida("B, Y", "A, X", 2, 1)])])
    assert a[0].clau == b[0].clau


# --- Clubs i equips ---------------------------------------------------------------


def test_equips_dels_clubs_i_equips_seguits():
    qui = Equips(
        ["C.B.BANYOLES", "C.B.SANT ADRIÀ"],
        ['C.B.SANTS "A"'],
        {"CBLLICAA": "C.B. LLIÇÀ"},
    )
    assert qui.seguiments("C.B. BANYOLES B") == {"c:C.B.BANYOLES"}
    assert qui.seguiments("C.B.SANT ADRIA A") == {"c:C.B.SANT ADRIÀ"}
    assert qui.seguiments("C.B.SANTS A") == {'e:C.B.SANTS "A"'}
    assert qui.seguiments("C.B.SANTS B") == frozenset()
    # La federació diu que és d'un club que no se segueix: no casa pel nom.
    assert qui.seguiments("C.B. LLIÇÀ A") == frozenset()


def test_seguits_de_nomes_compta_els_tipus_marcats():
    sub = {"tipus": ["clubs_seguits"], "seguiments": ["c:X", "e:X A", "j:1", "o:2"]}
    assert seguits_de(sub) == {"c:X", "e:X A"}
    assert seguits_de({"tipus": ["opens_3b"], "seguiments": ["j:1"]}) == set()


# --- Missatges ------------------------------------------------------------------


def _r(clau, tipus=(), grup="g", ordre=0, seguiments=()):
    return Resultat(
        clau,
        frozenset(tipus),
        grup,
        "Títol",
        f"línia {clau}",
        "/u",
        ordre,
        frozenset(seguiments),
    )


def test_missatges_filtra_per_tipus_i_seguiments_i_agrupa():
    nous = [
        _r("1", {"opens_3b"}, "open:1", ordre=1),
        _r("2", {"opens_3b"}, "open:1", ordre=2, seguiments={"j:278"}),
        _r("3", (), "lliga", seguiments={"c:C.B.BANYOLES"}),
    ]
    nomes_jugador = missatges(["jugadors_seguits"], nous, {"j:278"})
    assert [m["body"] for m in nomes_jugador] == ["línia 2"]  # sense estrella si és sol

    tots = missatges(list(avisos.TIPUS), nous, {"j:278", "c:C.B.BANYOLES"})
    assert len(tots) == 2
    open_ = next(m for m in tots if "2 resultats" in m["title"])
    assert open_["body"].splitlines() == ["★ línia 2", "línia 1"]  # el seguit al davant


def test_seguir_un_open_no_destaca_cap_linia():
    nous = [_r(str(i), (), "open:9", ordre=i, seguiments={"o:9"}) for i in range(3)]
    (m,) = missatges(["opens_seguits"], nous, {"o:9"})
    assert "★" not in m["body"]


def test_missatges_retalla_les_llargues():
    nous = [_r(str(i), {"opens_3b"}, ordre=i) for i in range(20)]
    (m,) = missatges(["opens_3b"], nous)
    linies = m["body"].splitlines()
    assert len(linies) == avisos.LINIES_PER_MISSATGE
    assert linies[-1] == "i 13 més"


def test_la_clau_no_porta_caracters_que_trenquen_el_filtre_in():
    r = Resultat('copa:1:2:C.B.BLANES "B"|C.B.BANYOLES (A), x', frozenset(), "g", "t", "l", "/")
    assert r.clau == "copa:1:2:C.B.BLANES B|C.B.BANYOLES A x"


def test_els_noms_mal_codificats_casen_amb_els_bons():
    assert avisos.arregla_codificacio("LE\xc3“N PUIG, ESTEBAN") == "LEÓN PUIG, ESTEBAN"
    assert avisos.arregla_codificacio("RODR\xc3\udc8dGUEZ MAIA") == "RODRÍGUEZ MAIA"
    assert avisos.arregla_codificacio("GÓMEZ AMETLLER, ALBERT") == "GÓMEZ AMETLLER, ALBERT"
    assert avisos._norm("LE\xc3“N PUIG, ESTEBAN") == avisos._norm("LEÓN PUIG, ESTEBAN")


# --- El flux sencer, amb un client fals -----------------------------------------


class _Consulta:
    def __init__(self, db, taula):
        self.db, self.taula, self.op, self.filtre = db, taula, "select", None

    def select(self, *_):
        return self

    def in_(self, _col, valors):
        self.filtre = set(valors)
        return self

    def neq(self, *_):
        return self

    def eq(self, _col, valor):
        self.filtre = {valor}
        return self

    def upsert(self, files, **_):
        self.op, self.files = "upsert", files
        return self

    def delete(self, **_):
        self.op = "delete"
        return self

    def execute(self):
        class R:
            data = None

        r = R()
        if self.taula == "avisos_enviats":
            if self.op == "upsert":
                self.db.enviats.update(f["clau"] for f in self.files)
            else:
                r.data = [{"clau": c} for c in self.db.enviats & self.filtre]
        elif self.taula == "push_subscripcions":
            if self.op == "delete":
                self.db.subs = [s for s in self.db.subs if s["endpoint"] not in self.filtre]
            else:
                r.data = list(self.db.subs)
        return r


class _Db:
    def __init__(self, subs):
        self.enviats: set[str] = set()
        self.subs = subs

    def table(self, nom):
        return _Consulta(self, nom)


def _sub(tipus, seguiments=()):
    return {
        "endpoint": "https://p/1",
        "p256dh": "x",
        "auth": "y",
        "tipus": tipus,
        "seguiments": list(seguiments),
    }


def _log(*_):
    return None


def test_primera_passada_no_envia_i_despres_nomes_el_nou(monkeypatch):
    enviats = []
    monkeypatch.setattr(avisos, "_envia_un", lambda sub, m, clau: enviats.append(m) or None)
    db = _Db([_sub(["opens_3b"])])
    vells = [_r("a", {"opens_3b"}), _r("b", {"opens_3b"})]

    c = avisos._avisa(db, "opens", vells, _log, max_nous=None, clau_privada="k")
    assert c["avisos_enviats"] == 0 and enviats == []

    nous = [*vells, _r("c", {"opens_3b"})]
    c = avisos._avisa(db, "opens", nous, _log, max_nous=None, clau_privada="k")
    assert c["avisos_nous"] == 1 and len(enviats) == 1

    c = avisos._avisa(db, "opens", nous, _log, max_nous=None, clau_privada="k")
    assert c["avisos_nous"] == 0 and len(enviats) == 1


def test_massa_nous_de_cop_es_marquen_sense_enviar(monkeypatch):
    enviats = []
    monkeypatch.setattr(avisos, "_envia_un", lambda sub, m, clau: enviats.append(m) or None)
    db = _Db([_sub(["opens_3b"])])
    db.enviats.add("base:reingesta")
    molts = [_r(str(i), {"opens_3b"}) for i in range(50)]
    avisos._avisa(db, "reingesta", molts, _log, max_nous=40, clau_privada="k")
    assert enviats == [] and "49" in db.enviats


def test_subscripcio_caducada_es_retira(monkeypatch):
    monkeypatch.setattr(avisos, "_envia_un", lambda *_: 410)
    db = _Db([_sub(["opens_3b"])])
    db.enviats.add("base:opens")
    avisos._avisa(db, "opens", [_r("z", {"opens_3b"})], _log, max_nous=None, clau_privada="k")
    assert db.subs == []


def test_sense_clau_vapid_no_marca_res(monkeypatch):
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    db = _Db([])
    avisos._avisa(db, "opens", [_r("a", {"opens_3b"})], _log, max_nous=None, clau_privada=None)
    assert db.enviats == set()


def test_un_seguiment_nou_no_envia_el_que_ja_s_ha_jugat(monkeypatch):
    enviats = []
    monkeypatch.setattr(avisos, "_envia_un", lambda sub, m, clau: enviats.append(m) or None)
    db = _Db([_sub(["clubs_seguits"], ["c:C.B.BANYOLES"])])
    db.enviats.add("base:reingesta")

    def de(clau):
        return _r(clau, (), "lliga", seguiments={"c:C.B.BANYOLES"})

    avisos._avisa(db, "reingesta", lambda s: [de("vell")], _log, max_nous=40, clau_privada="k")
    assert enviats == [] and "base:reingesta:c:C.B.BANYOLES" in db.enviats

    avisos._avisa(
        db, "reingesta", lambda s: [de("vell"), de("nou")], _log, max_nous=40, clau_privada="k"
    )
    assert len(enviats) == 1 and enviats[0]["body"] == "línia nou"


def test_la_funcio_rep_els_seguiments_dels_tipus_marcats(monkeypatch):
    monkeypatch.setattr(avisos, "_envia_un", lambda *_: None)
    db = _Db([_sub(["jugadors_seguits"], ["j:1", "c:X", "o:5"])])
    vist = {}

    def fes(seguits):
        vist["s"] = seguits
        return []

    avisos._avisa(db, "opens", fes, _log, max_nous=None, clau_privada="k")
    assert vist["s"] == {"j:1"}
