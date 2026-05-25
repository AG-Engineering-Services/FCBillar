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
from fcbillar.pipeline import (
    backfill_historical,
    backfill_modalitat,
    fetch_ranking_html,
    ingest_lliga_jornada,
    ingest_partides,
    ingest_ranking,
    run_status,
    set_follow,
    sync_current_rankings,
)
from fcbillar.scraper.client import ScraperClient

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
) -> None:
    """Descarrega les partides d'un jugador dins d'un rànquing i les desa a la BD."""
    settings = get_settings()
    with ScraperClient(settings) as client:
        result = ingest_partides(client, num_seq, modalitat, player_fcb_id, settings=settings)
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
        )
    console.print(
        f"[green]OK jornada {lliga_id}/{divisio_id}/{grup_id}/{jornada_id}: "
        f"{result.encontres_processed} encontres ({result.encontres_failed} fallats), "
        f"{result.total_games_upserted} partides desades, "
        f"{result.total_games_skipped} saltades.[/]"
    )


if __name__ == "__main__":
    app()
