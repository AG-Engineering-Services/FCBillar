"""Composició de la Lliga Catalana de Tres Bandes 2026-27 a partir dels inscrits.

`projeccio_lliga_2627.py` va projectar la composició abans de saber qui
s'inscriuria: la va derivar de les classificacions oficials 2025-26 i dels
play-offs de promoció. Ara la federació ja publica els **equips inscrits**
(pàgina nova del web d'agost de 2026), i aquest script confronta les dues coses:

- quins equips projectats no s'han inscrit,
- quins equips s'han inscrit de nou,
- i on va cada nou equip.

**Regla de sembra dels nous**: un equip nou entra just darrere de l'últim equip
del seu club — el pitjor classificat la temporada passada. És la mateixa lògica
que fa servir la federació: un club no pot col·locar un equip nou per sobre dels
que ja tenia. Els clubs que no hi eren van al final de tot.

Divisions: 16 equips en dos grups (Honor, 1a, 2a, 3a) i la resta a 4a, repartida
en quatre grups.

    uv run python scripts/inscripcions_lliga_2627.py
    uv run python scripts/inscripcions_lliga_2627.py --json data/lliga2627_inscrits.json
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from fcbillar.scraper import parsers as P  # noqa: E402
from fcbillar.scraper import urls as U  # noqa: E402
from fcbillar.scraper.taules import taula_amb  # noqa: E402

LLIGA_3B = 38  # Lliga Catalana Tres Bandes 2026-27 (la 39 és la de 4 Modalitats)
PROJECCIO = Path(__file__).with_name("projeccio_lliga_2627.py")

#: Divisions de 16 en dos grups; la 4a s'endú la resta en quatre grups.
DIVISIONS = ("Honor", "1a", "2a", "3a")
MIDA_DIVISIO = 16
GRUPS = {"Honor": 2, "1a": 2, "2a": 2, "3a": 2, "4a": 4}

# El cens oficial de clubs va canviar de nom en unes quantes entrades quan la
# federació va passar el llistat al WordPress. Aquestes equivalències estan
# comprovades contra l'adreça de cada club al llistat oficial nou —en particular
# «C.B.SANT FELIU», que és el de Sant Feliu de CODINES i no el de Llobregat.
EQUIVALENTS = {
    "BELMASNOU": "BILLARELMASNOU",
    "CBCANET": "CBCANETDEMAR",
    "SBFOMENTMOLINS": "SBFMOLINS",
    "CASALDECERVERA": "SECASALCERVERA",
    "BCSANTFELIUDECODINES": "CBSANTFELIU",
    "BLAUNIOCORAL": "SBLAUNIOCORAL",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.upper())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]", "", s)


def clau_club(nom: str) -> str:
    k = _norm(nom)
    return EQUIVALENTS.get(k, k)


def lletra(nom_equip: str) -> str:
    """La lletra final de l'equip, o '' si el club només en té un."""
    m = re.search(r"[\"“”'](\w)[\"“”']\s*$", nom_equip.strip())
    return m.group(1).upper() if m else ""


@dataclass
class Equip:
    club: str  # nom oficial del club
    nom: str  # nom de l'equip tal com s'inscriu
    divisio: str  # divisió assignada
    grup: str  # "A", "B", ...
    seed: int  # posició a l'ordre general de sembra
    origen: str  # "projectat" | "nou" | "club nou"


def carrega_projeccio(path: Path = PROJECCIO) -> list[tuple[str, str, str]]:
    """L'ordre de sembra projectat, aplanat: [(divisió, club, lletra), ...]."""
    arbre = ast.parse(path.read_text(encoding="utf-8"))
    comp = None
    for node in arbre.body:
        destí = getattr(node, "target", None) or (
            node.targets[0] if isinstance(node, ast.Assign) else None
        )
        if getattr(destí, "id", "") == "COMP":
            comp = ast.literal_eval(node.value)
    if comp is None:
        raise SystemExit(f"No he trobat COMP a {path}")
    return [
        (div, club, lletra)
        for div in ("Honor", "1a", "2a", "3a", "4a")
        for club, lletra in comp[div]
    ]


def baixa_inscrits(lliga: int = LLIGA_3B) -> list[P.LligaEquipInscrit]:
    """Els equips inscrits a una lliga, o un error clar si no els podem llegir.

    Una llista buida no és una resposta acceptable: el parser en retorna una
    tant si la lliga no té ningú inscrit com si el que ha arribat és una pàgina
    d'error, un formulari de login o un marcatge que ha canviat. Publicar una
    composició buida amb pinta de bona seria pitjor que no publicar-ne cap, així
    que aquí ens plantem.
    """
    url = U.lligues_inscripcions(lliga)
    with httpx.Client(
        headers={"User-Agent": "FCBillar/2.0"}, follow_redirects=True, timeout=60.0
    ) as c:
        r = c.get(url)
    r.raise_for_status()

    if taula_amb(r.text, "Club", "Equip") is None:
        raise SystemExit(
            f"No hi ha taula d'inscripcions a {url} — o la federació ha tornat a "
            f"canviar el web, o la lliga {lliga} no és la que esperem. "
            f"No genero cap composició."
        )
    equips = P.parse_lliga_inscripcions(r.text)
    if not equips:
        raise SystemExit(
            f"Cap equip inscrit a {url}: o la lliga {lliga} no existeix, o encara "
            f"no s'hi ha apuntat ningú. En tots dos casos no hi ha res a repartir."
        )
    return equips


def ordena(
    projectats: list[tuple[str, str, str]],
    inscrits: list[P.LligaEquipInscrit],
    *,
    intercalat: bool = False,
) -> tuple[list[Equip], list[tuple[str, str, str]]]:
    """Ordre de sembra general i llista dels projectats que no s'han inscrit.

    Els equips d'un club s'aparellen per POSICIÓ, no per lletra: uns quants
    clubs han passat de tenir un sol equip sense lletra a tenir-ne «A» i «B», i
    aparellar per lletra els comptaria com a equips nous que no ho són.
    """
    per_club_proj: dict[str, list[int]] = {}
    for i, (_, club, _) in enumerate(projectats):
        per_club_proj.setdefault(clau_club(club), []).append(i)

    per_club_insc: dict[str, list[P.LligaEquipInscrit]] = {}
    for e in inscrits:
        per_club_insc.setdefault(clau_club(e.club), []).append(e)
    for equips in per_club_insc.values():
        equips.sort(key=lambda e: (lletra(e.equip) or "A", e.equip))

    # Cada posició projectada rep l'equip inscrit que li toca; els que sobren
    # d'un club són equips nous i entren darrere de l'últim que ja hi era.
    assignat: dict[int, P.LligaEquipInscrit] = {}
    darrere: dict[int, list[P.LligaEquipInscrit]] = {}
    clubs_nous: list[P.LligaEquipInscrit] = []

    for ck, equips in per_club_insc.items():
        posicions = per_club_proj.get(ck, [])
        if not posicions:
            clubs_nous.extend(equips)
            continue
        for i, e in enumerate(equips):
            if i < len(posicions):
                assignat[posicions[i]] = e
            else:
                darrere.setdefault(posicions[-1], []).append(e)

    ordre: list[tuple[P.LligaEquipInscrit, str]] = []
    no_inscrits: list[tuple[str, str, str]] = []
    for i, (div, club, llet) in enumerate(projectats):
        e = assignat.get(i)
        if e is None:
            no_inscrits.append((div, club, llet))
        else:
            ordre.append((e, "projectat"))
        if intercalat:
            ordre.extend((x, "nou") for x in darrere.get(i, []))

    if not intercalat:
        # Els equips nous entren per baix, tots a la 4a, i entre ells s'ordenen
        # per la classificació de l'últim equip del seu club la temporada
        # passada. Un equip nou no pot fer baixar de divisió un que ja hi era.
        for pos in sorted(darrere):
            ordre.extend((x, "nou") for x in darrere[pos])
    ordre.extend((e, "club nou") for e in clubs_nous)

    # Les places que deixen lliures els equips que no s'han inscrit les ocupa el
    # següent de l'ordre: cada divisió es tanca a 16 comptant els que hi són.

    # Repartiment: 16 per divisió i la resta a 4a; dins de cada divisió, els
    # grups es formen en serpentina perquè quedin equilibrats.
    resultat: list[Equip] = []
    i = 0
    for div in (*DIVISIONS, "4a"):
        talla = MIDA_DIVISIO if div != "4a" else len(ordre) - i
        bloc = ordre[i : i + talla]
        n = GRUPS[div]
        for j, (e, origen) in enumerate(bloc):
            volta, dins = divmod(j, n)
            grup = chr(ord("A") + (dins if volta % 2 == 0 else n - 1 - dins))
            resultat.append(
                Equip(
                    club=e.club,
                    nom=e.equip,
                    divisio=div,
                    grup=grup,
                    seed=j + 1,
                    origen=origen,
                )
            )
        i += talla
    return resultat, no_inscrits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lliga", type=int, default=LLIGA_3B)
    ap.add_argument(
        "--intercalat",
        action="store_true",
        help="Posa cada equip nou just darrere de l'ultim del seu club, en comptes "
        "d'enviar-los tots a la 4a divisio",
    )
    ap.add_argument("--json", type=Path, help="Desa el resultat en JSON")
    args = ap.parse_args()

    projectats = carrega_projeccio()
    inscrits = baixa_inscrits(args.lliga)
    equips, no_inscrits = ordena(projectats, inscrits, intercalat=args.intercalat)

    print(f"Inscrits: {len(inscrits)} · projectats: {len(projectats)}\n")
    for div in (*DIVISIONS, "4a"):
        dels = [e for e in equips if e.divisio == div]
        grups = sorted({e.grup for e in dels})
        print(f"── {div}  ({len(dels)} equips, {len(grups)} grups)")
        for g in grups:
            print(f"   Grup {g}")
            for e in [x for x in dels if x.grup == g]:
                marca = {"nou": "  ← nou", "club nou": "  ← club nou"}.get(e.origen, "")
                print(f"     {e.seed:2d}. {e.nom}{marca}")
        print()

    if no_inscrits:
        print(f"Projectats que no s'han inscrit ({len(no_inscrits)}):")
        for div, club, llet in no_inscrits:
            print(f"   {div:5s} {club} {llet}".rstrip())

    if args.json:
        args.json.write_text(
            json.dumps([asdict(e) for e in equips], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nDesat a {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
