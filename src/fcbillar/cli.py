"""CLI de FCBillar (Typer)."""

from __future__ import annotations

import logging
import sys

import typer

for _stream in (sys.stdout, sys.stderr):
    reconf = getattr(_stream, "reconfigure", None)
    if reconf is not None:
        reconf(encoding="utf-8", errors="replace")
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from fcbillar.auth import interactive_login
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
def login() -> None:
    """Obre un navegador visible per fer login manual (resol captcha) i desa la sessió."""
    ok = interactive_login()
    raise typer.Exit(code=0 if ok else 1)


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
    modalitat: int = typer.Argument(..., help="Codi de modalitat (1=tres bandes, 2=lliure, 3=quadre 47/2, 4=banda, 6=quadre 71/2)"),
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
    player_fcb_id: str = typer.Argument(..., help="fcb_id intern del jugador (vist a la URL Partides)"),
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
            client, num_seq, modalitat, player_fcb_id, settings=settings,
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


@app.command("discover-lliga")
def discover_lliga_cmd(
    lliga_id: int = typer.Argument(..., help="Id de la lliga (36=TRES BANDES, 37=4 MODALITATS)"),
    depth: int = typer.Option(
        2, "--depth", min=1, max=3,
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
                console.print(
                    f"    [green]{grup.nom}[/] (grup_id={grup.grup_id}){resp}"
                )
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
            console.print(
                f"[green]Lliga {lliga_id}: {len(tree.divisions)} divisions desades[/]"
            )
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
    help="Sincronitza l'estat canònic (BD + sessió) amb Cloudflare R2.",
    no_args_is_help=True,
)


def _state_names(db: bool, opens_db: bool, session: bool, default) -> tuple[str, ...]:
    """Tradueix els flags --db/--opens-db/--session a noms lògics (o el per defecte)."""
    picked = []
    if db:
        picked.append("db")
    if opens_db:
        picked.append("opens-db")
    if session:
        picked.append("session")
    return tuple(picked) if picked else default


@state_app.command("pull")
def state_pull_cmd(
    db: bool = typer.Option(False, "--db", help="Només la BD principal"),
    opens_db: bool = typer.Option(False, "--opens-db", help="Només la BD d'opens"),
    session: bool = typer.Option(False, "--session", help="Només la sessió de login"),
) -> None:
    """Baixa de R2 a local (escriptura atòmica). Sense flags: baixa-ho tot."""
    from fcbillar import state_sync

    names = _state_names(db, opens_db, session, state_sync.ALL)
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
    session: bool = typer.Option(False, "--session", help="Només la sessió de login"),
    check_generation: bool = typer.Option(
        False, "--check-generation", help="Nega si el núvol ha avançat (guardó de divergència)"
    ),
    force: bool = typer.Option(False, "--force", help="Ignora el guardó de generació"),
) -> None:
    """Puja de local a R2. Sense flags: puja BD principal + BD d'opens (no la sessió)."""
    from fcbillar import state_sync

    names = _state_names(db, opens_db, session, ("db", "opens-db"))
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
    session_ok: bool = typer.Option(True, "--session-ok/--no-session-ok"),
    n_ok: int = typer.Option(0, "--n-ok", help="Passos correctes"),
    n_fail: int = typer.Option(0, "--n-fail", help="Passos fallats"),
    last_error: str = typer.Option("", "--last-error", help="Resum de l'últim error"),
    close_requests: bool = typer.Option(
        False, "--close-requests", help="Tanca les files reingest_requests en 'running'"
    ),
) -> None:
    """Escriu l'estat de l'última reingesta a `fcbillar.cloud_status` (per al banner del PWA).

    Amb `--close-requests` també marca a 'done'/'error' les peticions del botó que
    havien quedat en estat 'running'. Cal SUPABASE_URL i SUPABASE_SERVICE_ROLE_KEY.
    """
    from datetime import datetime, timezone

    from fcbillar.cloud_sync import get_client

    now = datetime.now(timezone.utc).isoformat()
    sb = get_client()
    sb.table("cloud_status").upsert(
        {
            "id": 1,
            "session_ok": session_ok,
            "last_run": now,
            "last_error": last_error or None,
            "n_ok": n_ok,
            "n_fail": n_fail,
            "updated_at": now,
        },
        on_conflict="id",
    ).execute()
    console.print(
        f"[green]OK cloud_status: session_ok={session_ok} n_ok={n_ok} n_fail={n_fail}[/]"
    )

    if close_requests:
        status = "error" if n_fail > 0 else "done"
        sb.table("reingest_requests").update(
            {"status": status, "finished_at": now, "n_ok": n_ok, "n_fail": n_fail}
        ).eq("status", "running").execute()
        console.print(f"[green]OK reingest_requests 'running' → '{status}'.[/]")


app.add_typer(state_app, name="state")


@app.command("session-check")
def session_check_cmd() -> None:
    """Comprova si la sessió de login encara és vàlida (per al job del núvol).

    Codis de sortida: 0 = autenticat · 2 = no hi ha fitxer de sessió ·
    3 = la sessió ha caducat (la federació torna a servir el formulari de login).
    Qualsevol altre error (xarxa, timeout) surt amb 1 i NO s'ha d'interpretar com
    a sessió caducada.
    """
    from fcbillar.auth import LOGIN_FORM_SELECTOR
    from fcbillar.scraper.client import ScraperClient

    settings = get_settings()
    if not settings.storage_state_path.exists():
        console.print("[red]No hi ha sessió desada.[/]")
        raise typer.Exit(code=2)

    # IMPORTANT: comprovem /jugador/home, NO /ca/jugador. La landing /ca/jugador
    # renderitza el formulari de login (#formloguinacion) al DOM SEMPRE —fins i tot
    # autenticat—, cosa que donava falsos "sessió caducada". A /jugador/home el form
    # només hi és si NO estàs autenticat (si la sessió ha caducat, la federació hi
    # redirigeix a la landing de login). Sessió vàlida = sense formulari I encara a
    # /jugador/home.
    url = f"{settings.base_url.rstrip('/')}/jugador/home"
    try:
        with ScraperClient(settings) as client:
            client.page.goto(url, wait_until="domcontentloaded")
            client.page.wait_for_timeout(1500)  # deixa que un eventual redirect s'assenti
            form_present = client.page.query_selector(LOGIN_FORM_SELECTOR) is not None
            on_home = "/jugador/home" in client.page.url
    except Exception as exc:  # noqa: BLE001 — error transitori, no és sessió caducada
        console.print(f"[yellow]No s'ha pogut comprovar la sessió (transitori): {exc}[/]")
        raise typer.Exit(code=1) from exc

    if form_present or not on_home:
        console.print("[red]Sessió caducada: cal `fcbillar login` al PC i `state push --session`.[/]")
        raise typer.Exit(code=3)
    console.print("[green]OK sessió vàlida.[/]")



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
    console.print(
        f"[green]OK alias '{alias_nom}' afegit al club '{club_fcb_id}'.[/]"
    )


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


@app.command("import-temporada")
def import_temporada_cmd(
    no_clubs: bool = typer.Option(False, "--no-clubs", help="No fer import-clubs"),
    no_sync: bool = typer.Option(False, "--no-sync", help="No fer sync"),
    historical: bool = typer.Option(
        False, "--historical", help="Incloure backfill històric (~2 min sense partides)"
    ),
    historical_top: int | None = typer.Option(
        0, "--historical-top",
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
            f"[yellow]Cap jugador trobat per '{club_fcb_id}'. "
            f"Cal ingest previ de lliga.[/]"
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
        "current", "--temporada",
        help="Temporada (ex: '2024-2025') o 'current' per a l'actual",
    ),
    cache: bool = typer.Option(
        False, "--cache",
        help="Permet servir HTML de la cache (per defecte, fresc per detectar novetats)",
    ),
) -> None:
    """Ingest dels torneigs individuals (opens, catalans, etc.) per temporada."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = ingest_individuals_temporada(
            client,
            temporada=None if temporada == "current" else temporada,
            create_missing_players=True,
            settings=settings,
            use_cache=cache,
        )
    console.print(
        f"[green]OK individuals temporada {temporada}: "
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
        console.print(f"  [yellow]mostres de conflicte (game→torneig):[/] {res.conflict_samples[:5]}")

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
        conn.executemany("UPDATE torneigs_individuals SET nom=? WHERE id=?",
                         [(new, i) for (i, _o, new) in changes])
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

    FASE 1: rànquings. Cal SUPABASE_URL i SUPABASE_SERVICE_ROLE_KEY (al .env o a
    l'entorn). Idempotent: es pot reexecutar després de cada actualització.
    """
    from fcbillar.cloud_sync import (
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
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error publicant al núvol: {exc}[/]")
        raise typer.Exit(code=1) from exc
    total = ", ".join(f"{k}={v}" for k, v in counts.items())
    console.print(f"[green]OK publicat a Supabase (fcbillar): {total}[/]")

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


@app.command("publish-live-opens")
def publish_live_opens_cmd() -> None:
    """Bolca l'estat EN VIU dels Opens en curs a Supabase (taula `open_live`).

    Raspa la federació en directe (pàgines públiques, sense login) i puja l'estat
    de cada Open en curs perquè l'app web en mostri el seguiment en temps real.
    Totes les modalitats; s'exclouen els femenins i els ja tancats. Idempotent —
    pensat per executar-se sovint des d'un job programat (p.ex. GitHub Action).
    Cal SUPABASE_URL i SUPABASE_SERVICE_ROLE_KEY (al .env o a l'entorn).
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
            get_client().table("rankings").select("num_seq")
            .eq("modalitat_codi", 1).eq("any_pub", year).eq("mes_pub", mon).execute()
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
        "", "--name",
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


if __name__ == "__main__":
    app()
