"""Partides de la Unió Mundial de Billar (umb-carom.org).

La pàgina de cada esdeveniment (`/events/<id>`) enllaça un PDF per fase a
`files.umb-carom.org/Uploads/Results/<id>/`. Des del 2008 el programa de la UMB
n'ha tret de dues menes, i totes dues tenen la mateixa forma: dues línies per
partida, una per jugador, amb el nom, les caramboles, les entrades, la mitjana i
els punts de match.

- Grups: «A RAMIREZ Eleazar 40 29 40 29 1,379 2 7 5». Sense país; el porta la
  taula de resum del grup («Players Nat T-Car…»), que es fa servir només per a
  això.
- Eliminatòries: «MERCKX Eddy BE 50 35 0 1.428 2 8», amb el país.

Les columnes canvien d'un any a l'altre (sets, penalitzacions, caramboles
repetides després de l'equiparació). Per no dependre'n, les caramboles i les
entrades són el parell de nombres seguits que dona la mitjana impresa. Al
programa nou el cognom i el nom surten enganxats («CHOMyungWoo»): es tornen a
separar on comença la primera paraula en minúscules.
"""

from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime
from pathlib import Path

from fcbillar.externes.model import (
    AMBIT_INTERNACIONAL,
    Esdeveniment,
    Partida,
    modalitat_de,
    tipus_de,
)

URL_ESDEVENIMENT = "https://www.umb-carom.org/events/{id}"
URL_FITXERS = "https://files.umb-carom.org/Uploads/Results/{id}/"

_RE_DECIMAL = re.compile(r"^-?\d+[.,]\d+$")
_RE_ENTER = re.compile(r"^-?\d+$")
_RE_NACIO = re.compile(r"^[A-Z]{2}$")


class SensePartides(ValueError):
    """L'esdeveniment no és de carambola, no és un Mundial ni una Copa del Món, o no té resultats."""


# --- La pàgina de l'esdeveniment ---------------------------------------------


def _text(pagina: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", pagina, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html_lib.unescape(t)).strip()


def _data(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%A, %B %d, %Y").date()
    except ValueError:
        return None


def fitxers_de_resultats(pagina: str) -> list[str]:
    """Noms dels PDF de partides enllaçats, en l'ordre en què surten (per lletra).

    Es descarten les llistes de jugadors, els grups, els horaris i les
    classificacions: només interessen els que porten partides.
    """
    noms = sorted(set(re.findall(r"Uploads/Results/\d+/([^\"]+?\.pdf)", pagina)))
    triats = []
    for nom in noms:
        n = nom.lower()
        if any(x in n for x in ("ranking", "rank_pdf", "training", "time table", "players list")):
            continue
        if "result" in n or "groups_pdf" in n or re.search(r"(^|\. )mt[ _]", n):
            triats.append(nom)
    return triats


def llegeix_esdeveniment(pagina: str, id_: int | str) -> Esdeveniment:
    """Les dades de l'esdeveniment, o `SensePartides` si no és dels que es desen."""
    t = _text(pagina)
    m = re.search(
        r"Event Details (.*?) Event Details Dates: (.*?) Country: (.*?) Type: (.*?) Organization",
        t,
    )
    if m is None:
        raise SensePartides("la pàgina no té la fitxa de l'esdeveniment")
    nom, dates, pais, tipus_umb = (g.strip() for g in m.groups())
    if "cancel" in nom.lower():
        raise SensePartides(f"«{nom}» es va anul·lar")
    modalitat = modalitat_de(nom)
    if modalitat is None:
        raise SensePartides(f"«{nom}» no és de cap modalitat de carambola que es desi")
    tipus = tipus_de(f"{tipus_umb} {nom}")
    if tipus is None:
        raise SensePartides(f"«{nom}» ({tipus_umb}) no és un Mundial ni una Copa del Món")
    trossos = dates.split(" - ")
    return Esdeveniment(
        font="umb",
        id=str(id_),
        nom=nom,
        modalitat=modalitat,
        ambit=AMBIT_INTERNACIONAL,
        tipus=tipus,
        data_inici=_data(trossos[0]),
        data_fi=_data(trossos[-1]),
        lloc=pais,
        url=URL_ESDEVENIMENT.format(id=id_),
    )


def fase_del_fitxer(nom: str) -> str:
    """«J. GroupResults_Q.pdf» → «Q»; «M. MT 1_8.pdf» → «1/8»; «P. MTResults_Quarter_Final.pdf» → «Quarter Final»."""
    n = re.sub(r"^[A-Z]\.\s*", "", Path(nom).stem)
    n = re.sub(r"(?i)^(group ?results_|mtresults_|mt )", "", n)
    n = re.sub(r"(?i)(-groups)?_pdf$", "", n)
    n = re.sub(r"(\d)_(\d)", r"\1/\2", n)
    return n.replace("_", " ").replace("-", " ").strip()


# --- Els PDF ----------------------------------------------------------------


def separa_nom(nom: str) -> str:
    """«CHOMyungWoo» → «CHO MyungWoo». Si ja hi ha espais o és tot majúscules, igual."""
    nom = re.sub(r"\s+", " ", nom).strip()
    if " " in nom:
        return nom
    m = re.match(r"^(.+?)([A-ZÀ-Þ][a-zß-ÿ].*)$", nom)
    if m and m.group(1).upper() == m.group(1):
        return f"{m.group(1)} {m.group(2)}"
    return nom


def _clau(nom: str) -> str:
    return re.sub(r"[^A-Z]", "", nom.upper())


def _numero(text: str) -> float:
    return float(text.replace(",", "."))


def _columnes_despres_de_la_mitjana(capcalera: str) -> list[str]:
    c = re.sub(r"(1st|2nd)\s+HR", r"\1HR", capcalera)
    c = re.sub(r"Gen-Av", "Av", c)
    tokens = c.split()
    for i, tok in enumerate(tokens):
        if tok in ("Av", "Avg", "G.Avg"):
            return tokens[i + 1 :]
    return []


def _linia_de_partida(linia: str, despres: list[str]) -> dict | None:
    tokens = linia.split()
    if not tokens:
        return None
    grup = ""
    if len(tokens) > 2 and re.fullmatch(r"[A-Z]", tokens[0]) and not _RE_ENTER.match(tokens[1]):
        grup, tokens = tokens[0], tokens[1:]
    # El nom: tot el que hi ha abans del primer nombre, menys el país.
    i = 0
    while i < len(tokens) and not (_RE_ENTER.match(tokens[i]) or _RE_DECIMAL.match(tokens[i])):
        i += 1
    if i == 0 or i == len(tokens):
        return None
    paraules = tokens[:i]
    nacio = ""
    if len(paraules) > 1 and _RE_NACIO.match(paraules[-1]):
        nacio, paraules = paraules[-1], paraules[:-1]
    resta = tokens[i:]
    pos_mitjana = next((k for k in range(len(resta) - 1, -1, -1) if _RE_DECIMAL.match(resta[k])), None)
    if pos_mitjana is None:
        return None
    mitjana = _numero(resta[pos_mitjana])
    abans = [int(x) for x in resta[:pos_mitjana] if _RE_ENTER.match(x)]
    despres_vals = [int(x) for x in resta[pos_mitjana + 1 :] if _RE_ENTER.match(x)]
    parell = None
    for k in range(len(abans) - 2, -1, -1):
        car, ent = abans[k], abans[k + 1]
        if ent > 0 and abs(car / ent - mitjana) < 0.0015:
            parell = (car, ent)
            break
        if ent > 0 and car == 0 and mitjana == 0:
            parell = (car, ent)
            break
    if parell is None:
        return None
    punts = serie = None
    if "MP" in despres and despres.index("MP") < len(despres_vals):
        punts = despres_vals[despres.index("MP")]
    hr = next((j for j, c in enumerate(despres) if "HR" in c), None)
    if hr is not None and hr < len(despres_vals):
        serie = despres_vals[hr]
    return {
        "grup": grup,
        "nom": separa_nom(" ".join(paraules)),
        "nacio": nacio,
        "car": parell[0],
        "ent": parell[1],
        "punts": punts,
        "serie": serie,
    }


def llegeix_text(text: str, fase: str, ordre_inicial: int = 1) -> list[Partida]:
    """Les partides del text d'un PDF de resultats de la UMB."""
    partides: list[Partida] = []
    nacions: dict[str, str] = {}
    despres: list[str] = []
    a_resum = False
    pendent: dict | None = None
    grup = ""
    pendents_de_nacio: list[Partida] = []
    #: On comença el grup en curs: la lletra del grup surt a qualsevol línia del
    #: bloc (al programa nou, a la del mig), i val per a totes les seves partides.
    inici_bloc = 0
    fase_en_curs = fase
    for linia in text.splitlines():
        linia = linia.strip()
        if m := re.search(r"Main Tournament\s*-\s*(.+)$", linia):
            # Semifinals i final van al mateix PDF, cadascuna amb el seu títol.
            fase_en_curs = m.group(1).replace("_", " ").strip()
            continue
        if re.search(r"\bPlayers\b.*\bNat\b", linia) and re.search(r"Place", linia):
            a_resum, pendent = True, None
            continue
        if re.search(r"(Match\s*players|MatchPlayers|Match players)", linia, re.I):
            despres = _columnes_despres_de_la_mitjana(linia)
            a_resum, pendent = False, None
            inici_bloc, grup = len(partides), ""
            continue
        if a_resum:
            # «TASDEMIR Tayfun TR 80 52 1,538 4 9 8 1»: només en volem el país.
            m = re.match(r"^(.*?)\s([A-Z]{2})\s+\d", linia)
            if m:
                nacions[_clau(m.group(1))] = m.group(2)
            continue
        if not despres:
            continue
        fila = _linia_de_partida(linia, despres)
        if fila is None:
            continue
        if fila["grup"]:
            grup = fila["grup"]
            for anterior in partides[inici_bloc:]:
                anterior.grup = grup
        if pendent is None:
            pendent = fila
            continue
        a, b = pendent, fila
        if abs(a["ent"] - b["ent"]) > 1:
            # Els dos jugadors d'una partida tenen les mateixes entrades (una de
            # diferència amb la sortida). Si no quadren, la primera línia era
            # solta: es descarta i la segona espera la seva parella.
            pendent = b
            continue
        pendent = None
        p = Partida(
            ordre=ordre_inicial + len(partides),
            jugador1=a["nom"],
            jugador2=b["nom"],
            caramboles1=a["car"],
            caramboles2=b["car"],
            entrades1=a["ent"],
            entrades2=b["ent"],
            serie1=a["serie"],
            serie2=b["serie"],
            punts1=a["punts"],
            punts2=b["punts"],
            fase=fase_en_curs,
            grup=grup,
            nacio1=a["nacio"],
            nacio2=b["nacio"],
        )
        partides.append(p)
        pendents_de_nacio.append(p)
    for p in pendents_de_nacio:
        p.nacio1 = p.nacio1 or nacions.get(_clau(p.jugador1), "")
        p.nacio2 = p.nacio2 or nacions.get(_clau(p.jugador2), "")
    return partides


def text_del_pdf(cami: str | Path) -> str:
    import pdfplumber

    with pdfplumber.open(str(cami)) as pdf:
        return "\n".join(pagina.extract_text() or "" for pagina in pdf.pages)
