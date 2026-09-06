"""CLI de FCBillar (Typer)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    reconf = getattr(_stream, "reconfigure", None)
    if reconf is not None:
        reconf(encoding="utf-8", errors="replace")
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from fcbillar.clubs import canonic
from fcbillar.config import get_settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository

# Sub-app per a comandes de manteniment de clubs.
clubs_app = typer.Typer(help="Gestió de clubs i aliases.", no_args_is_help=True)
from fcbillar.pipeline import (
    backfill_historical,
    backfill_modalitat,
    discover_lliga,
    fetch_ranking_html,
    find_club_grups,
    find_club_players,
    import_clubs_oficials,
    import_temporada,
    ingest_copa_edicio,
    ingest_individuals_all_temporades,
    ingest_individuals_temporada,
    ingest_lliga_grup,
    ingest_lliga_jornada,
    ingest_partides,
    ingest_ranking,
    reconcile_ranking_dates,
    run_status,
    set_follow,
    sync_current_rankings,
)
from fcbillar.scraper.client import ScraperClient
from fcbillar.scraper.parsers import parse_ranking_historial

app = typer.Typer(
    name="fcbillar",
    help="Scraper de rànquings i partides de la Federació Catalana de Billar.",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_time=False, show_path=False)],
    )


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Logs detallats")) -> None:
    _setup_logging(verbose)


@app.command()
def status() -> None:
    """Mostra el contingut actual de la BD."""
    counts = run_status()
    table = Table(title="FCBillar — estat de la BD")
    table.add_column("Taula", style="cyan")
    table.add_column("Files", justify="right", style="green")
    for name, n in counts.items():
        table.add_row(name, str(n))
    console.print(table)


@app.command()
def init_db() -> None:
    """Crea/actualitza l'esquema de la BD SQLite."""
    settings = get_settings()
    ensure_schema(settings.db_path)
    console.print(f"[green]✓ Esquema verificat a {settings.db_path}[/]")


@app.command("fix-winners")
def fix_winners_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Només mostra, no escriu"),
) -> None:
    """Recalcula el guanyador de cada partida des de les caramboles.

    A la caràmbola guanya qui fa més caramboles (empat = sense guanyador). Algunes
    partides poden tenir el guanyador inconsistent (p.ex. residu de col·lisions de
    deduplicació anteriors); aquesta comanda ho corregeix de forma determinista.
    """
    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    bad = conn.execute(
        """
        SELECT id, player1_id, player2_id, caramboles1, caramboles2
        FROM games
        WHERE caramboles1 IS NOT NULL AND caramboles2 IS NOT NULL
          AND caramboles1 <> caramboles2
          AND (
            guanyador_id IS NULL
            OR (caramboles1 > caramboles2 AND guanyador_id <> player1_id)
            OR (caramboles2 > caramboles1 AND guanyador_id <> player2_id)
          )
        """
    ).fetchall()
    for r in bad:
        correct = r["player1_id"] if r["caramboles1"] > r["caramboles2"] else r["player2_id"]
        if not dry_run:
            conn.execute("UPDATE games SET guanyador_id = ? WHERE id = ?", (correct, r["id"]))
    if not dry_run:
        conn.commit()
    verb = "es corregirien" if dry_run else "corregides"
    console.print(f"[green]OK {len(bad)} partides {verb}.[/]")


@app.command()
def fetch_ranking(
    num_seq: int = typer.Argument(..., help="Número seqüencial del rànquing"),
    modalitat: int = typer.Argument(..., help="Codi de modalitat (1=tres bandes…)"),
    save: bool = typer.Option(True, help="Desa l'HTML a tests/fixtures per a desenvolupament"),
) -> None:
    """Descarrega l'HTML d'un rànquing concret (POC). Encara no fa parsing."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = fetch_ranking_html(client, num_seq, modalitat)
    if result is None:
        console.print("[red]No s'ha pogut obtenir HTML vàlid amb cap format d'URL[/]")
        raise typer.Exit(1)
    console.print(f"[green]✓ HTML obtingut amb format '{result.fmt}'[/] de {result.url}")
    console.print(f"[dim]Mida: {len(result.html):,} bytes[/]")
    if save:
        from pathlib import Path

        fixtures = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
        fixtures.mkdir(parents=True, exist_ok=True)
        out = fixtures / f"ranking_{modalitat}_{num_seq}_{result.fmt}.html"
        out.write_text(result.html, encoding="utf-8")
        console.print(f"[dim]Desat a {out}[/]")


@app.command("ingest-ranking")
def ingest_ranking_cmd(
    num_seq: int = typer.Argument(..., help="Número seqüencial del rànquing"),
    modalitat: int = typer.Argument(
        ...,
        help="Codi de modalitat (1=tres bandes, 2=lliure, 3=quadre 47/2, 4=banda, 6=quadre 71/2)",
    ),
) -> None:
    """Descarrega un rànquing, el parseja i el desa a la BD."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = ingest_ranking(client, num_seq, modalitat, settings=settings)
    if result is None:
        console.print("[red]No s'ha pogut obtenir HTML vàlid per al rànquing[/]")
        raise typer.Exit(1)
    console.print(
        f"[green]OK rànquing {num_seq}/{modalitat} ingerit "
        f"({result.players_upserted} jugadors, {result.entries_upserted} entries) "
        f"des de {result.fetch.url}[/]"
    )


@app.command("ingest-partides")
def ingest_partides_cmd(
    num_seq: int = typer.Argument(..., help="Número seqüencial del rànquing"),
    modalitat: int = typer.Argument(..., help="Codi de modalitat"),
    player_fcb_id: str = typer.Argument(
        ..., help="fcb_id intern del jugador (vist a la URL Partides)"
    ),
    create_missing_players: bool = typer.Option(
        False,
        "--create-missing-players",
        help="Crea placeholders pels contraris no registrats (fusió automàtica posterior)",
    ),
) -> None:
    """Descarrega les partides d'un jugador dins d'un rànquing i les desa a la BD."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = ingest_partides(
            client,
            num_seq,
            modalitat,
            player_fcb_id,
            settings=settings,
            create_missing_players=create_missing_players,
        )
    console.print(
        f"[green]OK partides {num_seq}/{modalitat}/{player_fcb_id}: "
        f"{result.games_upserted} desades, "
        f"{result.games_skipped_missing_opponent} saltades (contrari fora BD), "
        f"{result.links_created} links creats[/]"
    )


@app.command()
def follow(
    fcb_id: str = typer.Argument(..., help="fcb_id intern del jugador (numèric)"),
    off: bool = typer.Option(False, "--off", help="Desmarcar (unfollow) enlloc de seguir"),
) -> None:
    """Marca un jugador com a seguit (o el desmarca amb --off)."""
    ok = set_follow(fcb_id, follow=not off)
    if not ok:
        console.print(f"[red]Jugador {fcb_id} no està a la BD.[/]")
        raise typer.Exit(1)
    accio = "desmarcat" if off else "marcat com a seguit"
    console.print(f"[green]OK Jugador {fcb_id} {accio}.[/]")


@app.command()
def sync() -> None:
    """Sincronitza: detecta rànquings nous a la home i els ingereix."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = sync_current_rankings(client, settings=settings)
    if result.ingested:
        console.print(
            f"[green]OK Ingerits {len(result.ingested)} rànquings nous: {result.ingested}[/]"
        )
    else:
        console.print(
            f"[yellow]Tot al dia. Rànquings actuals: {[(r.num_seq, r.modalitat_codi_fcb) for r in result.discovered.rankings]}[/]"
        )


@app.command("reconcile-ranking-dates")
def reconcile_ranking_dates_cmd(
    historial_html: str | None = typer.Argument(
        None,
        help="Camí a un HTML guardat de /ca/jugador/ranking/historial. "
        "Si s'omet, es prova la sessió viva.",
    ),
) -> None:
    """Lliga num_seq → data real de publicació (de l'historial) i en corregeix
    el mes/any. Desa rankings.data_pub i re-deriva any_pub/mes_pub."""
    from pathlib import Path

    settings = get_settings()
    if historial_html:
        html = Path(historial_html).read_text(encoding="utf-8", errors="replace")
        console.print(f"[cyan]Historial des de fitxer: {historial_html}[/]")
    else:
        url = f"{settings.base_url.rstrip('/')}/ca/jugador/ranking/historial"
        with ScraperClient(settings) as client:
            html = client.fetch_html(url, use_cache=False)
        console.print(f"[cyan]Historial des de la sessió viva: {url}[/]")

    entries = parse_ranking_historial(html)
    result = reconcile_ranking_dates(entries, settings=settings)

    console.print(
        f"[green]Datats {result.dated} num_seq de l'historial.[/]  "
        f"Canvis de mes: {len(result.changed)}.  "
        f"No a la BD: {result.not_in_db or '—'}"
    )
    if result.changed:
        table = Table(title="Correccions de mes (num_seq → mes real)")
        table.add_column("num_seq", justify="right")
        table.add_column("data_pub")
        table.add_column("abans")
        table.add_column("després")
        for c in result.changed:
            old = f"{c.old[0]}-{c.old[1]:02d}" if c.old[0] else "—"
            new = f"{c.new[0]}-{c.new[1]:02d}"
            table.add_row(str(c.num_seq), c.data_pub, old, f"[bold yellow]{new}[/]")
        console.print(table)


@app.command()
def backfill(
    modalitat: int = typer.Argument(
        ...,
        help="Codi de modalitat (1=tres bandes, 2=lliure, ...). Amb --historical: 0=totes les modalitats.",
    ),
    top: int | None = typer.Option(
        None, "--top", help="Limitar a top-N jugadors del rànquing (per defecte tots)"
    ),
    only_followed: bool = typer.Option(
        False, "--only-followed", help="Només jugadors marcats com a seguits"
    ),
    historical: bool = typer.Option(
        False, "--historical", help="Ingerir tots els rànquings de l'historial (no només l'actual)"
    ),
) -> None:
    """Backfill del rànquing actual (o tot l'historial amb --historical) + partides."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        if historical:
            mod_filter = None if modalitat == 0 else modalitat
            res = backfill_historical(
                client,
                modalitat_codi_fcb=mod_filter,
                top_n=top,
                only_followed=only_followed,
                settings=settings,
            )
            console.print(
                f"[green]OK backfill històric: {len(res.rankings_processed)} rànquings processats, "
                f"{len(res.rankings_failed)} fallats, "
                f"{res.total_players_processed} (player,ranking) processats, "
                f"{res.total_games_upserted} partides desades, "
                f"{res.total_games_skipped} saltades.[/]"
            )
            if res.rankings_failed:
                console.print(f"[yellow]Rànquings fallats: {res.rankings_failed}[/]")
        else:
            result = backfill_modalitat(
                client,
                modalitat,
                top_n=top,
                only_followed=only_followed,
                settings=settings,
            )
            console.print(
                f"[green]OK backfill modalitat {modalitat}: "
                f"{result.players_processed} jugadors processats, "
                f"{result.total_games_upserted} partides desades, "
                f"{result.total_games_skipped} saltades.[/]"
            )


@app.command("ingest-lliga-jornada")
def ingest_lliga_jornada_cmd(
    lliga_id: int = typer.Argument(..., help="Id de la lliga (36=TRES BANDES, 37=4 MODALITATS)"),
    divisio_id: int = typer.Argument(..., help="Id de la divisió"),
    grup_id: int = typer.Argument(..., help="Id del grup"),
    jornada_id: int = typer.Argument(..., help="Id de la jornada"),
    modalitat: int = typer.Option(1, "--modalitat", help="Codi de modalitat (1=tres bandes)"),
    data: str | None = typer.Option(
        None,
        "--data",
        help="Data de la jornada (YYYY-MM-DD); s'usa per derivar la temporada",
    ),
    create_missing_players: bool = typer.Option(
        False,
        "--create-missing-players",
        help="Crea placeholders pels jugadors no registrats (fusió automàtica posterior)",
    ),
) -> None:
    """Ingest tots els encontres+partides d'una jornada de lliga."""
    from datetime import date as _date

    settings = get_settings()
    data_val = _date.fromisoformat(data) if data else None
    with ScraperClient(settings) as client:
        result = ingest_lliga_jornada(
            client,
            lliga_id=lliga_id,
            divisio_id=divisio_id,
            grup_id=grup_id,
            jornada_id=jornada_id,
            modalitat_codi_fcb=modalitat,
            data=data_val,
            settings=settings,
            create_missing_players=create_missing_players,
        )
    console.print(
        f"[green]OK jornada {lliga_id}/{divisio_id}/{grup_id}/{jornada_id}: "
        f"{result.encontres_processed} encontres ({result.encontres_failed} fallats), "
        f"{result.total_games_upserted} partides desades, "
        f"{result.total_games_skipped} saltades.[/]"
    )


@app.command("ingest-lliga-grup")
def ingest_lliga_grup_cmd(
    lliga_id: int = typer.Argument(..., help="Id de la lliga (36=TRES BANDES, 37=4 MODALITATS)"),
    divisio_id: int = typer.Argument(..., help="Id de la divisió"),
    grup_id: int = typer.Argument(..., help="Id del grup"),
    modalitat: int = typer.Option(1, "--modalitat", help="Codi de modalitat"),
    create_missing_players: bool = typer.Option(
        False,
        "--create-missing-players",
        help="Crea placeholders pels jugadors no registrats",
    ),
) -> None:
    """Ingest totes les jornades d'un grup de lliga (descobreix automàticament)."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = ingest_lliga_grup(
            client,
            lliga_id=lliga_id,
            divisio_id=divisio_id,
            grup_id=grup_id,
            modalitat_codi_fcb=modalitat,
            settings=settings,
            create_missing_players=create_missing_players,
        )
    console.print(
        f"[green]OK grup {lliga_id}/{divisio_id}/{grup_id}: "
        f"{result.jornades_processed} jornades ({result.jornades_failed} fallades), "
        f"{result.total_encontres} encontres, "
        f"{result.total_games_upserted} partides desades, "
        f"{result.total_games_skipped} saltades.[/]"
    )


@app.command("ingest-lliga")
def ingest_lliga_cmd(
    lliga_id: int = typer.Argument(36, help="Id de la lliga (36=TRES BANDES, 37=4 MODALITATS)"),
    modalitat: int = typer.Option(1, "--modalitat", help="Codi de modalitat"),
    create_missing_players: bool = typer.Option(
        False, "--create-missing-players", help="Crea placeholders pels jugadors no registrats"
    ),
) -> None:
    """Ingest de TOTA una lliga: descobreix divisions+grups (incloses PROMOCIONS i
    FINALS) i ingest totes les jornades de cada grup. Pàgines públiques (no login)."""
    settings = get_settings()
    tot_enc = tot_up = tot_skip = 0
    with ScraperClient(settings) as client:
        tree = discover_lliga(client, lliga_id, depth=2)
        n_grups = sum(len(g) for g in tree.grups_by_div.values())
        console.print(
            f"[cyan]Lliga {lliga_id}: {len(tree.divisions)} divisions, {n_grups} grups[/]"
        )
        for div in tree.divisions:
            for grup in tree.grups_by_div.get(div.divisio_id, []):
                try:
                    r = ingest_lliga_grup(
                        client,
                        lliga_id=lliga_id,
                        divisio_id=div.divisio_id,
                        grup_id=grup.grup_id,
                        modalitat_codi_fcb=modalitat,
                        settings=settings,
                        create_missing_players=create_missing_players,
                    )
                    tot_enc += r.total_encontres
                    tot_up += r.total_games_upserted
                    tot_skip += r.total_games_skipped
                    console.print(
                        f"  {div.divisio_id}/{grup.grup_id} {grup.nom}: "
                        f"{r.jornades_processed} jorn, {r.total_encontres} enc, "
                        f"{r.total_games_upserted} desades, {r.total_games_skipped} pendents"
                    )
                except Exception as e:  # noqa: BLE001
                    console.print(
                        f"  [yellow]{div.divisio_id}/{grup.grup_id} {grup.nom}: ERROR {e}[/]"
                    )
    console.print(
        f"[green]OK lliga {lliga_id}: {tot_enc} encontres, {tot_up} desades, "
        f"{tot_skip} pendents/saltades.[/]"
    )


@app.command("discover-lliga")
def discover_lliga_cmd(
    lliga_id: int = typer.Argument(..., help="Id de la lliga (36=TRES BANDES, 37=4 MODALITATS)"),
    depth: int = typer.Option(
        2,
        "--depth",
        min=1,
        max=3,
        help="1=divisions, 2=+grups, 3=+jornades (cada nivell descarrega més)",
    ),
) -> None:
    """Mostra l'estructura divisions → grups [→ jornades] d'una lliga."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        tree = discover_lliga(client, lliga_id, depth=depth)
    console.print(f"[bold cyan]Lliga {tree.lliga_id} — {len(tree.divisions)} divisions[/]")
    for div in tree.divisions:
        console.print(f"  [yellow]{div.nom}[/] (divisio_id={div.divisio_id})")
        if depth >= 2:
            grups = tree.grups_by_div.get(div.divisio_id, [])
            for grup in grups:
                resp = f" [{grup.club_responsable}]" if grup.club_responsable else ""
                console.print(f"    [green]{grup.nom}[/] (grup_id={grup.grup_id}){resp}")
                if depth >= 3:
                    jornades = tree.jornades_by_grup.get((div.divisio_id, grup.grup_id), [])
                    for j in jornades:
                        data_str = j.data.isoformat() if j.data else "?"
                        console.print(
                            f"      [dim]{j.nom}[/] jornada_id={j.jornada_id} data={data_str}"
                        )


@app.command("discover-lliga-noms")
def discover_lliga_noms_cmd(
    lligues: list[int] = typer.Argument(
        None, help="Ids de lligues a descobrir (per defecte 36 i 37)"
    ),
) -> None:
    """Descobreix i desa els noms de divisions i grups de lliga (taula lliga_noms).

    Els encontres només desen ids numèrics; aquesta comanda omple els noms
    llegibles perquè la web app mostri les classificacions per categoria amb
    noms reals. Executa-la un cop per temporada (pàgines públiques, sense login).
    """
    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    targets = lligues or [36, 37]
    total = 0
    with ScraperClient(settings) as client:
        for lliga_id in targets:
            try:
                tree = discover_lliga(client, lliga_id, depth=2)
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]FAIL lliga {lliga_id}: {e}[/]")
                continue
            for div in tree.divisions:
                conn.execute(
                    "INSERT OR REPLACE INTO lliga_noms (lliga_id, divisio_id, grup_id, nom) "
                    "VALUES (?, ?, 0, ?)",
                    (lliga_id, div.divisio_id, div.nom),
                )
                total += 1
                for grup in tree.grups_by_div.get(div.divisio_id, []):
                    conn.execute(
                        "INSERT OR REPLACE INTO lliga_noms (lliga_id, divisio_id, grup_id, nom) "
                        "VALUES (?, ?, ?, ?)",
                        (lliga_id, div.divisio_id, grup.grup_id, grup.nom),
                    )
                    total += 1
            console.print(f"[green]Lliga {lliga_id}: {len(tree.divisions)} divisions desades[/]")
    conn.commit()
    console.print(f"[green]OK {total} noms de lliga desats a lliga_noms.[/]")


@app.command("import-clubs")
def import_clubs_cmd() -> None:
    """Descarrega el listing oficial de clubs (/ca/clubs/5/Federacio) i els desa."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = import_clubs_oficials(client, settings=settings)
    console.print(f"[green]OK {result.imported} clubs importats.[/]")


app.add_typer(clubs_app, name="clubs")


# --------------------------------------------------------------------------- #
# Estat canònic al núvol (Cloudflare R2) — vegeu fcbillar.state_sync
# --------------------------------------------------------------------------- #

state_app = typer.Typer(
    help="Sincronitza les bases de dades canòniques amb Cloudflare R2.",
    no_args_is_help=True,
)


def _state_names(db: bool, opens_db: bool, default) -> tuple[str, ...]:
    """Tradueix els flags --db/--opens-db a noms lògics (o el per defecte)."""
    picked = []
    if db:
        picked.append("db")
    if opens_db:
        picked.append("opens-db")
    return tuple(picked) if picked else default


@state_app.command("pull")
def state_pull_cmd(
    db: bool = typer.Option(False, "--db", help="Només la BD principal"),
    opens_db: bool = typer.Option(False, "--opens-db", help="Només la BD d'opens"),
) -> None:
    """Baixa de R2 a local (escriptura atòmica). Sense flags: baixa-ho tot."""
    from fcbillar import state_sync

    names = _state_names(db, opens_db, state_sync.ALL)
    try:
        res = state_sync.pull(names)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc
    for k, v in res.items():
        console.print(f"[dim]  {k}: {v}[/]")
    console.print("[green]OK pull de R2 completat.[/]")


@state_app.command("push")
def state_push_cmd(
    db: bool = typer.Option(False, "--db", help="Només la BD principal"),
    opens_db: bool = typer.Option(False, "--opens-db", help="Només la BD d'opens"),
    check_generation: bool = typer.Option(
        False, "--check-generation", help="Nega si el núvol ha avançat (guardó de divergència)"
    ),
    force: bool = typer.Option(False, "--force", help="Ignora el guardó de generació"),
) -> None:
    """Puja de local a R2. Sense flags: puja les dues BD."""
    from fcbillar import state_sync

    names = _state_names(db, opens_db, ("db", "opens-db"))
    try:
        res = state_sync.push(names, check_generation=check_generation, force=force)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc
    for k, v in res.items():
        console.print(f"[dim]  {k}: {v}[/]")
    console.print("[green]OK push a R2 completat.[/]")


@state_app.command("status")
def state_status_cmd() -> None:
    """Mostra generació local/remota i mida dels objectes a R2."""
    from fcbillar import state_sync

    try:
        info = state_sync.status()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc
    for k, v in info.items():
        console.print(f"[cyan]{k}[/]: {v}")


@state_app.command("report")
def state_report_cmd(
    n_ok: int = typer.Option(0, "--n-ok", help="Passos correctes"),
    n_fail: int = typer.Option(0, "--n-fail", help="Passos fallats"),
    last_error: str = typer.Option("", "--last-error", help="Resum de l'últim error"),
    close_requests: bool = typer.Option(
        False, "--close-requests", help="Tanca les files reingest_requests en 'running'"
    ),
) -> None:
    """Escriu l'estat de l'última reingesta a `fcbillar.cloud_status` (per al banner del PWA).

    Amb `--close-requests` també marca a 'done'/'error' les peticions del botó que
    havien quedat en estat 'running'. Cal NEON_DATA_API_URL i NEON_SERVICE_ROLE_TOKEN.
    """
    from datetime import datetime, timezone

    from fcbillar.cloud_sync import get_client

    now = datetime.now(timezone.utc).isoformat()
    sb = get_client()
    # `session_ok` es queda a la taula perque el PWA la llegeix, pero ja no pot
    # ser fals: des del web nou no hi ha cap sessio que pugui caducar.
    sb.table("cloud_status").upsert(
        {
            "id": 1,
            "session_ok": True,
            "last_run": now,
            "last_error": last_error or None,
            "n_ok": n_ok,
            "n_fail": n_fail,
            "updated_at": now,
        },
        on_conflict="id",
    ).execute()
    console.print(f"[green]OK cloud_status: n_ok={n_ok} n_fail={n_fail}[/]")

    if close_requests:
        status = "error" if n_fail > 0 else "done"
        sb.table("reingest_requests").update(
            {"status": status, "finished_at": now, "n_ok": n_ok, "n_fail": n_fail}
        ).eq("status", "running").execute()
        console.print(f"[green]OK reingest_requests 'running' → '{status}'.[/]")


app.add_typer(state_app, name="state")


@clubs_app.command("list")
def clubs_list_cmd() -> None:
    """Llista clubs registrats amb els seus aliases."""
    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    rows = repo.list_clubs_with_aliases()
    if not rows:
        console.print("[yellow]Cap club a la BD. Prova `fcbillar import-clubs`.[/]")
        return
    table = Table(title=f"Clubs ({len(rows)})")
    table.add_column("Club", style="cyan")
    table.add_column("Aliases", style="dim")
    for club_fcb_id, aliases in rows:
        table.add_row(club_fcb_id, ", ".join(aliases) if aliases else "—")
    console.print(table)


@clubs_app.command("alias")
def clubs_alias_cmd(
    alias_nom: str = typer.Argument(..., help="Nom alternatiu (ex: 'SB FOMENT MOLINS')"),
    club_fcb_id: str = typer.Argument(..., help="fcb_id del club canònic (ex: 'S.B.F.MOLINS')"),
) -> None:
    """Registra un alias per a un club. Útil per a noms variants entre pàgines."""
    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    try:
        repo.add_club_alias(alias_nom, club_fcb_id)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from e
    console.print(f"[green]OK alias '{alias_nom}' afegit al club '{club_fcb_id}'.[/]")


@clubs_app.command("merge")
def clubs_merge_cmd(
    source: str = typer.Argument(..., help="fcb_id del club que es vol fusionar (s'eliminarà)"),
    target: str = typer.Argument(..., help="fcb_id del club canònic que rebrà tot"),
) -> None:
    """Fusiona dos clubs duplicats en un de sol.

    Mou tots els equips, jugadors i aliases del 'source' al 'target', crea
    automàticament un alias amb el nom del 'source' i esborra el 'source'.
    """
    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    try:
        moved = repo.merge_clubs(source, target)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from e
    console.print(
        f"[green]OK fusionat '{source}' → '{target}': "
        f"{moved['equips_moved']} equips, "
        f"{moved['players_moved']} jugadors, "
        f"{moved['aliases_moved']} aliases moguts. "
        f"L'alias '{source}' apunta ara a '{target}'.[/]"
    )


@clubs_app.command("unifica")
def clubs_unifica_cmd(
    aplica: bool = typer.Option(
        False, "--aplica", help="Fes-ho de debò. Sense això només ho ensenya."
    ),
) -> None:
    """Aplica totes les equivalències de `clubs.ALIES` d'una tirada.

    `merge` fusiona una parella; això passa la llista sencera dels noms que la
    federació escriu de dues maneres. Per a cada parella fa una cosa o l'altra:
    si el nom vell té fitxa pròpia, la fusiona amb l'oficial; si no en té -perquè
    de moment només surt a les classificacions-, en registra l'àlies perquè la
    pròxima ingesta no la creï.

    Per defecte només ensenya què faria. Cal `--aplica` per tocar res.
    """
    from fcbillar.clubs import ALIES, normalitza

    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)

    noms = {normalitza(nom): nom for (nom,) in conn.execute("SELECT nom FROM clubs")}
    table = Table(title="Unificació de clubs" + ("" if aplica else " (assaig en sec)"))
    table.add_column("Nom vell", style="cyan")
    table.add_column("Oficial", style="green")
    table.add_column("Què hi fa")
    fusions = alies = 0

    for vell, oficial in sorted(ALIES.items()):
        real_oficial = noms.get(normalitza(oficial))
        if real_oficial is None:
            console.print(
                f"[red]«{oficial}» no és a la taula clubs: no hi puc fusionar "
                f"«{vell}». Repassa clubs.ALIES o fes `fcbillar import-clubs`.[/]"
            )
            raise typer.Exit(1)
        real_vell = noms.get(normalitza(vell))

        if real_vell is None:
            if aplica:
                repo.add_club_alias(vell, real_oficial)
                conn.commit()
            alies += 1
            table.add_row(vell, real_oficial, "només àlies (no té fitxa)")
            continue

        cid = repo.get_club_id_by_fcb_id(real_vell)
        n_jug = conn.execute("SELECT COUNT(*) FROM players WHERE club_id = ?", (cid,)).fetchone()[0]
        n_eq = conn.execute("SELECT COUNT(*) FROM equips WHERE club_id = ?", (cid,)).fetchone()[0]
        if aplica:
            try:
                repo.merge_clubs(real_vell, real_oficial)
            except ValueError as e:
                console.print(f"[red]{e}[/]")
                raise typer.Exit(1) from e
        fusions += 1
        table.add_row(vell, real_oficial, f"fusiona {n_jug} jugadors, {n_eq} equips")

    console.print(table)
    console.print(
        f"[green]OK {fusions} fusions i {alies} àlies.[/]"
        if aplica
        else f"[yellow]{fusions} fusions i {alies} àlies pendents. "
        f"Torna-hi amb --aplica per fer-ho.[/]"
    )

    # Duplicats que aquesta llista no veu: dues fitxes amb el MATEIX nom i
    # `fcb_id` diferent. No hi ha cap àlies a escriure -els noms ja són iguals-
    # i per això no surten a `clubs.ALIES`, però són dos clubs igualment. Va
    # passar amb el Sant Adrià: una fitxa amb els 25 jugadors i una del cens
    # buida, i el rànquing publicava l'una i la classificació l'altra, o sigui
    # que els seus quatre equips no lligaven amb els seus jugadors.
    repetits = list(
        conn.execute(
            "SELECT nom, COUNT(*) n, GROUP_CONCAT(fcb_id, ' | ') FROM clubs "
            "GROUP BY nom HAVING n > 1"
        )
    )
    if repetits:
        console.print("\n[yellow]Clubs amb el mateix nom i identificador diferent:[/]")
        for nom, quants, ids in repetits:
            console.print(f"  {nom} ({quants}): {ids}")
        console.print(
            "[dim]  Aquests no surten a clubs.ALIES perquè no hi ha cap nom a traduir. "
            "Mira quin té les dades i fusiona'ls amb `fcbillar clubs merge`.[/]"
        )


@app.command("import-temporada")
def import_temporada_cmd(
    no_clubs: bool = typer.Option(False, "--no-clubs", help="No fer import-clubs"),
    no_sync: bool = typer.Option(False, "--no-sync", help="No fer sync"),
    historical: bool = typer.Option(
        False, "--historical", help="Incloure backfill històric (~2 min sense partides)"
    ),
    historical_top: int | None = typer.Option(
        0,
        "--historical-top",
        help="Top N per modalitat al backfill històric (0=cap, None=tots, lent)",
    ),
    only_followed: bool = typer.Option(
        False, "--only-followed", help="Al historical, només seguits"
    ),
) -> None:
    """Macro: orquestra import-clubs + sync + backfill --historical en una crida."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = import_temporada(
            client,
            include_clubs=not no_clubs,
            include_sync=not no_sync,
            include_historical=historical,
            historical_top_n=historical_top,
            only_followed=only_followed,
            settings=settings,
        )
    console.print(
        f"[green]OK import-temporada: {result.clubs_imported} clubs, "
        f"{len(result.sync_ingested)} rànquings sync, "
        f"{result.historical_processed} rànquings històrics "
        f"({result.historical_failed} fallats), "
        f"{result.historical_games_upserted} partides desades.[/]"
    )


@clubs_app.command("grups")
def clubs_grups_cmd(
    club_fcb_id: str = typer.Argument(..., help="fcb_id del club (ex: 'C.B.BANYOLES')"),
) -> None:
    """Llista grups de lliga on hi ha equip d'aquest club (requereix ingest previ)."""
    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    grups = find_club_grups(repo, club_fcb_id)
    if not grups:
        console.print(
            f"[yellow]Cap grup trobat per '{club_fcb_id}'. "
            f"Has fet `ingest-lliga-grup` o `ingest-lliga-jornada` abans?[/]"
        )
        return
    table = Table(title=f"Grups de lliga amb equip de '{club_fcb_id}' ({len(grups)})")
    table.add_column("lliga_id", justify="right")
    table.add_column("divisio_id", justify="right")
    table.add_column("grup_id", justify="right")
    for lliga, div, grup in grups:
        table.add_row(str(lliga), str(div), str(grup))
    console.print(table)


@clubs_app.command("players")
def clubs_players_cmd(
    club_fcb_id: str = typer.Argument(..., help="fcb_id del club"),
    follow: bool = typer.Option(False, "--follow", help="Marca tots com a seguits"),
) -> None:
    """Llista jugadors que han jugat amb equip d'aquest club (derivat de games)."""
    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    players = find_club_players(repo, club_fcb_id)
    if not players:
        console.print(
            f"[yellow]Cap jugador trobat per '{club_fcb_id}'. Cal ingest previ de lliga.[/]"
        )
        return
    table = Table(title=f"Jugadors amb equip de '{club_fcb_id}' ({len(players)})")
    table.add_column("fcb_id", style="dim", justify="right")
    table.add_column("Nom", style="cyan")
    n_followed = 0
    for fcb_id, nom in players:
        table.add_row(fcb_id, nom)
        if follow:
            if repo.set_seguiment(fcb_id, True):
                n_followed += 1
    console.print(table)
    if follow:
        console.print(f"[green]OK {n_followed} jugadors marcats com a seguits.[/]")


@app.command("ingest-individuals")
def ingest_individuals_cmd(
    temporada: str = typer.Option(
        "current",
        "--temporada",
        help="Temporada (ex: '2024-2025') o 'current' per a l'actual",
    ),
    cache: bool = typer.Option(
        False,
        "--cache",
        help="Permet servir HTML de la cache (per defecte, fresc per detectar novetats)",
    ),
    historical: bool = typer.Option(
        False,
        "--historical",
        help="Ingerir TOTES les temporades (actual + històric de /ca/historial), no només una",
    ),
) -> None:
    """Ingest dels torneigs individuals (opens, catalans, etc.) per temporada."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        if historical:
            result = ingest_individuals_all_temporades(
                client,
                create_missing_players=True,
                settings=settings,
                use_cache=cache,
            )
            scope = "totes les temporades"
        else:
            result = ingest_individuals_temporada(
                client,
                temporada=None if temporada == "current" else temporada,
                create_missing_players=True,
                settings=settings,
                use_cache=cache,
            )
            scope = f"temporada {temporada}"
    console.print(
        f"[green]OK individuals {scope}: "
        f"{result.torneigs_processed} torneigs ({result.torneigs_failed} fallats), "
        f"{result.total_participants} participants[/]"
    )


@app.command("link-individuals")
def link_individuals_cmd() -> None:
    """Vincula les partides INDIVIDUAL del rànquing amb el campionat concret.

    Creua `games` amb `torneig_partides` (resultats reals dels campionats) per
    (modalitat + parella + caramboles + entrades) i omple games.torneig_id.
    Idempotent: recalcula els vincles 'exacte' des de zero.
    """
    from fcbillar.linking import coverage_by_season, link_individual_games

    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    res = link_individual_games(conn)
    conn.commit()

    console.print(
        f"[green]OK vinculació:[/] {res.linked_games} partides del rànquing vinculades "
        f"des de {res.matched_partides}/{res.torneig_partides} partides de campionat."
    )
    console.print(
        f"  no casa cap game: {res.no_game}  ·  ambigües: {res.ambiguous}  ·  "
        f"noms no resolts: {res.unresolved_players}  ·  torneig desconegut: {res.unknown_torneig}"
        f"  ·  conflictes: {res.conflicts}"
    )
    if res.conflict_samples:
        console.print(
            f"  [yellow]mostres de conflicte (game→torneig):[/] {res.conflict_samples[:5]}"
        )

    table = Table(title="Cobertura partides INDIVIDUAL per temporada")
    table.add_column("Temporada")
    table.add_column("Vinculades", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("%", justify="right")
    tot = lnk = 0
    for row in coverage_by_season(conn):
        tot += row.total
        lnk += row.linked
        table.add_row(row.season or "—", str(row.linked), str(row.total), f"{row.pct}%")
    pct = round(100 * lnk / tot) if tot else 0
    table.add_row("[b]TOTAL[/]", f"[b]{lnk}[/]", f"[b]{tot}[/]", f"[b]{pct}%[/]")
    console.print(table)
    conn.close()


@app.command("clean-torneig-noms")
def clean_torneig_noms_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Mostra els canvis sense desar-los"),
) -> None:
    """Neteja els noms dels torneigs individuals (treu sufix redundant i '- ÚNICA').

    Una sola passada sobre torneigs_individuals; idempotent. El tipus (open/
    campionat) NO es desa localment: es deriva del nom net a la publicació.
    """
    from fcbillar.torneig_naming import clean_torneig_nom, torneig_tipus

    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    rows = conn.execute("SELECT id, nom FROM torneigs_individuals").fetchall()
    changes = [(r["id"], r["nom"], clean_torneig_nom(r["nom"])) for r in rows]
    changes = [(i, old, new) for (i, old, new) in changes if new != old]

    for _id, old, new in changes:
        console.print(f"  [yellow]{old}[/] → [green]{new}[/]")
    if not dry_run:
        conn.executemany(
            "UPDATE torneigs_individuals SET nom=? WHERE id=?",
            [(new, i) for (i, _o, new) in changes],
        )
        conn.commit()
    n_open = sum(1 for r in rows if torneig_tipus(r["nom"]) == "open")
    console.print(
        f"[green]{'(dry-run) ' if dry_run else ''}noms netejats: {len(changes)}[/] "
        f"· tipus: {n_open} opens / {len(rows) - n_open} campionats"
    )
    conn.close()


@app.command("publish-cloud")
def publish_cloud_cmd() -> None:
    """Publica la BD local a Supabase (schema fcbillar) per al frontend de Vercel.

    FASE 1: rànquings. Cal NEON_DATA_API_URL i NEON_SERVICE_ROLE_TOKEN (al .env o a
    l'entorn). Idempotent: es pot reexecutar després de cada actualització.
    """
    from fcbillar.cloud_sync import (
        publish_calendari,
        publish_copa,
        publish_copa_encontres,
        publish_copa_player_rankings,
        publish_games,
        publish_lliga,
        publish_lliga_encontres,
        publish_lliga_player_rankings,
        publish_lliga_standings_hist,
        publish_open_partides,
        publish_open_ranking,
        publish_open_ranking_femeni,
        publish_opens,
        publish_pending_games,
        publish_player_clubs,
        publish_provisional_ranking,
        publish_rankings,
        publish_rating_buckets,
    )

    def _prog(level: str, msg: str) -> None:
        console.print(f"[dim]  {msg}[/]" if level == "ok" else f"[yellow]{msg}[/]")

    try:
        counts = publish_rankings(on_progress=_prog)
        counts.update(publish_games(on_progress=_prog))
        counts.update(publish_pending_games(on_progress=_prog))
        counts.update(publish_provisional_ranking(on_progress=_prog))
        counts.update(publish_lliga(on_progress=_prog))
        counts.update(publish_lliga_standings_hist(on_progress=_prog))
        counts.update(publish_copa(on_progress=_prog))
        counts.update(publish_opens(on_progress=_prog))
        counts.update(publish_lliga_player_rankings(on_progress=_prog))
        counts.update(publish_copa_player_rankings(on_progress=_prog))
        counts.update(publish_lliga_encontres(on_progress=_prog))
        counts.update(publish_copa_encontres(on_progress=_prog))
        counts.update(publish_open_partides(on_progress=_prog))
        counts.update(publish_open_ranking(on_progress=_prog))
        counts.update(publish_open_ranking_femeni(on_progress=_prog))
        counts.update(publish_player_clubs(on_progress=_prog))
        counts.update(publish_rating_buckets(on_progress=_prog))
        counts.update(publish_calendari(on_progress=_prog))
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error publicant al núvol: {exc}[/]")
        raise typer.Exit(code=1) from exc
    total = ", ".join(f"{k}={v}" for k, v in counts.items())
    console.print(f"[green]OK publicat a Supabase (fcbillar): {total}[/]")

    # App germana "Estadístiques": alimenta public.partides amb els games oficials i
    # pendents de FCBillar (adapta les del jugador i completa el que hi manqui; evita
    # duplicats). No fatal. Abans de computa perquè aquest usi les dades reconciliades.
    try:
        from fcbillar.cloud_sync import publish_estadistiques_partides

        c1 = publish_estadistiques_partides(on_progress=_prog)
        console.print(
            "[green]OK Estadístiques partides: "
            + ", ".join(f"{k}={v}" for k, v in c1.items())
            + "[/]"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Avís: no s'ha pogut alimentar partides a Estadístiques: {exc}[/]")

    # App germana "Estadístiques" (schema public): marca computa. No fatal.
    try:
        from fcbillar.cloud_sync import publish_estadistiques_computa

        c2 = publish_estadistiques_computa(on_progress=_prog)
        console.print(
            "[green]OK Estadístiques computa: "
            + ", ".join(f"{k}={v}" for k, v in c2.items())
            + "[/]"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Avís: no s'ha pogut marcar computa a Estadístiques: {exc}[/]")

    # App germana "Estadístiques": resum de la fitxa federativa (rànquing, opens,
    # radar, palmarès). No fatal.
    try:
        from fcbillar.cloud_sync import publish_estadistiques_fitxa

        c3 = publish_estadistiques_fitxa(on_progress=_prog)
        console.print(
            "[green]OK Estadístiques fitxa: " + ", ".join(f"{k}={v}" for k, v in c3.items()) + "[/]"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Avís: no s'ha pogut publicar la fitxa a Estadístiques: {exc}[/]")


@app.command("publish-estadistiques-computa")
def publish_estadistiques_computa_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Només informa, no escriu."),
) -> None:
    """Marca `public.partides.computa` (app Estadístiques) amb la finestra oficial.

    Casa cada partida d'Estadístiques amb les que computen al rànquing federatiu
    (ranking_game_links) per signatura+data. Idempotent. Es crida també des de
    `publish-cloud`."""
    from fcbillar.cloud_sync import publish_estadistiques_computa

    def _prog(level: str, msg: str) -> None:
        console.print(f"[dim]  {msg}[/]" if level == "ok" else f"[yellow]{msg}[/]")

    try:
        counts = publish_estadistiques_computa(on_progress=_prog, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error: {exc}[/]")
        raise typer.Exit(code=1) from exc
    total = ", ".join(f"{k}={v}" for k, v in counts.items())
    pref = "[DRY-RUN] " if dry_run else ""
    console.print(f"[green]{pref}OK: {total}[/]")


@app.command("publish-estadistiques-fitxa")
def publish_estadistiques_fitxa_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Només informa, no escriu."),
) -> None:
    """Publica el resum de la fitxa federativa (rànquing, opens, radar, palmarès) a
    `public.estadistiques_fitxa` per a l'app Estadístiques. Consistent amb la fitxa
    de FCBillar. Es crida també des de `publish-cloud`."""
    from fcbillar.cloud_sync import publish_estadistiques_fitxa

    def _prog(level: str, msg: str) -> None:
        console.print(f"[dim]  {msg}[/]" if level == "ok" else f"[yellow]{msg}[/]")

    try:
        counts = publish_estadistiques_fitxa(on_progress=_prog, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error: {exc}[/]")
        raise typer.Exit(code=1) from exc
    total = ", ".join(f"{k}={v}" for k, v in counts.items())
    pref = "[DRY-RUN] " if dry_run else ""
    console.print(f"[green]{pref}OK: {total}[/]")


@app.command("publish-estadistiques-partides")
def publish_estadistiques_partides_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Només informa, no escriu."),
) -> None:
    """Alimenta `public.partides` (app Estadístiques) amb les partides oficials i
    pendents de FCBillar: adapta les del jugador als valors de la federació, completa
    el que hi manqui (sèrie, competició, lloc, data), normalitza el nom del rival i
    insereix les que falten (sense duplicar). Es crida també des de `publish-cloud`."""
    from fcbillar.cloud_sync import publish_estadistiques_partides

    def _prog(level: str, msg: str) -> None:
        console.print(f"[dim]  {msg}[/]" if level == "ok" else f"[yellow]{msg}[/]")

    try:
        counts = publish_estadistiques_partides(on_progress=_prog, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error: {exc}[/]")
        raise typer.Exit(code=1) from exc
    total = ", ".join(f"{k}={v}" for k, v in counts.items())
    pref = "[DRY-RUN] " if dry_run else ""
    console.print(f"[green]{pref}OK: {total}[/]")


@app.command("publish-live-opens")
def publish_live_opens_cmd() -> None:
    """Bolca l'estat EN VIU dels Opens en curs a Supabase (taula `open_live`).

    Raspa la federació en directe (pàgines públiques, sense login) i puja l'estat
    de cada Open en curs perquè l'app web en mostri el seguiment en temps real.
    Totes les modalitats; s'exclouen els femenins i els ja tancats. Idempotent —
    pensat per executar-se sovint des d'un job programat (p.ex. GitHub Action).
    Cal NEON_DATA_API_URL i NEON_SERVICE_ROLE_TOKEN (al .env o a l'entorn).
    """
    from fcbillar.cloud_sync import publish_live_opens

    def _prog(level: str, msg: str) -> None:
        console.print(f"[dim]  {msg}[/]" if level == "ok" else f"[yellow]{msg}[/]")

    try:
        counts = publish_live_opens(on_progress=_prog)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error publicant els opens en directe: {exc}[/]")
        raise typer.Exit(code=1) from exc
    total = ", ".join(f"{k}={v}" for k, v in counts.items())
    console.print(f"[green]OK opens en directe publicats: {total}[/]")


@app.command("project-open-ranking")
def project_open_ranking_cmd(
    pdf: str = typer.Argument(..., help="PDF 'RÀNQUING INICIAL' de l'open"),
    season: str | None = typer.Option(None, "--season", help="Temporada, ex: 2025-2026"),
    division_id: int | None = typer.Option(
        None,
        "--division-id",
        help="fcb_division_id sintètic (negatiu). Per defecte, derivat del nom de l'open.",
    ),
    modality: str | None = typer.Option(
        None, "--modality", help="Modalitat (per defecte, derivada del nom o 'Tres Bandes')."
    ),
    horaris: str | None = typer.Option(
        None,
        "--horaris",
        help="PDF 'HORARIS' de l'open: enganxa dia/billar/hores a cada grup.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="No publica; només mostra el resum."),
    json_out: bool = typer.Option(
        False, "--json", help="Imprimeix una línia JSON final amb el resum (per al watcher)."
    ),
) -> None:
    """Genera un OPEN EN CURS *projectat* des del rànquing inicial (abans del sorteig FCB).

    Parseja el PDF oficial 'RÀNQUING INICIAL', genera els grups de TOTES les fases
    (reglament Art. VIII-IX; la sembra de l'Art. XVIII ja ve aplicada per la
    federació a la columna Posició) i el publica a `fcbillar.open_live` amb un
    `fcb_division_id` sintètic NEGATIU i el marcador `projected`. El web el mostra
    com un open 'En directe' amb el badge 'projecció · no oficial'. Quan la federació
    publiqui els grups reals, la propera `publish-live-opens` el substitueix pel
    seguiment real (mateix nom) i esborra la projecció.
    Cal NEON_DATA_API_URL i NEON_SERVICE_ROLE_TOKEN (al .env o a l'entorn).
    """
    import zlib
    from datetime import datetime, timezone
    from pathlib import Path

    from fcb_opens.projection import (
        build_projection_from_seeded,
        projection_to_live_payload,
    )
    from fcb_opens.scraper.ranking_inicial_pdf import parse_ranking_inicial_pdf
    from fcbillar.cloud_sync import (
        _enrich_live_payload,
        _open_modality,
        _upsert,
        get_client,
    )

    pdf_path = Path(pdf)
    if not pdf_path.exists():
        console.print(f"[red]No existeix el PDF: {pdf_path}[/]")
        raise typer.Exit(code=1)

    ranking = parse_ranking_inicial_pdf(pdf_path)
    n = ranking.num_players
    if n == 0:
        console.print("[red]No s'ha llegit cap jugador del PDF (format inesperat?).[/]")
        raise typer.Exit(code=1)

    schedule_by_group: dict[str, dict] | None = None
    if horaris:
        horaris_path = Path(horaris)
        if not horaris_path.exists():
            console.print(f"[red]No existeix el PDF d'horaris: {horaris_path}[/]")
            raise typer.Exit(code=1)
        from fcb_opens.scraper.horaris_pdf import parse_horaris_pdf

        schedule_by_group = parse_horaris_pdf(horaris_path)
        console.print(f"[dim]Horaris: {len(schedule_by_group)} grups amb dia/billar/hores.[/]")

    try:
        proj = build_projection_from_seeded(ranking, season=season)
    except NotImplementedError as exc:
        console.print(
            f"[red]No es pot projectar amb N={n} inscrits: {exc}[/]\n"
            f"[dim]El generador cobreix N parell dins [64,128].[/]"
        )
        raise typer.Exit(code=1) from exc

    name = proj["name"]
    if division_id is None:
        # id sintètic estable i negatiu: el mateix open sempre cau a la mateixa
        # fila, així una re-càrrega ACTUALITZA en lloc de duplicar.
        division_id = -(zlib.crc32(name.encode("utf-8")) % 2_000_000 + 1)
    elif division_id >= 0:
        console.print(
            "[yellow]Avís: --division-id hauria de ser negatiu per no xocar amb divisions reals de la FCB.[/]"
        )

    mod = modality or _open_modality(name) or "Tres Bandes"
    struct = " · ".join(f"{v} {k}" for k, v in proj["structure"].items())
    console.print(
        f"[bold]{name}[/]\n"
        f"[dim]{n} inscrits · {struct} + Fase Final · modalitat: {mod} · id sintètic: {division_id}[/]"
    )
    for w in proj.get("warnings", []):
        mark = "⛔" if w["level"] == "error" else "⚠️" if w["level"] == "warning" else "ℹ️"
        console.print(f"[dim]  {mark} {w['message']}[/]")

    if dry_run:
        console.print("[dim]DRY-RUN: no s'ha publicat res.[/]")
        if json_out:
            import json as _json

            typer.echo(
                _json.dumps(
                    {
                        "division_id": division_id,
                        "open_name": name,
                        "n_players": n,
                        "modality": mod,
                        "dry_run": True,
                    }
                )
            )
        return

    sb = get_client()
    fetched_at = datetime.now(timezone.utc).isoformat()
    payload = projection_to_live_payload(
        proj,
        division_id=division_id,
        fetched_at=fetched_at,
        schedule_by_group=schedule_by_group,
    )
    try:
        _enrich_live_payload(payload, sb, open_name=name, division_id=division_id)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]No s'han pogut resoldre els enllaços de jugador: {exc}[/]")

    row = {
        "fcb_division_id": division_id,
        "name": name,
        "modality": mod,
        "payload_json": payload,
        "captured_at": fetched_at,
        "updated_at": fetched_at,
    }
    try:
        _upsert(
            sb, "open_live", [row], "fcb_division_id", lambda _l, m: console.print(f"[dim]  {m}[/]")
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error publicant a open_live: {exc}[/]")
        raise typer.Exit(code=1) from exc

    n_links = len(payload.get("player_ids") or {})
    console.print(
        f"[green]OK: open projectat publicat a open_live (id {division_id}, "
        f"{n_links} jugadors enllaçats).[/]\n"
        f"[dim]Visible a la PWA: /opens/directe/{division_id}[/]"
    )
    if json_out:
        import json as _json

        typer.echo(
            _json.dumps(
                {
                    "division_id": division_id,
                    "open_name": name,
                    "n_players": n,
                    "modality": mod,
                    "n_links": n_links,
                }
            )
        )


@app.command("remove-projected-open")
def remove_projected_open_cmd(
    division_id: int | None = typer.Argument(
        None,
        help="id sintètic negatiu a esborrar. Sense argument, --all esborra totes les projeccions.",
    ),
    all_: bool = typer.Option(
        False, "--all", help="Esborra TOTES les projeccions (files amb id negatiu)."
    ),
) -> None:
    """Retira una projecció d'open (o totes) de `open_live`.

    Escapatòria manual: normalment `publish-live-opens` ja retira la projecció
    quan la federació publica el sorteig real, però si els noms no casen la pots
    treure a mà aquí.
    """
    from fcbillar.cloud_sync import get_client

    sb = get_client()
    q = sb.table("open_live").delete()
    if all_:
        q = q.lt("fcb_division_id", 0)
    elif division_id is not None:
        if division_id >= 0:
            console.print("[red]Aquesta comanda només esborra projeccions (id negatiu).[/]")
            raise typer.Exit(code=1)
        q = q.eq("fcb_division_id", division_id)
    else:
        console.print("[red]Indica un id negatiu o --all.[/]")
        raise typer.Exit(code=1)
    try:
        res = q.execute()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error esborrant: {exc}[/]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]OK: {len(res.data or [])} projeccio(ns) retirada(es).[/]")


@app.command("set-open-prize-ranking")
def set_open_prize_ranking_cmd(
    division_id: int = typer.Argument(..., help="fcb_division_id de l'open en curs"),
    num_seq: int | None = typer.Option(
        None, "--num-seq", help="num_seq del rànquing 3B a aplicar als premis"
    ),
    month: str | None = typer.Option(
        None, "--month", help="Mes del rànquing 3B (AAAA-MM); es resol a num_seq"
    ),
    clear: bool = typer.Option(
        False, "--clear", help="Treu el pin (torna al darrer rànquing publicat)"
    ),
) -> None:
    """Fixa quin rànquing de 3 bandes s'usa per als PREMIS d'un open (el vigent en
    el moment de la convocatòria). La propera `publish-live-opens` l'hi aplicarà i
    el web ho mostrarà per a tothom. Sense pin → darrer rànquing publicat."""
    from fcbillar.cloud_sync import get_client, set_open_prize_num_seq

    if clear:
        set_open_prize_num_seq(division_id, None)
        console.print(
            f"[green]Pin tret per a la divisió {division_id} (s'usarà el darrer rànquing).[/]"
        )
        return

    seq = num_seq
    if seq is None and month:
        try:
            year, mon = (int(x) for x in month.split("-"))
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]--month ha de ser AAAA-MM (ex: 2026-04). Rebut: {month!r}[/]")
            raise typer.Exit(code=1) from exc
        rows = (
            get_client()
            .table("rankings")
            .select("num_seq")
            .eq("modalitat_codi", 1)
            .eq("any_pub", year)
            .eq("mes_pub", mon)
            .execute()
        ).data or []
        if not rows:
            console.print(f"[red]No hi ha rànquing 3B publicat per {year}-{mon:02d}.[/]")
            raise typer.Exit(code=1)
        seq = int(rows[0]["num_seq"])
    if seq is None:
        console.print("[red]Cal indicar --num-seq N o --month AAAA-MM (o --clear).[/]")
        raise typer.Exit(code=1)

    set_open_prize_num_seq(division_id, seq)
    console.print(
        f"[green]Divisió {division_id}: premis amb rànquing 3B num_seq={seq}. "
        f"Republica amb 'fcbillar publish-live-opens'.[/]"
    )


@app.command("ingest-copa")
def ingest_copa_cmd(
    edicio: int = typer.Argument(..., help="ID d'edició de la Copa (ex: 7)"),
    jornada: int | None = typer.Option(
        None, "--jornada", help="Limita a una jornada concreta (per defecte, totes)"
    ),
    cache: bool = typer.Option(
        False, "--cache", help="Permet servir HTML de la cache (per defecte, fresc)"
    ),
) -> None:
    """Ingest d'una edició de Copa: jornades, grups, encontres i partides."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = ingest_copa_edicio(
            client, edicio, jornada=jornada, use_cache=cache, settings=settings
        )
    console.print(
        f"[green]OK copa edició {edicio}: {result.jornades} jornades, "
        f"{result.grups} grups, {result.encontres} encontres, "
        f"{result.partides} partides.[/]"
    )


@app.command("open-import-inscrits")
def open_import_inscrits_cmd(
    pdf: str = typer.Argument(..., help="Ruta al PDF 'LLISTAT D'INSCRITS PER CLUBS'"),
    season: str = typer.Option("2025-2026", "--season", help="Temporada de l'Open"),
    name: str = typer.Option(
        "",
        "--name",
        help="Nom de l'Open (per defecte, el llegit del PDF)",
    ),
) -> None:
    """Importa el llistat d'inscrits d'un Open i en genera el quadre projectat.

    Sembra el camp segons l'Art. XVIII i construeix l'estructura de fases/grups
    (Art. VIII-IX) abans que la federació publiqui els grups. El resultat es
    desa a la BD d'opens (data/fcb_opens.db) i es veu a la pestanya Opens.
    """
    import re as _re
    from datetime import datetime, timezone
    import json as _json

    from fcb_opens import db as _odb
    from fcb_opens.paths import resolve_db_path
    from fcb_opens.projection import build_projection
    from fcb_opens.scraper.inscrits_pdf import parse_inscrits_pdf

    inscrits = parse_inscrits_pdf(pdf)
    if not inscrits.entries:
        console.print("[red]No s'ha pogut llegir cap inscrit del PDF.[/]")
        raise typer.Exit(code=1)

    # Resol cada nom d'inscrit → fcb_id del jugador ja existent a FCBillar, perquè
    # el quadre projectat enllaci a la fitxa del jugador. El PDF de vegades omet
    # l'espai després de la coma ("COGNOM,NOM"); provem també la variant normalitzada.
    settings = get_settings()
    fcb_conn = ensure_schema(settings.db_path)
    repo = Repository(fcb_conn)

    def _resolve_fcb_id(nom: str) -> str | None:
        fid = repo.get_player_fcb_id_by_nom(nom)
        if fid:
            return fid
        alt = _re.sub(r",\s*", ", ", nom)
        return repo.get_player_fcb_id_by_nom(alt) if alt != nom else None

    # Punts actuals al Rànquing Català d'Opens (suma dels últims 5 opens) per nom,
    # per donar context a cada cap de sèrie. Best-effort: si la BD d'opens no en té,
    # el mapa queda buit i no passa res.
    db_path = resolve_db_path()
    _odb.init_db(db_path)
    conn = _odb.connect(db_path)
    points_by_name: dict[str, int] = {}
    try:
        from fcb_opens.reglament.ranquing_opens import compute_opens_ranking

        for entry in compute_opens_ranking(conn):
            points_by_name[entry.display_name] = entry.total_points
    except Exception:  # noqa: BLE001 — context only, never block the import
        points_by_name = {}

    try:
        proj = build_projection(
            inscrits,
            season=season,
            resolve_fcb_id=_resolve_fcb_id,
            opens_points_by_name=points_by_name,
        )
    except NotImplementedError as exc:
        fcb_conn.close()
        conn.close()
        console.print(
            f"[red]No es pot generar el quadre per a {len(inscrits.entries)} inscrits: {exc}[/]"
        )
        raise typer.Exit(code=1) from exc
    fcb_conn.close()
    n_linked = sum(1 for s in proj["seeds"] if s.get("fcb_id"))
    open_name = name or proj["name"]
    proj["name"] = open_name

    try:
        existing = _odb.find_projection_by_name(conn, open_name)
        proj_id = _odb.save_projection(
            conn,
            name=open_name,
            season=season,
            num_inscriptions=proj["num_inscriptions"],
            source_pdf=pdf,
            payload_json=_json.dumps(proj, ensure_ascii=False),
            created_at=datetime.now(timezone.utc).isoformat(),
            replace_id=existing["id"] if existing else None,
        )
    finally:
        conn.close()

    struct = ", ".join(f"{k}={v}" for k, v in proj["structure"].items())
    console.print(
        f"[green]OK '{open_name}': {proj['num_inscriptions']} inscrits "
        f"({n_linked} enllaçats a fitxa), estructura {struct} → projecció #{proj_id} desada.[/]"
    )


@app.command("ingest-divisions-individual")
def ingest_divisions_individual_cmd(
    pdf: str = typer.Argument(..., help="PDF de divisions del campionat individual."),
    club: str = typer.Option("BANYOLES", "--club", help="Part del nom del club a seguir."),
    temporada: str = typer.Option("2026/2027", "--temporada"),
) -> None:
    """Quan juga cada jugador del club el campionat individual.

    Creua dues coses que fins ara no es parlaven: el PDF de divisions, que diu a
    quina divisió juga cadascú, i el calendari esportiu ja ingerit, que diu quin
    cap de setmana es juga cada fase de cada divisió. En surt la data de cada
    jugador, que no diu cap dels dos documents per separat.

    Al calendari només hi van les fases classificatòries, que les juga tothom de
    la divisió. La final no: només hi arriba qui passa les prèvies, i per tant
    només se sap la data de qui hi entra directament.
    """
    from fcbillar.campionat_individual import cites, fases_del_calendari, ingest
    from fcbillar.campionat_individual import resum_per_divisio
    from fcbillar.divisions_individual import desa, llegeix, per_club, traspassos

    conn = ensure_schema(get_settings().db_path)
    # El `fcb_id` I el nom: no sempre són iguals -el Sant Adrià té el `fcb_id`
    # escurçat, «SANT ADRIÀ» per «C.B.SANT ADRIÀ»- i el tall del club es fa amb
    # la forma més llarga que casi. Amb només el `fcb_id`, el «C.B.» d'aquell
    # club se n'anava al nom de 21 jugadors.
    clubs = [x for r in conn.execute("SELECT fcb_id, nom FROM clubs") for x in r if x]

    inscrits, rebutjades = llegeix(pdf, clubs)
    if not inscrits:
        console.print(f"[red]No he pogut llegir cap inscrit de {pdf}[/]")
        raise typer.Exit(1)
    console.print(f"  {len(inscrits)} inscrits llegits")

    # El desat reemplaça la temporada sencera d'aquesta font. Si del PDF ens
    # n'hem deixat una línia, la reemplaçaríem per una llista incompleta i
    # ningú no se n'assabentaria: val més no tocar res. Passa quan hi ha un club
    # que no és al cens, que és el motiu habitual.
    if rebutjades:
        for linia in rebutjades:
            console.print(f"  [yellow]sense interpretar:[/] {linia}")
        console.print(
            f"\n[red]{len(rebutjades)} línies sense interpretar: no deso res.[/] "
            "Segurament hi ha un club que no és al cens; afegeix-l'hi i torna-ho a provar."
        )
        raise typer.Exit(1)

    # Desar-los abans de res: el PDF diu a quina divisió i amb quin club juga
    # cadascú, i això val molt més que les dates. És la font oficial dels
    # traspassos i la que dona la categoria de cada jugador.
    console.print(f"  {desa(conn, inscrits, temporada)} inscrits desats")
    canvis = traspassos(conn, temporada)
    if canvis:
        console.print(f"\n[bold]Fitxatges ({len(canvis)})[/]")
        for jugador, abans, ara in canvis:
            console.print(f"  {jugador:34} [dim]{abans}[/] → {ara}")

    fases = fases_del_calendari(conn, temporada)
    if not fases:
        console.print(
            f"[red]Cap fase al calendari de la temporada {temporada}. "
            f"Executa abans `fcbillar ingest-calendari --font FCB`.[/]"
        )
        raise typer.Exit(1)
    for linia in resum_per_divisio(fases):
        console.print(f"  {linia}")

    meus = per_club(inscrits, club)
    if not meus:
        console.print(f"[red]Cap jugador amb «{club}» al club.[/] N'hi ha de:")
        for c in sorted({i.club for i in inscrits}):
            console.print(f"    {c}")
        raise typer.Exit(1)
    console.print(f"\n  {len(meus)} jugadors del {club}:")
    for i in meus:
        console.print(f"    {i.divisio:6s} #{i.posicio:<4d} {i.jugador}")

    les_cites = cites(meus, fases)
    n = ingest(conn, les_cites, temporada)
    console.print(f"\n[green]{n} cites a calendari_events[/]")


@app.command("ingest-calendari-lliga")
def ingest_calendari_lliga_cmd(
    carpeta: str = typer.Argument(
        None, help="Carpeta amb els PDF. Si no la poses, els busca al web de la federació."
    ),
    club: str = typer.Option("BANYOLES", "--club", help="Part del nom del club a seguir."),
    temporada: str = typer.Option("2026/2027", "--temporada"),
    ics_a: str = typer.Option(
        None, "--ics", help="Desa també un .ics per importar a un calendari."
    ),
) -> None:
    """Ingesta els calendaris oficials de grup: encontres del club amb data.

    La federació publica un PDF per grup, i és l'única font que diu EL DIA de
    cada jornada; el calendari esportiu general només diu la setmana, i la
    intranet no publica ni els grups. Sense arguments els busca al web:

        fcbillar ingest-calendari-lliga --ics data/billar.ics

    i amb una carpeta llegeix els PDF que hi hagi, per si vols provar-ne un o
    la federació canvia de lloc:

        fcbillar ingest-calendari-lliga ~/Descarregues

    Les dates es contrasten entre grups. Si un PDF repeteix la mateixa data a
    mitja graella —com el de 2a divisió grup A de la 2026-27, que la federació
    va publicar amb la data de la primera jornada a totes— se li posen les dels
    grups que sí que la porten bé, perquè les jornades són comunes a la lliga.

    Si algun grup surt amb forats no es desa res. Un calendari incomplet no
    s'assembla a un error: s'assembla a un calendari, i qui el mira no té cap
    manera de saber que li falta el seu encontre.
    """
    from pathlib import Path

    from fcbillar.calendari_lliga import (
        dates_de_referencia,
        desa_grups,
        descobreix_grups,
        esmena_dates,
        ics,
        ingest,
        llegeix,
        problemes,
    )

    if carpeta:
        origens = [(p.name, p) for p in sorted(Path(carpeta).glob("*.pdf"))]
    else:
        import httpx

        publicats = descobreix_grups(temporada)
        console.print(f"[bold]{len(publicats)}[/] calendaris de grup publicats al web")
        with httpx.Client(follow_redirects=True, timeout=120.0) as client:
            origens = [(c.etiqueta, client.get(c.url).content) for c in publicats]

    calendaris = []
    for nom, origen in origens:
        try:
            cal = llegeix(origen)
        except Exception as e:
            # Un PDF que no sigui d'aquests no ha d'aturar la resta.
            console.print(f"  [dim]{nom}: no és un calendari de grup ({e})[/]")
            continue
        if cal.encontres:
            calendaris.append(cal)

    if not calendaris:
        console.print(f"[red]Cap calendari de grup a {carpeta or 'el web de la federació'}[/]")
        raise typer.Exit(1)

    referencia = dates_de_referencia(calendaris)
    esmenats = []
    for cal in calendaris:
        nou = esmena_dates(cal, referencia)
        canviades = sum(
            1 for a, b in zip(cal.encontres, nou.encontres, strict=True) if a.data != b.data
        )
        marca = f" [yellow]({canviades} dates esmenades)[/]" if canviades else ""
        console.print(
            f"  {cal.divisio} grup {cal.grup}: {len(cal.equips)} equips, "
            f"{len(cal.encontres)} encontres{marca}"
        )
        esmenats.append(nou)

    forats = [(cal, p) for cal in esmenats if (p := problemes(cal))]
    if forats:
        console.print("\n[red]No es desa res: hi ha grups que no quadren.[/]")
        for cal, p in forats:
            console.print(f"  [red]{cal.divisio} grup {cal.grup}[/]: {'; '.join(p)}")
        raise typer.Exit(1)

    conn = ensure_schema(get_settings().db_path)
    n = ingest(conn, esmenats, club, temporada)
    console.print(f"[green]{n} encontres del {club} a calendari_events[/]")
    # I el grup sencer, que és el que permet ensenyar la temporada que comença
    # amb la mateixa forma que una de jugada: qui hi ha a cada grup i la graella
    # de totes les jornades, no només les nostres.
    ng = desa_grups(conn, esmenats, temporada)
    console.print(f"[green]{ng} encontres de tots els grups a lliga_calendari[/]")

    if ics_a:
        Path(ics_a).write_text(ics(esmenats, club), encoding="utf-8")
        console.print(f"[green]{ics_a}[/] — importa'l al calendari que vulguis")


@app.command("ingest-calendari")
def ingest_calendari_cmd(
    url: str = typer.Option(
        None, "--url", help="URL del PDF (per defecte, la RFEB de la temporada en curs)."
    ),
    fitxer: str = typer.Option(None, "--fitxer", help="Llegeix un PDF local en lloc de baixar-lo."),
    font: str = typer.Option(
        "RFEB", "--font", help="Federació que publica el calendari: RFEB | FCB."
    ),
    versio: str = typer.Option(
        None, "--versio", help="Revisió del PDF de la FCB ('V-1'): no la diu enlloc."
    ),
    force: bool = typer.Option(
        False, "--force", help="Reparseja encara que el PDF no hagi canviat."
    ),
) -> None:
    """Ingesta el calendari esportiu federatiu (PDF) i n'apunta els canvis.

    Pensat per executar-se periòdicament: les federacions van publicant revisions
    del mateix fitxer. Si no ha canviat res, no fa feina; si ha canviat, llista què
    s'ha mogut respecte de la revisió anterior.

    Sense `--url` ni `--fitxer` prova la temporada en curs I la següent: la RFEB
    publica la del curs vinent al juliol, molt abans que se n'acabi l'actual.

    El de la FCB va a part perquè la graella és una altra, però tampoc no li cal
    res: se'l busca al gestor de fitxers del WordPress i n'agafa la revisió més
    nova de la temporada més nova.

        fcbillar ingest-calendari --font FCB

    Amb `--fitxer` es llegeix un PDF concret, que serveix per a una revisió que
    encara no hagin penjat o per rellegir-ne una de vella.
    """
    from pathlib import Path

    import httpx

    from fcbillar.calendari_fed import ingest_calendari, rfeb_url, temporada_actual

    if fitxer:
        # `--url` continua servint amb `--fitxer`: no s'hi baixa res, però queda
        # desat d'on surt el PDF i la web hi pot enllaçar.
        feines: list[tuple[str | None, bytes | None]] = [(url, Path(fitxer).read_bytes())]
    elif url:
        feines = [(url, None)]
    elif font.upper() == "FCB":
        # Cada federació publica el seu calendari on vol. La RFEB té una URL
        # previsible per temporada; la FCB el desa al gestor de fitxers del seu
        # WordPress amb identificadors que no es poden endevinar, i s'ha de
        # buscar. Sense aquesta branca s'hi baixava el PDF de la RFEB i es
        # parsejava com si fos de la FCB, que són graelles diferents.
        from fcbillar.calendari_fed import descobreix_fcb

        trobats = descobreix_fcb()
        if not trobats:
            console.print(
                "[red]No he trobat cap calendari de la FCB publicat.[/] "
                "Passa-li `--fitxer` amb el PDF si el tens a mà."
            )
            raise typer.Exit(1)
        for c in trobats:
            console.print(f"  [dim]publicat:[/] {c.temporada} {c.versio or 's/v'} — {c.url}")
        # Només la temporada més nova: les velles ja les tenim i tornar-les a
        # ingerir només mouria dates cap enrere.
        cal = trobats[0]
        versio = versio or cal.versio
        feines = [(cal.url, None)]
    else:
        any_actual = temporada_actual()
        feines = [(rfeb_url(a), None) for a in (any_actual, any_actual + 1)]

    fets = 0
    for u, dades in feines:
        try:
            res = ingest_calendari(
                get_settings().db_path,
                url=u,
                font=font,
                force=force,
                pdf_bytes=dades,
                versio=versio,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404 and len(feines) > 1:
                console.print(f"[dim]{u}: encara no publicat (404).[/]")
                continue
            console.print(f"[red]Error ingestant el calendari: {exc}[/]")
            raise typer.Exit(code=1) from exc
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Error ingestant el calendari: {exc}[/]")
            raise typer.Exit(code=1) from exc
        fets += 1

        if res["estat"] == "sense-canvis":
            console.print(f"[dim]Calendari {font} sense canvis ({res['motiu']}).[/]")
            continue
        console.print(
            f"[green]Calendari {font} {res['temporada']} {res.get('versio') or ''} "
            f"({res.get('data_versio') or 's/d'}): {res['n_events']} esdeveniments, "
            f"{res['n_canvis']} canvis.[/]"
        )
        canvis = res.get("canvis") or []
        if canvis:
            taula = Table(title=f"Canvis del calendari {res['temporada']}")
            taula.add_column("Setmana")
            taula.add_column("Què")
            taula.add_column("Canvi")
            taula.add_column("Abans/Després")
            for c in canvis[:50]:
                que = " · ".join(p for p in (c.disciplina, c.ambit, c.tipus) if p)
                if c.tipus_canvi == "modificacio":
                    detall = f"{c.abans} → {c.despres}"
                else:
                    detall = c.despres or f"(treta) {c.abans}"
                taula.add_row(c.setmana.isoformat(), que, c.tipus_canvi, detall)
            console.print(taula)
            if len(canvis) > 50:
                console.print(f"[dim]…i {len(canvis) - 50} canvis més.[/]")
    # Font FCB: aquí, només detecció. Serveix per saber quan la federació catalana
    # penja una revisió nova al seu web i deixar-ne apuntada la URL; ingestar-la és
    # un pas a part (`--font FCB --fitxer`), perquè fins ara el PDF ha arribat abans
    # per altres vies que no pas al /media/ de fcbillar.cat. Mai fatal.
    if not fitxer and not url:
        try:
            from fcbillar.calendari_fed import registra_fcb

            res_fcb = registra_fcb(get_settings().db_path)
            for c in res_fcb["calendaris"]:
                console.print(f"[dim]  FCB {c.temporada} {c.versio or ''}: {c.nom_fitxer}[/]")
            if not res_fcb["trobats"]:
                console.print("[dim]  FCB: cap calendari enllaçat al web.[/]")
            elif res_fcb["nous"]:
                console.print(f"[green]FCB: {res_fcb['nous']} calendari(s) nou(s) detectat(s).[/]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow]Avís: no s'ha pogut comprovar el calendari de la FCB: {exc}[/]")

    if not fets:
        console.print("[yellow]Cap calendari disponible per ingestar.[/]")
        raise typer.Exit(code=1)


@app.command("arxiva-lliga-en-viu")
def arxiva_lliga_en_viu_cmd(
    temporada: str = typer.Option(..., "--temporada", help="La que s'arxiva, ex. 2025-2026."),
    lliga: str = typer.Option("LLIGA CATALANA TRES BANDES", "--lliga"),
    aplica: bool = typer.Option(False, "--aplica", help="Fes-ho. Sense això només ho ensenya."),
) -> None:
    """Passa la classificació en viu a l'històric abans de rellevar-la.

    `publish_lliga` reescriu `lliga_standings` amb la temporada en curs. La
    temporada que hi havia no es mou a cap altra banda: si es publica la nova
    sense arxivar l'anterior, l'anterior desapareix del web i no queda enlloc.
    Aquesta comanda la copia a `lliga_standings_hist`, que és d'on beu el
    selector de temporades.

    S'arxiva el que hi ha PUBLICAT, no una classificació recalculada: així el
    que queda a l'històric és exactament el que ensenyava el web, amb les
    posicions oficials i les penalitzacions federatives tal com hi eren.

    L'importador històric (`scripts/import_lliga_standings.py`) fa una altra
    cosa i ara mateix no serveix per a això: llegeix les pàgines d'historial del
    web vell, que ja no existeixen.
    """
    from fcbillar.cloud_sync import get_client

    conn = ensure_schema(get_settings().db_path)
    sb = get_client()
    grups = {
        (g["divisio_id"], g["grup_id"]): (g["divisio_nom"], g["grup_nom"])
        for g in (sb.table("lliga_groups").select("*").execute().data or [])
    }
    # El nom del grup pot faltar al que hi ha publicat: les promocions es van
    # descobrir després de publicar-les i van pujar sense nom. Els noms locals
    # són més recents, i el nom és clau primària a l'històric —arxivar-lo sense
    # nom seria perdre'l.
    locals_ = {
        (d, g): n
        for d, g, n in conn.execute(
            "SELECT divisio_id, grup_id, nom FROM lliga_noms WHERE grup_id <> 0"
        )
    }
    for clau, (dn, gn) in list(grups.items()):
        if not gn:
            grups[clau] = (dn, locals_.get(clau))
    files = sb.table("lliga_standings").select("*").execute().data or []
    if not files:
        console.print("[red]No hi ha cap classificació en viu per arxivar.[/]")
        raise typer.Exit(1)

    ja = conn.execute(
        "SELECT COUNT(*) FROM lliga_standings_hist WHERE temporada = ? AND lliga = ?",
        (temporada, lliga),
    ).fetchone()[0]
    if ja:
        console.print(
            f"[yellow]La temporada {temporada} ja té {ja} files a l'històric.[/] "
            f"No la torno a escriure: si l'has de refer, esborra-les abans."
        )
        raise typer.Exit(1)

    rows = []
    for r in files:
        divisio, grup = grups.get((r["divisio_id"], r["grup_id"]), (None, None))
        if not divisio or not grup:
            console.print(
                f"[red]No sé com es diu el grup {r['divisio_id']}/{r['grup_id']} "
                f"(divisió={divisio!r}, grup={grup!r}) i no l'arxivo sense nom: el nom "
                f"és clau a l'històric.[/] Prova `fcbillar discover-lliga-noms`."
            )
            raise typer.Exit(1)
        rows.append(
            (temporada, lliga, divisio, grup, r["posicio"], r["equip"], r["punts"], r["pf"])
        )

    table = Table(title=f"{temporada} cap a l'històric" + ("" if aplica else " (assaig en sec)"))
    table.add_column("Divisió")
    table.add_column("Grup")
    table.add_column("Equips", justify="right")
    per_grup: dict[tuple[str, str], int] = {}
    for _t, _l, d, g, *_ in rows:
        per_grup[(d, g)] = per_grup.get((d, g), 0) + 1
    for (d, g), n in sorted(per_grup.items()):
        table.add_row(d, g, str(n))
    console.print(table)

    if not aplica:
        console.print(f"[yellow]{len(rows)} files. Torna-hi amb --aplica.[/]")
        return
    conn.executemany(
        "INSERT INTO lliga_standings_hist "
        "(temporada, lliga, divisio, grup, posicio, equip, pm, pp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    console.print(
        f"[green]OK {len(rows)} files desades a l'històric local.[/] "
        f"Ara `fcbillar publish --lliga-hist` per pujar-les."
    )


@app.command("ingest-inscrits-lliga")
def ingest_inscrits_lliga_cmd(
    lliga: int = typer.Option(
        0, "--lliga", help="Id de lliga de la federació. Per defecte, totes les obertes."
    ),
    temporada: str = typer.Option("2026/2027", "--temporada"),
    ranking_id: int = typer.Option(
        0, "--ranking", help="Rànquing amb què contrastar les mitjanes. 0 = no contrastar."
    ),
) -> None:
    """De qui està fet cada club a la lliga, tal com ho publica la federació.

    Des del setembre de 2026 la federació publica els jugadors que cada club
    inscriu a cada lliga, amb la mitjana i una etiqueta per als fitxatges. És la
    font oficial del que `plantilles` estimava a partir de qui havia jugat.

    Un fitxatge surt a dues llistes —al seu club sense marca i al club que se
    l'endú amb marca— i això no és cap error: són les dues cares del mateix
    fitxatge. El que sí que ho és va a la taula d'avisos del final.
    """
    from fcbillar.inscrits_lliga import (
        assigna_clubs_desconeguts,
        clubs_sense_jugadors,
        desa,
        llegeix_clubs,
        llegeix_inscrits,
        llegeix_lligues,
        mitjanes_del_ranquing,
        retira_lligues_tancades,
        revisa,
    )

    settings = get_settings()
    conn = ensure_schema(settings.db_path)
    mitjanes = mitjanes_del_ranquing(conn, ranking_id) if ranking_id else None

    with ScraperClient(settings) as client:
        obertes, descartades = llegeix_lligues(client)
        if not obertes:
            console.print("[red]Cap lliga oberta al llistat de la federació.[/]")
            raise typer.Exit(1)

        # Retirar el que ja no és al llistat només es pot fer si el llistat s'ha
        # entès SENCER. Una fila que no s'ha sabut llegir dona una llista curta
        # però no buida: passa per bona, i llavors les lligues que hi falten
        # s'esborrarien encara que segueixin obertes. Amb una de descartada val
        # més quedar-se files de més -es veuen i es resolen la propera vegada-
        # que esborrar-ne de bones.
        if descartades:
            console.print(
                f"  [yellow]{len(descartades)} files del llistat no s'han sabut llegir[/] "
                f"({', '.join(descartades[:3])}…): no retiro cap lliga."
            )
        else:
            # El llistat sencer, abans de filtrar per --lliga: amb la llista
            # retallada esborraríem totes les altres.
            tancades = retira_lligues_tancades(conn, temporada, {o.lliga_id for o in obertes})
            for lliga_id, quants in sorted(tancades.items()):
                console.print(
                    f"  [yellow]lliga {lliga_id}: {quants} inscrits retirats[/] "
                    f"(ja no és al llistat de la federació)"
                )

        if lliga:
            obertes = [o for o in obertes if o.lliga_id == lliga]
            if not obertes:
                console.print(f"[red]La lliga {lliga} no és al llistat d'obertes.[/]")
                raise typer.Exit(1)

        avisos_totals = []
        for oberta in obertes:
            console.print()
            console.print(f"[bold]{oberta.nom}[/] ({oberta.modalitat}, id {oberta.lliga_id})")
            info = llegeix_clubs(client, oberta)
            inscrits = llegeix_inscrits(client, info)
            if not inscrits:
                # Passa de debò: el setembre de 2026 la lliga de 4 Modalitats
                # tenia 29 equips inscrits i cap jugador a cap dels 20 clubs.
                # No és un error nostre i no ha d'aturar la resta.
                console.print(
                    f"  [yellow]{info.equips} equips de {len(info.clubs)} clubs, "
                    f"però cap jugador publicat.[/] No deso res d'aquesta lliga."
                )
                continue
            n = desa(conn, info, inscrits, temporada)
            fitxatges = sum(1 for i in inscrits if i.fitxatge)
            console.print(
                f"  [green]{n} inscrits[/] a "
                f"{len({i.club for i in inscrits})} de {len(info.clubs)} clubs · "
                f"{info.equips} equips · {fitxatges} fitxatges"
            )
            # Un club que no contesta no s'esborra, es deixa com estava. Dir-ho
            # és l'única manera que algú sàpiga que aquella composició és vella.
            muts = clubs_sense_jugadors(info, inscrits)
            if muts:
                console.print(
                    f"  [yellow]{len(muts)} clubs sense cap jugador publicat[/] "
                    f"(no els toco): {', '.join(muts)}"
                )
            avisos_totals += [(oberta.nom, a) for a in revisa(inscrits, mitjanes)]

        # Qui s'acaba de federar encara no és al cens de llicències i es queda
        # sense club, però la llista d'inscrits SÍ que diu de quin club juga.
        # Sense això, qualsevol pantalla que filtri per club el deixa fora.
        nous = assigna_clubs_desconeguts(conn, temporada)
        if nous:
            console.print()
            console.print(f"[bold]Club assignat des dels inscrits ({len(nous)})[/]")
            for jugador, club in sorted(nous.items())[:10]:
                console.print(f"  {jugador:36} [dim]→[/] {club}")
            if len(nous) > 10:
                console.print(f"  [dim]… i {len(nous) - 10} més[/]")

    if not avisos_totals:
        console.print()
        console.print("[green]Cap contradicció.[/]")
        return
    taula = Table(title=f"Contradiccions ({len(avisos_totals)})")
    taula.add_column("Tipus")
    taula.add_column("Jugador")
    taula.add_column("Clubs")
    taula.add_column("Detall")
    for _, a in avisos_totals:
        taula.add_row(a.tipus, a.jugador, " + ".join(a.clubs), a.detall)
    console.print()
    console.print(taula)


@app.command("plantilles")
def plantilles_cmd(
    temporada: str = typer.Option("2026/2027", "--temporada", help="La del llistat de divisions."),
    ranking_id: int = typer.Option(
        0, "--ranking", help="Rànquing de referència. Per defecte, l'últim abans de la 1a jornada."
    ),
) -> None:
    """Recalcula de qui està fet cada club, estimat.

    L'ordre de la graella de cada club és el del rànquing, i el rànquing que
    mana és **l'últim publicat abans que comenci la lliga**: si s'agafés el més
    recent, l'ordre canviaria a mitja temporada i el que va veure algú al
    setembre deixaria de quadrar amb el que veu al gener.

    És una estimació —la federació no publica plantilles— i va marcada com a tal
    a la interfície.
    """
    from fcbillar.plantilles import desa, plantilles

    conn = ensure_schema(get_settings().db_path)
    if not ranking_id:
        fila = conn.execute(
            """
            SELECT id, data_pub FROM rankings
             WHERE modalitat_id = 1
               AND data_pub < (SELECT MIN(data) FROM lliga_calendari WHERE data IS NOT NULL)
             ORDER BY data_pub DESC LIMIT 1
            """
        ).fetchone()
        if fila is None:
            console.print("[red]No hi ha cap rànquing de tres bandes anterior a la 1a jornada.[/]")
            raise typer.Exit(1)
        ranking_id, data_pub = fila
        console.print(f"  rànquing de referència: {ranking_id} ({data_pub})")

    jugadors = plantilles(conn, ranking_id, temporada)
    sense_fitxa = sum(1 for j in jugadors if j.player_fcb_id is None)
    sense_mitjana = sum(1 for j in jugadors if j.mitjana is None)
    n = desa(conn, jugadors, temporada)
    clubs = len({j.club for j in jugadors})
    console.print(
        f"  [green]{n} jugadors a {clubs} clubs[/] "
        f"({sense_fitxa} acabats de federar, {sense_mitjana} sense mitjana)"
    )


@app.command("sql-categoria-federativa")
def sql_categoria_federativa_cmd(
    club: str = typer.Option("C.B.BANYOLES", "--club", help="Club del qual generar-ho."),
    temporada: str = typer.Option("2026/2027", "--temporada"),
    federacio: str = typer.Option("fcb", "--federacio", help="`federations.id` a NouProjecte."),
    surt: str = typer.Option("", "--surt", help="Fitxer on desar-ho."),
) -> None:
    """El SQL que posa la categoria d'aquesta temporada als socis de NouProjecte.

    La categoria surt del PDF de divisions, que és el que reparteix els jugadors
    per divisions al campionat individual. NouProjecte ja té la columna
    (`member_federation_licenses.category_federacio`), o sigui que no cal cap
    migració d'esquema: és una actualització de dades.

    NO s'executa res. La política de NouProjecte és que cap SQL s'aplica sense
    que l'admin l'hagi validat, i aquesta comanda només l'escriu.

    El fitxer que en surt es comprova a si mateix: si el nombre de llicències
    que casen no és el que esperem, es planta dins de la transacció en comptes
    d'actualitzar-ne quatre i deixar-ho a mitges. És la manera de saber que els
    números de llicència de NouProjecte no s'escriuen igual que els nostres,
    que és l'única cosa que pot fallar aquí i que no es veu.
    """
    conn = ensure_schema(get_settings().db_path)
    files = conn.execute(
        """
        SELECT i.jugador, i.divisio, i.definitiva, p.fcb_id
          FROM inscrits_individual i
          LEFT JOIN players p ON p.nom = i.jugador
         WHERE i.temporada = ? AND i.club = ?
         ORDER BY i.posicio
        """,
        (temporada, canonic(club)),
    ).fetchall()
    if not files:
        console.print(
            f"[red]Cap inscrit del {canonic(club)} a la temporada {temporada}.[/] "
            f"Executa abans `fcbillar ingest-divisions-individual`."
        )
        raise typer.Exit(1)

    amb, sense = [f for f in files if f[3]], [f for f in files if not f[3]]
    # La coma va ABANS del comentari. Si va al final de la línia queda dins del
    # `--` i la llista de valors es converteix en un error de sintaxi.
    valors = "\n  ".join(
        f"('{lic}', '{div}')"
        + ("," if i < len(amb) - 1 else "")
        + f"  -- {jugador}"
        + ("" if defin else "  [mitjana provisional]")
        for i, (jugador, div, defin, lic) in enumerate(amb)
    )
    nota_sense = "".join(
        f"\n--   {j} ({d})" + ("  [mitjana provisional]" if not fi else "") for j, d, fi, _ in sense
    )
    sql = f"""-- Categoria federativa {temporada} dels socis del {canonic(club)}.
-- Generat per `fcbillar sql-categoria-federativa`. NO s'ha executat.
--
-- Surt del PDF de divisions de la FCB, que és el document amb què la federació
-- reparteix els jugadors per divisions al campionat individual.
--
-- No canvia cap taula ni cap columna: `member_federation_licenses.category_federacio`
-- ja existeix. Per tant no cal `NOTIFY pgrst`.
{"--" if not sense else f"-- SENSE LLICÈNCIA a la nostra base, i per tant fora d'aquí ({len(sense)}):{nota_sense}"}

BEGIN;

-- La llista va a una taula temporal, no repetida a cada sentència: així el
-- mira-t'ho, la comprovació i l'actualització diuen exactament el mateix.
CREATE TEMP TABLE categoria_nova (
  license_number TEXT PRIMARY KEY,
  categoria      TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO categoria_nova (license_number, categoria) VALUES
  {valors}
;

-- Mira-ho abans de deixar-ho anar: qui queda tocat i què tenia.
SELECT c.license_number, m.nom || ' ' || m.cognoms AS soci,
       l.category_federacio AS tenia, c.categoria AS passa_a
  FROM categoria_nova c
  JOIN member_federation_licenses l
    ON l.license_number = c.license_number AND l.federation_id = '{federacio}'
  JOIN members m ON m.id = l.member_id
 ORDER BY c.categoria, soci;

-- Si els números de llicència no s'escriuen igual als dos costats, l'UPDATE no
-- casaria res i no es veuria. Això ho fa visible abans de tocar cap fila.
DO $$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n
    FROM categoria_nova c
    JOIN member_federation_licenses l
      ON l.license_number = c.license_number AND l.federation_id = '{federacio}';
  IF n <> {len(amb)} THEN
    RAISE EXCEPTION
      'Esperava % llicències del {federacio} i n''he trobat %. No actualitzo res: '
      'mira si els números de llicència s''escriuen igual als dos costats.',
      {len(amb)}, n;
  END IF;
END $$;

UPDATE member_federation_licenses AS l
   SET category_federacio = c.categoria
  FROM categoria_nova c
 WHERE l.license_number = c.license_number
   AND l.federation_id = '{federacio}';

COMMIT;
"""
    if surt:
        Path(surt).write_text(sql, encoding="utf-8")
        console.print(f"[green]Escrit a {surt}[/] — {len(amb)} llicències.")
    else:
        console.print(sql)
    if sense:
        console.print(
            f"[yellow]{len(sense)} inscrit(s) sense llicència a la nostra base, "
            f"fora del SQL:[/] {', '.join(j for j, _, _, _ in sense)}"
        )


if __name__ == "__main__":
    app()
