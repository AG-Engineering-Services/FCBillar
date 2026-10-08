"""Ingesta d'un open o campionat individual des del web nou de la FCB.

## Per què calia refer-la

La ingesta d'individuals demanava la **classificació final** de cada divisió
(`/ca/individuals/classificaciofinal/{divisio}/{clf}`) i en treia els
participants amb la seva posició. Aquella pàgina va desaparèixer amb el canvi
de web d'agost de 2026 i ara retorna 404, o sigui que la ingesta corria sense
fallar i no desava res: tres torneigs descoberts, zero participants. El fallo
s'apuntava com un avís per torneig i la comanda acabava dient «OK», que és la
pitjor manera de trencar-se.

El que sí que publica el web nou és el **recorregut sencer**: les fases, els
grups de cada fase amb qui hi juga, i totes les partides amb caramboles,
entrades, sèrie major, àrbitre i estat. Amb això n'hi ha de sobres, i a més és
més ric que la classificació que hem perdut.

## La classificació la calculem nosaltres

I per tant s'ha de dir d'on surt. La federació ja no publica cap ordre final,
així que aquí es **dedueix del quadre**, que és el que el torneig demostra:

- la darrera fase que va jugar cadascú marca fins on va arribar;
- dins d'una mateixa fase, qui va guanyar l'última partida va davant de qui la
  va perdre —això reparteix el campió i el finalista, i els dos semifinalistes;
- i si encara empaten, mana la mitjana general del torneig.

No és cap invenció: és l'ordre que el reglament d'opens ja dona per bo quan
puntua (les posicions 3 i 4 valen igual, i la 5 a la 8 formen una altra
banda). Però tampoc no és la classificació oficial.

## I quan la federació publica la seva, mana la seva

L'octubre de 2026 la classificació final va tornar al portal, en una altra
adreça (`individuals/divisio-classificacio-final/{torneig}/{divisio}`), i
comparada amb la deduïda no deia el mateix: 5 posicions de 24 a l'Open de Lliure
del Punt d'Atac, 4 de 20 a l'Open de Banda de Granollers. A més porta el club de
cadascú, que no és a cap altra pàgina del torneig.

Per això es demana sempre, i quan hi és **substitueix** la deduïda
(`desa_classificacio_oficial`). La deducció es queda per a quan no n'hi ha:
mentre el torneig es juga, i per als torneigs que la federació tanca sense
arribar-la a crear —l'Open de Mataró de 2025-26 n'és un.

## Què no es desa

`torneig_partides` no desa l'àrbitre ni l'estat: qui creua aquestes partides amb
`games` ho fa pels jugadors, les caramboles, les entrades i la sèrie (vegeu
`linking.py`). Els punts de matx el web nou no els publica.

La **data sí** que s'hi desa, des de la v26, i abans no. El raonament era que la
data d'una partida ja arriba pel rànquing quan es creuen — i arriba, el mes que
ve. Una partida jugada ahir no és a cap rànquing, i sense data no es pot publicar
com a pendent: no sortia a la fitxa de ningú. És la del grup, que és l'única que
el portal dona.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from fcbillar.models import TorneigIndividualRecord, TorneigParticipantRecord
from fcbillar.scraper import parsers as P
from fcbillar.scraper import urls as U
from fcbillar.torneig_naming import clean_torneig_nom

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fase:
    """Una fase d'un torneig. `ordre` és el que marca fins on va arribar cadascú."""

    fase_id_extern: int
    nom: str
    tipus: str  # 'grups' | 'ko'
    ordre: int


@dataclass(frozen=True)
class Partida:
    """Una partida, de grup o d'eliminatòria."""

    fase_id_extern: int
    grup_nom: str | None  # None a les eliminatòries
    data: date | None  # la del grup; les eliminatòries la porten a la fase
    jugador1: str
    caramboles1: int | None
    serie1: int | None
    jugador2: str
    caramboles2: int | None
    serie2: int | None
    entrades: int | None
    arbitre: str | None
    estat: str | None

    @property
    def guanyador(self) -> str | None:
        """Qui la va guanyar, o `None` si no es pot dir."""
        if self.caramboles1 is None or self.caramboles2 is None:
            return None
        if self.caramboles1 == self.caramboles2:
            return None
        return self.jugador1 if self.caramboles1 > self.caramboles2 else self.jugador2


@dataclass(frozen=True)
class Membre:
    """Un jugador dins d'un grup d'una fase, i com hi ha quedat.

    La posició, els punts i la mitjana són els que publica la federació a la
    pàgina del grup («Grup I - CLASSIFICACIÓ»). Són `None` mentre el grup no
    s'hagi jugat.

    La **sèrie major** no és a aquella taula: allà només hi ha jugador, punts i
    mitjana. Es calcula del màxim de les partides que el jugador ha disputat en
    aquella ronda, que és on el portal la publica. Fa falta perquè és el quart
    criteri de desempat del rànquing d'una fase, després de la posició al grup,
    els punts i la mitjana.
    """

    fase_id_extern: int
    grup_nom: str
    grup_id_extern: int | None = None
    jugador: str = ""
    posicio_grup: int | None = None
    punts: int | None = None
    mitjana: float | None = None
    serie_major: int | None = None


@dataclass(frozen=True)
class Grup:
    """Un grup d'una fase: quin dia es juga i a quin club.

    La federació ho publica amb el sorteig, abans que es jugui cap partida.
    """

    fase_id_extern: int
    nom: str  # 'Grup A'
    grup_id_extern: int | None = None
    club_organitzador: str | None = None
    data: date | None = None


@dataclass(frozen=True)
class Divisio:
    """Una divisió d'un torneig, amb tot el que se n'ha pogut llegir."""

    torneig_id_extern: int
    divisio_id_extern: int
    nom: str  # nom complet, ja net
    fases: list[Fase] = field(default_factory=list)
    membres: list[Membre] = field(default_factory=list)
    partides: list[Partida] = field(default_factory=list)
    grups: list[Grup] = field(default_factory=list)
    #: La classificació final OFICIAL, si la federació l'ha creada. Buida vol dir
    #: «encara no n'hi ha»; `None`, «no s'ha pogut demanar». No és el mateix, i
    #: `desa` no fa el mateix amb cadascuna.
    oficial: list[P.IndividualParticipant] | None = field(default_factory=list)


@dataclass(frozen=True)
class Posicio:
    """Una posició de la classificació deduïda, amb el que la sosté."""

    posicio: int
    jugador: str
    fase_final: str  # fins on va arribar
    partides_jugades: int
    caramboles: int
    entrades: int
    serie_max: int | None
    #: Com va quedar al grup de la seva darrera fase, si aquella fase era de
    #: grups i la federació n'ha publicat la classificació.
    posicio_grup: int | None = None
    punts_grup: int | None = None

    @property
    def mitjana_general(self) -> float | None:
        return self.caramboles / self.entrades if self.entrades else None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s)


# --------------------------- descàrrega ---------------------------


def _partida(p: P.IndividualPartidaRow, fase: int, grup: str | None, data: date | None) -> Partida:
    return Partida(
        fase_id_extern=fase,
        grup_nom=grup,
        data=data,
        jugador1=p.local_nom,
        caramboles1=p.local_caramboles,
        serie1=p.local_serie_major,
        jugador2=p.visitant_nom,
        caramboles2=p.visitant_caramboles,
        serie2=p.visitant_serie_major,
        entrades=p.entrades,
        arbitre=p.arbitre,
        estat=p.estat,
    )


def llegeix_classificacio_oficial(
    client, torneig_id_extern: int, divisio_id_extern: int, *, use_cache: bool = False
) -> list[P.IndividualParticipant] | None:
    """La classificació final oficial d'una divisió. `[]` si no n'hi ha; `None` si falla.

    Una pàgina que no respon no ha de fer perdre el torneig sencer, que ve
    d'unes altres pàgines: s'avisa i es torna `None`, que vol dir «no ho sé».
    """
    url = U.individuals_classificacio_final(torneig_id_extern, divisio_id_extern)
    try:
        html = client.fetch_html(url, use_cache=use_cache)
    except Exception as e:
        log.warning(
            "Classificació final de %d/%d: no s'ha pogut llegir (%s)",
            torneig_id_extern,
            divisio_id_extern,
            e,
        )
        return None
    return P.parse_individuals_classificacio_final(html)


def llegeix(
    client, torneig_id_extern: int, nom_torneig: str | None, *, use_cache: bool = False
) -> list[Divisio]:
    """Un torneig sencer: divisions, fases, grups, partides i classificació final.

    Es baixa una pàgina per fase i una més per grup. Un open petit com el de
    lliure del Punt d'Atac són quinze peticions; no és car i es fa un cop.

    `nom_torneig` ve del llistat. Per a un torneig que ja no hi surt es passa
    `None` i es llegeix del títol de la seva pàgina de divisions.
    """
    html = client.fetch_html(U.individuals_divisions(torneig_id_extern), use_cache=use_cache)
    if nom_torneig is None:
        nom_torneig = P.parse_individuals_torneig_nom(html)
        if not nom_torneig:
            raise ValueError(f"El torneig {torneig_id_extern} no diu com es diu")
    out: list[Divisio] = []
    for div in P.parse_individuals_divisions(html):
        d = div.divisio_id_extern
        # "OPEN LLIURE PUNT D'ATAC - ÚNICA" no diu res més que el nom del
        # torneig: quan la divisió és l'única, el sufix sobra.
        cru = nom_torneig if _norm(div.nom) in {"UNICA", ""} else f"{nom_torneig} - {div.nom}"
        fases: list[Fase] = []
        membres: list[Membre] = []
        partides: list[Partida] = []
        grups: list[Grup] = []

        enllacos = P.parse_individuals_fases(
            client.fetch_html(U.individuals_fases(torneig_id_extern, d), use_cache=use_cache)
        )
        for ordre, f in enumerate(enllacos, start=1):
            fases.append(Fase(f.fase_id_extern, f.nom, f.tipus, ordre))
            if f.tipus == "ko":
                url = U.individuals_partides_eliminatories(torneig_id_extern, d, f.fase_id_extern)
                khtml = client.fetch_html(url, use_cache=use_cache)
                for p in P.parse_individuals_partides(khtml):
                    partides.append(_partida(p, f.fase_id_extern, None, None))
                continue

            ghtml = client.fetch_html(
                U.individuals_grups(torneig_id_extern, d, f.fase_id_extern), use_cache=use_cache
            )
            # Qui hi ha a cada grup, segons la taula de participants de la fase.
            per_grup: dict[str, dict[str, Membre]] = {}
            for m in P.parse_individuals_grups_membership(ghtml):
                per_grup.setdefault(m.grup_nom, {})[_norm(m.jugador_nom)] = Membre(
                    fase_id_extern=f.fase_id_extern,
                    grup_nom=m.grup_nom,
                    jugador=m.jugador_nom,
                )
            for g in P.parse_individuals_grups(ghtml):
                grups.append(
                    Grup(
                        fase_id_extern=f.fase_id_extern,
                        nom=g.nom,
                        grup_id_extern=g.grup_id_extern,
                        club_organitzador=g.club_organitzador,
                        data=g.data,
                    )
                )
                url = U.individuals_partides_grup(
                    torneig_id_extern, d, f.fase_id_extern, g.grup_id_extern
                )
                phtml = client.fetch_html(url, use_cache=use_cache)
                for p in P.parse_individuals_partides(phtml):
                    partides.append(_partida(p, f.fase_id_extern, g.nom, g.data))
                # La classificació del grup, que la federació publica a la
                # mateixa pàgina. És més completa que la taula de participants
                # de la fase: aquella es deixa qui encara no ha jugat cap
                # partida —dos dels 33 de la pre-prèvia de 1a de la 2026-27—, i
                # aquesta els porta tots, amb la mitjana buida.
                dins = per_grup.setdefault(g.nom, {})
                # La sèrie major de cadascú en aquesta ronda: el màxim de les
                # seves partides del grup. La taula de classificació no la porta.
                serie_grup: dict[str, int] = {}
                for p_ in P.parse_individuals_partides(phtml):
                    for nom_j, serie in (
                        (p_.local_nom, p_.local_serie_major),
                        (p_.visitant_nom, p_.visitant_serie_major),
                    ):
                        if not nom_j or serie is None:
                            continue
                        clau_j = _norm(nom_j)
                        if serie > serie_grup.get(clau_j, -1):
                            serie_grup[clau_j] = serie
                for c in P.parse_individuals_grup_classificacio(phtml):
                    dins[_norm(c.jugador_nom)] = Membre(
                        fase_id_extern=f.fase_id_extern,
                        grup_nom=g.nom,
                        grup_id_extern=g.grup_id_extern,
                        jugador=c.jugador_nom,
                        posicio_grup=c.posicio,
                        punts=c.punts,
                        mitjana=c.mitjana,
                        serie_major=serie_grup.get(_norm(c.jugador_nom)),
                    )
                for clau, m in dins.items():
                    if m.grup_id_extern is None:
                        dins[clau] = Membre(
                            fase_id_extern=m.fase_id_extern,
                            grup_nom=m.grup_nom,
                            grup_id_extern=g.grup_id_extern,
                            jugador=m.jugador,
                            posicio_grup=m.posicio_grup,
                            punts=m.punts,
                            mitjana=m.mitjana,
                            serie_major=m.serie_major,
                        )
            for grup_nom in sorted(per_grup):
                membres.extend(per_grup[grup_nom].values())

        out.append(
            Divisio(
                torneig_id_extern=torneig_id_extern,
                divisio_id_extern=d,
                nom=clean_torneig_nom(cru),
                fases=fases,
                membres=membres,
                partides=partides,
                grups=grups,
                oficial=llegeix_classificacio_oficial(
                    client, torneig_id_extern, d, use_cache=use_cache
                ),
            )
        )
    return out


# --------------------------- classificació deduïda ---------------------------


def classificacio(divisio: Divisio) -> list[Posicio]:
    """L'ordre final que el quadre demostra. Vegeu la capçalera del mòdul.

    Una partida sense caramboles no compta per a res: encara no s'ha jugat, i
    donar-la per zero baixaria qui l'ha de jugar.
    """
    ordre_fase = {f.fase_id_extern: f.ordre for f in divisio.fases}
    nom_fase = {f.fase_id_extern: f.nom for f in divisio.fases}
    tipus_fase = {f.fase_id_extern: f.tipus for f in divisio.fases}
    # Com va quedar cadascú al grup de cada fase, quan la federació ho publica.
    grups = {
        (m.fase_id_extern, _norm(m.jugador)): m
        for m in divisio.membres
        if m.posicio_grup is not None
    }

    acum: dict[str, dict] = {}

    def _entrada(jugador: str) -> dict:
        return acum.setdefault(
            _norm(jugador),
            {
                "nom": jugador,
                "pj": 0,
                "car": 0,
                "ent": 0,
                "serie": None,
                "fase": 0,
                "fase_id": None,
                "guanya": False,
            },
        )

    for p in divisio.partides:
        if p.caramboles1 is None or p.caramboles2 is None:
            continue
        guanyador = p.guanyador
        for jugador, car, serie in (
            (p.jugador1, p.caramboles1, p.serie1),
            (p.jugador2, p.caramboles2, p.serie2),
        ):
            if not jugador:
                continue
            a = _entrada(jugador)
            a["pj"] += 1
            a["car"] += car
            a["ent"] += p.entrades or 0
            if serie is not None and (a["serie"] is None or serie > a["serie"]):
                a["serie"] = serie
            fase = ordre_fase.get(p.fase_id_extern, 0)
            if fase > a["fase"]:
                a["fase"], a["fase_id"] = fase, p.fase_id_extern
                a["guanya"] = jugador == guanyador
            elif fase == a["fase"] and jugador == guanyador:
                a["guanya"] = True

    # Qui consta a la classificació d'un grup però no ha jugat cap partida hi ha
    # de sortir igualment: hi era. La federació els posa amb zero punts i la
    # mitjana buida, i és així com han de quedar —últims del seu grup, no fora
    # del torneig.
    for m in divisio.membres:
        if m.posicio_grup is None:
            continue
        clau = _norm(m.jugador)
        fase = ordre_fase.get(m.fase_id_extern, 0)
        a = acum.get(clau)
        if a is None:
            a = _entrada(m.jugador)
            a["fase"], a["fase_id"] = fase, m.fase_id_extern
        elif fase > a["fase"]:
            a["fase"], a["fase_id"], a["guanya"] = fase, m.fase_id_extern, False

    def clau(a: dict) -> tuple:
        """Fins on va arribar, com hi va quedar, i la mitjana com a últim recurs.

        Dins d'una fase de GRUPS manen les tres coses que la federació publica:
        la posició al grup, els punts i la mitjana del grup. Abans aquí hi havia
        «qui va guanyar l'última partida», que per a un quadre d'eliminatòries és
        correcte i per a una fase de grups no vol dir res: al campionat de
        Catalunya de tres bandes, que al setembre només havia jugat la prèvia i la
        pre-prèvia, ordenava per la darrera partida de cadascú en comptes de per
        com havia quedat el seu grup.

        A les ELIMINATÒRIES es manté el criteri d'abans, que és el que reparteix
        el campió i el finalista, i els dos semifinalistes.
        """
        m = grups.get((a["fase_id"], _norm(a["nom"])))
        mitjana_general = a["car"] / a["ent"] if a["ent"] else 0.0
        if m is not None and tipus_fase.get(a["fase_id"]) != "ko":
            return (
                -a["fase"],
                m.posicio_grup,
                -(m.punts or 0),
                -(m.mitjana or 0.0),
                -(m.serie_major or 0),
                a["nom"],
            )
        return (-a["fase"], 0 if a["guanya"] else 1, 0, -mitjana_general, 0, a["nom"])

    ultima = {f.ordre: f.nom for f in divisio.fases}
    out: list[Posicio] = []
    for i, a in enumerate(sorted(acum.values(), key=clau), start=1):
        m = grups.get((a["fase_id"], _norm(a["nom"])))
        out.append(
            Posicio(
                posicio=i,
                jugador=a["nom"],
                fase_final=ultima.get(a["fase"], nom_fase.get(a["fase_id"], "")),
                partides_jugades=a["pj"],
                caramboles=a["car"],
                entrades=a["ent"],
                serie_max=a["serie"],
                posicio_grup=m.posicio_grup if m else None,
                punts_grup=m.punts if m else None,
            )
        )
    return out


@dataclass(frozen=True)
class FilaRanquing:
    """Una línia del rànquing d'una fase de grups."""

    posicio: int
    jugador: str
    grup_nom: str
    posicio_grup: int
    punts: int
    mitjana: float | None
    serie_major: int | None = None


def ranquing_fase(divisio: Divisio, fase_id_extern: int) -> list[FilaRanquing]:
    """El rànquing d'una fase de grups: qui s'ha classificat i qui no.

    Una fase de grups reparteix la gent en grups de tres o de quatre que juguen
    per separat, i la federació publica la classificació de cada grup però cap
    ordre entre grups. Sense aquest ordre no es pot dir qui passa: quan
    s'emporten «els dos primers de cada grup» n'hi ha prou amb la posició, però
    quan passen els millors segons, o uns quants tercers, fa falta comparar-los.

    L'ordre és el que la federació aplica, i són QUATRE criteris: **posició dins
    del grup, punts de la ronda, mitjana i sèrie major**. O sigui: tots els
    primers, ordenats entre ells, després tots els segons, i així fins al final.

    La sèrie major hi és perquè els altres tres empaten més sovint del que
    sembla: a la pre-prèvia de 2a divisió de 2026-27 hi ha catorze grups de tres,
    i els primers de grup que han fet 4 punts són dotze.

    Qui no ha jugat cap partida hi surt, amb zero punts i sense mitjana: hi era.
    """
    files = [
        m
        for m in divisio.membres
        if m.fase_id_extern == fase_id_extern and m.posicio_grup is not None
    ]
    files.sort(
        key=lambda m: (
            m.posicio_grup,
            -(m.punts or 0),
            -(m.mitjana or 0.0),
            -(m.serie_major or 0),
            m.jugador,
        )
    )
    return [
        FilaRanquing(
            posicio=i,
            jugador=m.jugador,
            grup_nom=m.grup_nom,
            posicio_grup=m.posicio_grup or 0,
            punts=m.punts or 0,
            mitjana=m.mitjana,
            serie_major=m.serie_major,
        )
        for i, m in enumerate(files, start=1)
    ]


# --------------------------- desat ---------------------------


def desa(
    conn: sqlite3.Connection,
    divisio: Divisio,
    temporada: str,
    *,
    crea_jugadors: bool = True,
) -> dict[str, int]:
    """Desa una divisió sencera. Reemplaça el que hi hagués d'aquesta divisió.

    No es desa el buit: una divisió sense partides ni grups voldria dir que no hem
    sabut llegir-la, i substituir un open sencer per un silenci és pitjor que
    deixar-hi el que teníem.

    Una divisió amb grups i encara cap partida, en canvi, és un torneig sortejat
    que no ha començat, i es desa: és just quan fa falta saber qui juga contra
    qui. En aquest cas les partides que hi hagués no es toquen, per si el que ha
    fallat és llegir-les.
    """
    from fcbillar.db.repository import Repository

    if not divisio.partides and not divisio.membres:
        raise ValueError(
            f"Cap partida ni cap grup a {divisio.nom} ({divisio.torneig_id_extern}/"
            f"{divisio.divisio_id_extern}). No esborro el que hi ha per posar-hi el buit."
        )
    repo = Repository(conn)
    torneig_id = repo.upsert_torneig_individual(
        TorneigIndividualRecord(
            torneig_id_extern=divisio.torneig_id_extern,
            divisio_id_extern=divisio.divisio_id_extern,
            nom=divisio.nom,
            temporada_nom=temporada,
        )
    )

    # Fases i composició de grups.
    #
    # Les fases s'ACTUALITZEN, no es refan. Abans es feia un DELETE i un INSERT, i
    # això donava un `torneig_fases.id` nou a cada reingesta.
    #
    # I aquell id viatja: `torneig_partides.fase_id` el porta, i la publicació al
    # núvol desa `open_partides` amb la clau (open_id, fase_id, ordre). Amb ids
    # nous, les files de la ingesta anterior no s'hi sobreescriuen: s'hi queden al
    # costat. Reingerir dues vegades el campionat de 2a divisió va deixar 84 files
    # on n'hi havia d'haver 42, i cada partida sortia dues vegades a la pantalla.
    #
    # `UNIQUE (torneig_id, fase_id_extern)` fa que l'upsert sigui exacte: la fase
    # es reconeix per l'identificador que li dona la federació, que sí que és
    # estable.
    fase_ids: dict[int, int] = {}
    for f in divisio.fases:
        cur = conn.execute(
            "INSERT INTO torneig_fases (torneig_id, fase_id_extern, nom, tipus, ordre) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(torneig_id, fase_id_extern) DO UPDATE SET "
            "  nom = excluded.nom, tipus = excluded.tipus, ordre = excluded.ordre "
            "RETURNING id",
            (torneig_id, f.fase_id_extern, f.nom, f.tipus, f.ordre),
        )
        fase_ids[f.fase_id_extern] = cur.fetchone()[0]
    # Una fase que la federació hagi retirat sí que se'n va, amb el que en penja.
    if fase_ids:
        marques = ",".join("?" * len(fase_ids))
        conn.execute(
            f"DELETE FROM torneig_fases WHERE torneig_id = ? AND id NOT IN ({marques})",
            (torneig_id, *fase_ids.values()),
        )
    # La composició dels grups es refà sencera: és el contingut de la fase, no la
    # fase, i el DELETE de `torneig_fase_grups` ja no l'arrossega cap cascada.
    conn.executemany(
        "DELETE FROM torneig_fase_grups WHERE fase_id = ?",
        [(fid,) for fid in fase_ids.values()],
    )
    conn.executemany(
        "INSERT INTO torneig_fase_grups (fase_id, grup_nom, jugador_nom, ordre, "
        "grup_id_extern, posicio_grup, punts, mitjana, serie_major) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                fase_ids[m.fase_id_extern],
                m.grup_nom,
                m.jugador,
                i,
                m.grup_id_extern,
                m.posicio_grup,
                m.punts,
                m.mitjana,
                m.serie_major,
            )
            for i, m in enumerate(divisio.membres)
            if m.fase_id_extern in fase_ids
        ],
    )

    # El dia i el club de cada grup. Es refà sencer, com la composició.
    conn.executemany(
        "DELETE FROM torneig_grups WHERE fase_id = ?",
        [(fid,) for fid in fase_ids.values()],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO torneig_grups (fase_id, grup_nom, grup_id_extern, "
        "club_organitzador, data) VALUES (?, ?, ?, ?, ?)",
        [
            (
                fase_ids[g.fase_id_extern],
                g.nom,
                g.grup_id_extern,
                g.club_organitzador,
                g.data.isoformat() if g.data else None,
            )
            for g in divisio.grups
            if g.fase_id_extern in fase_ids
        ],
    )

    # Partides. Els punts de matx no els publica el web nou.
    if divisio.partides:
        conn.execute(
            "DELETE FROM torneig_partides WHERE torneig_id_extern = ? AND divisio_id_extern = ?",
            (divisio.torneig_id_extern, divisio.divisio_id_extern),
        )
    conn.executemany(
        "INSERT INTO torneig_partides (torneig_id_extern, divisio_id_extern, fase_id, "
        "grup_nom, data, player1_nom, caramboles1, serie1, punts1, player2_nom, "
        "caramboles2, serie2, punts2, entrades) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, ?)",
        [
            (
                divisio.torneig_id_extern,
                divisio.divisio_id_extern,
                fase_ids.get(p.fase_id_extern),
                p.grup_nom,
                p.data.isoformat() if p.data else None,
                p.jugador1,
                p.caramboles1,
                p.serie1,
                p.jugador2,
                p.caramboles2,
                p.serie2,
                p.entrades,
            )
            for p in divisio.partides
        ],
    )

    # Participants. Si la federació ha publicat la classificació final, mana
    # aquella; si no, la posició es dedueix del quadre.
    if divisio.oficial:
        n_part = desa_classificacio_oficial(
            conn,
            divisio.torneig_id_extern,
            divisio.divisio_id_extern,
            temporada,
            divisio.oficial,
            series={_norm(pos.jugador): pos.serie_max for pos in classificacio(divisio)},
            crea_jugadors=crea_jugadors,
        )
    elif divisio.oficial is None and te_classificacio_oficial(conn, torneig_id):
        # La pàgina de la classificació no ha respost i ja en teníem l'oficial:
        # tornar a la deduïda per una nit seria canviar posicions bones per unes
        # de pitjors. Es deixa com estava.
        n_part = conn.execute(
            "SELECT COUNT(*) FROM torneig_participants WHERE torneig_id = ?", (torneig_id,)
        ).fetchone()[0]
    else:
        n_part = _desa_classificacio_deduida(repo, divisio, temporada, crea_jugadors)

    conn.commit()
    return {
        "fases": len(divisio.fases),
        "grups": len({(m.fase_id_extern, m.grup_nom) for m in divisio.membres}),
        "partides": len(divisio.partides),
        "participants": n_part,
    }


def _desa_classificacio_deduida(repo, divisio: Divisio, temporada: str, crea_jugadors: bool) -> int:
    """Els participants amb la posició DEDUÏDA del quadre. Vegeu la capçalera."""
    n_part = 0
    for pos in classificacio(divisio):
        fcb_id = repo.get_player_fcb_id_by_nom(pos.jugador)
        if fcb_id is None:
            if not crea_jugadors:
                continue
            fcb_id = repo.resolve_or_create_player_by_nom(pos.jugador)
        repo.upsert_torneig_participant(
            TorneigParticipantRecord(
                torneig_id_extern=divisio.torneig_id_extern,
                divisio_id_extern=divisio.divisio_id_extern,
                player_fcb_id=fcb_id,
                posicio=pos.posicio,
                partides_jugades=pos.partides_jugades,
                caramboles=pos.caramboles,
                entrades=pos.entrades,
                mitjana_general=pos.mitjana_general,
                serie_max=pos.serie_max,
                # Els punts de la darrera ronda que va jugar, que és el que la
                # federació publica mentre no hi ha classificació final. Sense
                # això la columna de punts sortia buida a tot el que s'ingereix
                # del web nou.
                punts=pos.punts_grup,
            ),
            temporada_nom=temporada,
        )
        n_part += 1
    return n_part


def te_classificacio_oficial(conn: sqlite3.Connection, torneig_id: int) -> bool:
    """Aquest torneig ja té desada la classificació oficial?

    Es reconeix pel **club**: no surt de cap altra pàgina del torneig, o sigui
    que un participant amb club ve per força d'una classificació publicada per
    la federació —la del portal nou o la del vell. La deduïda no en porta mai.
    """
    fila = conn.execute(
        "SELECT 1 FROM torneig_participants "
        "WHERE torneig_id = ? AND TRIM(COALESCE(club_text, '')) <> '' LIMIT 1",
        (torneig_id,),
    ).fetchone()
    return fila is not None


def desa_classificacio_oficial(
    conn: sqlite3.Connection,
    torneig_id_extern: int,
    divisio_id_extern: int,
    temporada: str,
    oficial: list[P.IndividualParticipant],
    *,
    series: dict[str, int | None] | None = None,
    crea_jugadors: bool = True,
) -> int:
    """Desa la classificació final oficial d'una divisió. Mana sobre la deduïda.

    La deducció del quadre encerta el campió i el finalista i falla més avall,
    on la federació desempata amb criteris que el quadre no ensenya: a l'Open de
    Lliure del Punt d'Atac de 2026-27 en diferien 5 posicions de 24, i a l'Open
    de Banda de Granollers, 4 de 20. I la posició és el que dona els punts del
    rànquing d'opens.

    De la pàgina oficial en surt tot menys la **sèrie major**, que no hi és: es
    conserva la que s'ha calculat de les partides (`series`, per nom
    normalitzat), o la que ja hi hagués desada.

    Qui era a la deduïda i no és a l'oficial se'n va. Sol ser algú sortejat en
    un grup que no s'hi va presentar: la deducció el posa últim del grup perquè
    «hi era», i la federació no el classifica.

    El torneig ja ha d'existir: aquí no es crea. Torna quants participants ha
    desat.
    """
    from fcbillar.db.repository import Repository

    if not oficial:
        return 0
    repo = Repository(conn)
    series = series or {}
    vius: set[int] = set()
    for fila in oficial:
        fcb_id = repo.get_player_fcb_id_by_nom(fila.jugador_nom)
        if fcb_id is None:
            if not crea_jugadors:
                continue
            fcb_id = repo.resolve_or_create_player_by_nom(fila.jugador_nom)
        repo.upsert_torneig_participant(
            TorneigParticipantRecord(
                torneig_id_extern=torneig_id_extern,
                divisio_id_extern=divisio_id_extern,
                player_fcb_id=fcb_id,
                posicio=fila.posicio,
                partides_jugades=fila.partides_jugades,
                punts=fila.punts,
                caramboles=fila.caramboles,
                entrades=fila.entrades,
                mitjana_general=fila.mitjana_general,
                mitjana_particular=fila.mitjana_particular,
                serie_max=series.get(_norm(fila.jugador_nom)),
                club_text=fila.club,
            ),
            temporada_nom=temporada,
        )
        player_id = repo.get_player_id_by_fcb_id(fcb_id)
        if player_id is not None:
            vius.add(player_id)

    torneig_id = conn.execute(
        "SELECT ti.id FROM torneigs_individuals ti JOIN temporades te ON te.id = ti.temporada_id "
        "WHERE ti.torneig_id_extern = ? AND ti.divisio_id_extern = ? AND te.nom = ?",
        (torneig_id_extern, divisio_id_extern, temporada),
    ).fetchone()[0]
    sobren = [
        r[0]
        for r in conn.execute(
            "SELECT player_id FROM torneig_participants WHERE torneig_id = ?", (torneig_id,)
        )
        if r[0] not in vius
    ]
    conn.executemany(
        "DELETE FROM torneig_participants WHERE torneig_id = ? AND player_id = ?",
        [(torneig_id, pid) for pid in sobren],
    )
    if sobren:
        log.info(
            "%d/%d: %d participants de la classificació deduïda no són a l'oficial; es retiren",
            torneig_id_extern,
            divisio_id_extern,
            len(sobren),
        )
    conn.commit()
    return len(vius)


# --------------------------- la ronda següent, projectada ---------------------------


def projecta_ronda_seguent(conn: sqlite3.Connection, torneig_id: int) -> dict:
    """Projecta la ronda següent d'aquest torneig, si es pot i si cal.

    Es crida a cada ingesta, i per tant sola. Va en DUES passades, i l'ordre
    importa:

    1. **Es retira** tota projecció d'una ronda que la federació ja hagi publicat.
       Ha d'anar primer i ha de mirar-les totes: fent-ho en una sola passada de
       l'última fase a la primera, quan la PRÈVIA apareixia se'n mirava la ronda
       següent —la FINAL, que no té regla— i es sortia sense arribar a retirar la
       projecció de la PRE-PRÈVIA, que es quedava per sempre al costat dels grups
       de debò.
    2. **Es projecta** la ronda següent de la darrera fase de grups jugada, si
       porta la regla del PDF i si aquella ronda no és publicada.

    No fa cap endevinalla: una fase a mitges o sense regla no es projecta i es diu
    per què.
    """
    from fcbillar import projeccio_ronda as PR

    fases = conn.execute(
        "SELECT id, nom, regla, places FROM torneig_fases "
        "WHERE torneig_id = ? AND tipus = 'grups' ORDER BY ordre DESC",
        (torneig_id,),
    ).fetchall()

    # 1) Fora les projeccions que la federació ja ha substituït.
    retirades = 0
    for fase_id, nom_fase, _regla, _places in fases:
        ronda = PR.ronda_seguent(nom_fase or "")
        if ronda and PR.ja_publicada(conn, torneig_id, ronda):
            tretes = PR.retira(conn, torneig_id, ronda)
            if tretes:
                log.info(
                    "%s: la federació ja ha publicat la %s; retiro la projecció (%d files)",
                    nom_fase,
                    ronda,
                    tretes,
                )
            retirades += tretes

    # 2) I la projecció de la ronda que ve, si es pot.
    for fase_id, nom_fase, _regla, places in fases:
        ronda = PR.ronda_seguent(nom_fase or "")
        if ronda is None or PR.ja_publicada(conn, torneig_id, ronda):
            continue
        membres = conn.execute(
            "SELECT jugador_nom, posicio_grup FROM torneig_fase_grups WHERE fase_id = ? "
            "ORDER BY posicio_grup, punts DESC, mitjana DESC, serie_major DESC, jugador_nom",
            (fase_id,),
        ).fetchall()
        if not membres:
            continue
        if any(m[1] is None for m in membres):
            return {"ronda": ronda, "estat": "fase a mitges", "retirades": retirades}
        if not places:
            return {"ronda": ronda, "estat": "sense regla", "retirades": retirades}

        files = PR.projecta([m[0] for m in membres[:places]])
        n = PR.desa(conn, torneig_id, fase_id, ronda, files)
        return {
            "ronda": ronda,
            "estat": "projectada",
            "jugadors": n,
            "grups": len({f.grup_projectat for f in files}),
            "retirades": retirades,
        }
    return {"estat": "publicada" if retirades else "res a projectar", "retirades": retirades}
