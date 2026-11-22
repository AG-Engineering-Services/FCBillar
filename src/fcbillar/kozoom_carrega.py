"""Baixada (del Wayback) i càrrega a la BBDD local de les proves de Kozoom.

La carpeta de cache té:

- `proves.json`: l'inventari de proves arxivades (id, títol i la còpia més nova
  de `rankings.html` i `matches.html`);
- `jugadors.json`: per a cada prova, les còpies de les pàgines de partides dels
  seus jugadors (`players/…/matches.html?event_id=…`);
- `{id}_rankings.html`, `{id}_matches.html` i `jugadors/{id}/*.html`.

Només es carreguen les proves que interessen: les internacionals (copes i
campionats del món i d'Europa, grans premis, masters) i qualsevol altra on
hagi jugat algú d'Espanya. Les lligues i campionats nacionals d'altres països
sense cap jugador d'aquí es deixen.

Una prova que la UMB o la CEB ja tenen amb partides no es torna a carregar. Si
la tenen només amb la classificació (sense PDF de partides), les partides de
Kozoom s'afegeixen a aquella prova i la classificació oficial es manté.
Per això, si es torna a carregar la UMB, s'ha de tornar a carregar Kozoom.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx

from fcbillar.kozoom import (
    DESPLACAMENT,
    Titol,
    de_les_pagines_de_jugador,
    llegeix_classificacio,
    llegeix_partides,
    llegeix_titol,
)
from fcbillar.umb import Llegit
from fcbillar.umb_carrega import (
    Resultat,
    _hereta_ids,
    desa_esdeveniment,
    disciplina_de,
    esborra_esdeveniment,
)
from fcbillar.umb_descarrega import Esdeveniment

WAYBACK = "http://web.archive.org"
_CDX_JUGADORS = (
    WAYBACK + "/cdx/search/cdx?url=www.kozoom.com/en/billiard-carom/players/*"
    "&fl=timestamp,original&filter=statuscode:200&limit=200000"
)
_INTERNACIONAL = re.compile(
    r"world|europ|grand prix|masters|cup|survival|spain|spanish|españa|copa", re.I
)


def _get(c: httpx.Client, url: str, intents: int = 4) -> str:
    for i in range(intents):
        try:
            r = c.get(url)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return ""
        except httpx.HTTPError:
            pass
        time.sleep(3 * (i + 1))
    return ""


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (fcbillar recerca)"}, timeout=90, follow_redirects=True
    )


def indexa_jugadors(cache: Path) -> dict[str, list[list[str]]]:
    """Les còpies de les pàgines de partides de cada jugador, agrupades per prova."""
    with _client() as c:
        text = _get(c, _CDX_JUGADORS)
    per_prova: dict[str, dict[str, list[str]]] = {}
    for linia in text.splitlines():
        parts = linia.split()
        if len(parts) < 2:
            continue
        ts, url = parts
        m = re.search(r"/players/([^/]+)/matches\.html\?event_id=(\d+)", url)
        if not m:
            continue
        jugador, prova = m.groups()
        actual = per_prova.setdefault(prova, {}).get(jugador)
        if actual is None or ts > actual[0]:
            per_prova[prova][jugador] = [ts, url]
    out = {p: sorted(js.values(), key=lambda v: v[1]) for p, js in per_prova.items()}
    (cache / "jugadors.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


_CDX_PROVES = (
    WAYBACK + "/cdx/search/cdx?url=www.kozoom.com/en/billiard-carom/results/*"
    "&fl=timestamp,original&filter=statuscode:200&limit=20000"
)


def inventaria(cache: Path, espera: float = 1.0, id_max: int | None = None) -> dict[str, dict]:
    """Totes les proves arxivades: en baixa la classificació (o les partides) i en desa el títol.

    Triga hores (una pàgina per prova); es pot aturar i reprendre, perquè desa
    sovint i no torna a baixar el que ja té. Amb `id_max` només s'arriba fins a
    aquell id (els de Kozoom van creixent amb el temps: el 17000 és del 2016).
    """
    cache.mkdir(parents=True, exist_ok=True)
    sortida = cache / "proves.json"
    fetes = json.loads(sortida.read_text(encoding="utf-8")) if sortida.exists() else {}
    with _client() as c:
        proves: dict[str, dict] = {}
        for linia in _get(c, _CDX_PROVES).splitlines():
            parts = linia.split()
            m = (
                re.search(r"/results/(\d+)/(rankings|matches)\.html", parts[1])
                if len(parts) > 1
                else None
            )
            if not m:
                continue
            p = proves.setdefault(m.group(1), {"id": m.group(1)})
            if parts[0] > p.get(f"ts_{m.group(2)}", ""):
                p[f"ts_{m.group(2)}"], p[f"url_{m.group(2)}"] = parts[0], parts[1]
        for n, (pid, p) in enumerate(sorted(proves.items(), key=lambda kv: int(kv[0]))):
            if fetes.get(pid, {}).get("titol") or (id_max is not None and int(pid) > id_max):
                continue
            clau = "rankings" if "url_rankings" in p else "matches"
            html = _get(c, f"{WAYBACK}/web/{p['ts_' + clau]}id_/{p['url_' + clau]}")
            (cache / f"{pid}_{clau}.html").write_text(html, encoding="utf-8")
            t = re.search(r"<title>([^<]*)", html)
            p["titol"] = t.group(1).strip() if t else ""
            fetes[pid] = p
            if n % 25 == 0:
                sortida.write_text(
                    json.dumps(fetes, ensure_ascii=False, indent=1), encoding="utf-8"
                )
            time.sleep(espera)
    sortida.write_text(json.dumps(fetes, ensure_ascii=False, indent=1), encoding="utf-8")
    return fetes


def _proves(cache: Path) -> dict[str, dict]:
    return json.loads((cache / "proves.json").read_text(encoding="utf-8"))


def interessa(titol: Titol | None, nacionalitats: set[str | None]) -> bool:
    if titol is None:
        return False
    return "ES" in nacionalitats or bool(_INTERNACIONAL.search(titol.nom))


def seleccio(cache: Path) -> list[str]:
    """Els ids de les proves de l'inventari que s'han de carregar.

    Si el títol ja és d'una prova internacional no cal mirar la classificació
    (llegir-les totes costa minuts); només es mira per a les altres, a la
    recerca de jugadors d'Espanya.
    """
    triades = []
    for pid, p in _proves(cache).items():
        titol = llegeix_titol(p.get("titol", ""))
        if titol is None:
            continue
        if _INTERNACIONAL.search(titol.nom):
            triades.append(pid)
            continue
        f = cache / f"{pid}_rankings.html"
        if f.exists():
            _t, files, _j = llegeix_classificacio(f.read_text(encoding="utf-8"))
            if interessa(titol, {c.nacionalitat for c in files}):
                triades.append(pid)
    return sorted(triades, key=int)


def _ultima_pagina(html: str) -> int:
    """La pàgina més alta enllaçada des d'una pàgina de partides (`matches.html?page=N`)."""
    return max((int(n) for n in re.findall(r"matches\.html\?page=(\d+)", html)), default=1)


def _fitxers_de_partides(cache: Path, pid: str) -> list[Path]:
    """`{id}_matches.html` i les pàgines següents (`{id}_matches_p2.html`…), per ordre."""
    pags = [cache / f"{pid}_matches.html"] + sorted(
        cache.glob(f"{pid}_matches_p*.html"), key=lambda f: int(f.stem.rsplit("_p", 1)[1])
    )
    return [f for f in pags if f.exists()]


def descarrega(cache: Path, ids: list[str], espera: float = 1.0) -> dict[str, int]:
    """Baixa les partides de cada prova: totes les pàgines de `matches.html` (van de 32 en 32).

    Si en falta alguna pàgina, o la prova no en té, es baixen també les pàgines
    de partides dels jugadors, que les completen.
    """
    proves = _proves(cache)
    idx_f = cache / "jugadors.json"
    idx = (
        json.loads(idx_f.read_text(encoding="utf-8")) if idx_f.exists() else indexa_jugadors(cache)
    )
    compte = {"completes": 0, "amb_jugadors": 0, "res": 0}
    with _client() as c:
        for pid in ids:
            p = proves[pid]
            completa = False
            if "url_matches" in p:
                base = f"{WAYBACK}/web/{p['ts_matches']}id_/{p['url_matches']}"
                primera = cache / f"{pid}_matches.html"
                if not primera.exists() or primera.stat().st_size < 2000:
                    primera.write_text(_get(c, base), encoding="utf-8")
                    time.sleep(espera)
                html = primera.read_text(encoding="utf-8")
                completa = bool(llegeix_partides(html)[1])
                for n in range(2, _ultima_pagina(html) + 1):
                    f = cache / f"{pid}_matches_p{n}.html"
                    if not f.exists() or f.stat().st_size < 2000:
                        f.write_text(_get(c, f"{base}?page={n}"), encoding="utf-8")
                        time.sleep(espera)
                    if not llegeix_partides(f.read_text(encoding="utf-8"))[1]:
                        completa = False  # el Wayback no té aquella pàgina
            if completa:
                compte["completes"] += 1
                continue
            pagines = idx.get(pid, [])
            if not pagines:
                compte["res"] += 1
                continue
            carpeta = cache / "jugadors" / pid
            carpeta.mkdir(parents=True, exist_ok=True)
            for ts, url in pagines:
                nom = re.search(r"/players/([^/]+)/", url).group(1)
                f = carpeta / f"{nom}.html"
                if f.exists() and f.stat().st_size > 2000:
                    continue
                f.write_text(_get(c, f"{WAYBACK}/web/{ts}id_/{url}"), encoding="utf-8")
                time.sleep(espera)
            compte["amb_jugadors"] += 1
    return compte


def llegeix_prova(cache: Path, pid: str) -> tuple[Titol | None, Llegit]:
    """La classificació i totes les partides d'una prova.

    Les partides surten de totes les pàgines de `matches.html` i de les pàgines
    dels jugadors, si n'hi ha; una partida que surt a més d'un lloc es compta
    una sola vegada.
    """
    ll = Llegit()
    titol = None
    f = cache / f"{pid}_rankings.html"
    if f.exists():
        titol, ll.classificacio, ll.jugadors = llegeix_classificacio(f.read_text(encoding="utf-8"))
    pags = [x.read_text(encoding="utf-8") for x in _fitxers_de_partides(cache, pid)]
    if titol is None and pags:
        titol = llegeix_partides(pags[0])[0]
    if (carpeta := cache / "jugadors" / pid).is_dir():
        de_jugadors = [x.read_text(encoding="utf-8") for x in sorted(carpeta.glob("*.html"))]
        # La pàgina d'un jugador pot ser d'una altra prova (el Wayback a vegades
        # desa la del desplegable per defecte): només les que porten aquest títol.
        if titol:
            de_jugadors = [h for h in de_jugadors if (llegeix_partides(h)[0] or titol) == titol]
        pags += de_jugadors
    totes = de_les_pagines_de_jugador(pags)
    ll.partides = totes.partides
    noms = {j.nom for j in ll.jugadors}
    ll.jugadors += [j for j in totes.jugadors if j.nom not in noms]
    return titol, ll


def _mots(nom: str | None) -> set[str]:
    import unicodedata

    pla = unicodedata.normalize("NFKD", nom or "").encode("ascii", "ignore").decode().lower()
    return {m for m in re.findall(r"[a-z]+", pla) if len(m) > 2}


def _dia(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text[:10]) if text else None
    except ValueError:
        return None


class Firmes:
    """Les partides que ja hi ha (UMB, CEB, RFEB i Kozoom), per no desar-ne cap dues vegades.

    Una partida és la mateixa si té el mateix marcador i entrades, s'ha jugat en
    dates que encaixen i els dos jugadors comparteixen algun mot del nom (les
    fonts escriuen els noms de maneres diferents: «MATA Esteve», «Esteve Mata»,
    «MATA PARDO, Esteve»).
    """

    def __init__(self, conn: sqlite3.Connection, excepte: int | None = None) -> None:
        self._idx: dict[tuple, list[tuple]] = {}
        for ea, eb, ca, cb, ent, ini, fi, na, nb in conn.execute(
            "SELECT esdeveniment_id, 0, caramboles_a, caramboles_b, entrades_a, e.data_inici, "
            "e.data_fi, jugador_a, jugador_b FROM umb_partides p "
            "JOIN umb_esdeveniments e ON e.id = p.esdeveniment_id WHERE esdeveniment_id IS NOT ?",
            (excepte,),
        ):
            self._afegeix(ca, cb, ent, _dia(ini), _dia(fi) or _dia(ini), na, nb)
        for ca, cb, ent, d, ini, fi, temp, na, nb in conn.execute(
            "SELECT caramboles_a, caramboles_b, entrades, p.data, r.data_inici, r.data_fi, "
            "r.temporada, jugador_a, jugador_b FROM rfeb_partides p JOIN rfeb_proves r ON r.id = p.prova_id"
        ):
            if d or ini:
                de, fins = _dia(d) or _dia(ini), _dia(d) or _dia(fi) or _dia(ini)
            else:
                a = int(str(temp)[:4])
                de, fins = date(a, 8, 1), date(a + 1, 7, 31)
            self._afegeix(ca, cb, ent, de, fins, na, nb)

    def _afegeix(self, ca, cb, ent, de, fins, na, nb) -> None:
        if ca is None or cb is None:
            return
        clau = (min(ca, cb), max(ca, cb), ent)
        costats = (_mots(na), _mots(nb)) if ca <= cb else (_mots(nb), _mots(na))
        self._idx.setdefault(clau, []).append((de, fins, costats))

    def hi_es(self, p, de: date | None, fins: date | None) -> bool:
        ca, cb = p.a.caramboles, p.b.caramboles
        if ca is None or cb is None:
            return False
        clau = (min(ca, cb), max(ca, cb), p.a.entrades)
        costats = (_mots(p.a.jugador), _mots(p.b.jugador))
        if ca > cb:
            costats = costats[::-1]
        marge = timedelta(days=7)
        for d0, d1, (ma, mb) in self._idx.get(clau, []):
            if de and d0 and (d0 > (fins or de) + marge or (d1 or d0) < de - marge):
                continue
            noms = (ma & costats[0] and mb & costats[1]) or (
                ca == cb and ma & costats[1] and mb & costats[0]
            )
            if noms:
                return True
        return False

    def registra(self, p, de: date | None, fins: date | None) -> None:
        self._afegeix(
            p.a.caramboles, p.b.caramboles, p.a.entrades, de, fins, p.a.jugador, p.b.jugador
        )


def treu_repetides(firmes: Firmes, ll: Llegit, titol: Titol) -> int:
    """Treu de `ll` les partides que ja hi són per una altra font; torna quantes."""
    noves = []
    for p in ll.partides:
        if firmes.hi_es(p, titol.inici, titol.fi):
            continue
        firmes.registra(p, titol.inici, titol.fi)
        noves.append(p)
    tretes = len(ll.partides) - len(noves)
    ll.partides = noves
    return tretes


@dataclass
class Existent:
    id: int
    partides: int


def ja_hi_es(conn: sqlite3.Connection, titol: Titol) -> Existent | None:
    """La prova de la UMB o la CEB que és la mateixa: mateixa disciplina i dates (±4 dies)."""
    if titol.inici is None:
        return None
    disc = disciplina_de(titol.disciplina)
    marge = timedelta(days=4)
    for id_, ini, nom in conn.execute(
        "SELECT id, data_inici, nom FROM umb_esdeveniments WHERE id < ? AND disciplina IS ?",
        (DESPLACAMENT, disc),
    ):
        if not ini:
            continue
        try:
            d = date.fromisoformat(ini[:10])
        except ValueError:
            continue
        if abs(d - titol.inici) > marge:
            continue
        # Dues proves de la mateixa disciplina la mateixa setmana (copa del món i un
        # campionat nacional, per exemple): han de ser del mateix tipus.
        if _tipus(nom) != _tipus(titol.nom):
            continue
        n = conn.execute(
            "SELECT count(*) FROM umb_partides WHERE esdeveniment_id = ?", (id_,)
        ).fetchone()[0]
        return Existent(id_, n)
    return None


def _tipus(nom: str) -> str:
    n = nom.lower()
    # Primer el que distingeix proves que es juguen juntes (el femení, el júnior i el
    # d'equips solen compartir dates i lloc amb l'absolut).
    for k in (
        "team",
        "junior",
        "ladies",
        "women",
        "world cup",
        "world championship",
        "europ",
        "grand prix",
        "masters",
    ):
        if k in n:
            return k
    return n


def _afegeix_partides(conn: sqlite3.Connection, e_id: int, ll: Llegit) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO umb_jugadors (esdeveniment_id, nom, umb_id, nacionalitat) "
        "VALUES (?, ?, ?, ?)",
        [(e_id, j.nom, j.umb_id, j.nacionalitat) for j in ll.jugadors],
    )
    from fcbillar.umb import text_sets

    conn.executemany(
        "INSERT OR IGNORE INTO umb_partides (esdeveniment_id, fase, grup, ordre, jugador_a, "
        "caramboles_a, entrades_a, mitjana_a, punts_a, serie_a, serie2_a, jugador_b, "
        "caramboles_b, entrades_b, mitjana_b, punts_b, serie_b, serie2_b, nacio_a, nacio_b, "
        "sets_a, sets_b) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                e_id, p.fase, p.grup, p.ordre,
                p.a.jugador, p.a.caramboles, p.a.entrades, p.a.mitjana, p.a.punts, p.a.serie, p.a.serie2,
                p.b.jugador, p.b.caramboles, p.b.entrades, p.b.mitjana, p.b.punts, p.b.serie, p.b.serie2,
                p.a.nacio, p.b.nacio, text_sets(p.a.sets), text_sets(p.b.sets),
            )
            for p in ll.partides
        ],
    )  # fmt: skip


def falten_a(conn: sqlite3.Connection, firmes: Firmes, e_id: int, partides: list, titol: Titol) -> list:
    """Les partides de Kozoom que de debò no són a la prova `e_id`.

    Una partida que no ha coincidit pot ser que no hi sigui (un grup que el PDF de la
    UMB no porta) però també una mànega d'un partit a sets (Kozoom en dona el marcador
    de cada set) o un nom mal escrit a una de les dues fonts. Per això només es torna
    si la parella no ha jugat mai a la prova i cap partida amb el mateix marcador, en
    dates properes, no comparteix cap jugador.
    """
    parelles = [
        (_mots(a), _mots(b))
        for a, b in conn.execute(
            "SELECT jugador_a, jugador_b FROM umb_partides WHERE esdeveniment_id = ?", (e_id,)
        )
    ]
    marge = timedelta(days=7)
    noves = []
    for p in partides:
        ma, mb = _mots(p.a.jugador), _mots(p.b.jugador)
        if not ma or not mb or p.a.caramboles is None or p.b.caramboles is None:
            continue
        if any((x & ma and y & mb) or (x & mb and y & ma) for x, y in parelles):
            continue
        ca, cb = p.a.caramboles, p.b.caramboles
        # `firmes` ja porta aquesta mateixa partida (es registra en llegir-la): es busca
        # una altra amb el mateix marcador i algun jugador en comú.
        if any(
            (x | y) & (ma | mb) and {frozenset(x), frozenset(y)} != {frozenset(ma), frozenset(mb)}
            for d0, _d1, (x, y) in firmes._idx.get((min(ca, cb), max(ca, cb), p.a.entrades), [])
            if not (titol.inici and d0) or abs(d0 - titol.inici) <= 2 * marge
        ):
            continue
        noves.append(p)
    # En les proves a sets, Kozoom dona cada set i el total del partit amb la mateixa
    # parella i fase: només es queda el total (el de més caramboles).
    millor: dict[tuple, object] = {}
    for p in noves:
        clau = (p.fase, frozenset((p.a.jugador, p.b.jugador)))
        if clau not in millor or p.a.caramboles + p.b.caramboles > millor[clau].a.caramboles + millor[clau].b.caramboles:
            millor[clau] = p
    return [p for p in noves if millor[(p.fase, frozenset((p.a.jugador, p.b.jugador)))] is p]


def _nomes_les_que_falten(ll: Llegit, partides: list) -> None:
    """Deixa a `ll` només aquestes partides i els jugadors que hi surten."""
    ll.partides = partides
    noms = {p.a.jugador for p in partides} | {p.b.jugador for p in partides}
    ll.jugadors = [j for j in ll.jugadors if j.nom in noms]


def carrega(conn: sqlite3.Connection, cache: Path, ids: list[str]) -> list[Resultat]:
    out: list[Resultat] = []
    for pid in ids:
        esborra_esdeveniment(conn, DESPLACAMENT + int(pid))
    firmes = Firmes(conn)
    for pid in ids:
        titol, ll = llegeix_prova(cache, pid)
        if titol is None:
            out.append(Resultat(DESPLACAMENT + int(pid), pid, "sense_titol"))
            continue
        nom = f"{titol.nom} {titol.disciplina}"
        if not (ll.partides or ll.classificacio):
            out.append(Resultat(DESPLACAMENT + int(pid), nom, "buit"))
            continue
        abans = len(ll.partides)
        tretes = treu_repetides(firmes, ll, titol)
        if tretes and tretes * 2 >= abans:
            # La majoria de partides ja hi són per una altra font (la RFEB, una altra
            # còpia de Kozoom): és la mateixa prova i no s'ha de crear una segona vegada.
            # Les que falten a la prova de la UMB (grups que el PDF no porta) s'hi afegeixen.
            existent = ja_hi_es(conn, titol)
            afegides = 0
            if existent and ll.partides:
                _nomes_les_que_falten(ll, falten_a(conn, firmes, existent.id, ll.partides, titol))
                _afegeix_partides(conn, existent.id, ll)
                afegides = len(ll.partides)
            detall = f"{tretes} de {abans} partides"
            if afegides:
                detall += f", {afegides} afegides a {existent.id}"
            out.append(Resultat(DESPLACAMENT + int(pid), nom, "ja_hi_es", detall))
            continue
        existent = ja_hi_es(conn, titol)
        if existent and existent.partides:
            _nomes_les_que_falten(ll, falten_a(conn, firmes, existent.id, ll.partides, titol))
            _afegeix_partides(conn, existent.id, ll)
            detall = f"{existent.partides} partides"
            if ll.partides:
                detall += f", {len(ll.partides)} afegides"
            out.append(Resultat(existent.id, nom, "ja_hi_es", detall))
            continue
        if existent:
            if not ll.partides:
                out.append(Resultat(existent.id, nom, "ja_hi_es", "sense partides a Kozoom"))
                continue
            _afegeix_partides(conn, existent.id, ll)
            out.append(
                Resultat(
                    existent.id,
                    nom,
                    "afegides",
                    f"{len(ll.partides)} partides, {tretes} ja hi eren",
                )
            )
            continue
        ev = Esdeveniment(
            id=DESPLACAMENT + int(pid),
            nom=nom,
            lloc=titol.lloc,
            inici=titol.inici.isoformat() if titol.inici else None,
            fi=titol.fi.isoformat() if titol.fi else None,
            descripcio="",
            font=f"https://web.archive.org/web/2020/https://www.kozoom.com/en/billiard-carom/results/{pid}/rankings.html",
        )
        desa_esdeveniment(conn, ev, ll)
        out.append(
            Resultat(
                ev.id,
                nom,
                "desat",
                f"{len(ll.classificacio)} classificats, {len(ll.partides)} partides, {tretes} ja hi eren",
            )
        )
    _hereta_ids(conn)
    conn.commit()
    return out
