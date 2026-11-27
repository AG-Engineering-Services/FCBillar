from fcbillar import avisos
from fcbillar.avisos import Resultat, missatges, resultats_opens


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


def _open(div, nom, modalitat, partides, clubs):
    return {
        "fcb_division_id": div,
        "name": nom,
        "modality": modalitat,
        "payload_json": {
            "classification": [{"player_name": n, "club": c} for n, c in clubs.items()],
            "phases": [
                {
                    "label": "PRÈVIA",
                    "groups": [{"label": "Grup A", "matches": partides}],
                    "ko_matches": [],
                }
            ],
        },
    }


CLUBS = {
    "GARRIGA COMAS, JORDI": "C.B.SANT ADRIÀ",
    "MAS CANADELL, JOSEP": "C.B.LLINARS",
    "GÓMEZ AMETLLER, ALBERT": "C.B.BANYOLES",
    "PUIG SOLER, JOAN": "C.B.SANTS",
}


def test_opens_3b_inclou_les_acabades_i_marca_el_banyoles():
    fila = _open(
        223,
        "OPEN TRES BANDES SANT ADRIA",
        "Tres Bandes",
        [
            _partida("GARRIGA COMAS, JORDI", "MAS CANADELL, JOSEP", 30, 25),
            _partida("GÓMEZ AMETLLER, ALBERT", "PUIG SOLER, JOAN", 22, 30, pa=0, pb=2),
            _partida("GARRIGA COMAS, JORDI", "PUIG SOLER, JOAN", 0, 0, jugada=False),  # pendent
        ],
        CLUBS,
    )
    rs = resultats_opens([fila])
    assert len(rs) == 2
    assert all("opens_3b" in r.tipus for r in rs)
    nostra = [r for r in rs if r.destacat]
    assert len(nostra) == 1 and "banyoles_opens" in nostra[0].tipus
    assert nostra[0].linia == "Grup A: Gómez Ametller 22-30 Puig Soler (30 e.)"
    assert nostra[0].url == "/opens/directe/223"


def test_opens_d_altres_modalitats_nomes_si_hi_juga_el_banyoles():
    fila = _open(
        300,
        "OPEN BANDA GRANOLLERS",
        "Banda",
        [
            _partida("GARRIGA COMAS, JORDI", "MAS CANADELL, JOSEP", 30, 25),
            _partida("GÓMEZ AMETLLER, ALBERT", "PUIG SOLER, JOAN", 22, 30),
        ],
        CLUBS,
    )
    rs = resultats_opens([fila])
    assert [r.tipus for r in rs] == [frozenset({"banyoles_opens"})]


def test_la_clau_no_depen_de_l_ordre_dels_jugadors():
    a = resultats_opens([_open(1, "OPEN 3 BANDES X", None, [_partida("A, X", "B, Y", 1, 2)], {})])
    b = resultats_opens([_open(1, "OPEN 3 BANDES X", None, [_partida("B, Y", "A, X", 2, 1)], {})])
    assert a[0].clau == b[0].clau


def _r(clau, tipus, grup="g", destacat=False, ordre=0):
    return Resultat(clau, frozenset(tipus), grup, "Títol", f"línia {clau}", "/u", destacat, ordre)


def test_missatges_filtra_per_tipus_i_agrupa():
    nous = [
        _r("1", {"opens_3b"}, "open:1", ordre=1),
        _r("2", {"opens_3b", "banyoles_opens"}, "open:1", destacat=True, ordre=2),
        _r("3", {"banyoles_lliga"}, "lliga"),
    ]
    nomes_banyoles = missatges(["banyoles_opens"], nous)
    assert len(nomes_banyoles) == 1
    assert nomes_banyoles[0]["body"] == "línia 2"  # sense estrella si és sol

    tots = missatges(list(avisos.TIPUS), nous)
    assert len(tots) == 2
    open_ = next(m for m in tots if "2 resultats" in m["title"])
    assert open_["body"].splitlines() == ["★ línia 2", "línia 1"]  # el Banyoles al davant


def test_missatges_retalla_les_llargues():
    nous = [_r(str(i), {"opens_3b"}, ordre=i) for i in range(20)]
    (m,) = missatges(["opens_3b"], nous)
    linies = m["body"].splitlines()
    assert len(linies) == avisos.LINIES_PER_MISSATGE
    assert linies[-1] == "i 13 més"


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


def test_primera_passada_no_envia_i_despres_nomes_el_nou(monkeypatch):
    enviats = []
    monkeypatch.setattr(avisos, "_envia_un", lambda sub, m, clau: enviats.append(m) or None)
    db = _Db([{"endpoint": "https://p/1", "p256dh": "x", "auth": "y", "tipus": ["opens_3b"]}])

    def log(*_):
        return None

    vells = [_r("a", {"opens_3b"}), _r("b", {"opens_3b"})]

    c = avisos._avisa(db, "opens", vells, log, max_nous=None, clau_privada="k")
    assert c["avisos_enviats"] == 0 and enviats == []

    c = avisos._avisa(
        db, "opens", [*vells, _r("c", {"opens_3b"})], log, max_nous=None, clau_privada="k"
    )
    assert c["avisos_nous"] == 1 and len(enviats) == 1

    c = avisos._avisa(
        db, "opens", [*vells, _r("c", {"opens_3b"})], log, max_nous=None, clau_privada="k"
    )
    assert c["avisos_nous"] == 0 and len(enviats) == 1


def test_massa_nous_de_cop_es_marquen_sense_enviar(monkeypatch):
    enviats = []
    monkeypatch.setattr(avisos, "_envia_un", lambda sub, m, clau: enviats.append(m) or None)
    db = _Db([{"endpoint": "https://p/1", "p256dh": "x", "auth": "y", "tipus": ["banyoles_lliga"]}])
    db.enviats.add("base:reingesta")
    molts = [_r(str(i), {"banyoles_lliga"}) for i in range(50)]
    avisos._avisa(db, "reingesta", molts, lambda *_: None, max_nous=40, clau_privada="k")
    assert enviats == [] and "49" in db.enviats


def test_subscripcio_caducada_es_retira(monkeypatch):
    monkeypatch.setattr(avisos, "_envia_un", lambda *_: 410)
    db = _Db([{"endpoint": "https://p/1", "p256dh": "x", "auth": "y", "tipus": ["opens_3b"]}])
    db.enviats.add("base:opens")
    avisos._avisa(
        db, "opens", [_r("z", {"opens_3b"})], lambda *_: None, max_nous=None, clau_privada="k"
    )
    assert db.subs == []


def test_sense_clau_vapid_no_marca_res(monkeypatch):
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    db = _Db([])
    avisos._avisa(
        db, "opens", [_r("a", {"opens_3b"})], lambda *_: None, max_nous=None, clau_privada=None
    )
    assert db.enviats == set()


def test_la_clau_no_porta_caracters_que_trenquen_el_filtre_in():
    r = Resultat('copa:1:2:C.B.BLANES "B"|C.B.BANYOLES (A), x', frozenset(), "g", "t", "l", "/")
    assert r.clau == "copa:1:2:C.B.BLANES B|C.B.BANYOLES A x"


# --- Jugadors seguits ------------------------------------------------------------


def test_opens_d_altres_modalitats_pels_jugadors_seguits():
    fila = _open(
        400,
        "OPEN LLIURE PUNT D'ATAC",
        "Lliure",
        [
            _partida("GARRIGA COMAS, JORDI", "MAS CANADELL, JOSEP", 30, 25),
            _partida("PUIG SOLER, JOAN", "MAS CANADELL, JOSEP", 30, 25),
        ],
        CLUBS,
    )
    fila["payload_json"]["player_ids"] = {"GARRIGA COMAS, JORDI": 11, "MAS CANADELL, JOSEP": 22}
    assert resultats_opens([fila]) == []
    rs = resultats_opens([fila], seguits={"11"})
    assert len(rs) == 1 and rs[0].tipus == frozenset() and rs[0].jugadors == {"11"}


def test_missatges_dels_seguits_nomes_amb_el_tipus_marcat():
    r = _r("x", set())
    r.jugadors = frozenset({"11"})
    assert missatges(["opens_3b"], [r], {"11"}) == []
    (m,) = missatges(["jugadors_seguits"], [r], {"11"})
    assert m["body"] == "línia x"
    assert missatges(["jugadors_seguits"], [r], {"99"}) == []


def test_un_jugador_que_es_comenca_a_seguir_no_envia_el_que_ja_ha_jugat(monkeypatch):
    enviats = []
    monkeypatch.setattr(avisos, "_envia_un", lambda sub, m, clau: enviats.append(m) or None)
    sub = {
        "endpoint": "https://p/1",
        "p256dh": "x",
        "auth": "y",
        "tipus": ["jugadors_seguits"],
        "jugadors": ["11"],
    }
    db = _Db([sub])
    db.enviats.add("base:reingesta")

    def de(clau):
        r = _r(clau, set())
        r.jugadors = frozenset({"11"})
        return r

    def log(*_):
        return None

    avisos._avisa(db, "reingesta", lambda s: [de("vella")], log, max_nous=40, clau_privada="k")
    assert enviats == [] and "base:reingesta:jugador:11" in db.enviats

    avisos._avisa(
        db, "reingesta", lambda s: [de("vella"), de("nova")], log, max_nous=40, clau_privada="k"
    )
    assert len(enviats) == 1 and enviats[0]["body"] == "línia nova"


def test_els_noms_mal_codificats_casen_amb_els_bons():
    assert avisos.arregla_codificacio("LE\xc3“N PUIG, ESTEBAN") == "LEÓN PUIG, ESTEBAN"
    assert avisos.arregla_codificacio("RODR\xc3\udc8dGUEZ MAIA") == "RODRÍGUEZ MAIA"
    assert avisos.arregla_codificacio("GÓMEZ AMETLLER, ALBERT") == "GÓMEZ AMETLLER, ALBERT"
    assert avisos._norm("LE\xc3“N PUIG, ESTEBAN") == avisos._norm("LEÓN PUIG, ESTEBAN")
