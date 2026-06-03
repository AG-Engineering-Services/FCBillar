"""App FastAPI de FCBillar.

Tots els endpoints sota /api. Reutilitza `DataSource` (capa SQL sense Qt) i
converteix els dataclasses a dicts JSON. Pensat per ser consumit pel frontend
SvelteKit (proxy Vite /api → :8000 en dev).
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from desktop.models.data_source import DataSource

app = FastAPI(title="FCBillar API", version="1.0")

# En dev el frontend va al 5173 (Vite). CORS obert per a localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ds = DataSource()


def ds() -> DataSource:
    return _ds


# ======================================================================
# Opens (vendored fcb_opens package)
# ======================================================================
# The fcb_opens project is a complete, validated engine for FCB "Opens"
# (generator, reglament rules, live scraper). It ships its own FastAPI app
# (routes under /api/*) and its own SQLite DB (data/fcb_opens.db), so we mount
# it as a sub-application under /opens-backend instead of merging routes (its
# lliga/players/sync routes would collide with ours). The SvelteKit opens
# pages talk to it via base path /opens-backend/api.
try:
    from fcb_opens.api.app import app as _opens_app

    app.mount("/opens-backend", _opens_app)
except Exception as exc:  # noqa: BLE001 — never let opens break the core API
    import logging

    logging.getLogger(__name__).warning("Opens sub-app not mounted: %s", exc)


# ======================================================================
# Health / stats
# ======================================================================


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/stats")
def stats() -> dict:
    c = ds().counts()
    return asdict(c)


@app.get("/api/modalitats")
def modalitats() -> list[dict]:
    return [{"codi_fcb": codi, "nom": nom} for codi, nom in ds().modalitats()]


# ======================================================================
# Rànquings
# ======================================================================


@app.get("/api/rankings/top")
def rankings_top(top_n: int = 10) -> list[dict]:
    return [asdict(e) for e in ds().top_ranking_per_modalitat(top_n)]


@app.get("/api/rankings/{modalitat}/snapshots")
def ranking_snapshots(modalitat: int) -> list[int]:
    return ds().ranking_snapshots(modalitat)


@app.get("/api/rankings/{modalitat}")
def ranking_full(modalitat: int, num_seq: int | None = None) -> list[dict]:
    return [asdict(e) for e in ds().ranking_full(modalitat, num_seq)]


# ======================================================================
# Jugadors
# ======================================================================


@app.get("/api/players")
def players(q: str = "", limit: int = 200) -> list[dict]:
    return [asdict(p) for p in ds().search_players(q, limit)]


@app.get("/api/players/{fcb_id}")
def player_profile(fcb_id: str, modalitat: int | None = None) -> dict:
    summary = ds().player_summary(fcb_id, modalitat_codi_fcb=modalitat)
    if not summary:
        raise HTTPException(status_code=404, detail="Jugador no trobat")
    bw = ds().player_best_worst_games(fcb_id, top=5)
    return {
        "summary": summary,
        "best_worst": {k: [asdict(g) for g in v] for k, v in bw.items()},
    }


@app.get("/api/players/{fcb_id}/ranking-history")
def player_ranking_history(fcb_id: str, modalitat: int | None = None) -> list[dict]:
    return ds().player_ranking_history(fcb_id, modalitat)


@app.get("/api/players/{fcb_id}/games")
def player_games(fcb_id: str, limit: int = 100, modalitat: int | None = None) -> list[dict]:
    return [asdict(g) for g in ds().player_games(fcb_id, limit, modalitat_codi_fcb=modalitat)]


# ======================================================================
# Clubs
# ======================================================================


@app.get("/api/clubs")
def clubs() -> list[dict]:
    return [asdict(c) for c in ds().clubs_with_kpis()]


@app.get("/api/clubs/{club_fcb_id}/players")
def club_players(club_fcb_id: str, season_only: bool = True) -> list[dict]:
    return [
        asdict(p)
        for p in ds().club_players(club_fcb_id, current_season_only=season_only)
    ]


# ======================================================================
# Partides (cerca global)
# ======================================================================


@app.get("/api/games")
def games(
    player: str = "",
    club: str = "",
    modalitat: int | None = None,
    competicio: str = "",
    season_only: bool = False,
    limit: int = 300,
) -> list[dict]:
    return [
        asdict(g)
        for g in ds().search_games(
            player=player,
            club=club,
            modalitat_codi_fcb=modalitat,
            competicio=competicio,
            season_only=season_only,
            limit=limit,
        )
    ]


# ======================================================================
# Resultats: lliga / copa / individuals
# ======================================================================


@app.get("/api/results/lliga/groups")
def lliga_groups(season_only: bool = True) -> list[dict]:
    return ds().lliga_groups(season_only=season_only)


@app.get("/api/results/lliga/standings")
def lliga_standings(lliga_id: int, divisio_id: int, grup_id: int) -> list[dict]:
    return [asdict(s) for s in ds().lliga_standings(lliga_id, divisio_id, grup_id)]


@app.get("/api/results/lliga/tree")
def lliga_tree(season_only: bool = True) -> list[dict]:
    """Arbre complet: competició → categoria → grups amb classificacions."""
    return ds().lliga_tree(season_only=season_only)


@app.get("/api/results/lliga/jornades")
def lliga_jornades(lliga_id: int, divisio_id: int, grup_id: int) -> list[dict]:
    """Jornades d'un grup amb els seus encontres (resultat de match)."""
    return ds().lliga_jornades(lliga_id, divisio_id, grup_id)


@app.get("/api/results/encontre/{encontre_id}")
def encontre_detail(encontre_id: int) -> dict:
    """Detall d'un encontre: capçalera + partides individuals."""
    d = ds().encontre_detail(encontre_id)
    if not d:
        raise HTTPException(status_code=404, detail="Encontre no trobat")
    return d


@app.get("/api/results/copa")
def copa(season_only: bool = True, limit: int = 300) -> list[dict]:
    return [asdict(g) for g in ds().copa_games(season_only=season_only, limit=limit)]


@app.get("/api/results/copa/edicions")
def copa_edicions() -> list[dict]:
    return ds().copa_edicions()


@app.get("/api/results/copa/jornades")
def copa_jornades(edicio_id: int) -> list[dict]:
    return ds().copa_jornades(edicio_id)


@app.get("/api/results/copa/grup")
def copa_grup(edicio_id: int, jornada: int, grup_id: int) -> dict:
    return ds().copa_grup(edicio_id, jornada, grup_id)


@app.get("/api/results/copa/encontre/{encontre_copa_id}")
def copa_encontre_detail(encontre_copa_id: int) -> dict:
    d = ds().copa_encontre_detail(encontre_copa_id)
    if not d:
        raise HTTPException(status_code=404, detail="Encontre de copa no trobat")
    return d


@app.get("/api/results/lliga/temporades")
def lliga_temporades() -> list[dict]:
    return ds().lliga_temporades()


@app.get("/api/results/lliga/player-ranking")
def lliga_player_ranking(
    modalitat: int | None = None, temporada_id: int | None = None
) -> list[dict]:
    return ds().lliga_player_ranking(
        modalitat_codi_fcb=modalitat, temporada_id=temporada_id
    )


@app.get("/api/results/copa/player-ranking")
def copa_player_ranking(edicio_id: int | None = None) -> list[dict]:
    return ds().copa_player_ranking(edicio_id=edicio_id)


@app.get("/api/results/individuals/seasons")
def individuals_seasons() -> list[str]:
    return ds().individuals_seasons()


@app.get("/api/results/individuals")
def individuals_list(temporada: str | None = None) -> list[dict]:
    return [asdict(t) for t in ds().individuals_list(temporada=temporada)]


@app.get("/api/results/individuals/{torneig_id}")
def individual_classification(torneig_id: int) -> list[dict]:
    return ds().individual_classification(torneig_id)


@app.get("/api/results/individuals/{torneig_id}/phases")
def individual_phases(torneig_id: int) -> list[dict]:
    return ds().individual_phases(torneig_id)


# ======================================================================
# Focus de club (real o virtual) — l'eix central per a l'usuari
# ======================================================================


@app.get("/api/focus/resolve")
def focus_resolve(kind: str, key: str, season_only: bool = True) -> dict:
    """Resol els player_ids d'un focus i retorna KPIs + membres d'una tacada."""
    if kind == "real":
        ids = ds().real_club_player_ids(key, season_only=season_only)
    elif kind == "virtual":
        ids = ds().virtual_club_player_ids(int(key))
    else:
        raise HTTPException(status_code=400, detail="kind ha de ser 'real' o 'virtual'")
    return {
        "player_ids": ids,
        "summary": ds().focus_summary(ids, season_only=season_only),
        "players": [asdict(p) for p in ds().focus_players(ids)],
    }


@app.get("/api/focus/order-evolution")
def focus_order_evolution(
    kind: str, key: str, modalitat: int, season_only: bool = True
) -> dict:
    club: str | None = None
    if kind == "real":
        ids = ds().real_club_player_ids(key, season_only=season_only)
        club = key  # marca rànquings posteriors a deixar el club
    else:
        ids = ds().virtual_club_player_ids(int(key))
    return ds().focus_order_evolution(ids, modalitat, club_fcb_id=club)


@app.get("/api/focus/best-worst")
def focus_best_worst(
    kind: str, key: str, season_only: bool = True, top: int = 10
) -> dict:
    if kind == "real":
        ids = ds().real_club_player_ids(key, season_only=season_only)
    else:
        ids = ds().virtual_club_player_ids(int(key))
    return ds().focus_best_worst_games(ids, season_only=season_only, top=top)


@app.get("/api/focus/games")
def focus_games(
    kind: str, key: str, season_only: bool = True, result: str = "all", limit: int = 500
) -> list[dict]:
    if kind == "real":
        ids = ds().real_club_player_ids(key, season_only=season_only)
    else:
        ids = ds().virtual_club_player_ids(int(key))
    return [asdict(g) for g in ds().focus_games(ids, season_only=season_only, result=result, limit=limit)]


# ======================================================================
# Clubs virtuals (CRUD)
# ======================================================================


class VirtualClubIn(BaseModel):
    nom: str
    descripcio: str | None = None


class MemberIn(BaseModel):
    player_fcb_id: str


@app.get("/api/virtual-clubs")
def virtual_clubs() -> list[dict]:
    return [asdict(v) for v in ds().list_virtual_clubs()]


@app.post("/api/virtual-clubs")
def create_virtual_club(body: VirtualClubIn) -> dict:
    vc_id = ds().create_virtual_club(body.nom, body.descripcio)
    return {"id": vc_id}


@app.put("/api/virtual-clubs/{vc_id}")
def update_virtual_club(vc_id: int, body: VirtualClubIn) -> dict:
    ds().update_virtual_club(vc_id, body.nom, body.descripcio)
    return {"ok": True}


@app.delete("/api/virtual-clubs/{vc_id}")
def delete_virtual_club(vc_id: int) -> dict:
    ds().delete_virtual_club(vc_id)
    return {"ok": True}


@app.get("/api/virtual-clubs/{vc_id}/members")
def virtual_club_members(vc_id: int) -> list[dict]:
    return [asdict(p) for p in ds().virtual_club_members(vc_id)]


@app.post("/api/virtual-clubs/{vc_id}/members")
def add_virtual_club_member(vc_id: int, body: MemberIn) -> dict:
    ok = ds().add_virtual_club_member(vc_id, body.player_fcb_id)
    return {"added": ok}


@app.delete("/api/virtual-clubs/{vc_id}/members/{player_fcb_id}")
def remove_virtual_club_member(vc_id: int, player_fcb_id: str) -> dict:
    ds().remove_virtual_club_member(vc_id, player_fcb_id)
    return {"ok": True}


# ======================================================================
# Actualització de dades (executa comandes fcbillar en segon pla)
# ======================================================================


class SyncRunIn(BaseModel):
    task: str


@app.get("/api/sync/tasks")
def sync_tasks() -> list[dict]:
    from api.jobs import task_list

    return task_list()


@app.get("/api/sync/status")
def sync_status() -> dict:
    from api.jobs import runner

    return runner.status()


@app.get("/api/sync/session")
def sync_session() -> dict:
    from api.jobs import session_info

    return session_info()


@app.post("/api/sync/run")
def sync_run(body: SyncRunIn) -> dict:
    from api.jobs import runner

    accepted, msg = runner.start(body.task)
    return {"accepted": accepted, "message": msg}
