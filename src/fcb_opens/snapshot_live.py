"""Capture the live state of every ongoing Open and push it to Supabase.

The PWA reads from `fcb_opens.open_live_snapshots`, taking the most
recent row per `fcb_division_id`. This module:

1. Walks the FCB `/individuals/llistat` page to discover Opens that are
   on the current season.
2. For each, checks whether it already has a final classification (i.e.
   it's "closed"). Closed Opens are skipped.
3. For each ongoing Open, calls `fetch_live_state(division_id)` to get
   the in-progress structure (phases → groups + KO rounds + matches).
4. Serialises the result to the same JSON shape the old FastAPI
   produced (`LiveOpenResponse`), so the PWA already knows how to
   render it.
5. Inserts a new row into `fcb_opens.open_live_snapshots` per Open.

The history is intentional — every snapshot kept lets us replay an
Open's progression later. To prune, run a periodic cleanup on rows
older than 7 days.

Auth: requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars,
same as `supabase_sync`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client

from .reglament.puntuacio import points_for_position
from .scraper.classificacio import fetch_classification
from .scraper.open_live import (
    _norm_name,
    compute_open_classification,
    fetch_final_classification_id,
    fetch_has_final_classification,
    fetch_individuals_llistat,
    fetch_live_state,
)

SCHEMA = "fcb_opens"


def opens_ranking_by_name(sb_fcbillar, *, genere: str = "general") -> dict[str, int]:
    """`{nom normalitzat → posició al Rànquing Català d'Opens}` (1 = millor).

    Llegeix l'última ronda de `fcbillar.open_ranking` (la finestra vigent dels 5
    millors Opens). `sb_fcbillar` ha d'estar lligat a l'esquema `fcbillar`. Torna
    `{}` davant qualsevol error perquè l'ordenació en viu degradi cap a l'ordre de
    sorteig de la federació en comptes de petar."""
    try:
        tbl = sb_fcbillar.table("open_ranking")
        last = (
            tbl.select("ronda")
            .eq("genere", genere)
            .order("ronda", desc=True)
            .limit(1)
            .execute()
        )
        if not last.data:
            return {}
        ronda = last.data[0]["ronda"]
        rows = (
            tbl.select("posicio,jugador")
            .eq("genere", genere)
            .eq("ronda", ronda)
            .execute()
        )
        out: dict[str, int] = {}
        for r in rows.data or []:
            nom = r.get("jugador")
            pos = r.get("posicio")
            if nom and pos is not None:
                out[_norm_name(nom)] = int(pos)
        return out
    except Exception:  # noqa: BLE001
        return {}


def _client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url:
        raise RuntimeError("SUPABASE_URL env var is required")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY env var is required")
    return create_client(url, key)


# --------------------------------------------------------------------------- #
# Shape conversion: dataclasses → the same JSON the old FastAPI emitted
# --------------------------------------------------------------------------- #


def _match_payload(m) -> dict[str, Any]:
    return {
        "player_a": m.player_a,
        "player_b": m.player_b,
        "punts_a": m.punts_a,
        "punts_b": m.punts_b,
        "caramboles_a": m.caramboles_a,
        "caramboles_b": m.caramboles_b,
        "serie_major_a": m.serie_major_a,
        "serie_major_b": m.serie_major_b,
        "entrades": m.entrades,
        "arbitre": m.arbitre,
        "observations": getattr(m, "observations", None),
        "is_played": m.is_played,
    }


def _advancing_payload(p) -> dict[str, Any]:
    return {
        "name": p.name,
        "club": p.club,
        "mitjana": p.mitjana,
        "serie_major": p.serie_major,
        "source": p.source,
    }


def _state_payload(
    state,
    fetched_at: str,
    official: "Any | None" = None,
) -> dict[str, Any]:
    """Mirror of `LiveOpenResponse` from the old FastAPI."""
    phases_out: list[dict[str, Any]] = []
    for detail in state.phases:
        groups_out: list[dict[str, Any]] = []
        for g in detail.groups:
            played = sum(1 for m in g.matches if m.is_played)
            groups_out.append(
                {
                    "label": g.label,
                    "url": g.url,
                    "venue": g.venue,
                    "standings": [
                        {
                            "player_name": s.player_name,
                            "club": s.club,
                            "punts": s.punts,
                            "mitjana": s.mitjana,
                        }
                        for s in g.standings
                    ],
                    "matches": [_match_payload(m) for m in g.matches],
                    "n_matches_played": played,
                    "n_matches_total": len(g.matches),
                }
            )
        ko_out = [_match_payload(m) for m in detail.ko_matches]
        if detail.ref.kind == "group":
            played_total = sum(g["n_matches_played"] for g in groups_out)
            pending_total = sum(
                g["n_matches_total"] - g["n_matches_played"] for g in groups_out
            )
            is_active = played_total > 0 and pending_total > 0
        else:
            is_active = len(ko_out) > 0 and any(not m.is_played for m in detail.ko_matches)
        prov_quals = [
            {
                "group_label": q.group_label,
                "position_in_group": q.position_in_group,
                "player_name": q.player_name,
                "club": q.club,
                "punts": q.punts,
                "mitjana": q.mitjana,
                "serie_major": q.serie_major,
            }
            for q in detail.provisional_qualifiers
        ]
        prov_matches = [_match_payload(m) for m in detail.provisional_matches]
        prov_players = [_advancing_payload(p) for p in detail.provisional_players]
        phases_out.append(
            {
                "label": detail.ref.label,
                "kind": detail.ref.kind,
                "url": detail.ref.url,
                "groups": groups_out,
                "ko_matches": ko_out,
                "is_active": is_active,
                "provisional_qualifiers": prov_quals,
                "provisional_matches": prov_matches,
                "provisional_players": prov_players,
            }
        )
    # When FCB has published the official classification, use it as the
    # source of truth and only fall back to compute_open_classification
    # for the round_label enrichment (the official table doesn't carry
    # the elimination round directly).
    if official is not None:
        round_by_name = {
            r.player_name: r.round_label
            for r in compute_open_classification(state)
        }
        classification = [
            {
                "position": e.position,
                "player_name": e.player_name,
                "club": e.club or "",
                "round_label": round_by_name.get(e.player_name, ""),
                "mitjana": e.general_average,
                "serie_major": e.best_series,
                # Always derive Art. XVII open points from position; the
                # FCB 'Punts' column on the official table is the player's
                # match-wins, not the position-based reward.
                "open_points": points_for_position(e.position),
                "is_provisional_position": False,
            }
            for e in official.classification
        ]
        is_provisional = False
    else:
        classification = [
            {
                "position": r.position,
                "player_name": r.player_name,
                "club": r.club,
                "round_label": r.round_label,
                "mitjana": r.mitjana,
                "serie_major": r.serie_major,
                "open_points": r.open_points,
                "is_provisional_position": r.is_provisional_position,
            }
            for r in compute_open_classification(state)
        ]
        is_provisional = True
    return {
        "division_id": state.structure.division_id,
        "name": state.structure.name,
        "phase_id": state.structure.phase_id,
        "phases": phases_out,
        "classification": classification,
        "classification_is_provisional": is_provisional,
        "fetched_at": fetched_at,
    }


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


@dataclass
class SnapshotCounters:
    discovered: int = 0
    skipped_closed: int = 0
    snapshots_written: int = 0
    errors: list[str] = field(default_factory=list)


def snapshot_all_live_opens(
    *,
    on_progress=None,
    force_refresh: bool = False,
    include_closed: bool = False,
) -> SnapshotCounters:
    """Discover every ongoing Open and push a snapshot per Open.

    Args:
        force_refresh: bypass the FCB HTTP cache.
        include_closed: also re-snapshot Opens whose latest stored
            snapshot already has a CAMPIÓ row. Useful for one-off
            backfills after a classification-logic change.
    """
    if on_progress is None:
        on_progress = lambda *_a, **_kw: None  # noqa: E731

    counters = SnapshotCounters()
    sb = _client()
    fetched_at = datetime.now(timezone.utc).isoformat()
    # Ordre de sorteig dels grups encara no jugats = ordre del rànquing d'Opens.
    rank_by_name = opens_ranking_by_name(sb.schema("fcbillar"))

    on_progress("phase", "discover")
    entries = fetch_individuals_llistat(force=force_refresh)
    counters.discovered = len(entries)

    rows: list[dict[str, Any]] = []
    for entry in entries:
        name_upper = entry.name.upper()
        if "OPEN" not in name_upper:
            continue
        if "TRES BANDES" not in name_upper:
            # We only track Tres Bandes Opens; other modalities (quadre,
            # snooker, …) have a different live structure.
            continue
        if "FEMENI" in name_upper:
            # Women's Opens use a different format we don't track live.
            counters.skipped_closed += 1
            continue
        try:
            is_closed = fetch_has_final_classification(
                entry.division_id, force=force_refresh
            )
        except Exception as exc:  # noqa: BLE001
            counters.errors.append(
                f"final-classification probe failed for {entry.division_id}: {exc}"
            )
            continue
        # Once closed: only re-snapshot until we've stored a snapshot that
        # already captures the champion (= final played and rendered as a
        # 'CAMPIÓ' row in the classification). After that, skip — the
        # data won't change. `include_closed=True` overrides the skip,
        # used when we want to backfill a logic change.
        if is_closed and not include_closed:
            last = (
                sb.schema(SCHEMA)
                .table("open_live_snapshots")
                .select("payload_json")
                .eq("fcb_division_id", entry.division_id)
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
            existing = last.data[0]["payload_json"] if last.data else None
            cls = (existing or {}).get("classification") or []
            already_has_champion = any(
                (r or {}).get("round_label") == "CAMPIÓ" for r in cls
            )
            if already_has_champion:
                counters.skipped_closed += 1
                continue

        on_progress("open", f"{entry.division_id} · {entry.name}")
        try:
            state = fetch_live_state(
                entry.division_id, force=force_refresh, rank_by_name=rank_by_name
            )
        except Exception as exc:  # noqa: BLE001
            counters.errors.append(
                f"live-state fetch failed for {entry.division_id}: {exc}"
            )
            continue

        # When closed, prefer FCB's official classification — no need
        # to rely on our derived ranking once the tournament has ended.
        official = None
        if is_closed:
            try:
                clf_id = fetch_final_classification_id(
                    entry.division_id, force=force_refresh
                )
                if clf_id is not None:
                    official = fetch_classification(
                        entry.division_id, clf_id, force=force_refresh
                    )
            except Exception as exc:  # noqa: BLE001
                counters.errors.append(
                    f"official-classification fetch failed for "
                    f"{entry.division_id}: {exc}"
                )

        payload = _state_payload(state, fetched_at, official=official)
        rows.append(
            {
                "fcb_division_id": entry.division_id,
                "captured_at": fetched_at,
                "payload_json": payload,
            }
        )

    if rows:
        on_progress("phase", f"insert {len(rows)} snapshots")
        sb.schema(SCHEMA).table("open_live_snapshots").insert(rows).execute()
        counters.snapshots_written = len(rows)

    return counters
