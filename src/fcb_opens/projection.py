"""Build the *provisional* bracket projection for an Open from its inscrits.

This is the pre-publication half of live tracking: from the official
inscrits-per-clubs PDF we seed the field (Art. XVIII) and run the group
generator (Art. VIII-IX) to produce the complete projected structure —
which players land in which group of which phase, and how the Fase Final
K.O. is fed — *before* the federation draws the real groups.

Once the federation publishes the groups, the live scraper (open_live.py)
takes over and this projection is shown only for reference/comparison.

The output is a plain JSON-serialisable dict so it can be stored as a
payload (see db.save_projection) and returned verbatim by the API.
"""

from __future__ import annotations

from collections.abc import Callable

from .generator import GroupSlot, generate_tournament
from .scraper.inscrits_pdf import InscritEntry, InscritsList

# Human-readable phase names. The generator's P/PP/PPP are, top-down, the
# phases closest to the Fase Final (Art. VIII):
_PHASE_TITLES = {
    "P": "Prèvies",
    "PP": "Pre-prèvies",
    "PPP": "Pre-pre-prèvies",
}
# Order to present phases in the UI: deepest (played first) at the top.
_PHASE_ORDER = ["PPP", "PP", "P"]

# P phase group labels in draw order, to pair Fase Final setzens.
_P_LABELS = ["A", "B", "C", "D", "E", "F", "G", "H",
             "I", "J", "K", "L", "M", "N", "O", "P"]


def order_inscrits(inscrits: list[InscritEntry]) -> list[InscritEntry]:
    """Return inscrits sorted into final seed order (1..N), Art. XVIII.

    For seeded players the federation's "POSSIC. RANQ. OPEN" already encodes
    the full Art. XVIII ordering (opens points → tier → fcb position →
    mitjana), so we simply sort by that position ascending. Players with no
    opens position (newcomers) go last, definitius before provisionals, each
    by mitjana descending.
    """
    seeded = sorted(
        (e for e in inscrits if e.seed_position is not None),
        key=lambda e: e.seed_position,  # type: ignore[arg-type,return-value]
    )
    unranked = sorted(
        (e for e in inscrits if e.seed_position is None),
        key=lambda e: (1 if e.ranquing_estat.upper().startswith("PROV") else 0, -e.mitjana),
    )
    return [*seeded, *unranked]


def _ordinal_ca(n: int) -> str:
    """Catalan masculine ordinal abbreviation: 1r, 2n, 3r, 4t, 5è, 6è..."""
    return {1: "1r", 2: "2n", 3: "3r", 4: "4t"}.get(n, f"{n}è")


def _placeholder_label(slot: GroupSlot) -> str:
    """Human label for a 'winner of a lower phase' slot, e.g. '1r de Pre-prèvies'."""
    phase = _PHASE_TITLES.get(slot.placeholder_phase or "", slot.placeholder_phase or "")
    return f"Guanyador {_ordinal_ca(slot.placeholder_rank or 0)} de {phase}"


def _build_warnings(ordered: list[InscritEntry], inscrits: InscritsList, n: int) -> list[dict]:
    """Lightweight inscription checks surfaced to the organiser (validator-lite)."""
    warnings: list[dict] = []
    if inscrits.declared_total is not None and inscrits.declared_total != n:
        warnings.append({
            "level": "error",
            "message": f"El PDF declara {inscrits.declared_total} inscrits però se n'han llegit {n}.",
        })
    # Provisionals amb posició al rànquing d'opens (Art. XVIII: els provisionals
    # no haurien de tenir punts/posició d'opens consolidats).
    prov_ranked = [
        e.player_name for e in ordered
        if e.seed_position is not None and e.ranquing_estat.upper().startswith("PROV")
    ]
    for nom in prov_ranked:
        warnings.append({
            "level": "warning",
            "message": f"{nom}: provisional però amb posició al rànquing d'opens.",
        })
    # Homònims dins la mateixa llista (poden enganyar el sembrat i la resolució).
    seen: dict[str, int] = {}
    for e in ordered:
        seen[e.player_name] = seen.get(e.player_name, 0) + 1
    for nom, c in seen.items():
        if c > 1:
            warnings.append({"level": "warning", "message": f"{nom}: apareix {c} cops a la llista."})
    n_new = sum(1 for e in ordered if e.seed_position is None)
    if n_new:
        warnings.append({
            "level": "info",
            "message": f"{n_new} jugadors sense posició al rànquing d'opens (sembrats per mitjana al final).",
        })
    return warnings


def build_projection(
    inscrits: InscritsList,
    *,
    season: str | None = None,
    resolve_fcb_id: Callable[[str], str | None] | None = None,
    opens_points_by_name: dict[str, int] | None = None,
) -> dict:
    """Compute the full projected bracket payload from a parsed inscrits list.

    ``resolve_fcb_id`` maps a player name to the FCBillar ``fcb_id`` of the
    existing player profile (or None). When provided, every player reference in
    the payload carries an ``fcb_id`` so the UI can link to that player's page.
    ``opens_points_by_name`` attaches each player's current Catalan-Opens
    ranking points (sum of the last 5 opens) for context.
    """
    ordered = order_inscrits(list(inscrits.entries))
    n = len(ordered)

    tournament = generate_tournament(n)

    # Resolve each distinct player name to an fcb_id once (cheap DB lookups).
    fcb_ids: dict[str, str | None] = {}
    if resolve_fcb_id is not None:
        for e in ordered:
            if e.player_name not in fcb_ids:
                fcb_ids[e.player_name] = resolve_fcb_id(e.player_name)

    points = opens_points_by_name or {}

    # position (1-indexed) -> seed dict, for resolving direct slots.
    def seed_dict(position: int) -> dict:
        e = ordered[position - 1]
        return {
            "seed_order": position,
            "player_name": e.player_name,
            "club": e.club,
            "ranking_position": e.seed_position,
            "mitjana": e.mitjana,
            "ranquing_estat": e.ranquing_estat,
            "fcb_id": fcb_ids.get(e.player_name),
            "opens_points": points.get(e.player_name),
        }

    # Which phase each seed *enters*. Direct slots in a phase reveal this;
    # seeds 1-16 are direct entrants to the Fase Final.
    entry_phase: dict[int, str] = {p: "Fase Final" for p in range(1, 17)}

    phases_out: list[dict] = []
    for name in _PHASE_ORDER:
        phase = tournament.phases.get(name)
        if phase is None:
            continue
        groups_out: list[dict] = []
        for group in phase.groups:
            players_out: list[dict] = []
            for idx, slot in enumerate(group.slots):
                if slot.inscription_position is not None:
                    entry_phase[slot.inscription_position] = _PHASE_TITLES[name]
                    players_out.append({"slot": idx, "kind": "player", **seed_dict(slot.inscription_position)})
                else:
                    players_out.append({
                        "slot": idx,
                        "kind": "winner",
                        "placeholder": slot.label,
                        "label": _placeholder_label(slot),
                    })
            groups_out.append({"label": group.label, "players": players_out})
        phases_out.append({
            "name": name,
            "title": _PHASE_TITLES[name],
            "n_groups": len(phase.groups),
            "groups": groups_out,
        })

    # Seed list with the phase each player starts in.
    seeds_out = []
    for position in range(1, n + 1):
        seeds_out.append({**seed_dict(position), "entry_phase": entry_phase.get(position, "Prèvies")})

    # Fase Final K.O.: seeds 1-16 enter directly and are paired against the 16
    # P-group winners per the reglament setzens table (16-1P, 15-2P, ..., 1-16P).
    setzens = []
    for i in range(1, 17):
        seed_pos = 17 - i
        setzens.append({
            "match": i,
            "a": {"kind": "player", **seed_dict(seed_pos)},
            "b": {
                "kind": "winner",
                "group": _P_LABELS[i - 1],
                "label": f"Guanyador Grup {_P_LABELS[i - 1]}",
            },
        })

    return {
        "name": inscrits.open_name or "Open",
        "season": season,
        "num_inscriptions": n,
        "declared_total": inscrits.declared_total,
        "structure": {name: len(tournament.phases[name].groups) for name in tournament.phases},
        "warnings": _build_warnings(ordered, inscrits, n),
        "seeds": seeds_out,
        "phases": phases_out,
        "fase_final": {
            "title": "Fase Final (K.O.)",
            "n_direct_seeds": 16,
            "setzens": setzens,
        },
    }
