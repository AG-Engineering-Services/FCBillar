"""Partides de la web de la RFEB d'abans del 2012 (`rfeb.org/0HOME/PDF/…`, via Wayback).

La web vella només es pot recuperar de web.archive.org (`rfeb_wayback`), i els
PDF que hi queden són de tres maneres:

- **Una línia per jugador**: `[núm.] NOM FED caramboles [entrades] mitjana [sèrie]`.
  Dues línies seguides són una partida. Als de Gijón hi ha dues columnes de
  partides a la mateixa línia, i cada columna s'aparella per separat. Als del
  Campionat d'Espanya del 2009 i del 2010 les entrades no hi són, o van en una
  línia a part entre lletres girades (l'hora i el dia escrits en vertical): es
  treuen de les caramboles i la mitjana. Les dues línies d'una partida han de
  donar les mateixes entrades; si no, la primera es descarta i es torna a provar
  amb la següent. Es compta tot el que es descarta.
- **Seleccions autonòmiques**: `[núm.] JUGADOR A car car JUGADOR B en entrades`,
  sota una capçalera `Selecc: SELECCIÓ A [punts punts] SELECCIÓ B`.

Les proves no surten de cap llistat: cada PDF que es llegeix és a `PROVES` amb
el que se'n sap del medaller de la RFEB (edició, temporada, seu). Un PDF que no
hi és no es carrega.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from fcbillar.rfeb_fases_pdf import _quadra, desa_partides
from fcbillar.rfeb_fulls import PartidaFull


@dataclass(frozen=True)
class Prova:
    id: str
    temporada: str
    tipus: str  # 'ce', 'gpe' o 'seleccions'
    titol: str
    lloc: str | None
    inici: str | None
    fi: str | None
    #: (camí dins de `0HOME/PDF`, fase, format)
    fitxers: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    #: La classificació final (certificat del director esportiu o rànquing), si n'hi ha.
    classificacio: str | None = None


#: Les proves de la web vella que es carreguen. La temporada, l'edició i la seu
#: són les del medaller de la RFEB (proves del Gran Premi i seleccions).
PROVES: tuple[Prova, ...] = (
    Prova(
        "0HOME/asturias_2008",
        "2007-2008",
        "gpe",
        'XV Trofeo "Príncipe de Asturias"',
        "Pabellón Deportes de La Arena, Gijón",
        "2008-07-07",
        "2008-07-13",
        (
            ("asturias/PdA_FP.pdf", "Fase prèvia", "jugadors"),
            ("asturias/PdA_FF.pdf", "Fase final", "jugadors"),
        ),
    ),
    Prova(
        "0HOME/asturias_2009",
        "2008-2009",
        "gpe",
        'XVI Trofeo "Príncipe de Asturias"',
        "Pabellón Deportes de La Arena, Gijón",
        "2009-07-06",
        "2009-07-12",
        (("asturias/PdA_FP09.pdf", "Fase prèvia i final", "jugadors"),),
    ),
    Prova(
        "0HOME/asturias_2010",
        "2009-2010",
        "gpe",
        'XVII Trofeo "Príncipe de Asturias"',
        "Pabellón Deportes de La Arena, Gijón",
        "2010-07-05",
        "2010-07-11",
        (("asturias/PdA_FP10.pdf", "Fase prèvia i final", "jugadors"),),
        classificacio="asturias/PdA_Rnk10.pdf",
    ),
    Prova(
        "0HOME/castalla_2009",
        "2008-2009",
        "ce",
        "LXXV Campeonato de España de Billar a Tres Bandas",
        "C.B. Caseta Nova, Castalla (Alicante)",
        None,
        "2009-02-22",
        (
            ("Castalla/Fase_Previa.pdf", "Fase prèvia", "jugadors"),
            ("Castalla/Fase_final.pdf", "Fase final", "jugadors"),
        ),
        classificacio="Castalla/Clasif.pdf",
    ),
    Prova(
        "0HOME/alcantarilla_2008",
        "2007-2008",
        "gpe",
        'I Trofeo "Villa de Alcantarilla"',
        'Pabellón Deportes "Magritas", Alcantarilla (Murcia)',
        None,
        "2008-05-11",
        # Les fases (Alcantarilla_FP i _FF) són truncades a Wayback: només la classificació.
        (),
        classificacio="Alcantarilla_RK.pdf",
    ),
    Prova(
        "0HOME/lxxvi_ce_2010",
        "2009-2010",
        "ce",
        "LXXVI Campeonato de España de Billar a Tres Bandas",
        "Centro Cívico Parque Almansa, San Javier (Murcia)",
        None,
        None,
        (
            ("LXXVI-CE/Resultados.pdf", "Fase prèvia", "jugadors"),
            ("LXXVI-CE/Resultados-FF.pdf", "Fase final", "jugadors"),
        ),
    ),
    Prova(
        "0HOME/selecciones_2009",
        "2008-2009",
        "seleccions",
        "XIV Campeonato de España de Selecciones Autonómicas",
        "C.B. Paiporta (Valencia)",
        None,
        None,
        (
            ("CE_Sel_Aut-GrupoB.pdf", "Fase de grups", "seleccions"),
            ("CE_Sel_Aut-GrupoC.pdf", "Fase de grups", "seleccions"),
            ("CE_Sel_Aut-GrupoD.pdf", "Fase de grups", "seleccions"),
        ),
    ),
    Prova(
        "0HOME/selecciones_2011",
        "2010-2011",
        "seleccions",
        "XVI Campeonato de España de Selecciones Autonómicas",
        "Hotel Alfonso XIII, Cartagena",
        None,
        None,
        (
            ("CE-Msc-SelAut-GrA-2011.pdf", "Fase de grups", "seleccions"),
            ("CE-Msc-SelAut-GrB-2011.pdf", "Fase de grups", "seleccions"),
            ("CE-Msc-SelAut-GrC-2011.pdf", "Fase de grups", "seleccions"),
            ("CE-Msc-SelAut-Semif-2011.pdf", "Semifinals", "seleccions"),
            ("CE-Msc-SelAut-Final-2011.pdf", "Final", "seleccions"),
        ),
    ),
)

# --- Una línia per jugador ---------------------------------------------------

_JUGADOR = re.compile(
    r"(?:(?P<num>\d{1,3})\s*º?\s+)?"
    r"(?P<nom>[^\W\d_][^\d,()]*?)\s+"
    r"(?P<fed>[A-Z](?:[A-Za-z]{1,3})?-[A-Za-z]{1,3}|[A-Z][A-Za-z]{1,3})\s+"
    r"(?P<car>\d{1,3})(?:\s+(?P<ent>\d{1,3}))?(?:\s+[PGE])?\s+"
    r"(?P<prom>\d{1,2},\d{3,4})(?:\s+(?P<sm>\d{1,3}))?(?=\s|$)"
)
#: Lletres soltes del marge (el dia i l'hora en vertical) que queden davant del nom.
_SOROLL_DAVANT = re.compile(r"^(?:[^\W\d_]{1,2}\s+)+")


@dataclass
class _Jugador:
    nom: str
    fed: str
    car: int
    ent: int | None  # None: no es pot saber (zero caramboles sense entrades)
    sm: int | None


def _jugadors_de_linia(text: str) -> list[_Jugador]:
    out = []
    for m in _JUGADOR.finditer(text):
        nom = _SOROLL_DAVANT.sub("", m.group("nom")).strip()
        if len(nom) < 4 or " " not in nom:
            continue
        car = int(m.group("car"))
        prom = float(m.group("prom").replace(",", "."))
        if m.group("ent"):
            ent: int | None = int(m.group("ent"))
            if not _quadra(car, ent, prom):
                continue
        elif prom > 0:
            ent = round(car / prom)
            if not _quadra(car, ent, prom):
                continue
        elif car == 0:
            ent = None
        else:
            continue
        sm = int(m.group("sm")) if m.group("sm") else None
        if nom.isupper():
            nom = nom.title()
        out.append(_Jugador(nom, m.group("fed"), car, ent, sm if sm is None or sm <= car else None))
    return out


_FINAL_CAR = re.compile(r"\s[A-Z][A-Za-z\-]{0,5}\s+\d{1,3}$")
_NOMES_NUM = re.compile(r"^\d{1,3}$")
_NOMES_PROM = re.compile(r"^\d{1,2},\d{3,4}(?:\s+\d{1,3})?$")


def _ajunta_partides(linies: list[str]) -> list[str]:
    """Una línia de jugador partida en dues o tres («… MUR 24», «50», «0,4800 3») es torna a ajuntar."""
    out: list[str] = []
    i = 0
    while i < len(linies):
        t = linies[i]
        if _FINAL_CAR.search(t):
            if (
                i + 2 < len(linies)
                and _NOMES_NUM.match(linies[i + 1])
                and _NOMES_PROM.match(linies[i + 2])
            ):
                out.append(f"{t} {linies[i + 1]} {linies[i + 2]}")
                i += 3
                continue
            if i + 1 < len(linies) and _NOMES_PROM.match(linies[i + 1]):
                out.append(f"{t} {linies[i + 1]}")
                i += 2
                continue
        out.append(t)
        i += 1
    return out


def llegeix_jugadors(linies: list[str], fase: str) -> tuple[list[PartidaFull], int]:
    """Partides d'un PDF d'una línia per jugador i quants jugadors s'han descartat."""
    columnes: dict[int, list[_Jugador]] = {}
    for text in _ajunta_partides(linies):
        for i, j in enumerate(_jugadors_de_linia(text)):
            columnes.setdefault(i, []).append(j)
    partides: list[PartidaFull] = []
    descartats = 0
    for col in (columnes[k] for k in sorted(columnes)):
        i = 0
        while i + 1 < len(col):
            a, b = col[i], col[i + 1]
            ent = a.ent if a.ent is not None else b.ent
            if ent is None or (a.ent is not None and b.ent is not None and a.ent != b.ent):
                descartats += 1
                i += 1
                continue
            punts = (2, 0) if a.car > b.car else (0, 2) if b.car > a.car else (1, 1)
            partides.append(
                PartidaFull(
                    fase=fase,
                    grup="",
                    ordre=len(partides) + 1,
                    jugador_a=a.nom,
                    equip_a=a.fed,
                    caramboles_a=a.car,
                    serie_a=a.sm,
                    punts_a=punts[0],
                    jugador_b=b.nom,
                    equip_b=b.fed,
                    caramboles_b=b.car,
                    serie_b=b.sm,
                    punts_b=punts[1],
                    entrades=ent,
                )
            )
            i += 2
        descartats += len(col) - i
    return partides, descartats


# --- Seleccions ----------------------------------------------------------------

_SELECCIONS = (
    "CATALANA",
    "MADRILEÑA",
    "VALENCIANA",
    "MURCIANA",
    "ANDALUZA",
    "ASTURIANA",
    "BALEAR",
    "CÁNTABRA",
    "CAST. LA MANCHA",
    "CASTELLANO LEONESA",
    "CAST. Y LEÓN",
    "EUSKADI",
    "EXTREMEÑA",
    "GALLEGA",
    "ARAGONESA",
    "CANARIA",
    "RIOJANA",
    "NAVARRA",
)
_CAP_SELECC = re.compile(r"^Selecc:\s+(?P<resta>.+)$")
_PARTIDA_SELECC = re.compile(
    r"(?:(?<=\s)|^)(?:\d\s+)?(?P<a>[^\W\d_][^\d]*?)\s+(?P<ca>\d{1,3})\s+(?P<cb>\d{1,3})\s+"
    r"(?P<b>[^\W\d_][^\d]*?)\s+en\s+(?P<ent>\d{1,3})(?=\s+\d\s|\s*$)"
)
#: Capçalera de partit sense «Selecc:», una o dues per línia: «VALENCIANA 8 0 PAÍS VASCO».
_MAJ = r"[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ.\- ]*?"
_CAP_DOBLE = re.compile(rf"(?P<a>{_MAJ})\s+\d\s+\d\s+(?P<b>{_MAJ})(?=\s+{_MAJ}\s+\d\s+\d\s|\s*$)")
_NOMES_MAJ = re.compile(r"^[A-ZÁÉÍÓÚÑÜ0-9.\- ]+$")


def _dues_seleccions(resta: str) -> tuple[str | None, str | None]:
    """«EUSKADI 3 5 EXTREMEÑA» o «CATALANA CÁNTABRA» -> les dues seleccions."""
    m = re.match(r"^(?P<a>.+?)\s+\d+\s+\d+\s+(?P<b>.+)$", resta)
    if m:
        return m.group("a").strip(), m.group("b").strip()
    for s in _SELECCIONS:
        if resta.startswith(s + " ") and resta[len(s) + 1 :].strip() in _SELECCIONS:
            return s, resta[len(s) + 1 :].strip()
    return None, None


_LLISTA_GRUP = re.compile(
    r"(?:^|\s)\d\s*(?:\.-)?\s+([A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ.\- ]*?)(?=\s+\d\s*(?:\.-)?\s+\D|\s*$)"
)


def _seleccions_del_grup(linies: list[str]) -> set[str]:
    """Els noms de la llista del grup («1 VALENCIANA», «1.- ANDALUZA 3.- ASTURIANA»)."""
    out = set()
    for text in linies:
        if _NOMES_MAJ.match(text) and not _CAP_DOBLE.search(text):
            out |= {m.group(1).strip() for m in _LLISTA_GRUP.finditer(text)}
    return {s for s in out if len(s) > 3}


def _parelles_capcalera(text: str, conegudes: set[str]) -> list[tuple[str | None, str | None]]:
    """«VALENCIANA 8 0 PAÍS VASCO ANDALUZA 6 2 CASTILLA LEÓN» -> dues parelles.

    El tros del mig porta el final d'una i el principi de l'altra: es parteix on
    tots dos costats són seleccions conegudes. Si no n'hi ha cap, no s'endevina.
    """
    trossos = [t.strip() for t in re.split(r"\s+\d\s+\d\s+", text)]
    if len(trossos) == 2:
        return [(trossos[0], trossos[1])]
    if len(trossos) == 3:
        paraules = trossos[1].split()
        for k in range(1, len(paraules)):
            b, a = " ".join(paraules[:k]), " ".join(paraules[k:])
            if b in conegudes and a in conegudes:
                return [(trossos[0], b), (a, trossos[2])]
    return [(None, None)]


def llegeix_seleccions(
    linies: list[str], fase: str, grup: str = ""
) -> tuple[list[PartidaFull], int]:
    """Partides de seleccions. Hi pot haver dos partits per línia (dues columnes): la
    capçalera porta dues parelles de seleccions i cada línia, dues partides."""
    partides: list[PartidaFull] = []
    descartats = 0
    parelles: list[tuple[str | None, str | None]] = []
    conegudes = set(_SELECCIONS) | _seleccions_del_grup(linies)
    for text in linies:
        if m := _CAP_SELECC.match(text):
            parelles = [_dues_seleccions(m.group("resta").strip())]
            if parelles[0][0] is None:
                descartats += 1
            continue
        if _NOMES_MAJ.match(text) and _CAP_DOBLE.search(text):
            parelles = _parelles_capcalera(text, conegudes)
            if any(a is None for a, _ in parelles):
                descartats += 1
            continue
        for i, m in enumerate(_PARTIDA_SELECC.finditer(text)):
            ca, cb, ent = int(m.group("ca")), int(m.group("cb")), int(m.group("ent"))
            sel_a, sel_b = parelles[i] if i < len(parelles) else (None, None)
            if sel_a is None or ent <= 0:
                descartats += 1
                continue
            nom_a, nom_b = (x.strip() for x in (m.group("a"), m.group("b")))
            nom_a, nom_b = (x.title() if x.isupper() else x for x in (nom_a, nom_b))
            punts = (2, 0) if ca > cb else (0, 2) if cb > ca else (1, 1)
            partides.append(
                PartidaFull(
                    fase=fase,
                    grup=grup,
                    ordre=len(partides) + 1,
                    jugador_a=nom_a,
                    equip_a=sel_a,
                    caramboles_a=ca,
                    serie_a=None,
                    punts_a=punts[0],
                    jugador_b=nom_b,
                    equip_b=sel_b,
                    caramboles_b=cb,
                    serie_b=None,
                    punts_b=punts[1],
                    entrades=ent,
                )
            )
    return partides, descartats


# --- Càrrega -----------------------------------------------------------------


def _linies(cami: Path) -> list[str]:
    import pdfplumber

    with pdfplumber.open(str(cami)) as pdf:
        return [
            li.strip()
            for p in pdf.pages
            for li in (p.dedupe_chars().extract_text() or "").split("\n")
            if li.strip()
        ]


@dataclass
class Resultat:
    prova: str
    fitxer: str
    partides: int
    descartats: int
    motiu: str = ""


def llegeix_fitxer(cami: Path, fase: str, format_: str) -> tuple[list[PartidaFull], int]:
    linies = _linies(cami)
    if format_ == "seleccions":
        m = re.search(r"Gr(?:upo)?-?([A-D])\b", cami.stem)
        return llegeix_seleccions(linies, fase, m.group(1) if m else "")
    return llegeix_jugadors(linies, fase)


#: Certificat del director esportiu: `final [inici] Jugador Fed PJ Car Ent Mitjana SM Punts`.
_CLAS_CERTIFICAT = re.compile(
    r"^(?P<pos>\d{1,3})\s+(?:\d{1,3}\s+)?(?P<nom>[^\d]+?)\s+(?P<fed>[A-Z][A-Za-z\-]{1,4})\s+"
    r"(?P<pj>\d{1,2})\s+(?P<car>\d{1,4})\s+(?P<ent>\d{1,4})\s+(?P<prom>\d,\d{3})\s+"
    r"(?P<sm>\d{1,2})\s+(?P<pts>\d{1,3})$"
)
#: Rànquing de Gijón: `1º Jugador Fed J Car Ent Mitjana-general Mitjana-particular SM Punts`.
_CLAS_RANQUING = re.compile(
    r"^(?P<pos>\d{1,3})º\s+(?P<nom>[^\d]+?)\s+(?P<fed>[A-Z][A-Za-z\-]{1,4})\s+"
    r"(?P<pj>\d{1,2})\s+(?P<car>\d{1,4})\s+(?P<ent>\d{1,4})\s+(?P<prom>\d,\d{3})\s+(?:\d,\d{3}|…)\s+"
    r"(?P<sm>\d{1,2})\s+(?P<pts>\d{1,3})$"
)


#: No presentat («wo», «W. O.») o retirat («Ret. indispuesto»): posició sense xifres.
_CLAS_SENSE_JUGAR = re.compile(
    r"^(?P<pos>\d{1,3})º?\s+(?:\d{1,3}\s+)?(?P<nom>[^\d]+?)\s+(?P<fed>[A-Z][A-Za-z\-]{1,4})\s+"
    r"(?P<motiu>wo|W\.\s*O\.|Ret\.[^\d…]*)\s*(?P<pts>\d{1,3}|…)?$"
)


@dataclass
class Classificat:
    posicio: int
    jugador: str
    fed: str | None
    jugades: int | None
    caramboles: int | None
    entrades: int | None
    mitjana: float | None
    serie_major: int | None
    punts: int | None
    #: «w.o.» o «retirat» quan no hi ha xifres.
    ronda: str | None = None


def llegeix_classificacio(linies: list[str]) -> tuple[list[Classificat], int]:
    """Les files de la classificació final i quantes s'han descartat (la mitjana no quadra).

    Els que no es van presentar («W. O.») no tenen xifres i no hi surten.
    """
    from fcbillar.rfeb_individuals import normalitza_fed

    out: list[Classificat] = []
    descartats = 0
    for text in linies:
        if s := _CLAS_SENSE_JUGAR.match(text):
            nom = s.group("nom").strip()
            pts = s.group("pts")
            out.append(
                Classificat(
                    posicio=int(s.group("pos")),
                    jugador=nom.title() if nom.isupper() else nom,
                    fed=normalitza_fed(s.group("fed")) or s.group("fed").upper(),
                    jugades=None,
                    caramboles=None,
                    entrades=None,
                    mitjana=None,
                    serie_major=None,
                    punts=int(pts) if pts and pts.isdigit() else None,
                    ronda="retirat" if s.group("motiu").startswith("Ret") else "w.o.",
                )
            )
            continue
        m = _CLAS_CERTIFICAT.match(text) or _CLAS_RANQUING.match(text)
        if not m:
            continue
        car, ent = int(m.group("car")), int(m.group("ent"))
        prom = float(m.group("prom").replace(",", "."))
        if not _quadra(car, ent, prom):
            descartats += 1
            continue
        nom = m.group("nom").strip()
        out.append(
            Classificat(
                posicio=int(m.group("pos")),
                jugador=nom.title() if nom.isupper() else nom,
                fed=normalitza_fed(m.group("fed")) or m.group("fed").upper(),
                jugades=int(m.group("pj")),
                caramboles=car,
                entrades=ent,
                mitjana=prom,
                serie_major=int(m.group("sm")),
                punts=int(m.group("pts")),
            )
        )
    return out, descartats


def _desa_classificacio(conn: sqlite3.Connection, prova_id: str, files: list[Classificat]) -> None:
    conn.execute("DELETE FROM rfeb_classificacions WHERE prova_id = ?", (prova_id,))
    conn.executemany(
        "INSERT INTO rfeb_classificacions (prova_id, posicio, jugador, fed, ronda, jugades, "
        "caramboles, entrades, mitjana, serie_major, punts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                prova_id,
                f.posicio,
                f.jugador,
                f.fed,
                f.ronda,
                f.jugades,
                f.caramboles,
                f.entrades,
                f.mitjana,
                f.serie_major,
                f.punts,
            )
            for f in files
        ],
    )


def carrega(conn: sqlite3.Connection, arrel: str | Path) -> list[Resultat]:
    """Crea cada prova de `PROVES` a `rfeb_proves` i hi desa les partides dels seus PDF.

    `arrel` és la carpeta de `rfeb_wayback` (`<arrel>/0HOME/PDF/…`). Una prova de la
    qual no hi ha cap PDF no es crea.
    """
    arrel = Path(arrel)
    resultats = []
    for prova in PROVES:
        totes: list[PartidaFull] = []
        for rel, fase, format_ in prova.fitxers:
            cami = arrel / "0HOME" / "PDF" / rel
            if not cami.exists():
                resultats.append(Resultat(prova.id, rel, 0, 0, "no baixat"))
                continue
            partides, descartats = llegeix_fitxer(cami, fase, format_)
            resultats.append(
                Resultat(
                    prova.id, rel, len(partides), descartats, "" if partides else "sense partides"
                )
            )
            totes.extend(partides)
        classificats: list[Classificat] = []
        if prova.classificacio:
            cami = arrel / "0HOME" / "PDF" / prova.classificacio
            if cami.exists():
                classificats, descartats = llegeix_classificacio(_linies(cami))
                resultats.append(
                    Resultat(
                        prova.id,
                        prova.classificacio,
                        len(classificats),
                        descartats,
                        "classificació" if classificats else "classificació sense files",
                    )
                )
            else:
                resultats.append(Resultat(prova.id, prova.classificacio, 0, 0, "no baixat"))
        if not totes and not classificats:
            continue
        font = prova.fitxers[0][0] if prova.fitxers else prova.classificacio
        conn.execute(
            "INSERT OR REPLACE INTO rfeb_proves (id, temporada, modalitat, categoria, tipus, titol, "
            "lloc, data_inici, data_fi, font) VALUES (?, ?, '3b', 'absolut', ?, ?, ?, ?, ?, ?)",
            (
                prova.id,
                prova.temporada,
                prova.tipus,
                prova.titol,
                prova.lloc,
                prova.inici,
                prova.fi,
                "https://web.archive.org/web/2011/http://www.rfeb.org/0HOME/PDF/" + str(font),
            ),
        )
        if totes:
            desa_partides(conn, prova.id, totes)
        if classificats:
            _desa_classificacio(conn, prova.id, classificats)
    return resultats
