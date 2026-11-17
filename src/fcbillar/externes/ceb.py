"""Partides de la Confederació Europea de Billar (eurobillard.org).

Cada esdeveniment té una pàgina `/events/<qualsevol cosa>-<id>.html` amb
pestanyes. La de partides («Matches», `onglet_8`) les porta totes de cop, de la
primera ronda a la final, amb caramboles, entrades, mitjana i sèrie major de
cada jugador. La de jugadors (`onglet_6`) dona el país de cadascun.

El text que hi ha abans del guió de la URL no importa: el servidor només mira
l'id. Les Copes del Món surten al calendari però sense partides; aquelles les
dona la UMB.
"""

from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime

from fcbillar.externes.model import (
    AMBIT_INTERNACIONAL,
    Esdeveniment,
    Partida,
    Resultat,
    modalitat_de,
    tipus_de,
)

URL_ESDEVENIMENT = "https://www.eurobillard.org/events/e-{id}.html"


class SensePartides(ValueError):
    """La pàgina no és d'un esdeveniment de carambola que ens interessi, o no té partides."""


def _net(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _camp(pagina: str, nom: str) -> str:
    m = re.search(
        rf'<div class="field col-xs">{re.escape(nom)}</div>\s*<div class="value col-xs">(.*?)</div>',
        pagina,
        re.S,
    )
    return _net(m.group(1)) if m else ""


def _seccio(pagina: str, onglet: int) -> str:
    inici = pagina.find(f'id="onglet_{onglet}"')
    if inici < 0:
        return ""
    fi = pagina.find('id="onglet_', inici + 10)
    return pagina[inici : fi if fi > 0 else len(pagina)]


def _data(text: str) -> date | None:
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", text)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _parella(cela: str, conv=int) -> tuple:
    """Els dos valors d'una cel·la, un per jugador (`<span>a</span><br><span>b</span>`)."""
    valors = [_net(v) for v in re.findall(r"<span[^>]*>(.*?)</span>", cela, re.S)]
    if not valors:
        valors = [v.strip() for v in re.split(r"<br\s*/?>", re.sub(r"</?div[^>]*>", "", cela))]
    valors = [v for v in valors if v != ""]

    def u(v):
        try:
            return conv(v)
        except ValueError:
            return None

    if len(valors) == 1:
        # Les entrades d'una partida de carambola són les mateixes per als dos.
        return u(valors[0]), u(valors[0])
    if len(valors) >= 2:
        return u(valors[0]), u(valors[1])
    return None, None


def _nacions(pagina: str) -> dict[str, str]:
    """Nom del jugador → codi del país, de la pestanya de jugadors."""
    nacions: dict[str, str] = {}
    for nom, pais in re.findall(r">\s*([^<>()]+?)\s*\(([A-Z]{3})\)\s*<", _seccio(pagina, 6)):
        nacions[re.sub(r"\s+", " ", html_lib.unescape(nom)).strip()] = pais
    return nacions


def llegeix_esdeveniment(pagina: str, id_: int | str) -> Resultat:
    """Esdeveniment i partides d'una pàgina d'esdeveniment de la CEB.

    Llança `SensePartides` si no és de cap modalitat de carambola que es desi,
    si no és un Mundial, un Europeu o una Copa del Món, o si no té partides.
    """
    titol = re.search(r"<title>([^<]*)", pagina)
    nom = html_lib.unescape(titol.group(1)).strip() if titol else ""
    disciplina = _camp(pagina, "Discipline")
    modalitat = modalitat_de(disciplina)
    if modalitat is None:
        raise SensePartides(f"disciplina «{disciplina}»")
    tipus = tipus_de(nom)
    if tipus is None:
        raise SensePartides(f"«{nom}» no és un Mundial, un Europeu ni una Copa del Món")

    dates = _camp(pagina, "Event dates")
    trossos = dates.split(" - ")
    esdeveniment = Esdeveniment(
        font="ceb",
        id=str(id_),
        nom=nom,
        modalitat=modalitat,
        ambit=AMBIT_INTERNACIONAL,
        tipus=tipus,
        data_inici=_data(trossos[0]) if trossos else None,
        data_fi=_data(trossos[-1]) if trossos else None,
        lloc=", ".join(x for x in (_camp(pagina, "City"), _camp(pagina, "Country")) if x),
        url=URL_ESDEVENIMENT.format(id=id_),
    )

    seccio = _seccio(pagina, 8)
    if "select-matchs" not in seccio:
        raise SensePartides("sense pestanya de partides")
    nacions = _nacions(pagina)
    partides: list[Partida] = []
    for bloc in re.split(r'<div class="box_ligne">', seccio)[1:]:
        celes = re.findall(
            r'<div class="c_(\d+)(?: center)? col-s">(.*?)</div>\s*(?=<div class="c_|</div>|$)',
            bloc,
            re.S,
        )
        if len(celes) < 10:
            continue
        valors = [c[1] for c in celes]
        quan = _net(valors[0])
        try:
            ordre = int(_net(valors[1]))
        except ValueError:
            continue
        noms = [
            re.sub(r"\s+", " ", html_lib.unescape(n)).strip()
            for n in re.findall(r"<span[^>]*>(.*?)</span>", valors[5], re.S)
        ]
        if len(noms) != 2 or not all(noms):
            continue
        p1, p2 = _parella(valors[6])
        c1, c2 = _parella(valors[7])
        e1, e2 = _parella(valors[8])
        s1, s2 = _parella(valors[10]) if len(valors) > 10 else (None, None)
        moment = None
        try:
            moment = datetime.strptime(quan, "%d-%m-%Y %H:%M").date()
        except ValueError:
            moment = _data(quan)
        partides.append(
            Partida(
                ordre=ordre,
                jugador1=noms[0],
                jugador2=noms[1],
                caramboles1=c1,
                caramboles2=c2,
                entrades1=e1,
                entrades2=e2,
                serie1=s1,
                serie2=s2,
                punts1=p1,
                punts2=p2,
                data=moment,
                fase=_net(valors[3]),
                grup=_net(valors[4]),
                nacio1=nacions.get(noms[0], ""),
                nacio2=nacions.get(noms[1], ""),
            )
        )
    if not partides:
        raise SensePartides("la pestanya de partides és buida")
    return Resultat(esdeveniment=esdeveniment, partides=partides)
