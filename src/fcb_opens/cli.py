"""Command-line interface: `fcb-opens <command> [args]`.

Subcommands:
    init                            Initialize the SQLite database.
    scrape-ranking <month_id>       Fetch a monthly FCB ranking and store it.
    scrape-open <div_id> <clf_id>   Fetch an Open's final classification.
    scrape-historical               Ingest historical Opens from FCB.
    diff-official                   Compare official PDF ranking vs computed ranking.
    stats                           Print a quick summary of the local DB.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from . import db
from .diff import diff_rankings, pair_rankings
from .lliga.persistence import save_league_snapshot
from .lliga.scraper import incremental_refresh, scrape_competition
from .snapshot_live import snapshot_all_live_opens
from .supabase_sync import sync_all as supabase_sync_all
from .models import Player
from .paths import resolve_db_path
from .player_matching import build_matcher, normalize_for_matching
from .reglament.puntuacio import points_for_position
from .reglament.ranquing_opens import compute_opens_ranking
from .scraper import classificacio, historial, ranking
from .scraper.official_pdf import (
    OFFICIAL_RANKING_URL,
    fetch_official_ranking_pdf,
    parse_official_ranking,
)


def _resolve_cli_db(value: Path | None) -> Path:
    """Resolve the --db argument via the shared path rules."""
    return resolve_db_path(value)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help=(
            "path to the SQLite database. If omitted, uses FCB_OPENS_DB "
            "or <project_root>/data/fcb_opens.db."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="bypass the HTTP cache and refetch",
    )


def _supports_color() -> bool:
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _color(text: str, code: str) -> str:
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _kind_title(kind: str) -> str:
    return {
        "position_only": "POSITION_ONLY",
        "total_points": "TOTAL_POINTS",
        "per_open": "PER_OPEN",
        "penalty_expected": "PENALTY_EXPECTED",
        "penalty_cascade": "PENALTY_CASCADE",
        "position_cascade": "POSITION_CASCADE",
        "source_mismatch": "SOURCE_MISMATCH",
        "missing_in_official": "MISSING_IN_OFFICIAL",
        "missing_in_computed": "MISSING_IN_COMPUTED",
    }.get(kind, kind.upper())


def _kind_color(kind: str) -> str:
    if kind in {"total_points", "per_open"}:
        return "31"
    if kind == "position_only":
        return "33"
    if kind in {"penalty_expected", "penalty_cascade", "position_cascade", "source_mismatch"}:
        return "90"  # grey — expected, not a bug
    if kind in {"missing_in_official", "missing_in_computed"}:
        return "36"
    return "0"


def _print_expected_block(
    items: list,
    *,
    title: str,
    kind: str,
    subtitle: str,
    last_col_header: str,
    last_col_value: Callable[[object], str],
) -> None:
    """Render one of the discrete per-kind discrepancy blocks (penalty_expected,
    penalty_cascade, source_mismatch). All three share the same columns except
    for the last one, supplied via `last_col_header` / `last_col_value`."""
    if not items:
        return
    print()
    colored_title = _color(title, _kind_color(kind))
    print(f"[{colored_title}] count={len(items)} {subtitle}")
    last_width = max(len(last_col_header), 5)
    print(
        f"  {'pos':>4s}  {'display_name':<30s}  {'off_total':>9s}  "
        f"{'calc_total':>10s}  {last_col_header:>{last_width}s}"
    )
    for d in items:
        pos = str(d.official_position) if d.official_position is not None else "-"
        name = d.player.display_name
        if len(name) > 30:
            name = name[:29] + "…"
        off_t = d.official_total or 0
        calc_t = d.computed_total or 0
        print(
            f"  {pos:>4s}  {name:<30s}  {off_t:>9d}  "
            f"{calc_t:>10d}  {last_col_value(d)}"
        )


def cmd_init(args: argparse.Namespace) -> int:
    db.init_db(args.db)
    print(f"Initialized database at {args.db}")
    return 0


def cmd_scrape_ranking(args: argparse.Namespace) -> int:
    url = ranking.ranking_url(args.month_id)
    print(f"Fetching {url} ...")
    result = ranking.fetch_ranking(args.month_id, force=args.force)
    print(f"Parsed {len(result.entries)} entries for month_id={args.month_id}")

    db.init_db(args.db)
    conn = db.connect(args.db)
    try:
        db.save_monthly_ranking(conn, result)
        conn.commit()
    finally:
        conn.close()
    print(f"Stored in {args.db}")
    return 0


def cmd_scrape_open(args: argparse.Namespace) -> int:
    url = classificacio.classification_url(args.division_id, args.classification_id)
    print(f"Fetching {url} ...")
    open_data = classificacio.fetch_classification(
        args.division_id, args.classification_id, force=args.force
    )
    open_data.season = args.season or ""
    print(f"Parsed '{open_data.name}' - {len(open_data.classification)} players")
    print()
    print("Top 10 with Open points:")
    for entry in open_data.classification[:10]:
        pts = points_for_position(entry.position)
        club = entry.club or "-"
        print(
            f"  {entry.position:3d}. {entry.player_name:<40s} "
            f"[{club:<20s}] MG={entry.general_average:.3f}  -> {pts:>3d} pts"
        )

    db.init_db(args.db)
    conn = db.connect(args.db)
    try:
        db.save_open(conn, open_data)
        conn.commit()
    finally:
        conn.close()
    print(f"\nStored in {args.db}")
    return 0


def cmd_scrape_current_opens(args: argparse.Namespace) -> int:
    """Discover all current-season Tres Bandes Opens that already have a
    final classification published and store each one in the local DB.

    Idempotent: re-running re-imports the latest classification (FCB
    occasionally amends published rankings).
    """
    from .scraper.open_live import (
        fetch_final_classification_id,
        fetch_individuals_llistat,
    )

    print("Walking FCB /individuals/llistat ...")
    entries = fetch_individuals_llistat(force=args.force)

    db.init_db(args.db)
    conn = db.connect(args.db)
    saved = 0
    skipped = 0
    errors: list[str] = []
    try:
        for entry in entries:
            name_upper = entry.name.upper()
            if "OPEN" not in name_upper or "TRES BANDES" not in name_upper:
                continue
            if "FEMENI" in name_upper:
                continue
            try:
                clf_id = fetch_final_classification_id(
                    entry.division_id, force=args.force
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{entry.division_id}: probe failed: {exc}")
                continue
            if clf_id is None:
                skipped += 1
                print(f"  [skip] #{entry.division_id} {entry.name} — no classificaciofinal yet")
                continue
            try:
                open_data = classificacio.fetch_classification(
                    entry.division_id, clf_id, force=args.force
                )
                open_data.season = args.season or ""
                db.save_open(conn, open_data)
                saved += 1
                print(
                    f"  [ok]   #{entry.division_id}/{clf_id} {open_data.name} "
                    f"({len(open_data.classification)} players)"
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{entry.division_id}/{clf_id}: scrape failed: {exc}")
                continue
        conn.commit()
    finally:
        conn.close()

    print()
    print(f"Saved:    {saved}")
    print(f"Skipped:  {skipped}")
    if errors:
        print(f"Errors:   {len(errors)}")
        for e in errors:
            print(f"  - {e}")
    return 0


def cmd_scrape_historical(args: argparse.Namespace) -> int:
    """Walk the FCB historial pages and ingest all 3-bandes Opens."""
    include_ids: set[int] | None = set(args.include_id) if args.include_id else None
    extra_excludes = tuple(args.exclude_name) if args.exclude_name else ()
    exclude_patterns = historial.DEFAULT_EXCLUDE_PATTERNS + extra_excludes
    seasons_filter: list[str] | None = [args.season] if args.season else None

    # Discover
    print("Walking FCB historial ...")
    discovered: list[historial.HistoricalOpen] = []
    walk_errors: list[str] = []
    for item in historial.discover_historical_opens(
        seasons=seasons_filter,
        exclude_patterns=exclude_patterns,
        include_ids=include_ids,
        only_name_substring=args.only_name,
        rate_limit_s=args.rate_limit,
        force=args.force,
    ):
        if isinstance(item, historial.HistoricalOpen):
            discovered.append(item)
            print(f"  [{item.season}] #{item.division_id}/{item.classification_id}  {item.name}")
        else:
            _, message = item
            walk_errors.append(message)
            print(f"  [ERROR] {message}")

    print(f"\nDiscovered {len(discovered)} Opens across the walk")
    if walk_errors:
        print(f"Walk errors: {len(walk_errors)}")

    if args.dry_run:
        print("\n(dry-run: no classifications fetched, nothing stored)")
        return 0

    if not discovered:
        print("Nothing to ingest.")
        return 0

    # Ingest
    db.init_db(args.db)
    existing_div_ids: set[int] = set()
    if args.skip_existing:
        conn = db.connect(args.db)
        try:
            rows = conn.execute("SELECT fcb_division_id FROM opens").fetchall()
            existing_div_ids = {r["fcb_division_id"] for r in rows}
        finally:
            conn.close()

    saved = 0
    skipped = 0
    errors: list[tuple[historial.HistoricalOpen, str]] = []

    print(f"\nIngesting into {args.db} (one transaction per Open) ...")
    for h_open in discovered:
        if args.skip_existing and h_open.division_id in existing_div_ids:
            skipped += 1
            continue
        try:
            # Use the /individuals/ URL even for historical Opens: the FCB
            # serves the real classification table from there for all divisions.
            open_data = classificacio.fetch_classification(
                h_open.division_id,
                h_open.classification_id,
                force=args.force,
            )
            open_data.name = h_open.name
            open_data.season = h_open.season
        except Exception as e:
            errors.append((h_open, f"fetch failed: {e}"))
            print(f"  [ERROR] {h_open.name}: fetch failed: {e}")
            continue

        try:
            conn = db.connect(args.db)
            try:
                db.save_open(conn, open_data)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            errors.append((h_open, f"save failed: {e}"))
            print(f"  [ERROR] {h_open.name}: save failed: {e}")
            continue

        saved += 1
        print(
            f"  [{h_open.season}] {h_open.name}: saved "
            f"{len(open_data.classification)} entries"
        )

    print()
    print(f"Saved:   {saved}")
    print(f"Skipped: {skipped} (already in DB)")
    print(f"Errors:  {len(errors)}")
    if errors:
        print("\nFailed Opens:")
        for h, msg in errors:
            print(f"  #{h.division_id}  {h.name}  -  {msg}")
    return 0 if not errors else 2


def cmd_diff_official(args: argparse.Namespace) -> int:
    url = args.url
    print(f"Loading official ranking PDF from {url} ...")
    try:
        pdf = fetch_official_ranking_pdf(
            url=url,
            force=args.force,
            use_cache_only=args.no_fetch,
        )
    except FileNotFoundError as e:
        print(str(e))
        return 1

    official = parse_official_ranking(pdf, source_url=url)

    db.init_db(args.db)
    conn = db.connect(args.db)
    try:
        computed = compute_opens_ranking(conn, num_recent_opens=len(official.opens))

        rows = list(db.all_players(conn))
        players = [Player(display_name=r["display_name"], club=r["current_club"]) for r in rows]
        id_by_norm = {
            normalize_for_matching(r["display_name"]): int(r["id"])
            for r in rows
        }
    finally:
        conn.close()

    matcher = build_matcher(players)

    def _lookup_player_id(name: str) -> int | None:
        matched = matcher(name)
        if matched is None:
            return None
        return id_by_norm.get(normalize_for_matching(matched.display_name))

    report = diff_rankings(official, computed, _lookup_player_id)

    line = "=" * 56
    print(line)
    print(" DIFF RANKING OFICIAL vs CALCULAT")
    print(line)
    print(f" Font oficial: {report.official_source}")
    print(f" Opens al PDF: {len(official.opens)}")
    print(f" Entries oficial: {report.official_size}")
    print(f" Entries calculat: {report.computed_size}")
    print(f" Matched sense discrepancia: {_color(str(report.matched_count), '32')}")
    print(f" Discrepancies: {len(report.discrepancies)}")
    print(line)

    grouped: dict[str, list] = defaultdict(list)
    for d in report.discrepancies:
        grouped[d.kind].append(d)

    kind_order = [
        "position_only",
        "total_points",
        "per_open",
        "missing_in_official",
        "missing_in_computed",
    ]

    penalty_expected = grouped.get("penalty_expected", [])
    penalty_cascade = grouped.get("penalty_cascade", [])
    position_cascade = grouped.get("position_cascade", [])
    source_mismatch = grouped.get("source_mismatch", [])

    for kind in kind_order:
        items = grouped.get(kind, [])
        if not items:
            continue
        print()
        title = _color(_kind_title(kind), _kind_color(kind))
        print(f"[{title}] count={len(items)}")

        limit = args.limit if args.limit is not None else len(items)
        for d in items[:limit]:
            club = d.player.club or "-"
            pos = d.official_position if d.official_position is not None else d.computed_position
            pos_text = f"#{pos}" if pos is not None else "#-"
            print(f"  [{_kind_title(d.kind)}] {pos_text} {d.player.display_name} [{club}]")

            if d.kind == "missing_in_computed":
                print(f"     Al PDF: pos {d.official_position}, total {d.official_total}")
                print("     No s'ha trobat cap match a la BD")
            elif d.kind == "missing_in_official":
                print(f"     Al calcul: pos {d.computed_position}, total {d.computed_total}")
                print("     No existeix al PDF oficial")
            elif d.kind == "position_only":
                print(
                    f"     Oficial: pos {d.official_position}, calcul: pos {d.computed_position} "
                    f"(mateix total: {d.official_total})"
                )
                print(f"     Detalls: {d.details}")
            else:
                print(f"     Oficial: pos {d.official_position}, total {d.official_total}")
                print(f"     Calcul:  pos {d.computed_position}, total {d.computed_total}")
                print(f"     Detalls: {d.details}")

        if args.limit is not None and len(items) > args.limit:
            print(f"     ... {len(items) - args.limit} mes no mostrats")

    _print_expected_block(
        penalty_expected,
        title="PENALTY EXPECTED",
        kind="penalty_expected",
        subtitle="(penalitzacions -20 no implementades a la BD)",
        last_col_header="n_penalties",
        last_col_value=lambda d: f"{(d.n_penalties or 1):>11d}",
    )
    _print_expected_block(
        penalty_cascade,
        title="PENALTY CASCADE",
        kind="penalty_cascade",
        subtitle="(desplaçament posicions per -20 oficials)",
        last_col_header="diff",
        last_col_value=lambda d: f"{((d.official_total or 0) - (d.computed_total or 0)):>+5d}",
    )
    _print_expected_block(
        position_cascade,
        title="POSITION CASCADE",
        kind="position_cascade",
        subtitle="(POSITION_ONLY explicat per intruders amb total inflat)",
        last_col_header="delta",
        last_col_value=lambda d: f"{((d.computed_position or 0) - (d.official_position or 0)):>+5d}",
    )
    _print_expected_block(
        source_mismatch,
        title="SOURCE MISMATCH",
        kind="source_mismatch",
        subtitle="(PDF i HTML discrepen sobre quins Opens va jugar el jugador)",
        last_col_header="diff",
        last_col_value=lambda d: f"{((d.official_total or 0) - (d.computed_total or 0)):>+5d}",
    )

    if args.show_matched:
        print()
        print(_color("[MATCHED SENSE DISCREPANCIA]", "32"))
        discrepancy_names = {d.player.display_name for d in report.discrepancies}
        matched_pairs = pair_rankings(official, computed)
        clean = [p for p in matched_pairs if p.official.display_name not in discrepancy_names]
        for p in clean:
            club = p.official.club or p.computed.club or "-"
            print(f"  #{p.official.position} {p.official.display_name} [{club}] {p.official.total_points}")

    if args.exit_code_on_diff and report.discrepancies:
        return 2
    return 0


def cmd_scrape_lliga(args: argparse.Namespace) -> int:
    """Walk a league competition and persist every page to the DB.

    Default mode is *incremental*: jornades that are already 100% played in
    the local DB are reused without re-hitting the network. Pass `--full`
    to force a complete re-scrape from scratch (slow; useful after bugs).

    For Tres Bandes the competition id is 36. Progress streams to stdout.
    """
    competition_id: int = args.competition_id

    def _on_progress(level: str, message: str) -> None:
        prefix = {
            "competition": "[lliga]",
            "division": "  [div]   ",
            "group":    "    [grup]  ",
            "jornada":  "      [jorn] ",
        }.get(level, f"  [{level}]")
        print(f"{prefix} {message}")

    db.init_db(args.db)

    if args.full:
        print(f"Scraping (FULL) competition {competition_id} ...")
        snapshot, progress = scrape_competition(
            competition_id,
            season=args.season or "",
            force=args.force,
            on_progress=_on_progress,
        )
        conn = db.connect(args.db)
        try:
            save_league_snapshot(conn, snapshot)
            conn.commit()
        finally:
            conn.close()
    else:
        print(f"Refreshing (incremental) competition {competition_id} ...")
        conn = db.connect(args.db)
        try:
            progress = incremental_refresh(
                conn,
                competition_id,
                season=args.season or "",
                force=args.force,
                on_progress=_on_progress,
            )
        finally:
            conn.close()

    print()
    print(
        f"Parsed: {progress.divisions} divisions, {progress.groups} grups, "
        f"{progress.jornades} jornades "
        f"(reaprofitades: {progress.jornades_skipped}), "
        f"{progress.encontres} encontres, {progress.partides} partides"
    )
    print(f"Stored in {args.db}")
    return 0


def cmd_supabase_sync(args: argparse.Namespace) -> int:
    """Push the local SQLite snapshot to Supabase (`fcb_opens` schema).

    Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the environment.
    The service-role key bypasses RLS; never commit it.
    """
    if not args.db.exists():
        print(f"No database at {args.db}. Run scrape commands first.")
        return 1

    def _on_progress(level: str, message: str) -> None:
        prefix = {
            "phase":    "[fase]    ",
            "league":   "  [lliga]  ",
            "division": "    [div]   ",
            "group":    "      [grup] ",
        }.get(level, f"[{level}]")
        print(f"{prefix} {message}")

    conn = db.connect(args.db)
    try:
        counters = supabase_sync_all(conn, on_progress=_on_progress)
    finally:
        conn.close()

    print()
    print("Synced to Supabase:")
    print(f"  players:                  {counters.players}")
    print(f"  monthly_rankings:         {counters.monthly_rankings}")
    print(f"  monthly_ranking_entries:  {counters.monthly_ranking_entries}")
    print(f"  opens:                    {counters.opens}")
    print(f"  open_classifications:     {counters.open_classifications}")
    print(f"  leagues:                  {counters.leagues}")
    print(f"  league_divisions:         {counters.league_divisions}")
    print(f"  league_groups:            {counters.league_groups}")
    print(f"  league_team_standings:    {counters.league_team_standings}")
    print(f"  league_jornades:          {counters.league_jornades}")
    print(f"  league_encontres:         {counters.league_encontres}")
    print(f"  league_partides:          {counters.league_partides}")
    return 0


def cmd_snapshot_live_opens(args: argparse.Namespace) -> int:
    """Capture the live state of every ongoing Open and push to Supabase.

    Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the env. Bypasses
    the local SQLite — snapshots go straight to `fcb_opens.open_live_snapshots`.
    Use `--force` to bypass the FCB HTTP cache for the freshest data.
    """
    def _on_progress(level: str, message: str) -> None:
        prefix = {
            "phase": "[fase]",
            "open":  "  [open]",
        }.get(level, f"[{level}]")
        print(f"{prefix} {message}")

    counters = snapshot_all_live_opens(
        on_progress=_on_progress,
        force_refresh=args.force,
        include_closed=getattr(args, "include_closed", False),
    )
    print()
    print(f"Discovered:        {counters.discovered}")
    print(f"Skipped (closed):  {counters.skipped_closed}")
    print(f"Snapshots written: {counters.snapshots_written}")
    if counters.errors:
        print(f"Errors:            {len(counters.errors)}")
        for err in counters.errors:
            print(f"  - {err}")
        return 2
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"No database at {args.db}. Run `fcb-opens init` first.")
        return 1
    conn = db.connect(args.db)
    try:
        n_rankings = db.count_monthly_rankings(conn)
        n_opens = db.count_opens(conn)
        n_players = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
    finally:
        conn.close()
    print(f"Database: {args.db}")
    print(f"  Monthly rankings: {n_rankings}")
    print(f"  Opens:            {n_opens}")
    print(f"  Known players:    {n_players}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fcb-opens",
        description="Scraper and rule engine for FCB Opens Tres Bandes.",
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    p_init = subparsers.add_parser("init", help="initialize the database")
    _add_common_args(p_init)
    p_init.set_defaults(func=cmd_init)

    p_ranking = subparsers.add_parser(
        "scrape-ranking", help="fetch a monthly FCB ranking"
    )
    p_ranking.add_argument(
        "month_id", type=int, help="FCB month identifier (e.g. 120 = March 2026)"
    )
    _add_common_args(p_ranking)
    p_ranking.set_defaults(func=cmd_scrape_ranking)

    p_open = subparsers.add_parser(
        "scrape-open", help="fetch an Open's final classification"
    )
    p_open.add_argument("division_id", type=int, help="FCB division id (e.g. 204)")
    p_open.add_argument(
        "classification_id", type=int, help="FCB classification id (e.g. 439)"
    )
    p_open.add_argument("--season", type=str, default="", help="season label, e.g. 2025-26")
    _add_common_args(p_open)
    p_open.set_defaults(func=cmd_scrape_open)

    p_curr = subparsers.add_parser(
        "scrape-current-opens",
        help=(
            "auto-discover current-season Tres Bandes Opens with a published "
            "classification and ingest them into the local DB"
        ),
    )
    p_curr.add_argument(
        "--season",
        type=str,
        default="",
        help="season label to attach to imported Opens, e.g. 2025-26",
    )
    _add_common_args(p_curr)
    p_curr.set_defaults(func=cmd_scrape_current_opens)

    p_hist = subparsers.add_parser(
        "scrape-historical",
        help="walk the FCB historial and ingest all 3-bandes Opens",
    )
    p_hist.add_argument(
        "--season",
        type=str,
        default=None,
        help="restrict to a single season, e.g. 2023-2024",
    )
    p_hist.add_argument(
        "--dry-run",
        action="store_true",
        help="discover Opens and print the plan, do not fetch classifications",
    )
    p_hist.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="skip Opens whose division_id is already in the DB (default)",
    )
    p_hist.add_argument(
        "--overwrite",
        dest="skip_existing",
        action="store_false",
        help="re-fetch Opens that are already in the DB",
    )
    p_hist.add_argument(
        "--exclude-name",
        action="append",
        default=[],
        metavar="PATTERN",
        help="extra name substring (case/accent-insensitive) to exclude; repeatable",
    )
    p_hist.add_argument(
        "--include-id",
        action="append",
        type=int,
        default=[],
        metavar="DIV_ID",
        help="force-include a division id regardless of name; repeatable",
    )
    p_hist.add_argument(
        "--only-name",
        type=str,
        default=None,
        help="only keep competitions whose name contains this substring",
    )
    p_hist.add_argument(
        "--rate-limit",
        type=float,
        default=0.3,
        help="seconds to sleep between requests (default 0.3)",
    )
    _add_common_args(p_hist)
    p_hist.set_defaults(func=cmd_scrape_historical)

    p_diff = subparsers.add_parser(
        "diff-official",
        help="compare official PDF Open ranking vs computed ranking",
    )
    p_diff.add_argument("--url", type=str, default=OFFICIAL_RANKING_URL, help="official PDF URL")
    p_diff.add_argument(
        "--no-fetch",
        action="store_true",
        help="use only local cache; fail if cached PDF does not exist",
    )
    p_diff.add_argument(
        "--show-matched",
        action="store_true",
        help="print players matched without discrepancies",
    )
    p_diff.add_argument(
        "--exit-code-on-diff",
        action="store_true",
        help="exit with code 2 when discrepancies exist",
    )
    p_diff.add_argument(
        "--limit",
        type=int,
        default=None,
        help="limit shown discrepancies per kind",
    )
    _add_common_args(p_diff)
    p_diff.set_defaults(func=cmd_diff_official)

    p_lliga = subparsers.add_parser(
        "scrape-lliga",
        help="walk a full FCB league competition (e.g. 36 = Tres Bandes) and store it",
    )
    p_lliga.add_argument(
        "competition_id",
        type=int,
        help="FCB competition id (36 = Lliga Catalana Tres Bandes)",
    )
    p_lliga.add_argument(
        "--season",
        type=str,
        default="",
        help="season label, e.g. 2025-26",
    )
    p_lliga.add_argument(
        "--full",
        action="store_true",
        help=(
            "force a complete re-scrape, even for jornades already saved as "
            "fully played. Default is incremental: only refetch in-flight "
            "jornades."
        ),
    )
    _add_common_args(p_lliga)
    p_lliga.set_defaults(func=cmd_scrape_lliga)

    p_sync = subparsers.add_parser(
        "supabase-sync",
        help="push local SQLite snapshot to the Supabase fcb_opens schema",
    )
    _add_common_args(p_sync)
    p_sync.set_defaults(func=cmd_supabase_sync)

    p_live = subparsers.add_parser(
        "snapshot-live-opens",
        help="snapshot all ongoing Opens and push the JSON state to Supabase",
    )
    _add_common_args(p_live)
    p_live.add_argument(
        "--include-closed",
        action="store_true",
        help="also re-snapshot Opens whose latest stored snapshot already "
        "has a CAMPIÓ row (one-off backfill).",
    )
    p_live.set_defaults(func=cmd_snapshot_live_opens)

    p_stats = subparsers.add_parser("stats", help="print a summary of the local DB")
    _add_common_args(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.db = _resolve_cli_db(args.db)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
