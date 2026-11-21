"""Partides de les competicions de la RFEB llegides dels seus fulls de Google.

Des del 2019 la RFEB porta el desenvolupament de moltes proves en un full de
càlcul compartit (play-offs de la Lliga Nacional, seleccions autonòmiques,
campionats sub-15, els GPE de la web nova…) i l'enllaça des de la pàgina de la
prova. A diferència dels PDF de classificació final, el full té les partides una
a una. Es llegeix pestanya a pestanya en CSV, per l'URL públic
`…/gviz/tq?tqx=out:csv&sheet=<pestanya>`, que funciona encara que el propietari
no deixi baixar el fitxer.

Cada full el fa qui organitza i no n'hi ha dos d'iguals, però les partides
surten de dues maneres:

- **Actes**: una partida per fila, els dos jugadors a banda i banda i els números
  al mig: `NOM A | sèrie | caramboles | entrades | caramboles | sèrie | NOM B`
  (play-offs, seleccions), o amb les mitjanes: `NOM A | sèrie | mitjana |
  caramboles | entrades | caramboles | mitjana | sèrie | NOM B` (campionat per
  equips). Una fila pot portar dues o quatre actes l'una al costat de l'altra.
- **Parelles**: una fila per jugador i la partida en dues files seguides, amb
  les mateixes entrades (sub-15, GPE).

No es fa servir cap posició fixa de columna: es busquen els noms i els números
de cada fila i només es desa el que quadra. A les actes, cinc enters o set
números amb les mitjanes que coincideixen amb caramboles/entrades; a les
parelles, una mitjana que és caramboles/entrades a totes dues files. Les files
d'equips (dos o quatre números entre els noms), les de totals i les partides no
jugades no quadren i no es desen.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

#: Les cel·les de capçalera que tenen lletres però no són noms de jugador.
_NO_NOMS = {
    "NOMBRE",
    "JUGADOR",
    "JUGADORES",
    "TOTAL",
    "PARCIAL",
    "PROMEDIO GENERAL",
    "EQUIPO",
    "EQUIPOS",
    "PTOS",
    "PARC",
    "CAR",
    "ENT",
    "PRO",
    "PROM",
    "HORA",
    "FECHA",
    "GRUPO",
    "FASE",
    "CLS",
    "FED",
    "SELECCION",
    "FEDERACION",
    "MODALIDAD",
    "PERDEDOR",
    "GANADOR",
    "SEMIFINAL",
    "SEMIFINALES",
    "FINAL",
    "CUARTOS",
    "OCTAVOS",
    "DESEMPATE",
    "PREVIA",
}

#: Primera cel·la d'una fila d'acta del campionat per equips: la modalitat.
_MODALITATS = {
    "BANDA": "banda",
    "LIBRE": "lliure",
    "TRES BANDAS": "3b",
    "3 BANDAS": "3b",
    "CUADRO 47/2": "47_2",
    "CUADRO 71/2": "71_2",
    "47/2": "47_2",
    "71/2": "71_2",
}

_RE_ENTER = re.compile(r"^\d{1,4}$")
#: Amb coma; amb punt, només amb tres decimals perquè no es confongui amb una hora.
_RE_DECIMAL = re.compile(r"^\d{1,2}(?:,\d{1,3}|\.\d{3})$")
_RE_DATA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_RE_GRUP = re.compile(r"^GRUPO\s+([A-Z])$")


@dataclass
class PartidaFull:
    fase: str
    grup: str
    ordre: int
    jugador_a: str
    caramboles_a: int
    serie_a: int | None
    jugador_b: str
    caramboles_b: int
    serie_b: int | None
    entrades: int
    punts_a: int | None = None
    punts_b: int | None = None
    equip_a: str | None = None
    equip_b: str | None = None
    data: date | None = None
    modalitat: str | None = None


def files_csv(text: str) -> list[list[str]]:
    return [[c.strip() for c in fila] for fila in csv.reader(io.StringIO(text))]


def _pla(text: str) -> str:
    sense = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(sense.upper().replace(".", " ").split())


def _es_nom(cel: str) -> bool:
    """Un nom de jugador o d'equip: lletres, i més que unes sigles de federació."""
    if sum(ch.isalpha() for ch in cel) < 4 or cel.startswith("#"):
        return False
    pla = _pla(cel)
    if pla in _NO_NOMS or pla in _MODALITATS or _RE_DATA.search(cel):
        return False
    return " " in cel.strip() or len(cel.strip()) > 5


_RE_FED_AL_NOM = re.compile(r"\s*\(([A-Za-z.\- ]{2,8})\)\s*$")


def neteja_nom(nom: str) -> tuple[str, str | None]:
    """(nom, federació) de «Sergio Jiménez Galera (CAT)»; sense parèntesis, (nom, None)."""
    if m := _RE_FED_AL_NOM.search(nom):
        return nom[: m.start()].strip(), m.group(1).strip().upper()
    return nom.strip(), None


def _num(cel: str) -> int | float | None:
    if _RE_ENTER.match(cel):
        return int(cel)
    if _RE_DECIMAL.match(cel):
        return float(cel.replace(",", "."))
    return None


def _quadra(car: int, ent: int, mitjana: float) -> bool:
    return ent > 0 and abs(car / ent - mitjana) < 0.0015


def _punts(a: int, b: int) -> tuple[int, int]:
    return (2, 0) if a > b else (0, 2) if b > a else (1, 1)


def _data(cel: str) -> date | None:
    if m := _RE_DATA.search(cel):
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


class _Context:
    """El que una acta hereta de les files de sobre: data, grup i equips.

    Una fila pot tenir actes l'una al costat de l'altra, i cadascuna hereta el
    de la seva columna: es desa per columna i es busca el més proper per
    l'esquerra.
    """

    def __init__(self) -> None:
        self.dates: dict[int, date] = {}
        self.grups: dict[int, str] = {}
        self.equips: dict[int, tuple[str, str | None]] = {}

    @staticmethod
    def _proper(d: dict, col: int):
        cols = [c for c in d if c <= col + 2]
        return d[max(cols)] if cols else None

    def data(self, col: int) -> date | None:
        return self._proper(self.dates, col)

    def grup(self, col: int) -> str:
        return self._proper(self.grups, col) or ""

    def equip(self, col: int) -> tuple[str, str | None] | None:
        return self._proper(self.equips, col)


def _numeros(fila: list[str], de: int, a: int) -> list[int | float] | None:
    """Els números entre dues columnes, o None si hi ha cap altra cosa."""
    out = []
    for cel in fila[de + 1 : a]:
        if not cel:
            continue
        n = _num(cel)
        if n is None:
            return None
        out.append(n)
    return out


def _acta(nums: list[int | float]) -> tuple[int, int, int, int, int] | None:
    """(sèrie A, caramboles A, entrades, caramboles B, sèrie B), si quadra."""
    if len(nums) == 5 and all(isinstance(n, int) for n in nums):
        sa, ca, ent, cb, sb = nums
    elif len(nums) == 7 and isinstance(nums[1], float) and isinstance(nums[5], float):
        sa, ma, ca, ent, cb, mb, sb = nums
        if not all(isinstance(n, int) for n in (sa, ca, ent, cb, sb)):
            return None
        if not (_quadra(ca, ent, ma) and _quadra(cb, ent, mb)):
            return None
    elif (
        len(nums) in (8, 9)
        and isinstance(nums[0], float)
        and all(isinstance(n, int) for n in nums[1:])
    ):
        # CE 2018-19: «NOM A | mitjana | punts | sèrie | caramboles | entrades |
        # caramboles | sèrie | punts | [núm.] NOM B». La mitjana, de vegades
        # amb dos decimals.
        ma, _pa, sa, ca, ent, cb, sb = nums[:7]
        if not ent or abs(ca / ent - ma) >= 0.006:
            return None
    else:
        return None
    if ent < 1 or sa > ca or sb > cb or max(ca, cb) == 0:
        return None
    return sa, ca, ent, cb, sb


def llegeix_actes(files: list[list[str]], fase: str) -> list[PartidaFull]:
    """Les partides d'una pestanya d'actes (una partida per fila)."""
    ctx = _Context()
    partides: list[PartidaFull] = []
    for fila in files:
        modalitat = None
        primera = next((c for c in fila if c), "")
        if _pla(primera) in _MODALITATS:
            modalitat = _MODALITATS[_pla(primera)]
        for col, cel in enumerate(fila):
            if d := _data(cel):
                ctx.dates[col] = d
            pla = _pla(cel)
            if m := _RE_GRUP.match(pla):
                ctx.grups[col] = m.group(1)
            elif pla == "GRUPO":
                seg = next((c for c in fila[col + 1 :] if c), "")
                if re.fullmatch(r"[A-Z]", seg):
                    ctx.grups[col] = seg
        noms = [i for i, c in enumerate(fila) if _es_nom(c)]
        abans = len(partides)
        equips_fila: dict[int, tuple[str, str | None]] = {}
        k = 0
        while k < len(noms):
            i = noms[k]
            j = noms[k + 1] if k + 1 < len(noms) else len(fila)
            nums = _numeros(fila, i, j)
            enters = nums is not None and all(isinstance(n, int) for n in nums)
            # La capçalera de l'equip: el seu nom i els punts dels dos equips
            # («PAÍS VASCO | 2 | 6»), o els dos noms amb els punts al mig
            # («ANDALUCIA | 2 | 6 | 0 | 2 | NAVARRA»).
            if enters and len(nums) == 2:
                equips_fila[i] = (fila[i], None)
                k += 1
                continue
            if enters and len(nums) == 4 and j < len(fila):
                equips_fila[i] = (fila[i], fila[j])
                k += 2
                continue
            if j == len(fila):
                break
            if nums is None or (acta := _acta(nums)) is None:
                k += 1
                continue
            sa, ca, ent, cb, sb = acta
            pa, pb = _punts(ca, cb)
            equips = ctx.equip(i)
            nom_a, fed_a = neteja_nom(fila[i])
            nom_b, fed_b = neteja_nom(fila[j])
            partides.append(
                PartidaFull(
                    fase=fase,
                    grup=ctx.grup(i),
                    ordre=len(partides) + 1,
                    jugador_a=nom_a,
                    caramboles_a=ca,
                    serie_a=sa,
                    jugador_b=nom_b,
                    caramboles_b=cb,
                    serie_b=sb,
                    entrades=ent,
                    punts_a=pa,
                    punts_b=pb,
                    equip_a=equips[0] if equips else fed_a,
                    equip_b=equips[1] if equips else fed_b,
                    data=ctx.data(i),
                    modalitat=modalitat,
                )
            )
            k += 2
        # Una fila amb partides no és mai la capçalera d'un equip, encara que
        # una de les seves actes en tingui la forma.
        if len(partides) == abans:
            ctx.equips.update(equips_fila)
    return partides


@dataclass
class _Linia:
    nom: str
    col: int
    nums: list[int | float]
    fase: str | None  # la fase escrita a la mateixa fila («PPPQ», «Q»…)


def _linia(fila: list[str]) -> _Linia | None:
    # El primer nom de la fila i els números que el segueixen. Als GPE la
    # primera fila de cada partida repeteix al final el nom del guanyador.
    noms = [i for i, c in enumerate(fila) if _es_nom(c)]
    if not noms:
        return None
    i = noms[0]
    nums, fase = [], None
    for cel in fila[i + 1 :]:
        if not cel:
            continue
        n = _num(cel)
        if n is not None:
            nums.append(n)
        elif re.fullmatch(r"[A-Z0-9-]{1,10}", cel) and nums:
            fase = cel
            break
        elif nums:
            break
    return _Linia(fila[i], i, nums, fase)


def _jugador(lin: _Linia, ent_altre: int | None):
    """(caramboles, entrades, sèrie, punts) d'una fila de parella, o None.

    La mitjana és l'únic decimal. Les caramboles i les entrades són els dos
    enters de davant que la fan; la segona fila de vegades no repeteix les
    entrades, i llavors valen les de la primera. La sèrie és l'enter de darrere
    la mitjana. Els punts, un enter de 0 a 3 just davant de les caramboles, o el
    de darrere la sèrie si la fila no en porta cap davant.
    """
    decs = [k for k, n in enumerate(lin.nums) if isinstance(n, float)]
    if len(decs) != 1:
        return None
    d = decs[0]
    mitjana = lin.nums[d]
    davant = [n for n in lin.nums[:d] if isinstance(n, int)]
    darrere = [n for n in lin.nums[d + 1 :] if isinstance(n, int)]
    car = ent = None
    punts = None
    for k in range(len(davant) - 1):
        if _quadra(davant[k], davant[k + 1], mitjana):
            car, ent = davant[k], davant[k + 1]
            if k and davant[k - 1] <= 3:
                punts = davant[k - 1]
            break
    if car is None and ent_altre and davant and _quadra(davant[-1], ent_altre, mitjana):
        car, ent = davant[-1], ent_altre
        if len(davant) > 1 and davant[-2] <= 3:
            punts = davant[-2]
    if car is None:
        return None
    serie = darrere[0] if darrere else None
    if punts is None and len(darrere) > 1 and darrere[1] <= 3:
        punts = darrere[1]
    if serie is not None and serie > max(car, 1):
        return None
    return car, ent, serie, punts


def llegeix_parelles(files: list[list[str]], fase: str, grup: str = "") -> list[PartidaFull]:
    """Les partides d'una pestanya on cada partida són dues files seguides.

    Si la pestanya té un bloc «RESULTADOS PARTIDOS», només es llegeix el que hi
    ha a sota: el de dalt és la classificació del grup, que té la mateixa forma.
    """
    inici = next(
        (k + 1 for k, f in enumerate(files) if any("RESULTADOS PARTIDOS" in _pla(c) for c in f)),
        0,
    )
    linies = [lin for f in files[inici:] if (lin := _linia(f)) is not None]
    partides: list[PartidaFull] = []
    k = 0
    while k + 1 < len(linies):
        a, b = linies[k], linies[k + 1]
        if not a.nums or a.col != b.col:
            k += 1
            continue
        ja = _jugador(a, None)
        jb = _jugador(b, ja[1] if ja else None)
        if ja and jb and ja[1] == jb[1]:
            ca, ent, sa, pa = ja
            cb, _, sb, pb = jb
            if pa is None or pb is None:
                pa, pb = _punts(ca, cb)
            partides.append(
                PartidaFull(
                    fase=a.fase or fase,
                    grup=grup,
                    ordre=len(partides) + 1,
                    jugador_a=neteja_nom(a.nom)[0],
                    caramboles_a=ca,
                    serie_a=sa,
                    jugador_b=neteja_nom(b.nom)[0],
                    caramboles_b=cb,
                    serie_b=sb,
                    entrades=ent,
                    punts_a=pa,
                    punts_b=pb,
                )
            )
        # Les parelles van sempre de dues en dues, jugades o no.
        k += 2
    return partides


# ------------------------------------------------------------ fulls i càrrega

URL_PESTANYA = "https://docs.google.com/spreadsheets/d/{full}/gviz/tq?tqx=out:csv&sheet={pestanya}"
URL_FULL = "https://docs.google.com/spreadsheets/d/{full}"

#: Nom de la pestanya (sense accents, en majúscules) → fase. Els grups («GRUPO
#: B») porten la lletra a part.
_FASES = {
    "FASE DE GRUPOS": "Grups",
    "FASE GRUPOS": "Grups",
    "ACTAS FASE DE GRUPOS": "Grups",
    "RESULTADOS": "Grups",
    "VIERNES": "Grups",
    "SABADO": "Grups",
    "OCTAVOS": "Vuitens",
    "CUARTOS": "Quarts",
    "SEMIS Y FINAL": "Semifinals i final",
    "FASE KO": "Fase final",
    "FASE FINAL": "Fase final",
    "ACTAS FASE FINAL": "Fase final",
    "PARTIDOS VIERNES": "Divendres",
    "PARTIDOS SABADO": "Dissabte",
    "PARTIDOS DOMINGO": "Diumenge",
}


@dataclass
class Full:
    full: str
    temporada: str
    modalitat: str
    categoria: str
    tipus: str
    titol: str
    lloc: str | None
    data_inici: str | None
    data_fi: str | None
    format: str  # actes | parelles | auto
    pestanyes: list[str]
    viu: bool
    #: La prova de `rfeb_proves` (la classificació d'un PDF) on van les partides,
    #: si n'hi ha. Sense, la prova és el mateix full: `full/{id}`.
    prova: str | None = None

    @property
    def prova_id(self) -> str:
        return self.prova or f"full/{self.full}"


def llegeix_config(cami: str | Path) -> list[Full]:
    with Path(cami).open(encoding="utf-8", newline="") as f:
        return [
            Full(
                full=r["full"],
                temporada=r["temporada"],
                modalitat=r["modalitat"],
                categoria=r["categoria"],
                tipus=r["tipus"],
                titol=r["titol"],
                lloc=r["lloc"] or None,
                data_inici=r["data_inici"] or None,
                data_fi=r["data_fi"] or None,
                format=r["format"],
                pestanyes=[p for p in r["pestanyes"].split("|") if p],
                viu=r["viu"].strip().lower() == "si",
                prova=(r.get("prova") or "").strip() or None,
            )
            for r in csv.DictReader(f)
        ]


def fitxer_pestanya(pestanya: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", _pla(pestanya)).strip("_") + ".csv"


def fase_de_pestanya(pestanya: str) -> tuple[str, str]:
    pla = _pla(pestanya)
    if m := re.fullmatch(r"GRUPO ([A-Z])", pla):
        return "Grups", m.group(1)
    return _FASES.get(pla, pestanya), ""


def baixa(fulls: list[Full], carpeta: str | Path, nomes_vius: bool = False) -> list[str]:
    """Baixa en CSV les pestanyes de cada full. Retorna els errors."""
    errors = []
    for full in fulls:
        if nomes_vius and not full.viu:
            continue
        dest = Path(carpeta) / full.full
        dest.mkdir(parents=True, exist_ok=True)
        for p in full.pestanyes:
            url = URL_PESTANYA.format(full=full.full, pestanya=urllib.parse.quote(p))
            req = urllib.request.Request(url, headers={"User-Agent": "fcbillar"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    text = r.read().decode("utf-8")
            except Exception as exc:
                errors.append(f"{full.titol} / {p}: {exc}")
                continue
            # Un full que ja no és públic torna la pàgina d'inici de sessió.
            if not text.startswith('"'):
                errors.append(f"{full.titol} / {p}: no és un CSV")
                continue
            (dest / fitxer_pestanya(p)).write_text(text, encoding="utf-8")
            time.sleep(0.5)
    return errors


def partides_del_full(full: Full, carpeta: str | Path) -> list[PartidaFull]:
    """Totes les partides d'un full, numerades per fase i grup."""
    out: list[PartidaFull] = []
    for p in full.pestanyes:
        f = Path(carpeta) / full.full / fitxer_pestanya(p)
        if not f.exists():
            continue
        files = files_csv(f.read_text(encoding="utf-8"))
        fase, grup = fase_de_pestanya(p)
        if full.format == "actes":
            out.extend(llegeix_actes(files, fase))
        elif full.format == "parelles":
            out.extend(llegeix_parelles(files, fase, grup))
        else:
            # Cada pestanya del full a la seva manera: la lectura que en treu més.
            actes, parelles = llegeix_actes(files, fase), llegeix_parelles(files, fase, grup)
            out.extend(actes if len(actes) >= len(parelles) else parelles)
    out = sense_repetides(out)
    comptes: dict[tuple[str, str], int] = {}
    for partida in out:
        clau = (partida.fase, partida.grup)
        comptes[clau] = comptes.get(clau, 0) + 1
        partida.ordre = comptes[clau]
    return out


def sense_repetides(partides: list[PartidaFull]) -> list[PartidaFull]:
    """Sense la mateixa partida dues vegades.

    Molts fulls tenen una pestanya per ronda i una altra amb «tots els
    partits»: la mateixa partida hi surt dues vegades, de vegades amb els
    jugadors girats. Es queda la primera.
    """
    vistes, out = set(), []
    for p in partides:
        clau = (
            frozenset({(_pla(p.jugador_a), p.caramboles_a), (_pla(p.jugador_b), p.caramboles_b)}),
            p.entrades,
        )
        if clau in vistes:
            continue
        vistes.add(clau)
        out.append(p)
    return out


def desa(conn: sqlite3.Connection, full: Full, partides: list[PartidaFull]) -> None:
    """Desa la prova i les seves partides, reemplaçant les que ja hi hagi.

    Si el full va a una prova que ja hi és (`prova`), la prova no es toca.
    """
    dates = sorted(p.data for p in partides if p.data)
    inici = full.data_inici or (dates[0].isoformat() if dates else None)
    fi = full.data_fi or (dates[-1].isoformat() if dates else None)
    conn.execute("DELETE FROM rfeb_partides WHERE prova_id = ?", (full.prova_id,))
    if full.prova:
        _insereix_partides(conn, full.prova_id, partides)
        return
    conn.execute(
        "INSERT OR REPLACE INTO rfeb_proves (id, temporada, modalitat, categoria, tipus, titol, "
        "lloc, data_inici, data_fi, font) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            full.prova_id,
            full.temporada,
            full.modalitat,
            full.categoria,
            full.tipus,
            full.titol,
            full.lloc,
            inici,
            fi,
            URL_FULL.format(full=full.full),
        ),
    )
    _insereix_partides(conn, full.prova_id, partides)


def _insereix_partides(
    conn: sqlite3.Connection, prova_id: str, partides: list[PartidaFull]
) -> None:
    conn.executemany(
        "INSERT INTO rfeb_partides (prova_id, fase, grup, ordre, data, modalitat, jugador_a, "
        "equip_a, caramboles_a, serie_a, punts_a, jugador_b, equip_b, caramboles_b, serie_b, "
        "punts_b, entrades) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                prova_id,
                p.fase,
                p.grup,
                p.ordre,
                p.data.isoformat() if p.data else None,
                p.modalitat,
                p.jugador_a,
                p.equip_a,
                p.caramboles_a,
                p.serie_a,
                p.punts_a,
                p.jugador_b,
                p.equip_b,
                p.caramboles_b,
                p.serie_b,
                p.punts_b,
                p.entrades,
            )
            for p in partides
        ],
    )
