"""Lectura dels PDF de resultats de la UMB (umb-carom.org).

Cada prova té una llista de jugadors, les partides de cada fase i una
classificació final. El format ha canviat tres vegades (2013: noms amb espais i
decimals amb coma; 2018: noms enganxats i sense identificador; 2021 en
endavant: identificador UMB de quatre xifres), així que no es llegeix cap columna
per posició fixa: el nom és el que hi ha abans del primer número, la mitjana és
l'únic número amb decimals d'una fila de partida, i el que hi ha abans i després
d'ella és el que toca.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

#: Els noms dels països de les llistes de jugadors sense codi (2018) i el seu codi.
_PAISOS = {
    "SPAIN": "ES", "FRANCE": "FR", "BELGIUM": "BE", "NETHERLANDS": "NL", "TURKEY": "TR",
    "ITALY": "IT", "GERMANY": "DE", "DENMARK": "DK", "DANMARK": "DK", "SWEDEN": "SE",
    "KOREA": "KR", "SOUTH KOREA": "KR", "JAPAN": "JP", "VIETNAM": "VN", "EGYPT": "EG",
    "COLOMBIA": "CO", "GREECE": "GR", "AUSTRIA": "AT", "PORTUGAL": "PT", "FINLAND": "FI",
    "SWITZERLAND": "CH", "UNITED STATES": "US", "USA": "US", "PERU": "PE", "ARGENTINA": "AR",
    "BRAZIL": "BR", "CHILE": "CL", "MEXICO": "MX", "VENEZUELA": "VE", "ECUADOR": "EC",
    "CZECH REPUBLIC": "CZ", "POLAND": "PL", "HUNGARY": "HU", "ISRAEL": "IL", "CHINA": "CN",
    "CHINESE TAIPEI": "TW", "TAIWAN": "TW", "THAILAND": "TH", "INDIA": "IN", "SLOVENIA": "SI",
    "CROATIA": "HR", "SERBIA": "RS", "BULGARIA": "BG", "ROMANIA": "RO", "RUSSIA": "RU",
    "UKRAINE": "UA", "MOROCCO": "MA", "ALGERIA": "DZ", "TUNISIA": "TN", "JORDAN": "JO",
    "LUXEMBOURG": "LU", "IRELAND": "IE", "ENGLAND": "GB", "BOLIVIA": "BO", "PARAGUAY": "PY",
    "URUGUAY": "UY", "THE NETHERLANDS": "NL", "CZECH": "CZ", "SLOVAKIA": "SK",
    "MONTENEGRO": "ME", "LATVIA": "LV", "LITHUANIA": "LT", "ESTONIA": "EE", "NORWAY": "NO",
    "NEW ZEALAND": "NZ", "PHILIPPINES": "PH", "INDONESIA": "ID", "MALAYSIA": "MY",
    "SINGAPORE": "SG", "SAUDI ARABIA": "SA", "QATAR": "QA", "LEBANON": "LB", "IRAN": "IR",
    "PANAMA": "PA", "COSTA RICA": "CR", "DOMINICAN REPUBLIC": "DO", "GUATEMALA": "GT", "CANADA": "CA", "AUSTRALIA": "AU", "SOUTH AFRICA": "ZA",
}  # fmt: skip

#: Els PDF posen «0000» als jugadors sense identificador: no és d'ningú, i compartit
#: ajuntaria centenars de persones en una de sola.
ID_SENSE_VALOR = {"0000"}

_RE_NUM = re.compile(r"^\d+$")
_RE_DEC = re.compile(r"^\d+[.,]\d+$")
_RE_DATA = re.compile(r"\d{2}/\d{2}/\d{4}")


class PdfNoReconegut(Exception):
    """El PDF no és cap taula de resultats que sapiguem llegir."""


def clau(nom: str) -> str:
    """El nom sense espais, majúscules ni accents: «SIDHOMSameh» i «SIDHOM Sameh» coincideixen."""
    plan = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", plan.lower())


def _dec(t: str) -> float:
    return float(t.replace(",", "."))


def separa_nom(nom: str) -> str:
    """«KARAKURTBerkay» -> «KARAKURT Berkay»; un nom que ja té espais es deixa tal qual."""
    if " " in nom.strip():
        return nom.strip()
    # El cognom és la tira de majúscules; l'última és ja la inicial del nom.
    m = re.match(r"^([A-Z'\-]+?)([A-Z][a-z].*)$", nom)
    if not m:
        return nom
    cognom, resta = m.groups()
    resta = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", resta)
    return f"{cognom} {resta}"


# ------------------------------- dades llegides -------------------------------


@dataclass
class Jugador:
    nom: str
    nacionalitat: str | None = None
    umb_id: str | None = None


@dataclass
class Classificat:
    posicio: int
    jugador: str
    nacionalitat: str | None
    ronda: str | None
    punts: int | None
    mitjana: float | None
    mitjana_particular: float | None
    serie1: int | None
    serie2: int | None
    caramboles: int | None
    entrades: int | None


@dataclass
class Costat:
    jugador: str
    caramboles: int
    mitjana: float
    punts: int
    serie: int | None
    serie2: int | None
    # Qui comença juga una entrada més, així que cada costat porta les seves.
    entrades: int = 0
    # Només als mundials per equips nacionals: el país amb què juga.
    nacio: str | None = None


@dataclass
class Partida:
    fase: str
    grup: str
    ordre: int
    a: Costat
    b: Costat


@dataclass
class Llegit:
    """Tot el que s'ha pogut llegir dels PDF d'una prova."""

    jugadors: list[Jugador] = field(default_factory=list)
    classificacio: list[Classificat] = field(default_factory=list)
    partides: list[Partida] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    llegits: list[str] = field(default_factory=list)


# --------------------------------- llista de jugadors ---------------------------------


def _divideix_cognom(tokens: list[str]) -> str:
    """«JASPERS», «Dick» -> «JASPERS Dick». Només normalitza els espais."""
    return " ".join(tokens)


def llegeix_jugadors(text: str) -> list[Jugador]:
    out: list[Jugador] = []
    for linia in text.splitlines():
        t = linia.split()
        if len(t) < 4 or not _RE_NUM.match(t[0]):
            continue
        t = t[1:]
        data = next((i for i, x in enumerate(t) if _RE_DATA.fullmatch(x)), None)
        if data is not None:
            # 2018: «ANGUITA Carlos Spain 16/01/1997 1.029»; la data de naixement no es desa.
            antes = t[:data]
            nat = None
            for n in (3, 2, 1):
                if len(antes) > n and " ".join(antes[-n:]).upper() in _PAISOS:
                    nat = _PAISOS[" ".join(antes[-n:]).upper()]
                    antes = antes[:-n]
                    break
            if antes:
                out.append(Jugador(nom=_divideix_cognom(antes), nacionalitat=nat))
            continue
        # «JASPERS Dick NL 1 428 0106 …»: el codi de país és el primer token de 2-3
        # majúscules, no el primer, i seguit d'un número.
        idx = next(
            (
                i
                for i in range(1, len(t) - 1)
                if re.fullmatch(r"[A-Z]{2,3}", t[i]) and _RE_NUM.match(t[i + 1])
            ),
            None,
        )
        if idx is None:
            continue
        nums = []
        for x in t[idx + 1 :]:
            if not _RE_NUM.match(x):
                break
            nums.append(x)
        umb_id = nums[2] if len(nums) >= 3 and len(nums[2]) == 4 else None
        if umb_id in ID_SENSE_VALOR:
            umb_id = None
        nat = t[idx]
        out.append(Jugador(nom=_divideix_cognom(t[:idx]), nacionalitat=nat[:2], umb_id=umb_id))
    return out


# ----------------------------- partides i classificacions -----------------------------


def _tokens_fila(linia: str, estricte: bool = False) -> tuple[list[str], list[str]]:
    """(tokens del nom, números) d'una fila; None si no acaba en números."""
    t = linia.split()
    i = next((k for k, x in enumerate(t) if _RE_NUM.match(x) or _RE_DEC.match(x)), None)
    if i is None or i == 0:
        return t, []
    # Alguns PDF porten un resto de capçalera enganxat a la fila («S5-Inn»): s'ignora.
    resta = [x for x in t[i:] if _RE_NUM.match(x) or _RE_DEC.match(x)]
    if estricte and len(resta) != len(t) - i:
        return t, []
    return t[:i], resta


@dataclass
class _Fila:
    nom: str
    nat: str | None
    car: int
    inn: int
    avg: float
    mp: int
    hr: list[int]
    grup: str = ""


def _fila_partida(linia: str, amb_nat: bool) -> _Fila | None:
    nom, nums = _tokens_fila(linia)
    if not nums or not nom:
        return None
    nat = None
    if amb_nat:
        if len(nom) < 2 or not re.fullmatch(r"[A-Z]{2,3}", nom[-1]):
            return None
        nat = nom[-1][:2]
        nom = nom[:-1]
    k = next((i for i, x in enumerate(nums) if _RE_DEC.match(x)), None)
    if k is None or k < 2 or k + 2 > len(nums):
        return None
    try:
        return _Fila(
            nom=" ".join(nom),
            nat=nat,
            car=int(nums[0]),
            inn=int(nums[1]),
            avg=_dec(nums[k]),
            mp=int(nums[k + 1]),
            hr=[int(x) for x in nums[k + 2 :]],
        )
    except ValueError:
        return None


_RE_FASE = re.compile(
    r"(?i)(qual|final|semi|quarter|round|groups?\b|rank\s*\d|1/\d|\br\d+\b|main tournament)"
)
_RE_CAPCALERA = re.compile(r"(?i)^(group\s+match|match\s*players|players\s+nat|pena|lty|rank\s)")


def _fase_de_linia(linia: str) -> str | None:
    """El nom de la fase si la línia n'és el títol, no una fila ni una capçalera."""
    if _RE_CAPCALERA.match(linia) or not _RE_FASE.search(linia):
        return None
    if _tokens_fila(linia, estricte=True)[1]:
        return None
    if " -- " in linia:  # «04th till 09th November 2013 -- Medellin (CO) SEMI FINAL»
        m = re.search(r"\)\s+(.+)$", linia)
        return m.group(1).strip() if m else None
    if re.search(r"(?i)world (cup|champ)|grand prix", linia) and not re.search(
        r"(?i)(qual|final|semi|quarter|round|groups)", linia
    ):
        return None
    return re.sub(r"\s+", " ", linia).strip()


def _sense_grup(nom: str, conegut: set[str]) -> tuple[str, str]:
    """(grup, nom) traient la lletra de grup que algunes files porten davant."""
    t = nom.split()
    if len(t) >= 2 and re.fullmatch(r"[A-Z]{1,2}", t[0]):
        resta = " ".join(t[1:])
        if clau(nom) not in conegut and (clau(resta) in conegut or len(t[0]) == 1):
            return t[0], resta
    return "", nom


def llegeix_partides(
    text: str, conegut: set[str], fase_per_defecte: str
) -> tuple[list[Partida], list[str]]:
    """Les partides d'un PDF de grups o d'eliminatòries, i els blocs que no s'han aparellat."""
    errors: list[str] = []
    fase = fase_per_defecte
    mode: str | None = None  # "grup", "elim" o None (classificació de grup)
    blocs: list[tuple[str, str, list[_Fila]]] = []
    files: list[_Fila] = []

    def tanca() -> None:
        nonlocal files
        if files:
            blocs.append((fase, mode or "", files))
        files = []

    for linia in text.splitlines():
        linia = linia.strip()
        if not linia:
            continue
        if re.match(r"(?i)^group\s+match", linia):
            tanca()
            mode = "grup"
            continue
        if re.match(r"(?i)^match\s*players", linia):
            tanca()
            mode = "elim"
            continue
        if re.match(r"(?i)^players\s+nat", linia):
            tanca()
            mode = None
            continue
        f = _fase_de_linia(linia)
        if f:
            tanca()
            fase = f
            mode = None if mode == "grup" else mode
            continue
        if mode is None:
            continue
        fila = _fila_partida(linia, amb_nat=(mode == "elim"))
        if fila is None:
            continue
        if mode == "grup":
            fila.grup, fila.nom = _sense_grup(fila.nom, conegut)
        files.append(fila)
    tanca()

    out: list[Partida] = []
    ordre = 0
    for fase_b, _, fs in blocs:
        if len(fs) % 2:  # una fila mal llegida desparella tot el bloc: es descarta sencer
            errors.append(f"{fase_b}: bloc amb un nombre senar de files ({len(fs)}), saltat")
            continue
        # La lletra del grup va en una sola fila del bloc.
        grup = next((f.grup for f in fs if f.grup), "")
        for i in range(0, len(fs), 2):
            a, b = fs[i], fs[i + 1]
            ordre += 1
            out.append(
                Partida(
                    fase=fase_b,
                    grup=grup,
                    ordre=ordre,
                    a=_costat(a),
                    b=_costat(b),
                )
            )
    return out, errors


def _costat(f: _Fila) -> Costat:
    return Costat(
        jugador=f.nom,
        caramboles=f.car,
        mitjana=f.avg,
        punts=f.mp,
        serie=f.hr[0] if f.hr else None,
        serie2=f.hr[1] if len(f.hr) > 1 else None,
        entrades=f.inn,
    )


def _fila_antiga(
    pos: int, nom: str, nat: str, nums: list[str], decs: list[int]
) -> Classificat | None:
    """Les classificacions d'abans del 2018, que canvien de columnes d'un any a l'altre.

    Davant de la mitjana hi ha les caramboles i les entrades (i els punts de partida
    abans, si en són tres); darrere, una segona mitjana opcional, els punts, la sèrie,
    una segona sèrie opcional i els punts de rànquing.
    """
    k = decs[0]
    if k not in (2, 3):
        return None
    mp = int(nums[0]) if k == 3 else None
    car, inn = (int(nums[k - 2]), int(nums[k - 1]))
    avg, j, millor = _dec(nums[k]), k + 1, None
    if j < len(nums) and _RE_DEC.match(nums[j]):
        millor, j = _dec(nums[j]), j + 1
    resta = [int(x) for x in nums[j:]]
    if mp is None:
        if not resta:
            return None
        mp, resta = resta[0], resta[1:]
    hr1 = resta[0] if resta else None
    hr2 = resta[1] if len(resta) >= 3 else None  # l'últim és sempre els punts de rànquing
    return Classificat(pos, nom, nat, None, mp, avg, millor, hr1, hr2, car, inn)


def llegeix_classificacio(text: str) -> list[Classificat]:
    """La classificació final: format nou («MT 1 NOM Nat …») o antic («1 NOM Nat …»)."""
    out: list[Classificat] = []
    vistos: set[tuple[int, str]] = set()
    for linia in text.splitlines():
        t = linia.split()
        ronda = None
        if t and re.fullmatch(r"(MT|Q|PQ|PPQ|PPPQ|R\d+|[A-Z]{1,5})", t[0]) and len(t) > 2:
            if _RE_NUM.match(t[1]) and not _RE_NUM.match(t[0]):
                ronda = t[0]
                t = t[1:]
        if not t or not _RE_NUM.match(t[0]):
            continue
        pos = int(t[0])
        nom, nums = _tokens_fila(" ".join(t[1:]))
        if not nums or len(nom) < 2 or not re.fullmatch(r"[A-Z]{2,3}", nom[-1]):
            continue
        nat = nom[-1][:2]
        nom_s = " ".join(nom[:-1])
        decs = [i for i, x in enumerate(nums) if _RE_DEC.match(x)]
        if not decs:
            continue
        try:
            if ronda:  # MP Avg S-Avg HR1 HR2 Carom Inning WR
                if len(nums) < 8:
                    continue
                c = Classificat(
                    pos, nom_s, nat, ronda, int(nums[0]), _dec(nums[1]), _dec(nums[2]),
                    int(nums[3]), int(nums[4]), int(nums[5]), int(nums[6]),
                )  # fmt: skip
            else:
                c = _fila_antiga(pos, nom_s, nat, nums, decs)
                if c is None:
                    continue
        except (ValueError, IndexError):
            continue
        if (pos, nom_s) in vistos:
            continue
        vistos.add((pos, nom_s))
        out.append(c)
    return out


# ------------------------- mundial per equips nacionals -------------------------
# Cada fila és un jugador d'un encontre entre seleccions: «[joc] PAÍS Nom car inn mitjana
# mp hr [hr2]». El número de joc (davant o en una línia a part) no es fa servir: la
# càrrega renumera les partides de tota la prova.

_RE_FILA_EQUIP = re.compile(
    r"^(?:(\d+)\s+)?(.+?)\s+(\d+)\s+(\d+)\s+(\d+[.,]\d+)\s+(\d)\s+(\d+)(?:\s+(\d+))?$"
)
_RE_FASE_EQUIP = re.compile(
    r"(?i)^(group\s+\w+|(?:round of \d+|quarter|semi)[ -]?finals?|finals?|ranking.*)$"
)


def es_equips(text: str) -> bool:
    return bool(re.search(r"(?mi)^game\s+nation\s+match\s*/\s*players", text))


def noms_de_la_llista_d_equips(text: str, nacions: list[str]) -> list[str]:
    """Els noms de «TEAM PLAYERS RESERVE»: titulars i reserves, de dos en dos o més per línia."""
    if not re.search(r"(?mi)^team\s+players\s+reserve", text):
        return []
    out: list[str] = []
    for linia in text.splitlines():
        t = linia.split()
        if len(t) < 2 or not _RE_NUM.match(t[0]):
            continue
        t = t[1:]
        for n in nacions:  # «9 BELGIUM 2 FORTHOMME Roland …»: el país va davant d'un número
            k = len(n.split())
            if t[:k] == n.split() and len(t) > k and _RE_NUM.match(t[k]):
                t = t[k + 1 :]
                break
        t = [x for x in t if not _RE_NUM.match(x)]
        nom: list[str] = []
        for x in t:
            majus = not any(c.islower() for c in x)
            if majus and nom and any(any(c.islower() for c in y) for y in nom):
                out.append(" ".join(nom))
                nom = []
            nom.append(x)
        if nom and any(any(c.islower() for c in y) for y in nom):
            out.append(" ".join(nom))
    return out


def _nacions_de(textos: list[str]) -> list[str]:
    """Els noms de país que surten a la classificació per equips, més els coneguts."""
    trobats = set(_PAISOS)
    for text in textos:
        for m in re.finditer(r"(?m)^\d+\s+([A-Z][A-Z .]+?)\s+\d+\s+\d+\s+\d+\s+\d+[.,]\d+", text):
            trobats.add(m.group(1).strip())
    return sorted(trobats, key=len, reverse=True)


def llegeix_equips(
    text: str, nacions: list[str], fase_per_defecte: str
) -> tuple[list[Partida], list[str]]:
    """Les partides individuals d'un PDF de resultats d'un mundial per equips nacionals."""
    errors: list[str] = []
    fase, grup = fase_per_defecte, ""
    files: list[tuple[str, str, str, _Fila]] = []
    for linia in text.splitlines():
        linia = linia.strip()
        if not linia:
            continue
        f = _RE_FASE_EQUIP.match(linia)
        if f:
            fase = linia.upper() if not linia.lower().startswith("group") else fase_per_defecte
            grup = linia.split()[-1].upper() if linia.lower().startswith("group") else ""
            continue
        m = _RE_FILA_EQUIP.match(linia)
        if not m:
            continue
        _, resta, car, inn, avg, mp, hr1, hr2 = m.groups()
        pais = next((n for n in nacions if resta.upper().startswith(n + " ")), None)
        nom = resta[len(pais) :].strip() if pais else ""
        if not pais or not re.search(r"[A-Za-z]", nom):
            continue
        fila = _Fila(nom, _PAISOS.get(pais, pais[:2]), int(car), int(inn), _dec(avg), int(mp),
                     [int(x) for x in (hr1, hr2) if x is not None])  # fmt: skip
        files.append((fase, grup, pais, fila))
    # Dos jugadors seguits són una partida; el joc solt va entre els dos o després.
    out: list[Partida] = []
    i = 0
    while i + 1 < len(files):
        (fa, ga, pa, a), (_, _, pb, b) = files[i], files[i + 1]
        if pa == pb or a.inn != b.inn:
            errors.append(f"{fa}: files que no fan parella ({a.nom}, {b.nom}), saltades")
            i += 1
            continue
        c1, c2 = _costat(a), _costat(b)
        c1.nacio, c2.nacio = a.nat, b.nat
        out.append(Partida(fase=fa, grup=ga, ordre=len(out) + 1, a=c1, b=c2))
        i += 2
    return out, errors


def _unifica_noms(partides: list[Partida], llista: list[str]) -> None:
    """Les columnes tallen els noms llargs («DE BRUIJN Jean Pau»): s'agafa el més llarg del país."""
    from difflib import SequenceMatcher

    per_pais: dict[str, list[str]] = defaultdict(list)
    for p in partides:
        for c in (p.a, p.b):
            if c.jugador not in per_pais[c.nacio or ""]:
                per_pais[c.nacio or ""].append(c.jugador)
    canon: dict[tuple[str, str], str] = {}
    for pais, noms in per_pais.items():
        for n in noms:
            kn = clau(n)
            # Primer la llista de jugadors, que té el nom sencer i ben escrit.
            amb_llista = [x for x in llista if clau(x).startswith(kn)] if len(kn) >= 8 else []
            if len(amb_llista) != 1:
                amb_llista = [x for x in llista if clau(x) == kn] or sorted(
                    (x for x in llista if SequenceMatcher(None, kn, clau(x)).ratio() >= 0.92),
                    key=lambda x: -SequenceMatcher(None, kn, clau(x)).ratio(),
                )[:1]
            if amb_llista:
                canon[(pais, n)] = amb_llista[0]
                continue
            millor = n
            for altre in noms:
                kn, ka = clau(n), clau(altre)
                if altre == n or len(ka) <= len(kn):
                    continue
                semblant = ka.startswith(kn) or SequenceMatcher(None, kn, ka).ratio() >= 0.9
                if semblant and len(altre) > len(millor):
                    millor = altre
            canon[(pais, n)] = millor
    for p in partides:
        for c in (p.a, p.b):
            c.jugador = canon[(c.nacio or "", c.jugador)]


# ------------------------------------ una prova ------------------------------------


def _text(cami: Path, y_tolerance: float = 3) -> str:
    # Alguns PDF antics imprimeixen el text dues vegades desplaçat («NNGGOO»): es treu el duplicat.
    with pdfplumber.open(cami) as pdf:
        return "\n".join(
            (p.dedupe_chars().extract_text(y_tolerance=y_tolerance) or "") for p in pdf.pages
        )


def _fase_del_fitxer(cami: Path) -> str:
    return re.sub(r"^[A-Z]\.\s*", "", cami.stem).replace("_", " ")


def llegeix_prova(carpeta: Path) -> Llegit:
    """Llegeix tots els PDF d'una carpeta de prova; un PDF dolent no tomba els altres."""
    res = Llegit()
    textos: dict[Path, str] = {}
    for cami in sorted(carpeta.glob("*.pdf")):
        try:
            textos[cami] = _text(cami)
        except Exception as e:  # PDF truncat o malmès
            res.errors.append(f"{cami.name}: il·legible ({type(e).__name__})")

    # Primer la llista de jugadors: dóna els noms amb què es reconeixen els enganxats.
    for cami, text in textos.items():
        capcalera = "\n".join(text.splitlines()[:6])
        if re.search(r"(?i)players\s+list", capcalera):
            try:
                js = llegeix_jugadors(text)
            except Exception as e:
                res.errors.append(f"{cami.name}: {type(e).__name__}: {e}")
                continue
            res.jugadors.extend(js)
            res.llegits.append(cami.name)
    per_clau = {clau(j.nom): j for j in res.jugadors}
    conegut = set(per_clau)

    nacions = _nacions_de(list(textos.values()))
    llista_equips = [n for t in textos.values() for n in noms_de_la_llista_d_equips(t, nacions)]
    for cami, text in textos.items():
        if cami.name in res.llegits:
            continue
        try:
            if re.search(r"(?mi)^(Round\s+Counter|Rank)\s+Players", text):
                # El número de lloc va a una altura una mica diferent de la resta de la fila.
                rows = llegeix_classificacio(_text(cami, y_tolerance=5))
                if rows:
                    res.classificacio = rows
                    res.llegits.append(cami.name)
                continue
            if es_equips(text):
                ps, errs = llegeix_equips(text, nacions, _fase_del_fitxer(cami))
                res.errors.extend(f"{cami.name}: {e}" for e in errs)
                if ps:
                    res.partides.extend(ps)
                    res.llegits.append(cami.name)
                continue
            if re.search(r"(?i)group\s+match|match\s*players", text) and re.search(
                r"(?i)t-?\s?car", text
            ):
                ps, errs = llegeix_partides(text, conegut, _fase_del_fitxer(cami))
                res.errors.extend(f"{cami.name}: {e}" for e in errs)
                if ps:
                    res.partides.extend(ps)
                    res.llegits.append(cami.name)
        except PdfNoReconegut as e:
            res.errors.append(f"{cami.name}: {e}")
        except Exception as e:
            res.errors.append(f"{cami.name}: {type(e).__name__}: {e}")

    # L'ordre és de tota la prova: dos PDF no han de repetir la clau.
    for i, p in enumerate(res.partides, 1):
        p.ordre = i

    # Les partides porten el nom tal com el PDF el té; el canònic és el de la llista.
    nats: dict[str, str] = {c.jugador: c.nacionalitat for c in res.classificacio if c.nacionalitat}
    nom_de: dict[str, str] = {}

    def canon(n: str) -> str:
        if n not in nom_de:
            j = per_clau.get(clau(n))
            nom_de[n] = j.nom if j else separa_nom(n)
        return nom_de[n]

    equips = [p for p in res.partides if p.a.nacio]
    if equips:
        _unifica_noms(equips, llista_equips)
    for c in res.classificacio:
        c.jugador = canon(c.jugador)
    for p in res.partides:
        p.a.jugador = canon(p.a.jugador)
        p.b.jugador = canon(p.b.jugador)
    # Jugadors que surten a partides o classificació però no a la llista (o llista absent).
    coneguts = {j.nom for j in res.jugadors}
    nat_per_clau = {clau(k): v for k, v in nats.items()}
    for j in res.jugadors:
        if not j.nacionalitat:
            j.nacionalitat = nat_per_clau.get(clau(j.nom))
    nous = {c.jugador: c.nacionalitat for c in res.classificacio}
    for p in res.partides:
        nous.setdefault(p.a.jugador, p.a.nacio)
        nous.setdefault(p.b.jugador, p.b.nacio)
    for nom, nat in nous.items():
        if nom not in coneguts:
            res.jugadors.append(Jugador(nom=nom, nacionalitat=nat))
            coneguts.add(nom)
    return res
