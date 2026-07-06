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
from dataclasses import dataclass

from .generator import GroupSlot, generate_tournament
from .scraper.inscrits_pdf import InscritEntry, InscritsList
from .scraper.ranking_inicial_pdf import RankingInicialEntry, RankingInicialList

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


@dataclass(frozen=True)
class _Seed:
    """A player in final seed order, uniform across the two PDF sources.

    ``ranking_position`` is the Catalan-Opens ranking position to *display*
    (from the inscrits' POSSIC. RANQ. OPEN, or the initial ranking's Rànquing
    column) — not the seed order, which is the 1-indexed position in the list.
    """

    player_name: str
    club: str
    ranking_position: int | None
    mitjana: float
    ranquing_estat: str


def _assemble_projection(
    *,
    name: str,
    season: str | None,
    declared_total: int | None,
    seeds: list[_Seed],
    warnings: list[dict],
    resolve_fcb_id: Callable[[str], str | None] | None,
    opens_points_by_name: dict[str, int] | None,
) -> dict:
    """Build the full projected bracket payload from an ordered seed list.

    Shared core for both entry points (inscrits list and initial ranking): given
    players already in final seed order (1..N), runs the group generator and
    lays out phases, seed table and Fase Final setzens.
    """
    n = len(seeds)
    tournament = generate_tournament(n)

    # Resolve each distinct player name to an fcb_id once (cheap DB lookups).
    fcb_ids: dict[str, str | None] = {}
    if resolve_fcb_id is not None:
        for s in seeds:
            if s.player_name not in fcb_ids:
                fcb_ids[s.player_name] = resolve_fcb_id(s.player_name)

    points = opens_points_by_name or {}

    # position (1-indexed) -> seed dict, for resolving direct slots.
    def seed_dict(position: int) -> dict:
        s = seeds[position - 1]
        return {
            "seed_order": position,
            "player_name": s.player_name,
            "club": s.club,
            "ranking_position": s.ranking_position,
            "mitjana": s.mitjana,
            "ranquing_estat": s.ranquing_estat,
            "fcb_id": fcb_ids.get(s.player_name),
            "opens_points": points.get(s.player_name),
        }

    # Which phase each seed *enters*. Direct slots in a phase reveal this;
    # seeds 1-16 are direct entrants to the Fase Final.
    entry_phase: dict[int, str] = {p: "Fase Final" for p in range(1, 17)}

    phases_out: list[dict] = []
    for pname in _PHASE_ORDER:
        phase = tournament.phases.get(pname)
        if phase is None:
            continue
        groups_out: list[dict] = []
        for group in phase.groups:
            players_out: list[dict] = []
            for idx, slot in enumerate(group.slots):
                if slot.inscription_position is not None:
                    entry_phase[slot.inscription_position] = _PHASE_TITLES[pname]
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
            "name": pname,
            "title": _PHASE_TITLES[pname],
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
        "name": name,
        "season": season,
        "num_inscriptions": n,
        "declared_total": declared_total,
        "structure": {pn: len(tournament.phases[pn].groups) for pn in tournament.phases},
        "warnings": warnings,
        "seeds": seeds_out,
        "phases": phases_out,
        "fase_final": {
            "title": "Fase Final (K.O.)",
            "n_direct_seeds": 16,
            "setzens": setzens,
        },
    }


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
    seeds = [
        _Seed(e.player_name, e.club, e.seed_position, e.mitjana, e.ranquing_estat)
        for e in ordered
    ]
    return _assemble_projection(
        name=inscrits.open_name or "Open",
        season=season,
        declared_total=inscrits.declared_total,
        seeds=seeds,
        warnings=_build_warnings(ordered, inscrits, n),
        resolve_fcb_id=resolve_fcb_id,
        opens_points_by_name=opens_points_by_name,
    )


def _build_warnings_seeded(entries: list[RankingInicialEntry]) -> list[dict]:
    """Lightweight checks for the initial-ranking path (validator-lite)."""
    warnings: list[dict] = []
    # Homònims dins la mateixa llista (poden enganyar la resolució de jugador).
    seen: dict[str, int] = {}
    for e in entries:
        seen[e.player_name] = seen.get(e.player_name, 0) + 1
    for nom, c in seen.items():
        if c > 1:
            warnings.append({"level": "warning", "message": f"{nom}: apareix {c} cops a la llista."})
    n_new = sum(1 for e in entries if e.ranking_position is None)
    if n_new:
        warnings.append({
            "level": "info",
            "message": f"{n_new} jugadors sense posició al rànquing d'opens "
                       f"(definitius/provisionals, sembrats per mitjana al final per la federació).",
        })
    return warnings


def build_projection_from_seeded(
    ranking: RankingInicialList,
    *,
    season: str | None = None,
    resolve_fcb_id: Callable[[str], str | None] | None = None,
    opens_points_by_name: dict[str, int] | None = None,
) -> dict:
    """Compute the projected bracket from the official RÀNQUING INICIAL PDF.

    The initial ranking already carries the federation's final seed order (Art.
    XVIII fully applied), so — unlike the inscrits path — we do **not** re-seed:
    the ``Posició`` column is authoritative and drives the group generator
    directly.
    """
    ordered = list(ranking.entries)  # already sorted by Posició in the parser
    seeds = [
        _Seed(e.player_name, e.club, e.ranking_position, e.mitjana, e.ranquing_estat)
        for e in ordered
    ]
    return _assemble_projection(
        name=ranking.open_name or "Open",
        season=season,
        declared_total=None,
        seeds=seeds,
        warnings=_build_warnings_seeded(ordered),
        resolve_fcb_id=resolve_fcb_id,
        opens_points_by_name=opens_points_by_name,
    )


def _live_match(player_a: str, player_b: str) -> dict:
    """A not-yet-played match in the live-open payload shape."""
    return {
        "player_a": player_a,
        "player_b": player_b,
        "punts_a": 0,
        "punts_b": 0,
        "caramboles_a": 0,
        "caramboles_b": 0,
        "serie_major_a": 0,
        "serie_major_b": 0,
        "entrades": None,
        "arbitre": None,
        "observations": None,
        "is_played": False,
    }


def projection_to_live_payload(
    projection: dict,
    *,
    division_id: int,
    fetched_at: str,
    schedule_by_group: dict[str, dict] | None = None,
) -> dict:
    """Map a projected bracket to the `open_live` payload shape (LiveOpenResponse).

    The PWA renders projected opens through the very same live-open card and
    detail as real ones; the only difference is ``projected: True``, which the
    frontend uses to badge it 'projecció · no oficial'. Group phases carry the
    seeded players as standings (no matches played yet) and placeholder slots
    (winner of a lower phase) as unlinkable preview rows. The Fase Final is a KO
    phase whose 16 setzens are shown as pending matches, with the 16 direct
    seeds listed as reserved qualifiers.

    ``schedule_by_group`` (from ``horaris_pdf.parse_horaris_pdf``) maps a bare
    group label ("AG", "Q", "B") to ``{date, billar, matches:[{type,time}]}``;
    when given, each group carries a ``schedule`` field (and its ``venue`` shows
    the billar) so the PWA — and NouProjecte's member board — can show when and
    on which table each group plays.
    """
    sched_map = schedule_by_group or {}

    def _standing(p: dict) -> dict:
        if p["kind"] == "player":
            return {
                "player_name": p["player_name"],
                "club": p.get("club") or "",
                "punts": 0,
                "mitjana": p.get("mitjana") or 0.0,
            }
        # placeholder ("Guanyador Grup X"): a preview row, no player to link to
        return {"player_name": p["label"], "club": "", "punts": 0, "mitjana": 0.0}

    def _group_out(g: dict) -> dict:
        sched = sched_map.get(g["label"])
        billar = sched.get("billar") if sched else None
        return {
            "label": f"Grup {g['label']}",
            "url": "",
            "venue": f"Billar {billar}" if billar else None,
            "standings": [_standing(p) for p in g["players"]],
            "matches": [],
            "n_matches_played": 0,
            "n_matches_total": len(sched["matches"]) if sched else 0,
            "schedule": sched,  # {date, billar, matches:[{type,time}]} or None
        }

    phases_out: list[dict] = []
    for ph in projection["phases"]:
        groups_out = [_group_out(g) for g in ph["groups"]]
        phases_out.append({
            "label": ph["title"],
            "kind": "group",
            "url": "",
            "groups": groups_out,
            "ko_matches": [],
            "is_active": False,
            "provisional_qualifiers": [],
            "provisional_matches": [],
            "provisional_players": [],
        })

    # Fase Final K.O.: setzens as pending matches + the 16 direct seeds as
    # reserved qualifiers (rendered in the KO 'classificats' box).
    ff = projection["fase_final"]
    ko_matches = [_live_match(m["a"]["player_name"], m["b"]["label"]) for m in ff["setzens"]]
    reserved = [
        {
            "name": s["player_name"],
            "club": s.get("club") or "",
            "mitjana": s.get("mitjana") or 0.0,
            "serie_major": 0,
            "source": "reservat",
        }
        for s in projection["seeds"]
        if s.get("entry_phase") == "Fase Final"
    ]
    phases_out.append({
        "label": ff.get("title") or "Fase Final",
        "kind": "ko",
        "url": "",
        "groups": [],
        "ko_matches": ko_matches,
        "is_active": False,
        "provisional_qualifiers": [],
        "provisional_matches": [],
        "provisional_players": reserved,
    })

    player_ids = {
        s["player_name"]: s["fcb_id"] for s in projection["seeds"] if s.get("fcb_id")
    }

    return {
        "division_id": division_id,
        "name": projection["name"],
        "phase_id": None,
        "phases": phases_out,
        "classification": [],
        "classification_is_provisional": True,
        "fetched_at": fetched_at,
        "player_ids": player_ids,
        # Marker the PWA uses to badge this as a non-official projection.
        "projected": True,
        "num_inscriptions": projection.get("num_inscriptions"),
        "structure": projection.get("structure"),
    }
