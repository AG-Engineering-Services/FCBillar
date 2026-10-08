"""Comprovació de frescor: què tenim de cada família de dades, contra el que hi hauria d'haver.

La reingesta nocturna fa quinze passos aïllats i fins a l'octubre de 2026 sortia
verda passés el que passés. L'auditoria del 8 d'octubre va trobar vuit pèrdues
que el job no deia: els rànquings de mitjana aturats des del juliol, el
seguiment d'opens en directe llegint zero fases cada cap de setmana, una
projecció que es calculava i no es publicava. Cap va fer fallar res, perquè cap
pas no mirava si el que havia desat era d'avui o de feia deu setmanes.

Això ho mira. Per a cada família compara **el més nou que tenim** amb **el que
diu la federació** —el seu llistat, el seu índex, el seu sitemap— o amb el que
toca segons el calendari, i en treu una fila:

- `OK`: al dia.
- `AVÍS`: cal mirar-s'ho, però no és una pèrdua (encara).
- `FALLA`: hi ha dades que la federació té i nosaltres no, una font que hi era
  ha desaparegut, o fa massa dies que una cosa no es mou. Fa acabar el job en
  vermell.
- `N/A`: ara no toca (no hi ha cap copa oberta, la lliga encara no ha començat).

**El calendari no s'escriu aquí.** No hi ha cap «a l'agost no hi ha lliga»: el
que s'espera surt de les dates que la mateixa federació publica. Si l'última
jornada amb data passada és de fa una setmana, hi ha d'haver resultats; si no
n'hi ha cap de passada, no s'espera res. Així no crida al llop a l'estiu ni
calla el dia que comença la temporada.

Al final hi ha l'**inventari de documents**: els fitxers del sitemap del
WordPress que cap pas d'ingesta no reconeix. No fa fallar res; hi és perquè un
document nou o reanomenat es vegi el dia que el pengen i no dos mesos després.

Les comprovacions són funcions pures sobre la base de dades i les pàgines ja
baixades (`Fonts`), i és així com es proven. `llegeix_fonts` fa les cinc
peticions; `comprova` ho ajunta tot.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from fcbillar import en_curs

OK = "OK"
AVIS = "AVÍS"
FALLA = "FALLA"
NA = "N/A"

#: Quants dies té la federació per publicar els resultats d'una jornada de lliga
#: abans que comptem que ja hi haurien de ser. Es juga en cap de setmana i
#: l'acta es puja dilluns o dimarts.
DIES_GRACIA_JORNADA = 4

#: La Lliga Nacional no es baixa: algú ha de pujar el PDF de la jornada al
#: repositori. Avisa al cap de deu dies i falla al cap de vint-i-quatre, que és
#: quan ja s'ha jugat la jornada següent.
DIES_AVIS_NACIONAL = 10
DIES_FALLA_NACIONAL = 24
#: I al cap de tres mesos deixa de fallar: una jornada que ningú no ha pujat en
#: tot aquest temps ja no es pujarà, i el job no pot quedar-se vermell per sempre.
DIES_FORAT_NACIONAL = 90

#: Les partides de `games` entren amb el rànquing mensual. Si el rànquing més
#: nou que tenim és posterior a competició jugada i `games` no hi arriba, és
#: que el rànquing ha entrat sense les seves partides.
DIES_MARGE_PARTIDES = 14

#: Cada quant s'ha d'haver mirat el calendari. La reingesta és diària.
DIES_SENSE_MIRAR_CALENDARI = 3

#: Un torneig «Actiu» sense cap partida ingerida, tants dies després de tancar
#: inscripcions, ja s'hauria d'haver començat a jugar.
DIES_TORNEIG_SENSE_PARTIDES = 30

#: Quan la federació triga a refrescar el PDF del rànquing d'opens després d'un
#: open, la ronda es publica provisional. És normal uns dies.
DIES_PDF_OPENS_ENDARRERIT = 21

#: Els documents del sitemap modificats fa menys d'això surten sencers a
#: l'inventari; els més vells, plegats.
DIES_DOCUMENT_RECENT = 14

MODALITATS = {1: "Tres Bandes", 2: "Lliure", 3: "Quadre 47/2", 4: "Banda", 6: "Quadre 71/2"}


@dataclass(frozen=True)
class Fila:
    """Una línia de l'informe."""

    familia: str
    estat: str
    nostre: str
    esperat: str
    detall: str = ""


@dataclass(frozen=True)
class Font:
    """Una pàgina de la federació ja baixada, o per què no s'ha pogut baixar."""

    url: str
    text: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class Fonts:
    """Tot el que l'informe llegeix de la federació: quatre llistats i un sitemap."""

    ranquings: Font
    lligues: Font
    individuals: Font
    copa: Font
    sitemap: Font


@dataclass(frozen=True)
class Document:
    """Un fitxer del sitemap de documents, i si algú el llegeix."""

    slug: str
    modificat: date | None
    #: 'ingerit', 'sabut' (se sap què és i no s'ingereix a posta) o 'nou'.
    classe: str
    que_es: str = ""


@dataclass
class Informe:
    files: list[Fila] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    fet: datetime | None = None

    @property
    def falla(self) -> bool:
        return any(f.estat == FALLA for f in self.files)

    def nous(self) -> list[Document]:
        return [d for d in self.documents if d.classe == "nou"]


# --------------------------- baixar ---------------------------


def llegeix_fonts(client) -> Fonts:
    """Les cinc pàgines, fresques. Una que falla no atura les altres.

    Van sense caché a posta: el que es comprova és què diu la federació ARA, i
    una còpia de fa una hora diria el mateix que ja ha vist la ingesta.
    """
    from fcbillar.scraper import urls as U

    def _baixa(url: str) -> Font:
        try:
            return Font(url=url, text=client.fetch_html(url, use_cache=False))
        except Exception as e:  # l'error és el resultat, no una excepció
            return Font(url=url, error=str(e))

    return Fonts(
        ranquings=_baixa(U.rankings_llistat()),
        lligues=_baixa(U.lligues_llistat()),
        individuals=_baixa(U.individuals_llistat()),
        copa=_baixa(U.copa_llistat()),
        sitemap=_baixa(U.web_sitemap_documents()),
    )


def _no_llegida(familia: str, font: Font) -> Fila:
    return Fila(familia, FALLA, "—", "—", f"No s'ha pogut llegir {font.url}: {font.error}")


def _dia(text: str | None) -> date | None:
    try:
        return date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def _un(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    fila = conn.execute(sql, params).fetchone()
    return fila[0] if fila else None


# --------------------------- rànquings de mitjana ---------------------------


def ranquings(conn: sqlite3.Connection, font: Font) -> list[Fila]:
    """El rànquing més nou de l'índex de la federació contra el nostre, a cada modalitat.

    És la comprovació que hauria avisat el 2 d'octubre de 2026: la federació
    publicava el 126 i aquí es republicava el 124 cada nit.
    """
    from fcbillar.scraper.parsers import parse_rankings_index

    familia = "Rànquings de mitjana"
    if font.text is None:
        return [_no_llegida(familia, font)]
    index = parse_rankings_index(font.text)
    seus: dict[int, tuple[int, date | None]] = {}
    for v in index.vigents:
        if v.modalitat_codi_fcb not in seus or v.num_seq > seus[v.modalitat_codi_fcb][0]:
            seus[v.modalitat_codi_fcb] = (v.num_seq, v.data)
    if not seus:
        return [
            Fila(
                familia,
                FALLA,
                "—",
                "—",
                "L'índex de rànquings no porta cap rànquing vigent: ha canviat de forma.",
            )
        ]
    nostres = dict(
        conn.execute(
            "SELECT m.codi_fcb, MAX(r.num_seq) FROM rankings r "
            "JOIN modalitats m ON m.id = r.modalitat_id GROUP BY m.codi_fcb"
        ).fetchall()
    )
    enrere = [
        f"{MODALITATS.get(mod, mod)}: tenim el {nostres.get(mod) or 'cap'}, hi ha el {num}"
        for mod, (num, _d) in sorted(seus.items())
        if (nostres.get(mod) or 0) < num
    ]
    num_seu = max(n for n, _ in seus.values())
    data_seu = max((d for _, d in seus.values() if d), default=None)
    num_nostre = min((nostres.get(mod) or 0) for mod in seus)
    return [
        Fila(
            familia,
            FALLA if enrere else OK,
            f"núm. {num_nostre} a {len(seus)} modalitats",
            f"núm. {num_seu} ({data_seu or 'sense data'})",
            "; ".join(enrere),
        )
    ]


# --------------------------- partides per jugador ---------------------------


def partides(conn: sqlite3.Connection) -> list[Fila]:
    """`games` ha d'arribar fins a la competició que el rànquing més nou ja compta.

    Les partides de `games` entren amb el rànquing: cada jugador porta enganxada
    la llista de les que li computen. Si el rànquing més nou que tenim és del 2
    d'octubre i s'ha jugat lliga el 26 de setembre, `games` ha de tenir partides
    de finals de setembre. Del 27 de juliol al 8 d'octubre de 2026 no en va
    entrar cap, i tot el que en penja —la fitxa, els índexs, c3b— va quedar
    congelat sense que res ho digués.
    """
    familia = "Partides per jugador (games)"
    ranquing = _un(conn, "SELECT MAX(data_pub) FROM rankings")
    nostra = _un(conn, "SELECT MAX(data_partida) FROM games")
    if not ranquing:
        return [Fila(familia, NA, nostra or "—", "—", "No hi ha cap rànquing amb data.")]
    jugat = max(
        filter(
            None,
            (
                _un(
                    conn,
                    "SELECT MAX(data) FROM encontres_lliga "
                    "WHERE p_match_local IS NOT NULL AND data <= ?",
                    (ranquing,),
                ),
                _un(conn, "SELECT MAX(data) FROM torneig_partides WHERE data <= ?", (ranquing,)),
            ),
        ),
        default=None,
    )
    if not jugat:
        return [Fila(familia, NA, nostra or "—", "—", "Cap competició jugada abans del rànquing.")]
    limit = (_dia(jugat) - timedelta(days=DIES_MARGE_PARTIDES)).isoformat()
    endarrerit = not nostra or nostra[:10] < limit
    return [
        Fila(
            familia,
            FALLA if endarrerit else OK,
            f"fins al {(nostra or '—')[:10]}",
            f"≥ {limit}",
            f"El rànquing del {ranquing} ja compta competició jugada fins al {jugat[:10]}"
            + (
                ", i `games` no hi arriba: ha entrat sense les seves partides."
                if endarrerit
                else "."
            ),
        )
    ]


# --------------------------- lliga ---------------------------


def lliga(conn: sqlite3.Connection, font: Font, avui: date) -> list[Fila]:
    """Cada lliga del llistat de la federació: que s'ingereixi, que es publiqui i que tingui resultats.

    Tres preguntes per lliga:

    1. **Hi és?** Una lliga del llistat sense cap encontre a la base de dades és
       la que va passar el setembre de 2026 amb la 38, a l'inrevés.
    2. **És la que es publica?** `en_curs.lliga_en_curs` ha de triar una lliga
       del llistat. Si en tria una altra, el web ensenya una temporada passada.
    3. **Té resultats?** L'última jornada que ja s'ha jugat (la data, amb uns
       dies de marge per pujar les actes) n'ha de tenir. Si cap encontre de la
       jornada en té, la ingesta de resultats s'ha aturat.
    """
    from fcbillar.scraper.parsers import parse_lligues_llistat

    if font.text is None:
        return [_no_llegida("Lliga", font)]
    obertes, descartades = parse_lligues_llistat(font.text)
    files: list[Fila] = []
    if descartades:
        files.append(
            Fila(
                "Lliga (llistat)",
                FALLA,
                "—",
                f"{len(descartades)} files sense llegir",
                "Files del llistat de lligues que no s'han sabut interpretar: "
                + ", ".join(descartades),
            )
        )
    if not obertes and not descartades:
        # Entre temporades el llistat pot ser buit. Només és un problema si
        # n'esperàvem: si la darrera lliga que vam veure encara té jornades per jugar.
        pendent = _un(
            conn,
            "SELECT MAX(e.data) FROM encontres_lliga e "
            "JOIN lligues_obertes l ON l.lliga_id = e.lliga_id",
        )
        if pendent and pendent[:10] >= avui.isoformat():
            return [
                Fila(
                    "Lliga",
                    FALLA,
                    f"jornades fins al {pendent[:10]}",
                    "cap lliga al llistat",
                    "El llistat de lligues de la federació és buit i en tenim de no acabades.",
                )
            ]
        return [Fila("Lliga", NA, "—", "cap lliga oberta", "Entre temporades.")]

    for ll in obertes:
        mena = en_curs.mena_de_lliga(ll.nom, ll.modalitat)
        familia = f"Lliga {ll.modalitat or ll.nom} ({ll.lliga_id})"
        encontres = _un(
            conn, "SELECT COUNT(*) FROM encontres_lliga WHERE lliga_id = ?", (ll.lliga_id,)
        )
        if mena is None:
            files.append(
                Fila(
                    familia,
                    AVIS,
                    f"{encontres} encontres",
                    "—",
                    f"«{ll.nom}» no és ni la de Tres Bandes ni la de 4 Modalitats: "
                    "s'ingereix i no es publica enlloc.",
                )
            )
            continue
        try:
            publicada = en_curs.lliga_en_curs(conn, mena)
        except en_curs.NoDeterminat as e:
            files.append(Fila(familia, FALLA, "—", f"lliga {ll.lliga_id}", str(e)))
            continue
        if publicada != ll.lliga_id:
            files.append(
                Fila(
                    familia,
                    FALLA,
                    f"es publica la {publicada}",
                    f"la {ll.lliga_id}",
                    "La publicació no segueix el llistat de la federació: el web ensenyaria "
                    "una altra temporada. Executa `fcbillar ingest-lliga`.",
                )
            )
            continue
        if not encontres:
            files.append(
                Fila(
                    familia,
                    AVIS if ll.estat.lower().startswith("inscrip") else FALLA,
                    "cap encontre",
                    f"estat «{ll.estat}»",
                    "La lliga és al llistat i no n'hem ingerit cap encontre.",
                )
            )
            continue
        files.append(_resultats_de_lliga(conn, familia, ll.lliga_id, avui))
    return files


def _resultats_de_lliga(conn: sqlite3.Connection, familia: str, lliga_id: int, avui: date) -> Fila:
    """L'última jornada que ja s'hauria d'haver publicat, i quants resultats en tenim."""
    tall = (avui - timedelta(days=DIES_GRACIA_JORNADA)).isoformat()
    jornada = conn.execute(
        """
        SELECT data, COUNT(*), SUM(p_match_local IS NOT NULL)
          FROM encontres_lliga
         WHERE lliga_id = ? AND data IS NOT NULL AND data <= ?
         GROUP BY data ORDER BY data DESC LIMIT 1
        """,
        (lliga_id, tall),
    ).fetchone()
    total = _un(conn, "SELECT COUNT(*) FROM encontres_lliga WHERE lliga_id = ?", (lliga_id,))
    if jornada is None:
        primera = _un(conn, "SELECT MIN(data) FROM encontres_lliga WHERE lliga_id = ?", (lliga_id,))
        return Fila(
            familia,
            OK,
            f"{total} encontres al calendari",
            "cap jornada jugada encara",
            f"La primera jornada és el {(primera or '?')[:10]}.",
        )
    data, quants, amb_resultat = jornada[0][:10], jornada[1], jornada[2] or 0
    if amb_resultat == 0:
        return Fila(
            familia,
            FALLA,
            f"jornada del {data}: 0 de {quants} amb resultat",
            "resultats publicats",
            f"Fa més de {DIES_GRACIA_JORNADA} dies que es va jugar i no en tenim cap resultat.",
        )
    return Fila(
        familia,
        OK if amb_resultat * 2 >= quants else AVIS,
        f"jornada del {data}: {amb_resultat} de {quants} amb resultat",
        "resultats publicats",
        "" if amb_resultat * 2 >= quants else "Menys de la meitat dels encontres tenen resultat.",
    )


# --------------------------- individuals i opens ---------------------------


def individuals(conn: sqlite3.Connection, font: Font, avui: date) -> list[Fila]:
    """Els torneigs «Actius» del llistat de la federació contra els que tenim amb partides.

    Un torneig acabat de donar d'alta no té res per ingerir, i no és cap error.
    El que sí que ho és: que el llistat no es pugui llegir, que un torneig amb
    partides no tingui cap participant (l'Open de Mataró va estar així tres
    mesos), o que cap dels actius no tingui ni una partida.
    """
    from fcbillar.scraper.taules import taula_amb

    familia = "Individuals i opens"
    if font.text is None:
        return [_no_llegida(familia, font)]
    taula = taula_amb(font.text, "Torneig", "Estat")
    if taula is None:
        return [
            Fila(
                familia, FALLA, "—", "—", "El llistat d'individuals no porta la taula de torneigs."
            )
        ]
    actius: list[tuple[int, str, date | None]] = []
    sense_id: list[str] = []
    altres = 0
    for fila in taula:
        m = next(
            (
                re.search(r"individuals/divisions/(\d+)", e)
                for e in fila.enllacos()
                if "individuals/divisions/" in e
            ),
            None,
        )
        if m is None:
            sense_id.append(fila["Torneig"])
            continue
        if fila["Estat"].strip().lower().startswith("activ"):
            limit = fila.data("Data límit inscripció") if fila.te("Data límit inscripció") else None
            actius.append((int(m.group(1)), fila["Torneig"], limit))
        else:
            altres += 1

    amb_partides: list[str] = []
    sense_partides: list[str] = []
    sense_participants: list[str] = []
    mes_nova = None
    for torneig_id, nom, limit in actius:
        n, darrera = conn.execute(
            "SELECT COUNT(*), MAX(data) FROM torneig_partides WHERE torneig_id_extern = ?",
            (torneig_id,),
        ).fetchone()
        if not n:
            if limit and (avui - limit).days > DIES_TORNEIG_SENSE_PARTIDES:
                sense_partides.append(f"{nom} ({torneig_id})")
            continue
        amb_partides.append(nom)
        mes_nova = max(filter(None, (mes_nova, darrera)), default=None)
        divisions_buides = _un(
            conn,
            """
            SELECT COUNT(*) FROM torneigs_individuals ti
             WHERE ti.torneig_id_extern = ?
               AND EXISTS (SELECT 1 FROM torneig_partides tp
                            WHERE tp.torneig_id_extern = ti.torneig_id_extern
                              AND tp.divisio_id_extern = ti.divisio_id_extern)
               AND NOT EXISTS (SELECT 1 FROM torneig_participants p WHERE p.torneig_id = ti.id)
            """,
            (torneig_id,),
        )
        if divisions_buides:
            sense_participants.append(f"{nom} ({torneig_id})")

    estat, detall = OK, []
    if sense_id:
        estat = FALLA
        detall.append("torneigs del llistat sense id que sàpiga llegir: " + ", ".join(sense_id))
    if sense_participants:
        estat = FALLA
        detall.append("amb partides i sense cap participant: " + ", ".join(sense_participants))
    if actius and not amb_partides and sense_partides:
        estat = FALLA
        detall.append("cap torneig actiu té partides ingerides")
    if sense_partides and estat != FALLA:
        estat = AVIS
    if sense_partides:
        detall.append(
            f"actius sense cap partida {DIES_TORNEIG_SENSE_PARTIDES} dies després de tancar "
            "inscripcions: " + ", ".join(sense_partides)
        )
    return [
        Fila(
            familia,
            estat,
            f"{len(amb_partides)} amb partides (l'última, {(mes_nova or '—')[:10]})",
            f"{len(actius)} actius al llistat (+{altres} en inscripció o tancats)",
            "; ".join(detall),
        )
    ]


def ranquing_opens(
    conn: sqlite3.Connection,
    sitemap: Font,
    documents: list[Document],
    avui: date,
    publicacio: dict | None = None,
) -> list[Fila]:
    """El PDF del rànquing d'opens de tres bandes: que hi sigui i que s'hagi aplicat.

    El PDF és l'única font dels punts oficials. Quan la federació l'ha canviat
    de nom o de lloc —dues vegades— la publicació s'ho ha empassat marcant la
    ronda com a provisional, i l'últim open valia zero punts per a tothom
    durant setmanes.

    Dues coses, de dos llocs. Que el document hi sigui es mira al sitemap. Si
    s'ha aplicat ho diu l'última publicació (`publicacio`, el que `publish-cloud`
    deixa escrit): 1 aplicat, 0 la ronda és provisional perquè el PDF encara no
    porta l'últim open —normal uns dies, i un avís si s'allarga—, -1 no s'ha
    pogut llegir.
    """
    familia = "Rànquing d'opens (PDF oficial)"
    if sitemap.text is None:
        return [_no_llegida(familia, sitemap)]
    pdfs = [d for d in documents if d.que_es == "rànquing d'opens de tres bandes"]
    # L'últim open de tres bandes amb data: el que el PDF hauria d'incloure.
    no3b = ("QUADRE", "LLIURE", "BANDA", "QUILLES", "ARTISTIC", "BIATHL", "FEMENI", "71/2", "47/2")
    darrer = None
    for nom, data in conn.execute(
        "SELECT ti.nom, MAX(tp.data) FROM torneigs_individuals ti "
        "JOIN torneig_partides tp ON tp.torneig_id_extern = ti.torneig_id_extern "
        "AND tp.divisio_id_extern = ti.divisio_id_extern "
        "WHERE UPPER(ti.nom) LIKE '%OPEN%' AND tp.data IS NOT NULL GROUP BY ti.id"
    ):
        if any(x in (nom or "").upper() for x in no3b):
            continue
        if darrer is None or data > darrer[1]:
            darrer = (nom, data)
    if not pdfs:
        return [
            Fila(
                familia,
                FALLA if darrer else NA,
                "—",
                "un PDF al sitemap de documents",
                "No hi ha cap document de rànquing d'opens de tres bandes al sitemap: la "
                "federació l'ha tret o l'ha reanomenat, i la ronda es publicarà provisional.",
            )
        ]
    pdf = max(pdfs, key=lambda d: d.modificat or date.min)
    trobat = f"{pdf.slug} ({pdf.modificat or 'sense data'})"
    esperat = f"que inclogui {darrer[0]} ({darrer[1][:10]})" if darrer else "un PDF al sitemap"
    dies = (avui - _dia(darrer[1])).days if darrer else 0
    aplicat = (publicacio or {}).get("open_ranking_pdf_oficial")
    if aplicat == -1:
        return [
            Fila(
                familia,
                FALLA,
                f"{trobat}, NO aplicat",
                esperat,
                "L'última publicació no ha pogut trobar o llegir el PDF i ha marcat la ronda "
                "com a provisional. Mira el pas `publish-cloud`.",
            )
        ]
    if aplicat == 1:
        return [Fila(familia, OK, f"{trobat}, aplicat", esperat, "")]
    # No aplicat perquè encara no toca (0), o no se sap (no hi ha publicació d'avui).
    endarrerit = dies > DIES_PDF_OPENS_ENDARRERIT and (
        aplicat == 0 or (pdf.modificat is not None and pdf.modificat < _dia(darrer[1]))
    )
    if endarrerit:
        return [
            Fila(
                familia,
                AVIS,
                f"{trobat}, ronda provisional",
                esperat,
                f"Fa {dies} dies que es va jugar l'últim open i el PDF de la federació encara "
                "no el porta.",
            )
        ]
    return [
        Fila(
            familia,
            OK,
            f"{trobat}, ronda provisional" if aplicat == 0 else trobat,
            esperat,
            "El PDF encara no porta l'últim open: és normal uns dies."
            if aplicat == 0
            else "Si s'ha aplicat ho diu `publish-cloud`, que aquí no ha corregut.",
        )
    ]


# --------------------------- copa ---------------------------


def copa(conn: sqlite3.Connection, font: Font) -> list[Fila]:
    """Les copes del llistat han de ser a la base de dades. Sense cap d'oberta, no toca."""
    from fcbillar.scraper.parsers import parse_copa_llistat

    familia = "Copa"
    if font.text is None:
        return [_no_llegida(familia, font)]
    llistat = parse_copa_llistat(font.text)
    darrera = _un(conn, "SELECT MAX(edicio_id) FROM copa_jornades")
    if llistat is None:
        return [
            Fila(
                familia, FALLA, f"edició {darrera}", "—", "La pàgina no porta el llistat de copes."
            )
        ]
    obertes, descartades = llistat
    if descartades:
        return [
            Fila(
                familia,
                FALLA,
                f"edició {darrera}",
                f"{len(descartades)} copes sense id",
                "Hi ha copes al llistat i no en sé llegir l'edició: " + ", ".join(descartades),
            )
        ]
    if not obertes:
        return [Fila(familia, NA, f"edició {darrera}", "cap copa oberta", "")]
    nostres = {r[0] for r in conn.execute("SELECT DISTINCT edicio_id FROM copa_jornades")}
    falten = [f"{c.edicio_id} «{c.nom}»" for c in obertes if c.edicio_id not in nostres]
    en_inscripcio = all(c.estat.lower().startswith("inscrip") for c in obertes)
    return [
        Fila(
            familia,
            (AVIS if en_inscripcio else FALLA) if falten else OK,
            f"edició {darrera}",
            ", ".join(f"{c.edicio_id} ({c.estat})" for c in obertes),
            ("Copes del llistat que no hem ingerit: " + ", ".join(falten)) if falten else "",
        )
    ]


# --------------------------- Lliga Nacional ---------------------------


def nacional(conn: sqlite3.Connection, avui: date) -> list[Fila]:
    """La jornada més nova de la Lliga Nacional amb resultats, contra el seu calendari.

    No hi ha res a baixar: la RFEB no publica la temporada en curs i els PDF es
    pugen a mà al repositori. Si ningú no en puja, es queda on era i tot surt
    bé. El calendari sí que el tenim, i és el que diu quina jornada ja s'ha
    jugat.
    """
    familia = "Lliga Nacional"
    temporada = _un(conn, "SELECT MAX(temporada) FROM nacional_encontres")
    if not temporada:
        return [Fila(familia, NA, "—", "—", "No hi ha cap temporada carregada.")]
    jornades = conn.execute(
        "SELECT jornada, MIN(data), SUM(punts_local IS NOT NULL) FROM nacional_encontres "
        "WHERE temporada = ? AND data IS NOT NULL GROUP BY jornada ORDER BY jornada",
        (temporada,),
    ).fetchall()
    jugades = [j for j in jornades if j[1][:10] <= avui.isoformat()]
    amb = [j for j in jugades if j[2]]
    nostre = f"jornada {amb[-1][0]} ({amb[-1][1][:10]})" if amb else "cap jornada amb resultats"
    sense = [j for j in jugades if not j[2]]
    if not sense:
        return [
            Fila(
                familia,
                OK if jugades else NA,
                nostre,
                f"jornada {jugades[-1][0]} ({jugades[-1][1][:10]})"
                if jugades
                else "encara no ha començat",
                f"Temporada {temporada}.",
            )
        ]
    primera = sense[0]
    dies = (avui - _dia(primera[1])).days
    estat = FALLA if dies > DIES_FALLA_NACIONAL else AVIS if dies > DIES_AVIS_NACIONAL else OK
    if dies > DIES_FORAT_NACIONAL:
        # Ja no és un retard, és un forat que s'ha quedat. Segueix sortint, però
        # un job que no pot tornar a sortir verd deixa de dir res quan falla.
        estat = AVIS
    return [
        Fila(
            familia,
            estat,
            nostre,
            f"jornada {sense[-1][0]} ({sense[-1][1][:10]})",
            f"La jornada {primera[0]} es va jugar fa {dies} dies i no en tenim els resultats: "
            "cal pujar el PDF a `fonts/nacional/`."
            if estat != OK
            else f"La jornada {primera[0]} és de fa {dies} dies; el PDF encara no toca.",
        )
    ]


# --------------------------- calendari ---------------------------

_RE_VERSIO_SLUG = re.compile(r"(\d{4})-(\d{2,4})-v-?(\d+)", re.IGNORECASE)


def calendari(conn: sqlite3.Connection, sitemap: Font, ara: datetime) -> list[Fila]:
    """El calendari esportiu (FCB i RFEB) i els calendaris de grup de la lliga.

    Del de la FCB es compara la revisió del sitemap amb la que tenim: la
    federació en va treure nou de la 2025-26. De tots dos es mira que la
    comprovació nocturna segueixi passant. I dels de grup, que n'hi hagi tants
    d'ingerits com de publicats.
    """
    from fcbillar import calendari_lliga as CL

    files: list[Fila] = []
    if sitemap.text is None:
        return [_no_llegida("Calendari", sitemap)]

    for font in ("FCB", "RFEB"):
        fila = conn.execute(
            "SELECT temporada, versio, last_checked_at FROM calendari_versions "
            "WHERE font = ? ORDER BY last_checked_at DESC, id DESC LIMIT 1",
            (font,),
        ).fetchone()
        familia = f"Calendari {font}"
        if fila is None:
            files.append(Fila(familia, AVIS, "cap", "—", "No se n'ha ingerit mai cap."))
            continue
        temporada, versio, mirat = fila
        try:
            dies = (ara - datetime.fromisoformat(mirat)).days
        except (TypeError, ValueError):
            dies = 999
        estat, detall, esperat = OK, "", "comprovat cada nit"
        if dies > DIES_SENSE_MIRAR_CALENDARI:
            estat, detall = FALLA, f"Fa {dies} dies que no es comprova si n'hi ha una revisió nova."
        if font == "FCB":
            # La revisió més nova que hi ha al sitemap, pel nom del document.
            publicades = []
            for u in re.findall(r"<loc>([^<]+)</loc>", sitemap.text):
                slug = u.rstrip("/").rsplit("/", 1)[-1].lower()
                m = _RE_VERSIO_SLUG.search(slug)
                if "calendari" in slug and "lliga" not in slug and m:
                    a, b = m.group(1), m.group(2)
                    publicades.append((f"{a}/{a[:2] + b if len(b) == 2 else b}", int(m.group(3))))
            if publicades:
                temp_p, v_p = max(publicades)
                esperat = f"{temp_p} V-{v_p}"
                m = re.search(r"(\d+)", versio or "")
                nostra = (temporada, int(m.group(1)) if m else -1)
                if nostra < (temp_p, v_p):
                    estat = FALLA
                    detall = "Al web hi ha una revisió més nova que la ingerida."
        files.append(Fila(familia, estat, f"{temporada} {versio or ''}".strip(), esperat, detall))

    temporada = CL.temporada_mes_nova(sitemap.text)
    sense_llegir = CL.calendaris_sense_llegir(sitemap.text)
    if temporada is None and not sense_llegir:
        files.append(Fila("Calendaris de grup", NA, "—", "cap de publicat", ""))
        return files
    publicats = len(CL.slugs_de_grup(sitemap.text, temporada)) if temporada else 0
    ingerits = _un(
        conn,
        "SELECT COUNT(DISTINCT divisio || '|' || grup) FROM lliga_calendari WHERE temporada = ?",
        (temporada,),
    )
    estat, detall = OK, ""
    if sense_llegir:
        estat = FALLA
        detall = (
            "Documents que semblen calendaris de grup i no es reconeixen pel nom: "
            + ", ".join(sense_llegir)
        )
    elif ingerits < publicats:
        estat = FALLA
        detall = "N'hi ha de publicats que no s'han ingerit."
    files.append(
        Fila(
            "Calendaris de grup",
            estat,
            f"{ingerits} grups de la {temporada}",
            f"{publicats} PDF al web",
            detall,
        )
    )
    return files


# --------------------------- els passos del workflow ---------------------------

#: El pas que prova el lector d'opens en directe. Té fila pròpia perquè és
#: l'única comprovació d'una cosa que només passa els caps de setmana d'open.
PAS_OPENS_DIRECTE = "opens-directe-prova"


def passos(linies: list[str] | None) -> list[Fila]:
    """Com han acabat els passos de la reingesta: una fila pels fallats i una per a la prova de fum.

    `linies` és el fitxer que escriu el workflow, una línia per pas amb el nom i
    el codi de sortida separats per un tabulador. `None` vol dir que la
    comprovació no corre dins del workflow.
    """
    if linies is None:
        return [
            Fila(
                "Opens en directe (prova de fum)",
                NA,
                "—",
                "—",
                "Només es prova dins de la reingesta (`publish-live-opens --dry-run`).",
            )
        ]
    resultats: dict[str, int] = {}
    for linia in linies:
        parts = linia.rstrip("\n").split("\t")
        if len(parts) >= 2 and parts[1].strip().lstrip("-").isdigit():
            resultats[parts[0]] = int(parts[1])
    fallats = {nom: rc for nom, rc in resultats.items() if rc != 0}
    files = [
        Fila(
            "Passos de la reingesta",
            FALLA if fallats else OK if resultats else FALLA,
            f"{len(resultats) - len(fallats)} de {len(resultats)} han acabat bé",
            "tots",
            ", ".join(f"{nom} (exit {rc})" for nom, rc in fallats.items())
            if resultats
            else "El fitxer de passos és buit: la reingesta no ha arribat a córrer.",
        )
    ]
    if PAS_OPENS_DIRECTE in resultats:
        rc = resultats[PAS_OPENS_DIRECTE]
        files.append(
            Fila(
                "Opens en directe (prova de fum)",
                OK if rc == 0 else FALLA,
                "llegeix les fases" if rc == 0 else f"exit {rc}",
                "llegir l'últim open del llistat",
                ""
                if rc == 0
                else "El lector d'opens en directe no sap llegir el web: el cap de setmana "
                "de l'open no hi haurà seguiment.",
            )
        )
    return files


# --------------------------- inventari de documents ---------------------------

#: Documents que se sap què són i que no s'ingereixen a posta: no porten dades de
#: competició (reglaments, actes) o les que porten ja venen de la intranet (els
#: papers de cada open). El que casa amb això no surt a l'inventari com a «nou».
#:
#: La llista és curta i només hi ha paraules d'administració. Un rànquing, una
#: classificació o un calendari que no reconegui ningú NO hi ha de ser: és
#: justament el que l'inventari ha d'ensenyar.
_SABUTS: tuple[tuple[str, str], ...] = (
    (
        r"reglament|reglas|normativa|estatuts|disciplinari|faltes-i-infraccions",
        "reglament o normativa",
    ),
    (r"^\d{2}-(desempats|normativa)", "normativa de la temporada"),
    (
        r"^acta-|assemblea|organigrama-federacio|roda-de-clubs|adjudicacio",
        "document de la federació",
    ),
    (r"convocatoria|organigrama|horaris", "paper d'un open (les dades venen de la intranet)"),
    (
        r"open.*(grups|fase|ranquing-?inicial|ranking-inicial|classificacio-?final)"
        r"|(grups|fase|ranking-inicial|ranquing-inicial).*open",
        "paper d'un open (les dades venen de la intranet)",
    ),
)


def _classifica(slug: str) -> tuple[str, str]:
    """`(classe, què és)` d'un document del sitemap, pel seu nom.

    Es demana a cada mòdul d'ingesta si el reconeix, amb el mateix criteri amb
    què decideix obrir-lo: així l'inventari no es pot desviar del que la
    ingesta fa de debò.
    """
    from fcb_opens.scraper.official_pdf import _es_ranquing_opens_3_bandes
    from fcbillar import calendari_lliga as CL
    from fcbillar import sorteig_fase as S

    s = slug.lower()
    if CL.es_calendari_de_grup(s):
        return "ingerit", "calendari de grup de la lliga"
    if "calendari" in s and "lliga" not in s:
        return "ingerit", "calendari esportiu de la FCB"
    if _es_ranquing_opens_3_bandes(s):
        return "ingerit", "rànquing d'opens de tres bandes"
    for patro, que in _SABUTS:
        if re.search(patro, s):
            return "sabut", que
    # Els sortejos de fase del campionat individual. Va després dels sabuts
    # perquè els papers dels opens també diuen «grups» i «previa», i el pas que
    # els obre els descarta per la categoria del fitxer, que aquí no es veu.
    if S.es_pagina_de_sorteig(s) and "open" not in s:
        return "ingerit", "sorteig de fase de l'individual"
    return "nou", ""


def inventari(sitemap: Font) -> list[Document]:
    """Tots els documents del sitemap del WordPress, classificats."""
    if sitemap.text is None:
        return []
    out: list[Document] = []
    for bloc in re.findall(r"<url>(.*?)</url>", sitemap.text, flags=re.DOTALL):
        m = re.search(r"<loc>[^<]*/wpfd_file/([^/<]+)/?</loc>", bloc)
        if m is None:
            continue
        mod = re.search(r"<lastmod>([^<]+)</lastmod>", bloc)
        classe, que = _classifica(m.group(1))
        out.append(Document(m.group(1), _dia(mod.group(1)) if mod else None, classe, que))
    return sorted(out, key=lambda d: (d.modificat or date.min, d.slug), reverse=True)


# --------------------------- tot junt ---------------------------


def comprova(
    conn: sqlite3.Connection,
    fonts: Fonts,
    *,
    ara: datetime | None = None,
    linies_passos: list[str] | None = None,
    publicacio: dict | None = None,
) -> Informe:
    """L'informe sencer. `ara` és UTC, com les dates que desa SQLite.

    `linies_passos` i `publicacio` són el que deixa la reingesta d'aquesta nit:
    el codi de sortida de cada pas i els comptadors de `publish-cloud`. Sense
    ells es miren només les dades.
    """
    ara = ara or datetime.now(UTC).replace(tzinfo=None)
    avui = ara.date()
    documents = inventari(fonts.sitemap)
    informe = Informe(documents=documents, fet=ara)
    # Dins del workflow, la primera fila diu com han anat els passos i la de la
    # prova de fum va amb els opens. Fora, només hi ha la segona, com a «N/A».
    dels_passos = passos(linies_passos)
    resum_passos = dels_passos[:1] if linies_passos is not None else []
    prova_de_fum = dels_passos[1:] if linies_passos is not None else dels_passos
    comprovacions = (
        lambda: resum_passos,
        lambda: ranquings(conn, fonts.ranquings),
        lambda: partides(conn),
        lambda: lliga(conn, fonts.lligues, avui),
        lambda: individuals(conn, fonts.individuals, avui),
        lambda: ranquing_opens(conn, fonts.sitemap, documents, avui, publicacio),
        lambda: prova_de_fum,
        lambda: copa(conn, fonts.copa),
        lambda: nacional(conn, avui),
        lambda: calendari(conn, fonts.sitemap, ara),
    )
    for fn in comprovacions:
        try:
            informe.files += fn()
        except Exception as e:
            # Una comprovació que peta no ha de callar les altres, ni passar per
            # bona: surt com a fallada amb el que ha passat.
            informe.files.append(
                Fila("Comprovació interna", FALLA, "—", "—", f"{type(e).__name__}: {e}")
            )
    return informe


_ICONA = {OK: "✅", AVIS: "⚠️", FALLA: "❌", NA: "⚪"}


def markdown(informe: Informe, *, avui: date | None = None) -> str:
    """L'informe en Markdown, per al resum del job de GitHub."""
    avui = avui or (informe.fet.date() if informe.fet else date.today())
    fallen = [f for f in informe.files if f.estat == FALLA]
    avisos = [f for f in informe.files if f.estat == AVIS]
    cap = (
        f"### ❌ Frescor: {len(fallen)} comprovacions fallen"
        if fallen
        else f"### ⚠️ Frescor: tot al dia, {len(avisos)} avisos"
        if avisos
        else "### ✅ Frescor: tot al dia"
    )

    def cel_la(s: str) -> str:
        return (s or "").replace("|", "\\|").replace("\n", " ")

    linies = [
        cap,
        "",
        "| | Família | Tenim | Hi hauria d'haver | Detall |",
        "|---|---|---|---|---|",
    ]
    for f in informe.files:
        linies.append(
            f"| {_ICONA[f.estat]} {f.estat} | {cel_la(f.familia)} | {cel_la(f.nostre)} | "
            f"{cel_la(f.esperat)} | {cel_la(f.detall)} |"
        )
    linies.append("")

    nous = informe.nous()
    recents = [d for d in nous if d.modificat and (avui - d.modificat).days <= DIES_DOCUMENT_RECENT]
    vells = [d for d in nous if d not in recents]
    ingerits = sum(1 for d in informe.documents if d.classe == "ingerit")
    sabuts = sum(1 for d in informe.documents if d.classe == "sabut")
    linies += [
        f"#### Documents de la federació que no llegeix cap pas ({len(nous)} de "
        f"{len(informe.documents)})",
        "",
        f"Al sitemap de documents n'hi ha {len(informe.documents)}: {ingerits} s'ingereixen, "
        f"{sabuts} se sap què són i no porten dades (reglaments, actes, papers dels opens), i "
        f"{len(nous)} no els reconeix ningú. No fa fallar res: és per veure'ls.",
        "",
    ]
    if recents:
        linies.append(f"**Nous o modificats els últims {DIES_DOCUMENT_RECENT} dies:**")
        linies.append("")
        linies += [f"- `{d.slug}` ({d.modificat})" for d in recents]
        linies.append("")
    elif nous:
        linies += [f"Cap de nou els últims {DIES_DOCUMENT_RECENT} dies.", ""]
    if vells:
        linies += ["<details><summary>Els de més enrere</summary>", ""]
        linies += [f"- `{d.slug}` ({d.modificat or 'sense data'})" for d in vells]
        linies += ["", "</details>", ""]
    return "\n".join(linies)
