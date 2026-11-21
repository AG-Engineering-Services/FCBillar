"""Les partides llegides d'una prova de la RFEB, contrastades amb la seva classificació.

Els fulls de desenvolupament i els PDF de fases no porten cap marca que digui
«això és una partida»: el lector hi busca files amb la forma d'una partida. Hi
ha taules que la tenen i no ho són: el total de cada parella als grups (dues
partides sumades, 100 entrades), el total de cada jugador a una fase. I en un
PDF de text barrejat, una entrada pot anar a parar a la partida del costat.

La classificació final de la prova és una font independent: hi ha, per a cada
jugador, les caramboles i les entrades de totes les seves partides, i sovint
quantes en va jugar. Una partida bona no pot fer que un jugador en tingui més
que això. Per això:

1. Si una fase sencera fa passar diversos jugadors per sobre de la
   classificació (almenys tres, i la meitat dels que hi passen), és una taula
   de resum i es treu la fase.
2. Si encara hi ha algú per sobre, es treuen totes les seves partides
   d'aquella prova.

Que en faltin no és cap error: vol dir que alguna fase no s'ha pogut llegir, i
el que hi ha és bo. La fitxa, en aquest cas, fa servir els totals de la
classificació per als indicadors d'aquell jugador.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from fcbillar.rfeb_fases_pdf import _mots


@dataclass
class Validacio:
    prova_id: str
    partides: int
    fases_fora: list[str] = field(default_factory=list)
    jugadors_fora: list[str] = field(default_factory=list)
    partides_fora: int = 0


@dataclass
class _Oficial:
    nom: str
    jugades: int | None
    caramboles: int
    entrades: int | None


def _clau(nom: tuple[str, ...], classificats: list[tuple[str, ...]]) -> tuple[str, ...] | None:
    """El nom de la classificació d'un jugador llegit: el mateix, o un prefix únic."""
    if nom in classificats:
        return nom
    cands = [c for c in classificats if nom and (c[: len(nom)] == nom or nom[: len(c)] == c)]
    return cands[0] if len(cands) == 1 else None


def _excessos(
    partides: list[tuple], oficials: dict[tuple[str, ...], _Oficial], grans: bool = False
) -> set[tuple[str, ...]]:
    """Els jugadors amb més del que diu la classificació.

    Amb `grans`, només els que en tenen com a mínim una partida de més (10
    caramboles, 15 entrades o més partides que les jugades): és el rastre d'una
    taula de resum, que suma partides senceres. Una entrada de més és una
    altra cosa.
    """
    classificats = list(oficials)
    tot: dict[tuple[str, ...], list[int]] = defaultdict(lambda: [0, 0, 0])
    for _id, _fase, ja, ca, jb, cb, ent in partides:
        for j, car in ((ja, ca), (jb, cb)):
            if (k := _clau(_mots(j), classificats)) is not None:
                t = tot[k]
                t[0] += 1
                t[1] += car
                t[2] += ent
    out = set()
    for k, (n, car, ent) in tot.items():
        o = oficials[k]
        marge_c, marge_e = (10, 15) if grans else (0, 0)
        if (
            car - o.caramboles > marge_c
            or (o.entrades and ent - o.entrades > marge_e)
            or (o.jugades and n > o.jugades)
        ):
            out.add(k)
    return out


def valida(conn: sqlite3.Connection, prova_id: str) -> Validacio | None:
    """Treu de `rfeb_partides` el que la classificació desmenteix. None si no n'hi ha."""
    oficials = {
        _mots(n): _Oficial(n, j, c, e)
        for n, j, c, e in conn.execute(
            "SELECT jugador, jugades, caramboles, entrades FROM rfeb_classificacions "
            "WHERE prova_id = ? AND caramboles IS NOT NULL",
            (prova_id,),
        )
    }
    if not oficials:
        return None
    partides = conn.execute(
        "SELECT rowid, fase, jugador_a, caramboles_a, jugador_b, caramboles_b, entrades "
        "FROM rfeb_partides WHERE prova_id = ?",
        (prova_id,),
    ).fetchall()
    res = Validacio(prova_id, len(partides))
    excessos = _excessos(partides, oficials)

    # 1. Les fases que, tretes, deixen menys gent per sobre de la classificació
    #    (comptant només els excessos d'una partida o més).
    grans = _excessos(partides, oficials, grans=True)
    while grans:
        fases = {p[1] for p in partides}
        if len(fases) < 2:
            break
        millor = min(
            fases,
            key=lambda f: len(_excessos([p for p in partides if p[1] != f], oficials, grans=True)),
        )
        sense = [p for p in partides if p[1] != millor]
        restants = _excessos(sense, oficials, grans=True)
        # Una taula de resum desquadra molta gent alhora. Un jugador sol per
        # sobre (una carambola de més a la classificació, una entrada mal
        # llegida) no és motiu per treure una fase sencera: va al pas 2.
        resolts = len(grans) - len(restants)
        if resolts < max(3, (len(grans) + 1) // 2):
            break
        res.fases_fora.append(millor)
        partides, grans = sense, restants
    excessos = _excessos(partides, oficials)

    # 2. Qui encara passa: fora les seves partides d'aquesta prova.
    if excessos:
        classificats = list(oficials)
        res.jugadors_fora = sorted(oficials[k].nom for k in excessos)
        partides = [
            p
            for p in partides
            if _clau(_mots(p[2]), classificats) not in excessos
            and _clau(_mots(p[4]), classificats) not in excessos
        ]

    queden = {p[0] for p in partides}
    fora = [
        (r[0],)
        for r in conn.execute("SELECT rowid FROM rfeb_partides WHERE prova_id = ?", (prova_id,))
        if r[0] not in queden
    ]
    conn.executemany("DELETE FROM rfeb_partides WHERE rowid = ?", fora)
    res.partides_fora = len(fora)
    return res


def valida_totes(conn: sqlite3.Connection) -> list[Validacio]:
    out = []
    for (pid,) in conn.execute("SELECT DISTINCT prova_id FROM rfeb_partides ORDER BY 1").fetchall():
        if (v := valida(conn, pid)) is not None:
            out.append(v)
    return out
