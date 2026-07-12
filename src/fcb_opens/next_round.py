"""Munta la RONDA SEGÜENT d'un open des dels classificats SEGURS de la ronda en
joc, abans que la federació en publiqui el sorteig.

L'estructura de grups de cada ronda ve fixada pel generador (Art. VIII-IX): cada
grup de la ronda següent té slots que són o bé seeds directes o bé PLACEHOLDERS
`<k>-<fase>` (= "el k-è millor guanyador de <fase>"). Aquí RESOLEM aquests
placeholders amb els guanyadors SEGURS reals (1r d'un grup TANCAT), ordenats pels
resultats de la ronda acabada — **punts desc, mitjana desc, sèrie major desc**
(regla FCB). Els placeholders sense guanyador segur encara es deixen pendents; a
mesura que es tanquen més grups, la resolució s'amplia. Quan la federació publica
el sorteig real, aquest passa a manar (el seguiment real substitueix la projecció).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .scraper.open_live import (
    Group,
    PhaseDetail,
    _group_sm_by_player,
    _is_regular_group,
)


@dataclass(frozen=True)
class RoundWinner:
    """1r classificat SEGUR d'un grup tancat, amb els stats de la ronda acabada."""

    player_name: str
    club: str
    group_label: str
    punts: int
    mitjana: float
    serie_major: int


def group_is_closed(group: Group) -> bool:
    """Un grup està TANCAT (guanyador decidit) quan totes les partides estan
    jugades, o bé —grup amb un no-presentat— quan totes les jugades són el MATEIX
    parell (els 2 presents juguen dos cops i el grup queda tancat amb 2 partides).
    Mirall de `groupClosed` del frontend."""
    matches = group.matches
    if matches and all(m.is_played for m in matches):
        return True
    played = [m for m in matches if m.is_played and m.player_a and m.player_b]
    if len(played) >= 2:
        pairs = {tuple(sorted((m.player_a, m.player_b))) for m in played}
        if len(pairs) == 1:
            return True
    return False


def secured_winners(phase: PhaseDetail) -> list["RoundWinner"]:
    """Guanyadors SEGURS d'una fase de grups: el 1r de cada grup REGULAR i TANCAT,
    amb punts/mitjana/sèrie-major de la ronda. L'ordre dins el grup és l'oficial de
    la federació (ja aplica els seus desempats), així que `standings[0]` és el 1r."""
    out: list[RoundWinner] = []
    for g in phase.groups:
        if not _is_regular_group(g.label) or not g.standings:
            continue
        if not group_is_closed(g):
            continue
        sm = _group_sm_by_player(g)
        top = g.standings[0]
        out.append(
            RoundWinner(
                player_name=top.player_name,
                club=top.club,
                group_label=g.label,
                punts=top.punts,
                mitjana=top.mitjana,
                serie_major=sm.get(top.player_name, 0),
            )
        )
    return out


def rank_winners(winners: list["RoundWinner"]) -> list["RoundWinner"]:
    """Ordre de sembra a la ronda següent: **punts desc, mitjana desc, sèrie major
    desc**, i nom com a últim desempat (determinisme). El k-è d'aquesta llista omple
    el placeholder `<k>-<fase>`."""
    return sorted(
        winners,
        key=lambda w: (-w.punts, -w.mitjana, -w.serie_major, w.player_name),
    )


_PLACEHOLDER_RE = re.compile(r"^(\d+)-([A-Z]+)$")


def resolve_next_round(
    projected_groups: list[dict],
    winners_ranked: list["RoundWinner"],
    from_phase: str,
) -> tuple[list[dict], int, int]:
    """Resol els placeholders `<k>-<from_phase>` dels grups PROJECTATS de la ronda
    següent amb `winners_ranked[k-1]`.

    Els slots de seed directe (`kind='player'`) i els placeholders d'ALTRES fases es
    deixen igual. Un placeholder el guanyador del qual encara no és segur
    (`k > len(winners_ranked)`) es manté pendent (marcat `pending=True`). Retorna
    `(grups_resolts, n_resolts, n_pendents)`.
    """
    resolved = 0
    pending = 0
    out: list[dict] = []
    for g in projected_groups:
        players_out: list[dict] = []
        for p in g.get("players", []):
            m = (
                _PLACEHOLDER_RE.match(str(p.get("placeholder", "")))
                if p.get("kind") == "winner"
                else None
            )
            if m is not None and m.group(2) == from_phase:
                k = int(m.group(1))
                if k <= len(winners_ranked):
                    w = winners_ranked[k - 1]
                    players_out.append(
                        {
                            "slot": p.get("slot"),
                            "kind": "player",
                            "player_name": w.player_name,
                            "club": w.club,
                            "from_group": w.group_label,
                            "seed_rank": k,
                            "resolved": True,
                        }
                    )
                    resolved += 1
                else:
                    players_out.append({**p, "pending": True})
                    pending += 1
            else:
                players_out.append(p)
        out.append({"label": g.get("label"), "players": players_out})
    return out, resolved, pending
