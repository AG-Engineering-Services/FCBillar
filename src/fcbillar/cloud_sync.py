"""Publica la BD SQLite local al núvol (Supabase, schema `fcbillar`).

Aquesta és la meitat d'"escriptura" del model desktop→núvol: el desktop és
l'únic que baixa dades (scraping) i les desa a SQLite; aquí les puja a Supabase,
des d'on el frontend desplegat a Vercel les llegeix (només lectura, RLS).

Auth: SUPABASE_URL i SUPABASE_SERVICE_ROLE_KEY (la service_role salta RLS i pot
escriure; mai s'ha de publicar). Es llegeixen de l'entorn o del fitxer .env.

FASE 1: només la llesca de rànquings (modalitats, clubs, jugadors, rankings,
ranking_entries). Idempotent via upsert sobre claus naturals.
"""

from __future__ import annotations

import functools
import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path

from fcbillar.config import PROJECT_ROOT, get_settings

SCHEMA = "fcbillar"
Progress = Callable[[str, str], None]

# --- App germana "Estadístiques" (schema public, mateix projecte Supabase) ---
# Mapatge entre el seu món i el federatiu, per marcar `public.partides.computa`.
EST_USERS: dict[int, str] = {1: "278", 2: "2535", 3: "332"}  # usuari_id -> fcb_id
EST_MOD_BY_FCB: dict[int, int] = {1: 1, 2: 2, 3: 4, 4: 3, 6: 5}  # codi_fcb -> modalitat_id


@functools.lru_cache(maxsize=1)
def _name_overrides() -> dict[str, str]:
    """Mapa 'nom federatiu' → 'nom a mostrar' llegit de `noms_list.txt` (arrel).

    Els noms vénen de la federació tal qual (sovint en castellà: "MÓNICA",
    "CASTAÑO"…). Aquest fitxer permet forçar la forma a mostrar sense tocar la
    dada d'origen. S'aplica al publicar, de manera que TOTES les apps que
    llegeixen el núvol (FCBillar web i campionats) reben el nom corregit.
    """
    out: dict[str, str] = {}
    f = PROJECT_ROOT / "noms_list.txt"
    if f.exists():
        for raw in f.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            left, right = line.split("=", 1)
            if left.strip() and right.strip():
                out[left.strip()] = right.strip()
    return out


def _disp(nom: str | None) -> str | None:
    """Nom de jugador a mostrar, aplicant l'override de `noms_list.txt` si n'hi ha."""
    return _name_overrides().get(nom, nom) if nom is not None else None


def _env(name: str) -> str | None:
    """Llegeix una variable de l'entorn o, si no hi és, del .env del projecte."""
    import os

    val = os.environ.get(name)
    if val:
        return val.strip()
    env = PROJECT_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                return line.partition("=")[2].strip().strip('"').strip("'") or None
    return None


def get_client():
    """Client Supabase amb la service_role, fixat al schema `fcbillar`."""
    from supabase import create_client

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not url:
        raise RuntimeError("Falta SUPABASE_URL (entorn o .env).")
    if not key:
        raise RuntimeError("Falta SUPABASE_SERVICE_ROLE_KEY (entorn o .env).")
    return create_client(url, key).schema(SCHEMA)


def get_public_client():
    """Client Supabase amb service_role, schema `public` (app germana Estadístiques).

    Comparteix el mateix projecte Supabase; la service_role salta RLS i pot
    escriure a `public.partides` (marca `computa`)."""
    from supabase import create_client

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Falta SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (entorn o .env).")
    return create_client(url, key).schema("public")


def _chunks(rows: list[dict], n: int = 500) -> Iterable[list[dict]]:
    for i in range(0, len(rows), n):
        yield rows[i : i + n]


def _upsert(sb, table: str, rows: list[dict], on_conflict: str, prog: Progress) -> int:
    total = 0
    for chunk in _chunks(rows):
        sb.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        total += len(chunk)
    prog("ok", f"{table}: {total} files")
    return total


def publish_rankings(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja la llesca de rànquings de la BD SQLite a Supabase. Retorna comptadors."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()
    counts: dict[str, int] = {}

    # 1. modalitats
    mods = [
        {"codi_fcb": r["codi_fcb"], "nom": r["nom"]}
        for r in conn.execute("SELECT codi_fcb, nom FROM modalitats")
    ]
    counts["modalitats"] = _upsert(sb, "modalitats", mods, "codi_fcb", prog)

    # 2. clubs
    clubs = [
        {"fcb_id": r["fcb_id"], "nom": r["nom"]}
        for r in conn.execute("SELECT fcb_id, nom FROM clubs")
    ]
    club_ids = {c["fcb_id"] for c in clubs}
    counts["clubs"] = _upsert(sb, "clubs", clubs, "fcb_id", prog)

    # 3. players (club_fcb_id null si el club no és a la taula → respecta la FK)
    players = []
    for r in conn.execute(
        """
        SELECT p.fcb_id, p.nom, c.fcb_id AS club_fcb_id, p.seguiment
        FROM players p LEFT JOIN clubs c ON c.id = p.club_id
        """
    ):
        club = r["club_fcb_id"] if r["club_fcb_id"] in club_ids else None
        players.append({
            "fcb_id": r["fcb_id"],
            "nom": _disp(r["nom"]),
            "club_fcb_id": club,
            "seguiment": bool(r["seguiment"]),
        })
    counts["players"] = _upsert(sb, "players", players, "fcb_id", prog)

    # 4. rankings
    rankings = [
        {
            "modalitat_codi": r["modalitat_codi"],
            "num_seq": r["num_seq"],
            "any_pub": r["any_pub"],
            "mes_pub": r["mes_pub"],
            "data_pub": r["data_pub"],
        }
        for r in conn.execute(
            """
            SELECT m.codi_fcb AS modalitat_codi, r.num_seq, r.any_pub, r.mes_pub, r.data_pub
            FROM rankings r JOIN modalitats m ON m.id = r.modalitat_id
            """
        )
    ]
    counts["rankings"] = _upsert(sb, "rankings", rankings, "modalitat_codi,num_seq", prog)

    # 5. ranking_entries
    entries = [
        {
            "modalitat_codi": r["modalitat_codi"],
            "num_seq": r["num_seq"],
            "player_fcb_id": r["player_fcb_id"],
            "posicio": r["posicio"],
            "mitjana_general": r["mitjana_general"],
            "mitjana_particular": r["mitjana_particular"],
            "partides": r["partides"],
        }
        for r in conn.execute(
            """
            SELECT m.codi_fcb AS modalitat_codi, r.num_seq,
                   p.fcb_id AS player_fcb_id, re.posicio,
                   re.mitjana_general, re.mitjana_particular, re.partides
            FROM ranking_entries re
            JOIN rankings r ON r.id = re.ranking_id
            JOIN modalitats m ON m.id = r.modalitat_id
            JOIN players p ON p.id = re.player_id
            """
        )
    ]
    counts["ranking_entries"] = _upsert(
        sb, "ranking_entries", entries, "modalitat_codi,num_seq,player_fcb_id", prog
    )

    conn.close()
    return counts


def publish_provisional_ranking(
    db_path: Path | None = None,
    on_progress: Progress | None = None,
    modalitats: tuple[int, ...] = (1,),
) -> dict[str, int]:
    """Computa i puja el rànquing PROVISIONAL a `fcbillar.ranking_provisional`.

    Projecció del proper rànquing reusant la MATEIXA lògica que la fitxa (`rank15`):
    per cada jugador rankejat, mitjana = ΣC/ΣE sobre les seves `pending_games`
    (competicions en curs no a `games`) + les (15 − n_pending) partides MÉS RECENTS
    de `games` (dins la finestra de 24 mesos respecte del proper rànquing). Reordena
    els jugadors per aquesta mitjana efectiva i assigna posició projectada.

    Un jugador només "es mou" si té ≥1 partida pendent; altrament conserva la mitjana
    oficial per a l'ordre. Si ningú té pendents, la modalitat queda sense files i el
    frontend no mostra la columna provisional. Pilot: Tres Bandes (codi 1)."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    def _next_month(y: int, m: int) -> tuple[int, int]:
        m += 1
        if m == 8:  # el rànquing salta l'agost
            m = 9
        if m == 13:
            y, m = y + 1, 1
        return y, m

    def _month_offset(y: int, m: int, off: int) -> str:
        idx = y * 12 + (m - 1) + off
        return f"{idx // 12:04d}-{idx % 12 + 1:02d}-01"

    total = 0
    for mod in modalitats:
        rk = conn.execute(
            """SELECT r.id, r.num_seq, r.any_pub, r.mes_pub
               FROM rankings r JOIN modalitats m ON m.id = r.modalitat_id
               WHERE m.codi_fcb = ? ORDER BY r.num_seq DESC LIMIT 1""",
            (mod,),
        ).fetchone()
        if rk is None:
            continue
        if rk["any_pub"] and rk["mes_pub"]:
            ny, nm = _next_month(rk["any_pub"], rk["mes_pub"])
            age_cutoff = _month_offset(ny, nm, -24)
        else:
            age_cutoff = "0000-00-00"

        entries = conn.execute(
            """SELECT p.fcb_id, e.posicio, e.mitjana_general, e.extras_json
               FROM ranking_entries e JOIN players p ON p.id = e.player_id
               WHERE e.ranking_id = ?""",
            (rk["id"],),
        ).fetchall()
        if not entries:
            continue

        mod_id = conn.execute(
            "SELECT id FROM modalitats WHERE codi_fcb = ?", (mod,)
        ).fetchone()[0]
        # Per jugador: (data, caramboles_propis, caramboles_rival, entrades, game_id).
        games_by: dict[str, list[tuple[str, int | None, int | None, int | None, str]]] = {}
        for r in conn.execute(
            """SELECT g.id gid, p1.fcb_id f1, g.caramboles1 c1, p2.fcb_id f2,
                      g.caramboles2 c2, g.entrades e, g.data_partida d
               FROM games g JOIN players p1 ON p1.id = g.player1_id
               JOIN players p2 ON p2.id = g.player2_id WHERE g.modalitat_id = ?""",
            (mod_id,),
        ):
            if r["d"] and r["d"] >= age_cutoff:
                games_by.setdefault(r["f1"], []).append((r["d"], r["c1"], r["c2"], r["e"], r["gid"]))
                games_by.setdefault(r["f2"], []).append((r["d"], r["c2"], r["c1"], r["e"], r["gid"]))

        # pending per jugador (de Supabase, publicat per publish_pending_games abans).
        pend: dict[str, list[tuple[int | None, int | None, int | None]]] = {}
        pdata = (
            sb.table("pending_games")
            .select("player_fcb_id, caramboles, caramboles_opp, entrades")
            .eq("modalitat_codi", mod)
            .execute()
            .data
            or []
        )
        for pr in pdata:
            pend.setdefault(pr["player_fcb_id"], []).append(
                (pr["caramboles"], pr["caramboles_opp"], pr["entrades"])
            )

        # IDs dels games que componen el rànquing OFICIAL vigent (per jugador): per
        # ressaltar "quins games computen" també als qui NO s'han mogut (autoritatiu,
        # de la federació via ranking_game_links).
        #
        # A més, el `rowid` d'aquests links == ordre de la pàgina `partideshome`
        # de la federació (agrupada per competició; dins d'un mateix dia, en ordre
        # de joc). Quan la finestra de 15 PARTEIX un dia, la federació conserva la
        # partida llistada MÉS TARD (rowid més alt = jugada més tard = més recent)
        # i en deixa fora l'anterior. Comprovat empíricament sobre 5 rànquings:
        # 265/267 casos de partició coincideixen (les 2 excepcions són partides del
        # mateix dia en competicions diferents, que la pròpia federació ordena de
        # forma inconsistent). Guardem l'ordre per usar-lo com a desempat al sort.
        links_by_fcb: dict[str, list[str]] = {}
        order_by_fcb: dict[str, dict[str, int]] = {}
        for lr in conn.execute(
            """SELECT p.fcb_id f, l.game_id gid, l.rowid rid FROM ranking_game_links l
               JOIN players p ON p.id = l.player_id_origen WHERE l.ranking_id = ?
               ORDER BY l.rowid""",
            (rk["id"],),
        ):
            links_by_fcb.setdefault(lr["f"], []).append(lr["gid"])
            order_by_fcb.setdefault(lr["f"], {})[lr["gid"]] = lr["rid"]

        import json as _json

        computed: list[dict] = []
        for e in entries:
            fcb, off_pos, off_mj = e["fcb_id"], e["posicio"], e["mitjana_general"]
            try:
                off_def = bool((_json.loads(e["extras_json"] or "{}")).get("definitiva", True))
            except Exception:  # noqa: BLE001
                off_def = True
            pg = pend.get(fcb, [])
            n_pending = len(pg)
            # Definitiu = 15 partides computables (24 mesos). Mai degradem un
            # definitiu oficial (la nostra `games` pot ser incompleta); però un
            # no-definitiu que arribi a 15 amb les pendents SÍ que es promociona.
            computable = len(games_by.get(fcb, [])) + n_pending
            proj_def = off_def or (n_pending > 0 and computable >= 15)
            if n_pending == 0:
                # Sense partides noves: ressaltem els games oficials que ja computen.
                computed.append({"fcb": fcb, "pos": off_pos, "mj": off_mj, "def": proj_def,
                                 "proj": None, "n": 0, "eff": off_mj or 0.0,
                                 "won": None, "lost": None, "tie": None,
                                 "gids": links_by_fcb.get(fcb) or None,
                                 "cur_gids": links_by_fcb.get(fcb) or None})
                continue
            # Finestra de 15: pendents (les més recents) + les més recents de games.
            # Desempat intradia per ordre de la federació (vegeu order_by_fcb):
            # mateixa data → rowid més alt primer, perquè la federació conserva la
            # partida llistada més tard. Les partides fora del darrer rànquing
            # oficial (més antigues, sempre sota el tall) reben -1 i queden al
            # final del seu dia.
            order = order_by_fcb.get(fcb, {})
            recent = sorted(
                games_by.get(fcb, []),
                key=lambda x: (x[0], order.get(x[4], -1)),
                reverse=True,
            )
            recent_window = recent[: max(0, 15 - min(n_pending, 15))]
            car = ent = won = lost = tie = 0

            def _tally(c, c_opp):
                nonlocal won, lost, tie
                if c is None or c_opp is None:
                    return
                if c > c_opp:
                    won += 1
                elif c < c_opp:
                    lost += 1
                else:
                    tie += 1

            for c, c_opp, en in pg[:15]:
                if c is not None and en is not None:
                    car += c
                    ent += en
                _tally(c, c_opp)
            gids: list[str] = []
            for _d, c, c_opp, en, gid in recent_window:
                if c is not None and en is not None:
                    car += c
                    ent += en
                _tally(c, c_opp)
                gids.append(gid)
            proj = (car / ent) if ent else None
            eff = proj if proj is not None else (off_mj or 0.0)
            computed.append({"fcb": fcb, "pos": off_pos, "mj": off_mj, "def": proj_def,
                             "proj": proj, "n": n_pending, "eff": eff,
                             "won": won, "lost": lost, "tie": tie, "gids": gids,
                             "cur_gids": links_by_fcb.get(fcb) or None})

        # La federació ordena TOTS els definitius (per mitjana) abans dels no
        # definitius. Respectem-ho: un no-definitiu amb 2 bones partides NO pot
        # avançar els definitius. (Projecció pilot: la condició definitiu/no es
        # conserva de l'oficial.)
        computed.sort(
            key=lambda c: (0 if c["def"] else 1, -c["eff"],
                           c["pos"] if c["pos"] is not None else 1_000_000)
        )
        active = [c for c in computed if c["n"] > 0]
        sb.table("ranking_provisional").delete().eq("modalitat_codi", mod).execute()
        if not active:
            prog("ok", f"ranking_provisional[{mod}]: 0 (sense partides pendents)")
            continue

        rows = [
            {
                "modalitat_codi": mod, "num_seq": rk["num_seq"], "player_fcb_id": c["fcb"],
                "posicio_oficial": c["pos"], "mitjana_oficial": c["mj"],
                "posicio_provisional": i,
                "mitjana_provisional": round(c["proj"], 4) if c["proj"] is not None else None,
                "partides_post": c["n"],
                "proj_won": c["won"], "proj_lost": c["lost"], "proj_tie": c["tie"],
                "window_game_ids": c["gids"], "current_game_ids": c["cur_gids"],
            }
            for i, c in enumerate(computed, start=1)
        ]
        for chunk in _chunks(rows):
            sb.table("ranking_provisional").insert(chunk).execute()
        total += len(rows)
        prog("ok",
             f"ranking_provisional[{mod}]: {len(rows)} files ({len(active)} amb partides noves)")

    conn.close()
    return {"ranking_provisional": total}


def publish_pending_games(
    db_path: Path | None = None,
    on_progress: Progress | None = None,
    modalitats: tuple[int, ...] = (1,),
) -> dict[str, int]:
    """Publica `fcbillar.pending_games`: partides jugades en competicions EN CURS
    (copa via `copa_partides` local + opens via `open_live` a Supabase) encara NO
    presents a `games`. És la font de la projecció del proper rànquing (la fitxa i
    `ranking_provisional`). Una fila per jugador i partida (perspectiva del jugador).

    Dedup per signatura (parella de noms normalitzats + caramboles + entrades)
    contra `games`: quan la partida ja hi consta, deixa de ser pendent. Pilot: Tres
    Bandes (la copa catalana és de 3 bandes; els opens es filtren per modalitat)."""
    import re as _re
    import unicodedata as _ud

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    def _nm(s: str | None) -> str:
        s = "".join(c for c in _ud.normalize("NFD", s or "") if _ud.category(c) != "Mn")
        return " ".join(s.strip().lower().split())

    def _sig(na, ca, nb, cb, ent) -> str:
        a, b = sorted([
            f"{_nm(na)}:{'' if ca is None else ca}",
            f"{_nm(nb)}:{'' if cb is None else cb}",
        ])
        return f"{a}|{b}|{'' if ent is None else ent}"

    _MODNM = {1: "Tres Bandes", 2: "Lliure", 3: "Quadre 47/2", 4: "Banda", 6: "Quadre 71/2"}
    nom2fcb: dict[str, str] = {}
    for r in conn.execute("SELECT nom, fcb_id FROM players"):
        nom2fcb.setdefault(_nm(r["nom"]), r["fcb_id"])

    # open_live es llegeix una sola vegada (Supabase).
    live_rows = sb.table("open_live").select("modality, payload_json, captured_at").execute().data or []

    total = 0
    for mod in modalitats:
        mrow = conn.execute("SELECT id FROM modalitats WHERE codi_fcb = ?", (mod,)).fetchone()
        if mrow is None:
            continue
        mod_id = mrow[0]

        game_sigs: set[str] = set()
        for r in conn.execute(
            """SELECT p1.nom n1, g.caramboles1 c1, p2.nom n2, g.caramboles2 c2, g.entrades e
               FROM games g JOIN players p1 ON p1.id = g.player1_id
               JOIN players p2 ON p2.id = g.player2_id WHERE g.modalitat_id = ?""",
            (mod_id,),
        ):
            game_sigs.add(_sig(r["n1"], r["c1"], r["n2"], r["c2"], r["e"]))

        out: dict[tuple[str, str], dict] = {}

        def _add(pf, opp_nom, opp_fcb, car, car_opp, ent, serie, comp, font, sig, cap):
            # Només jugadors amb fcb_id federatiu real; els placeholders ("name:…")
            # no tenen fitxa ni surten al rànquing, així que no aporten res.
            if pf is None or str(pf).startswith("name:"):
                return
            out.setdefault((pf, sig), {
                "player_fcb_id": pf, "modalitat_codi": mod, "signatura": sig,
                "competicio": comp, "font": font, "opponent_nom": opp_nom,
                "opponent_fcb_id": opp_fcb, "caramboles": car, "caramboles_opp": car_opp,
                "entrades": ent, "serie": serie, "captured_at": cap,
            })

        # --- COPA (Copa Catalana = 3 bandes → només modalitat 1) ---
        if mod == 1:
            for r in conn.execute(
                """SELECT local_nom, local_caramboles, local_serie, visitant_nom,
                          visitant_caramboles, visitant_serie, entrades FROM copa_partides"""
            ):
                if not r["entrades"] or r["entrades"] <= 0:
                    continue  # fixture no jugada (caramboles 0-0, sense entrades)
                sig = _sig(r["local_nom"], r["local_caramboles"], r["visitant_nom"],
                           r["visitant_caramboles"], r["entrades"])
                if sig in game_sigs:
                    continue
                lf = nom2fcb.get(_nm(r["local_nom"]))
                vf = nom2fcb.get(_nm(r["visitant_nom"]))
                _add(lf, r["visitant_nom"], vf, r["local_caramboles"], r["visitant_caramboles"],
                     r["entrades"], r["local_serie"], "Copa", "copa", sig, None)
                _add(vf, r["local_nom"], lf, r["visitant_caramboles"], r["local_caramboles"],
                     r["entrades"], r["visitant_serie"], "Copa", "copa", sig, None)

            # --- OPENS 3B de la temporada en curs (torneig_partides) ---
            # Partides reals d'opens scrapejades per ingest_open_games, encara NO al
            # rànquing oficial (dedup per signatura contra `games`). Cobreix l'OPEN ja
            # acabat però no absorbit pel rànquing mensual (cas Costa Daurada): mentre
            # open_live només té els opens EN DIRECTE, aquesta font manté la pendència
            # fins que la ingesta oficial els incorpora a `games`. La modalitat de l'open
            # viu al NOM (torneigs_individuals.modalitat_id és NULL), per això filtrem
            # per "TRES BANDES" i temporada en curs (temporada_id=1, no femení).
            for r in conn.execute(
                """SELECT ti.nom comp, tp.player1_nom n1, tp.caramboles1 c1, tp.serie1 s1,
                          tp.player2_nom n2, tp.caramboles2 c2, tp.serie2 s2, tp.entrades e
                   FROM torneig_partides tp
                   JOIN torneigs_individuals ti
                     ON ti.torneig_id_extern = tp.torneig_id_extern
                        AND ti.divisio_id_extern = tp.divisio_id_extern
                   WHERE ti.temporada_id = 1
                     AND ti.nom LIKE '%TRES BANDES%' AND ti.nom NOT LIKE '%FEMENI%'"""
            ):
                if not r["e"] or r["e"] <= 0:
                    continue
                sig = _sig(r["n1"], r["c1"], r["n2"], r["c2"], r["e"])
                if sig in game_sigs:
                    continue
                comp = _re.sub(r"^OPEN\s+TRES BANDES\s+", "", r["comp"] or "", flags=_re.I).strip() or "Open"
                lf = nom2fcb.get(_nm(r["n1"]))
                vf = nom2fcb.get(_nm(r["n2"]))
                _add(lf, r["n2"], vf, r["c1"], r["c2"], r["e"], r["s1"], comp, "open", sig, None)
                _add(vf, r["n1"], lf, r["c2"], r["c1"], r["e"], r["s2"], comp, "open", sig, None)

        # --- OPENS EN CURS (open_live) ---
        modname = _MODNM.get(mod)
        for ol in live_rows:
            if (ol.get("modality") or "") != modname:
                continue
            payload = ol.get("payload_json") or {}
            cap = ol.get("captured_at")
            comp = _re.sub(r"\s*-\s*[ÚU]NICA\s*$", "", payload.get("name") or "", flags=_re.I).strip()
            pids = payload.get("player_ids") or {}

            def _pid(n):
                return pids.get(n) or nom2fcb.get(_nm(n))

            def _match(m):
                if not m.get("is_played"):
                    return
                na, nb = m.get("player_a"), m.get("player_b")
                ca, cb, ent = m.get("caramboles_a"), m.get("caramboles_b"), m.get("entrades")
                if not ent or ent <= 0:
                    return  # marcada jugada però sense entrades: descartem
                sig = _sig(na, ca, nb, cb, ent)
                if sig in game_sigs:
                    return
                fa, fb = _pid(na), _pid(nb)
                _add(fa, nb, fb, ca, cb, ent, m.get("serie_major_a"), comp, "open_live", sig, cap)
                _add(fb, na, fa, cb, ca, ent, m.get("serie_major_b"), comp, "open_live", sig, cap)

            for ph in payload.get("phases", []):
                for grp in ph.get("groups", []):
                    for m in grp.get("matches", []):
                        _match(m)
                for m in ph.get("ko_matches", []):
                    _match(m)

        # --- LLIGA: partides jugades encara no al rànquing oficial (lliga_pending_partides) ---
        # Capturades per ingest_lliga_encontre (promocions/finals i jornades recents)
        # abans que partideshome les pugi a `games`. Dedup per signatura contra `games`:
        # en incorporar-les la ingesta oficial, deixen de ser pendents.
        for r in conn.execute(
            """SELECT competicio, player1_nom n1, caramboles1 c1, serie1 s1,
                      player2_nom n2, caramboles2 c2, serie2 s2, entrades e
               FROM lliga_pending_partides WHERE modalitat_codi = ?""",
            (mod,),
        ):
            if not r["e"] or r["e"] <= 0:
                continue
            sig = _sig(r["n1"], r["c1"], r["n2"], r["c2"], r["e"])
            if sig in game_sigs:
                continue
            lf = nom2fcb.get(_nm(r["n1"]))
            vf = nom2fcb.get(_nm(r["n2"]))
            comp = r["competicio"] or "Lliga"
            _add(lf, r["n2"], vf, r["c1"], r["c2"], r["e"], r["s1"], comp, "lliga", sig, None)
            _add(vf, r["n1"], lf, r["c2"], r["c1"], r["e"], r["s2"], comp, "lliga", sig, None)

        sb.table("pending_games").delete().eq("modalitat_codi", mod).execute()
        rows = list(out.values())
        for chunk in _chunks(rows):
            sb.table("pending_games").insert(chunk).execute()
        total += len(rows)
        prog("ok", f"pending_games[{mod}]: {len(rows)} files")

    conn.close()
    return {"pending_games": total}


def publish_games(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja les partides (per a la fitxa de jugador) a Supabase. FASE 2."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    import re as _re
    import unicodedata as _ud

    def _nm(s):
        s = "".join(c for c in _ud.normalize("NFD", s or "") if _ud.category(c) != "Mn")
        return " ".join(s.strip().lower().split())

    # Lligues multi-modalitat (4 modalitats / Catalana) vs 3 bandes pures.
    multimod = {3, 7, 9, 13, 18, 22, 25, 27, 31, 33, 35, 37}

    # Signatura de partida d'open → nom de l'open (per etiquetar les INDIVIDUAL).
    open_nom = {
        (r["torneig_id_extern"], r["divisio_id_extern"]): r["nom"]
        for r in conn.execute(
            "SELECT torneig_id_extern, divisio_id_extern, nom FROM torneigs_individuals"
        )
    }
    def _sigkey(p1n, c1, p2n, c2, ent):
        return (frozenset({(_nm(p1n), c1), (_nm(p2n), c2)}), ent)

    open_sig: dict = {}  # key -> (nom_open, {norm_nom: serie})
    try:
        tp_rows = conn.execute("SELECT * FROM torneig_partides").fetchall()
    except sqlite3.OperationalError:
        tp_rows = []
    for r in tp_rows:
        nom = open_nom.get((r["torneig_id_extern"], r["divisio_id_extern"]))
        if not nom:
            continue
        nom = _re.sub(r"\s*-\s*[ÚU]NICA\s*$", "", nom, flags=_re.I).strip()
        key = _sigkey(r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"])
        open_sig[key] = (nom, {_nm(r["player1_nom"]): r["serie1"], _nm(r["player2_nom"]): r["serie2"]})

    copa_sig: dict = {}  # key -> {norm_nom: serie}
    try:
        cp_rows = conn.execute(
            "SELECT local_nom, local_caramboles, local_serie, visitant_nom, "
            "visitant_caramboles, visitant_serie, entrades FROM copa_partides"
        ).fetchall()
    except sqlite3.OperationalError:
        cp_rows = []
    for r in cp_rows:
        key = _sigkey(r["local_nom"], r["local_caramboles"], r["visitant_nom"], r["visitant_caramboles"], r["entrades"])
        copa_sig[key] = {_nm(r["local_nom"]): r["local_serie"], _nm(r["visitant_nom"]): r["visitant_serie"]}

    # Índex de participació: norm(jugador) -> {(nom_torneig, modalitat, temporada)}.
    # Permet etiquetar games INDIVIDUAL quan no hi ha la partida exacta scrapejada:
    # si A i B van participar al mateix torneig (mateixa modalitat+temporada), el
    # joc és d'aquell torneig (van jugar-hi l'un contra l'altre).
    part_idx: dict = {}
    for r in conn.execute(
        """SELECT p.nom pname, ti.nom tnom, m.codi_fcb modc, te.nom season
           FROM torneig_participants tp JOIN torneigs_individuals ti ON ti.id=tp.torneig_id
           JOIN players p ON p.id=tp.player_id JOIN modalitats m ON m.id=ti.modalitat_id
           LEFT JOIN temporades te ON te.id=ti.temporada_id"""
    ):
        tnom = _re.sub(r"\s*-\s*[ÚU]NICA\s*$", "", r["tnom"] or "", flags=_re.I).strip()
        part_idx.setdefault(_nm(r["pname"]), set()).add((tnom, r["modc"], r["season"]))

    def _season_of(ds):
        if not ds:
            return None
        y, mo = int(ds[:4]), int(ds[5:7])
        return f"{y}-{y + 1}" if mo >= 8 else f"{y - 1}-{y}"

    _MODNM = {1: "Tres Bandes", 2: "Lliure", 3: "Quadre 47/2", 4: "Banda", 6: "Quadre 71/2"}
    _CHMODS = ("TRES BANDES", "3 BANDES", "BANDA", "LLIURE", "QUADRE 47/2", "QUADRE 71/2", "QUADRE")

    def _norm_label(label, modc):
        """Unifica etiquetes equivalents (campionats de Catalunya, variants 3B)."""
        if not label or label == "INDIVIDUAL" or label.startswith("Lliga") or label == "COPA":
            return label
        u = label.upper()
        # Opens i altres torneigs propis: només normalitzar "3 BANDES" -> "TRES BANDES".
        if any(k in u for k in ("OPEN", "MEMORIAL", "CIUTAT", "TROFEU", "PROVINCIAL")):
            return label.replace("3 BANDES", "TRES BANDES").replace("3 Bandes", "Tres Bandes")
        # Campionat de Catalunya (per modalitat): unifica totes les variants.
        mn = _MODNM.get(modc)
        if mn and (
            "CAMPIONAT" in u
            or "ABSOLUT" in u
            or "CATALUNYA" in u
            or any(u == m or u.startswith(m + " ") or u.startswith(m + "-") for m in _CHMODS)
        ):
            return f"Camp. Catalunya {mn}"
        return label.replace("3 BANDES", "TRES BANDES")

    def enrich(r):
        """Retorna (etiqueta_competicio, serie1, serie2) enriquint des d'opens/copa."""
        comp, lliga_id = r["competicio"], r["lliga_id"]
        s1, s2 = r["serie_max1"], r["serie_max2"]
        label = comp
        if comp == "LLIGA":
            if lliga_id is not None:
                label = "Lliga 4 Modalitats" if lliga_id in multimod else "Lliga 3 Bandes"
            elif r["modalitat_codi"] != 1:
                # Sense encontre: un joc que NO és de 3 bandes només pot venir
                # de la lliga de 4 modalitats (la lliga 3 bandes només té 3 b).
                label = "Lliga 4 Modalitats"
            else:
                label = "Lliga 3 Bandes"
        elif comp == "INDIVIDUAL":
            hit = open_sig.get(
                _sigkey(r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"])
            )
            # Font primària: el vincle exacte persistit a games.torneig_id
            # (linking.py). Validat localment i consistent amb la BD; substitueix
            # el recàlcul de signatura. La sèrie encara s'enriqueix des de la
            # partida de campionat exacta (open_sig) quan la tenim.
            tnom = r["torneig_nom"]
            if tnom:
                label = _re.sub(r"\s*-\s*[ÚU]NICA\s*$", "", tnom, flags=_re.I).strip()
                if hit:
                    if s1 is None:
                        s1 = hit[1].get(_nm(r["player1_nom"]))
                    if s2 is None:
                        s2 = hit[1].get(_nm(r["player2_nom"]))
            elif hit:
                label = hit[0]
                if s1 is None:
                    s1 = hit[1].get(_nm(r["player1_nom"]))
                if s2 is None:
                    s2 = hit[1].get(_nm(r["player2_nom"]))
            else:
                # Fallback (sense vincle exacte): torneig compartit (mateixa
                # modalitat + temporada). Baixa confiança; només per a partides
                # que el rànquing no va capturar dins de cap campionat scrapejat.
                shared = part_idx.get(_nm(r["player1_nom"]), set()) & part_idx.get(
                    _nm(r["player2_nom"]), set()
                )
                cands = [t for t in shared if t[1] == r["modalitat_codi"]]
                season = _season_of(r["data_partida"])
                if season:
                    sc = [t for t in cands if t[2] == season]
                    if sc:
                        cands = sc
                if cands:
                    label = cands[0][0]
        elif comp == "COPA":
            sm = copa_sig.get(
                _sigkey(r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"])
            )
            if sm:
                if s1 is None:
                    s1 = sm.get(_nm(r["player1_nom"]))
                if s2 is None:
                    s2 = sm.get(_nm(r["player2_nom"]))
        # Guàrdies de sanitat: la sèrie no pot superar les caramboles del jugador;
        # a 3 bandes és impossible superar ~20 (error de parsing si ho fa).
        cap = 20 if r["modalitat_codi"] == 1 else None
        if s1 is not None and ((r["caramboles1"] is not None and s1 > r["caramboles1"]) or (cap and s1 > cap)):
            s1 = None
        if s2 is not None and ((r["caramboles2"] is not None and s2 > r["caramboles2"]) or (cap and s2 > cap)):
            s2 = None
        return _norm_label(label, r["modalitat_codi"]), s1, s2

    games = []
    for r in conn.execute(
        """
        SELECT g.id, g.data_partida, m.codi_fcb AS modalitat_codi,
               comp.nom AS competicio, en.lliga_id AS lliga_id,
               ti.nom AS torneig_nom,
               p1.fcb_id AS player1_fcb_id, p1.nom AS player1_nom,
               g.caramboles1, g.serie_max1,
               p2.fcb_id AS player2_fcb_id, p2.nom AS player2_nom,
               g.caramboles2, g.serie_max2,
               g.entrades, pw.fcb_id AS guanyador_fcb_id
        FROM games g
        JOIN modalitats m ON m.id = g.modalitat_id
        LEFT JOIN competicions comp ON comp.id = g.competicio_id
        LEFT JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
        LEFT JOIN torneigs_individuals ti ON ti.id = g.torneig_id
        JOIN players p1 ON p1.id = g.player1_id
        JOIN players p2 ON p2.id = g.player2_id
        LEFT JOIN players pw ON pw.id = g.guanyador_id
        """
    ):
        label, s1, s2 = enrich(r)
        games.append({
            "id": r["id"], "data_partida": r["data_partida"], "modalitat_codi": r["modalitat_codi"],
            "competicio": label,
            "player1_fcb_id": r["player1_fcb_id"], "player1_nom": _disp(r["player1_nom"]),
            "caramboles1": r["caramboles1"], "serie_max1": s1,
            "player2_fcb_id": r["player2_fcb_id"], "player2_nom": _disp(r["player2_nom"]),
            "caramboles2": r["caramboles2"], "serie_max2": s2,
            "entrades": r["entrades"], "guanyador_fcb_id": r["guanyador_fcb_id"],
        })
    n = _upsert(sb, "games", games, "id", prog)
    conn.close()
    return {"games": n}


def publish_rating_buckets(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Precomputa i puja el rendiment per nivell d'oponent (aranya de la fitxa).

    Franges per quantils + indicadors (índex ponderat, creuament 50%), per a
    **totes les modalitats** (els quantils s'adapten sols a cada escala). La
    lògica viu a `fcbillar.analytics` perquè local (API) i núvol calculin idèntic."""
    from fcbillar.analytics import rating_breakdown

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    fcb_by_pid = {r["id"]: r["fcb_id"] for r in conn.execute("SELECT id, fcb_id FROM players")}
    mods = [r["codi_fcb"] for r in conn.execute("SELECT codi_fcb FROM modalitats ORDER BY codi_fcb")]

    bucket_rows, index_rows = [], []
    for codi in mods:
        data = rating_breakdown(conn, codi, None)
        for pid, prof in data.items():
            fid = fcb_by_pid.get(pid)
            if not fid:
                continue
            for b in prof["buckets"]:
                bucket_rows.append({
                    "player_fcb_id": fid,
                    "modalitat_codi": codi,
                    "bucket": f"b{b['order']}",
                    "bucket_order": b["order"],
                    "label": b["label"],
                    "wins": b["wins"],
                    "losses": b["losses"],
                    "draws": b["draws"],
                })
            index_rows.append({
                "player_fcb_id": fid,
                "modalitat_codi": codi,
                "weighted_index": prof["weighted_index"],
                "crossover": prof["crossover"],
                "total_games": prof["total"],
            })
        prog("ok", f"rating modalitat {codi}: {len(data)} jugadors")
    conn.close()

    sb = get_client()
    # Recalcul complet: esborrem totes les files (totes les modalitats) abans
    # d'inserir perquè l'upsert no deixi franges/índexs orfes.
    sb.table("player_rating_buckets").delete().gt("modalitat_codi", 0).execute()
    n = _upsert(
        sb, "player_rating_buckets", bucket_rows, "player_fcb_id,modalitat_codi,bucket", prog
    )
    sb.table("player_rating_index").delete().gt("modalitat_codi", 0).execute()
    ni = _upsert(
        sb, "player_rating_index", index_rows, "player_fcb_id,modalitat_codi", prog
    )
    return {"player_rating_buckets": n, "player_rating_index": ni}


# Lliga Catalana Tres Bandes = competició/portal lliga_id 36.
LLIGA_3B_ID = 36


def _fetch_official_lliga_standings(
    group_keys: list[tuple[int, int]], prog: Progress
) -> dict[tuple[int, int], list]:
    """Scrapeja la classificació OFICIAL (live) de cada grup de la lliga 36.

    Retorna {(divisio_id, grup_id): [LligaClassificacioRow]}. És la font de
    veritat per a posició + punts (penalitzacions i desempat ja aplicats).
    Robust: si l'scraper no arrenca o un grup falla, l'omet i el caller cau a
    l'ordre calculat des dels encontres per a aquell grup.
    """
    out: dict[tuple[int, int], list] = {}
    try:
        from fcbillar.config import get_settings
        from fcbillar.scraper.client import ScraperClient
        from fcbillar.scraper.parsers import parse_lliga_classificacio
    except Exception as e:  # pragma: no cover - dependència de scraper absent
        prog("warn", f"classificació oficial: import fallit ({e}); s'usa l'ordre calculat")
        return out

    settings = get_settings()
    base = settings.base_url.rstrip("/")
    try:
        with ScraperClient(settings) as cl:
            for div, gid in group_keys:
                url = f"{base}/ca/lligues/classificacio/{LLIGA_3B_ID}/{div}/{gid}"
                try:
                    rows = parse_lliga_classificacio(cl.fetch_html(url))
                except Exception as e:
                    prog("warn", f"classificació oficial {div}/{gid} fallida: {e}")
                    continue
                if rows:
                    out[(div, gid)] = rows
    except Exception as e:
        prog("warn", f"scraper classificació oficial no disponible ({e}); ordre calculat")
    prog("ok", f"classificació oficial: {len(out)}/{len(group_keys)} grups")
    return out


def _match_official_rows(off_rows, stats: dict, equips: dict, repo) -> dict:
    """Casa cada fila oficial amb un equip del grup → {eid: LligaClassificacioRow}.

    Primer per (club_id, lletra); si falla, per club_id únic dins del grup (les
    fases FINAL reasignen la lletra de l'equip, p.ex. "B"→"A"). El club s'obté
    del text oficial via el mateix resolutor (exacte/normalitzat/àlies) que fa
    servir la ingesta d'encontres, de manera que noms com "SANT ADRIÀ" casen
    amb "C.B.SANT ADRIÀ".
    """
    from fcbillar.pipeline import _split_equip_nom

    by_club_lletra: dict[tuple, int] = {}
    by_club: dict[int, list[int]] = {}
    for eid in stats:
        meta = equips.get(eid)
        if not meta:
            continue
        _nom, _fcb, lletra, club_id = meta
        by_club_lletra[(club_id, (lletra or "").upper())] = eid
        by_club.setdefault(club_id, []).append(eid)

    matched: dict[int, object] = {}
    used: set[int] = set()
    for r in off_rows:
        club_nom, lletra = _split_equip_nom(r.equip)
        club_id = repo.resolve_club_id_by_nom(club_nom)
        if club_id is None:
            continue
        eid = by_club_lletra.get((club_id, (lletra or "").upper()))
        if eid is None or eid in used:
            cands = [e for e in by_club.get(club_id, []) if e not in used]
            eid = cands[0] if len(cands) == 1 else None
        if eid is None or eid in used:
            continue
        used.add(eid)
        matched[eid] = r
    return matched


def publish_lliga(
    db_path: Path | None = None,
    on_progress: Progress | None = None,
    use_official: bool = True,
) -> dict[str, int]:
    """Calcula i puja les classificacions de la lliga 3 bandes (temporada actual).

    Les estadístiques de detall (PJ/G/E/P, parcials) es deriven dels encontres,
    però la POSICIÓ i els PUNTS són els de la classificació OFICIAL de la
    federació (`/ca/lligues/classificacio/...`), que ja porta el desempat oficial
    (per parcials) i les penalitzacions federatives —que no es publiquen com a
    fet separat, només es veuen com a menys punts dels que tocarien. Quan un equip
    té menys punts oficials dels esperats per les seves victòries, la diferència
    es desa a `penalitzacio` per marcar la sanció. Si l'scraper no està disponible
    (`use_official=False` o error de xarxa), es cau a l'ordre calculat des dels
    encontres (PM, després parcials a favor), com fa la federació.
    """
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    from fcbillar.db.repository import Repository

    repo = Repository(conn)

    tr = conn.execute("SELECT id FROM temporades ORDER BY nom DESC LIMIT 1").fetchone()
    season_id = tr["id"] if tr else None

    noms = {
        (r["divisio_id"], r["grup_id"]): r["nom"]
        for r in conn.execute(
            "SELECT divisio_id, grup_id, nom FROM lliga_noms WHERE lliga_id = ?",
            (LLIGA_3B_ID,),
        )
    }
    equips = {
        r["id"]: (r["nom"], r["fcb_id"], r["lletra"], r["club_id"])
        for r in conn.execute(
            "SELECT e.id, e.lletra, e.club_id, c.nom, c.fcb_id "
            "FROM equips e JOIN clubs c ON c.id = e.club_id"
        )
    }

    groups = conn.execute(
        """
        SELECT DISTINCT divisio_id, grup_id FROM encontres_lliga
        WHERE lliga_id = ? AND temporada_id = ? AND grup_id <> 0
        """,
        (LLIGA_3B_ID, season_id),
    ).fetchall()

    official: dict[tuple[int, int], list] = {}
    if use_official:
        official = _fetch_official_lliga_standings(
            [(g["divisio_id"], g["grup_id"]) for g in groups], prog
        )

    group_rows: list[dict] = []
    standing_rows: list[dict] = []
    for grp in groups:
        div, gid = grp["divisio_id"], grp["grup_id"]
        group_rows.append({
            "lliga_id": LLIGA_3B_ID, "divisio_id": div, "grup_id": gid,
            "divisio_nom": noms.get((div, 0)), "grup_nom": noms.get((div, gid)),
        })
        enc = conn.execute(
            """
            SELECT equip_local_id AS loc, equip_visitant_id AS vis,
                   p_match_local AS pml, p_match_visitant AS pmv,
                   p_parcials_local AS ppl, p_parcials_visitant AS ppv
            FROM encontres_lliga
            WHERE lliga_id = ? AND divisio_id = ? AND grup_id = ? AND temporada_id = ?
            """,
            (LLIGA_3B_ID, div, gid, season_id),
        ).fetchall()
        stats: dict[int, dict] = {}

        def _s(eid):
            return stats.setdefault(
                eid, {"pj": 0, "g": 0, "e": 0, "p": 0, "pf": 0, "pc": 0, "ppf": 0, "ppc": 0}
            )

        for r in enc:
            pml, pmv = r["pml"], r["pmv"]
            if pml is None or pmv is None:
                continue
            sl, sv = _s(r["loc"]), _s(r["vis"])
            sl["pj"] += 1; sv["pj"] += 1
            sl["pf"] += pml; sl["pc"] += pmv
            sv["pf"] += pmv; sv["pc"] += pml
            ppl, ppv = r["ppl"], r["ppv"]
            if ppl is not None and ppv is not None:
                sl["ppf"] += ppl; sl["ppc"] += ppv
                sv["ppf"] += ppv; sv["ppc"] += ppl
            if pml > pmv:
                sl["g"] += 1; sv["p"] += 1
            elif pml < pmv:
                sv["g"] += 1; sl["p"] += 1
            else:
                sl["e"] += 1; sv["e"] += 1

        # Casa cada equip amb la seva fila oficial (posició + punts de la
        # federació). Els equips sense fila oficial s'ordenen al final per
        # (PM, parcials a favor), el mateix desempat que aplica la federació.
        off_rows = official.get((div, gid))
        matched = _match_official_rows(off_rows, stats, equips, repo) if off_rows else {}

        def _rank_key(kv):
            eid, s = kv
            off = matched.get(eid)
            if off is not None:
                return (0, off.posicio, 0, 0)
            return (1, 0, -(3 * s["g"] + s["e"]), -s["ppf"])

        ranked = sorted(stats.items(), key=_rank_key)
        for pos, (eid, s) in enumerate(ranked, start=1):
            nom, fcb_id, lletra, _club_id = equips.get(eid, ("?", None, "", None))
            # "UNICO" = club amb un sol equip → no es mostra la lletra.
            equip = nom if (lletra or "").strip().upper() in ("", "UNICO") else f"{nom} {lletra}".strip()
            computed_pm = 3 * s["g"] + s["e"]
            off = matched.get(eid)
            punts = off.pm if off is not None else computed_pm
            # Sanció federativa = punts esperats per victòries − punts oficials.
            # Només > 0 és sanció; < 0 vol dir que ens falten resultats (no sanció).
            penal = (
                computed_pm - off.pm
                if off is not None and computed_pm > off.pm
                else None
            )
            standing_rows.append({
                "lliga_id": LLIGA_3B_ID, "divisio_id": div, "grup_id": gid,
                "posicio": pos, "equip": equip, "club_fcb_id": fcb_id,
                "pj": s["pj"], "g": s["g"], "e": s["e"], "p": s["p"],
                "punts": punts, "pf": s["pf"], "pc": s["pc"],
                "penalitzacio": penal,
            })

    counts = {}
    counts["lliga_groups"] = _upsert(
        sb, "lliga_groups", group_rows, "lliga_id,divisio_id,grup_id", prog
    )
    counts["lliga_standings"] = _upsert(
        sb, "lliga_standings", standing_rows, "lliga_id,divisio_id,grup_id,equip", prog
    )
    conn.close()
    return counts


def publish_lliga_standings_hist(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja les classificacions HISTÒRIQUES de lliga (totes les temporades i fases).

    Origen: taula SQLite `lliga_standings_hist`, omplerta per
    `scripts/import_lliga_standings.py`. A diferència de `publish_lliga` (temporada
    actual, calculada des dels encontres), aquí pugem el que s'ha scrapejat tal
    qual, amb el NOM REAL del grup ("FINAL 1a DIVISIÓ"…), perquè l'app germana
    pugui filtrar per fase FINAL i mostrar el podi real per temporada/divisió.
    """
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    try:
        src = conn.execute(
            "SELECT temporada, lliga, divisio, grup, posicio, equip, pm, pp "
            "FROM lliga_standings_hist"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        prog("warn", "lliga_standings_hist no existeix a la BD local; res a publicar")
        return {"lliga_standings_hist": 0}

    # Uniformitza les categories a forma curta ("4ª DIVISIÓ" → "4a", "GRUP A" → "A",
    # "FINAL 4a DIVISIÓ" → "Final"). Dedup defensiu per la nova clau (norm pot
    # col·lapsar variants ortogràfiques al mateix grup/divisió).
    from fcbillar.categories import norm_divisio, norm_grup

    by_pk: dict[tuple, dict] = {}
    for r in src:
        divisio, grup = norm_divisio(r["divisio"]), norm_grup(r["grup"])
        by_pk[(r["temporada"], r["lliga"], divisio, grup, r["equip"])] = {
            "temporada": r["temporada"], "lliga": r["lliga"], "divisio": divisio,
            "grup": grup, "posicio": r["posicio"], "equip": r["equip"],
            "pm": r["pm"], "pp": r["pp"],
        }
    rows = list(by_pk.values())
    n = _upsert(
        sb, "lliga_standings_hist", rows,
        "temporada,lliga,divisio,grup,equip", prog,
    )
    conn.close()
    return {"lliga_standings_hist": n}


def publish_copa(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja les classificacions de la Copa (edició actual) a Supabase. FASE 4."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    ed_row = conn.execute("SELECT MAX(edicio_id) AS m FROM copa_classificacio").fetchone()
    edicio = ed_row["m"] if ed_row else None

    jornades = {
        r["jornada"]: (r["nom"], r["ordre"])
        for r in conn.execute(
            "SELECT jornada, nom, ordre FROM copa_jornades WHERE edicio_id = ?", (edicio,)
        )
    }

    group_rows = [
        {
            "edicio_id": edicio, "jornada": r["jornada"], "grup_id": r["grup_id"],
            "grup_nom": r["grup_nom"],
            "jornada_nom": jornades.get(r["jornada"], (None, None))[0],
            "ordre": jornades.get(r["jornada"], (None, None))[1],
        }
        for r in conn.execute(
            """
            SELECT DISTINCT jornada, grup_id, grup_nom FROM copa_classificacio
            WHERE edicio_id = ?
            """,
            (edicio,),
        )
    ]
    standing_rows = [
        {
            "edicio_id": edicio, "jornada": r["jornada"], "grup_id": r["grup_id"],
            "posicio": r["posicio"], "equip": r["equip"],
            "punts": r["punts"], "parcials": r["parcials"], "mitjana": r["mitjana"],
        }
        for r in conn.execute(
            """
            SELECT jornada, grup_id, posicio, equip, punts, parcials, mitjana
            FROM copa_classificacio WHERE edicio_id = ?
            """,
            (edicio,),
        )
        if r["equip"] and str(r["equip"]).strip() not in ("0", "")
    ]

    counts = {}
    counts["copa_groups"] = _upsert(
        sb, "copa_groups", group_rows, "edicio_id,jornada,grup_id", prog
    )
    counts["copa_standings"] = _upsert(
        sb, "copa_standings", standing_rows, "edicio_id,jornada,grup_id,equip", prog
    )
    conn.close()
    return counts


def publish_opens(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja els opens (torneigs individuals) + classificacions a Supabase. FASE 5."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    # open_id = id intern (únic: torneig_id_extern es repeteix per divisions).
    # `tipus` (open/campionat) es deriva del nom amb el classificador compartit,
    # perquè el frontend filtri per camp i no per heurística de string. El nom es
    # neteja de manera defensiva (sufix redundant) per si la BD no s'ha netejat.
    from fcbillar.categories import short_divisio_inline, unify_modalitat
    from fcbillar.torneig_naming import clean_torneig_nom, torneig_tipus

    def _open_nom(raw: str, tipus: str) -> str:
        # Nom net + divisió curta ("TRES BANDES - 1ª DIVISIÓ" → "TRES BANDES - 1a").
        # Als campionats, a més, s'unifica la modalitat i es treu el prefix
        # "Campionat Catalunya" → "Tres Bandes - 1a".
        nom = short_divisio_inline(clean_torneig_nom(raw))
        return unify_modalitat(nom) if tipus == "campionat" else nom

    opens = []
    for r in conn.execute(
        "SELECT ti.id, ti.nom, ti.temporada_id, te.nom AS temp "
        "FROM torneigs_individuals ti LEFT JOIN temporades te ON te.id = ti.temporada_id"
    ):
        tipus = torneig_tipus(r["nom"])
        opens.append({
            "open_id": r["id"],
            "nom": _open_nom(r["nom"], tipus),
            "tipus": tipus,
            "temporada_id": r["temporada_id"],
            "temporada": r["temp"],
        })
    seen: set[tuple[int, str]] = set()
    classifs = []
    for r in conn.execute(
        """
        SELECT tp.torneig_id AS open_id, tp.posicio,
               p.fcb_id AS player_fcb_id, p.nom AS jugador, tp.club_text AS club,
               tp.partides_jugades AS partides, tp.punts, tp.caramboles, tp.entrades,
               tp.mitjana_general, tp.mitjana_particular, tp.serie_max
        FROM torneig_participants tp
        JOIN players p ON p.id = tp.player_id
        ORDER BY tp.torneig_id, tp.posicio
        """
    ):
        key = (r["open_id"], r["player_fcb_id"])
        if key in seen:
            continue
        seen.add(key)
        classifs.append({
            "open_id": r["open_id"], "posicio": r["posicio"],
            "player_fcb_id": r["player_fcb_id"], "jugador": _disp(r["jugador"]), "club": r["club"],
            "partides": r["partides"], "punts": r["punts"], "caramboles": r["caramboles"],
            "entrades": r["entrades"], "mitjana_general": r["mitjana_general"],
            "mitjana_particular": r["mitjana_particular"], "serie_max": r["serie_max"],
        })

    counts = {}
    counts["opens"] = _upsert(sb, "opens", opens, "open_id", prog)
    counts["open_classifications"] = _upsert(
        sb, "open_classifications", classifs, "open_id,player_fcb_id", prog
    )
    conn.close()
    return counts


def _rank_players(acc: dict) -> list[tuple]:
    """Ordena per (punts desc, mitjana desc) i assigna posició. acc: key->stats."""
    from collections import defaultdict

    groups: dict = defaultdict(list)
    for key, a in acc.items():
        groups[key[:-1]].append((key[-1], a))
    out = []
    for gkey, lst in groups.items():
        ranked = sorted(
            lst,
            key=lambda kv: (kv[1]["punts"], (kv[1]["car"] / kv[1]["ent"]) if kv[1]["ent"] else 0),
            reverse=True,
        )
        for pos, (who, a) in enumerate(ranked, start=1):
            out.append((gkey, pos, who, a))
    return out


def publish_lliga_player_rankings(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Rànquing individual de jugadors per grup de la lliga 3 bandes (punts + mitjana)."""
    import json

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    tr = conn.execute("SELECT id FROM temporades ORDER BY nom DESC LIMIT 1").fetchone()
    season_id = tr["id"] if tr else None
    players = {r["id"]: (r["fcb_id"], r["nom"]) for r in conn.execute("SELECT id, fcb_id, nom FROM players")}
    equip_club = {
        r["id"]: r["nom"]
        for r in conn.execute("SELECT e.id, c.nom FROM equips e JOIN clubs c ON c.id = e.club_id")
    }

    acc: dict = {}
    for r in conn.execute(
        """
        SELECT en.divisio_id AS div, en.grup_id AS grup,
               g.player1_id AS p1, g.player2_id AS p2,
               g.caramboles1 AS c1, g.caramboles2 AS c2, g.entrades AS e,
               g.equip1_id AS eq1, g.equip2_id AS eq2, g.extras_json AS ex
        FROM games g JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
        WHERE en.lliga_id = ? AND en.temporada_id = ? AND g.entrades > 0
        """,
        (LLIGA_3B_ID, season_id),
    ):
        try:
            ex = json.loads(r["ex"] or "{}")
        except (ValueError, TypeError):
            ex = {}
        for pid, car, pu, eq in (
            (r["p1"], r["c1"], ex.get("punts1"), r["eq1"]),
            (r["p2"], r["c2"], ex.get("punts2"), r["eq2"]),
        ):
            a = acc.setdefault((r["div"], r["grup"], pid), {"pj": 0, "punts": 0, "car": 0, "ent": 0, "eq": eq})
            a["pj"] += 1
            a["punts"] += pu or 0
            a["car"] += car or 0
            a["ent"] += r["e"] or 0
            a["eq"] = eq

    rows = []
    for (div, grup), pos, pid, a in _rank_players(acc):
        fcb, nom = players.get(pid, (None, "?"))
        if not fcb:
            continue
        rows.append({
            "lliga_id": LLIGA_3B_ID, "divisio_id": div, "grup_id": grup, "posicio": pos,
            "player_fcb_id": fcb, "jugador": _disp(nom), "club": equip_club.get(a["eq"]),
            "partides": a["pj"], "punts": a["punts"], "caramboles": a["car"], "entrades": a["ent"],
            "mitjana": (a["car"] / a["ent"]) if a["ent"] else None,
        })
    n = _upsert(sb, "lliga_player_rankings", rows, "lliga_id,divisio_id,grup_id,player_fcb_id", prog)
    conn.close()
    return {"lliga_player_rankings": n}


def publish_copa_player_rankings(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Rànquing individual de jugadors per grup de la Copa (punts + mitjana)."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    ed_row = conn.execute("SELECT MAX(edicio_id) AS m FROM copa_classificacio").fetchone()
    edicio = ed_row["m"] if ed_row else None
    name_to_fcb = {r["nom"]: r["fcb_id"] for r in conn.execute("SELECT nom, fcb_id FROM players")}

    # Rànquing de TOTA la competició (no per grup): s'agrega per jugador i es
    # desa amb jornada=0, grup_id=0 com a sentinella de "competició sencera".
    acc: dict = {}
    for r in conn.execute(
        """
        SELECT cp.local_nom AS ln, cp.local_caramboles AS lc, cp.punts_local AS lp,
               cp.visitant_nom AS vn, cp.visitant_caramboles AS vc, cp.punts_visitant AS vp,
               cp.entrades AS e
        FROM copa_partides cp JOIN copa_encontres ce ON ce.id = cp.encontre_copa_id
        WHERE ce.edicio_id = ?
        """,
        (edicio,),
    ):
        if not r["e"]:
            continue
        for nom, car, pu in ((r["ln"], r["lc"], r["lp"]), (r["vn"], r["vc"], r["vp"])):
            if not nom or str(nom).strip() in ("0", ""):
                continue
            a = acc.setdefault(nom, {"pj": 0, "punts": 0, "car": 0, "ent": 0})
            a["pj"] += 1
            a["punts"] += pu or 0
            a["car"] += car or 0
            a["ent"] += r["e"] or 0

    ranked = sorted(
        acc.items(),
        key=lambda kv: (kv[1]["punts"], (kv[1]["car"] / kv[1]["ent"]) if kv[1]["ent"] else 0),
        reverse=True,
    )
    rows = []
    pos = 0
    for nom, a in ranked:
        fcb = name_to_fcb.get(nom)
        if not fcb:
            continue
        pos += 1
        rows.append({
            "edicio_id": edicio, "jornada": 0, "grup_id": 0, "posicio": pos,
            "player_fcb_id": fcb, "jugador": _disp(nom), "club": None,
            "partides": a["pj"], "punts": a["punts"], "caramboles": a["car"], "entrades": a["ent"],
            "mitjana": (a["car"] / a["ent"]) if a["ent"] else None,
        })
    n = _upsert(sb, "copa_player_rankings", rows, "edicio_id,jornada,grup_id,player_fcb_id", prog)
    conn.close()
    return {"copa_player_rankings": n}


def publish_lliga_encontres(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Encontres de lliga 3 bandes (per jornada) + les seves partides individuals."""
    from collections import defaultdict

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    tr = conn.execute("SELECT id FROM temporades ORDER BY nom DESC LIMIT 1").fetchone()
    season_id = tr["id"] if tr else None
    equips = {
        r["id"]: (r["nom"], r["lletra"])
        for r in conn.execute("SELECT e.id, c.nom, e.lletra FROM equips e JOIN clubs c ON c.id = e.club_id")
    }

    def eqname(eid):
        nom, lletra = equips.get(eid, ("?", ""))
        return nom if (lletra or "").strip().upper() in ("", "UNICO") else f"{nom} {lletra}".strip()

    encs = conn.execute(
        """
        SELECT id, divisio_id, grup_id, jornada_id, data,
               equip_local_id, equip_visitant_id, p_match_local, p_match_visitant
        FROM encontres_lliga WHERE lliga_id = ? AND temporada_id = ?
        """,
        (LLIGA_3B_ID, season_id),
    ).fetchall()

    # Ordre de jornada per grup: rang del jornada_id per data mínima.
    jdates: dict = defaultdict(dict)
    for e in encs:
        key = (e["divisio_id"], e["grup_id"])
        cur = jdates[key].get(e["jornada_id"])
        if cur is None or (e["data"] and e["data"] < cur):
            jdates[key][e["jornada_id"]] = e["data"]
    jorder: dict = {}
    for (div, grup), jmap in jdates.items():
        for i, (jid, _) in enumerate(sorted(jmap.items(), key=lambda kv: (kv[1] or "")), start=1):
            jorder[(div, grup, jid)] = i

    enc_rows = [{
        "encontre_id": e["id"], "divisio_id": e["divisio_id"], "grup_id": e["grup_id"],
        "jornada": jorder.get((e["divisio_id"], e["grup_id"], e["jornada_id"])),
        "data": e["data"], "equip_local": eqname(e["equip_local_id"]),
        "equip_visitant": eqname(e["equip_visitant_id"]),
        "gols_local": e["p_match_local"], "gols_visitant": e["p_match_visitant"],
    } for e in encs]

    part_rows = []
    counter: dict = defaultdict(int)
    for r in conn.execute(
        """
        SELECT g.encontre_lliga_id AS eid, m.codi_fcb AS mod,
               p1.nom AS j1, g.caramboles1 AS c1, p2.nom AS j2, g.caramboles2 AS c2, g.entrades AS e
        FROM games g JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
        JOIN modalitats m ON m.id = g.modalitat_id
        JOIN players p1 ON p1.id = g.player1_id JOIN players p2 ON p2.id = g.player2_id
        WHERE en.lliga_id = ? AND en.temporada_id = ?
        ORDER BY g.encontre_lliga_id, m.codi_fcb
        """,
        (LLIGA_3B_ID, season_id),
    ):
        counter[r["eid"]] += 1
        part_rows.append({
            "encontre_id": r["eid"], "ordre": counter[r["eid"]], "modalitat_codi": r["mod"],
            "jugador_local": _disp(r["j1"]), "caramboles_local": r["c1"],
            "jugador_visitant": _disp(r["j2"]), "caramboles_visitant": r["c2"], "entrades": r["e"],
        })

    counts = {}
    counts["lliga_encontres"] = _upsert(sb, "lliga_encontres", enc_rows, "encontre_id", prog)
    counts["lliga_partides"] = _upsert(sb, "lliga_partides", part_rows, "encontre_id,ordre", prog)
    conn.close()
    return counts


def publish_copa_encontres(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Encontres de copa (edició actual) + les seves partides individuals."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    ed = conn.execute("SELECT MAX(edicio_id) AS m FROM copa_encontres").fetchone()["m"]
    enc_rows = [{
        "encontre_id": r["id"], "jornada": r["jornada"], "grup_id": r["grup_id"], "grup_nom": r["grup_nom"],
        "equip_local": r["equip_local"], "equip_visitant": r["equip_visitant"],
        "gols_local": r["p_match_local"], "gols_visitant": r["p_match_visitant"],
    } for r in conn.execute(
        """
        SELECT id, jornada, grup_id, grup_nom, equip_local, equip_visitant,
               p_match_local, p_match_visitant
        FROM copa_encontres WHERE edicio_id = ?
        """, (ed,))
    ]
    part_rows = [{
        "encontre_id": r["encontre_copa_id"], "ordre": r["ordre"],
        "jugador_local": r["local_nom"], "caramboles_local": r["local_caramboles"],
        "jugador_visitant": r["visitant_nom"], "caramboles_visitant": r["visitant_caramboles"],
        "entrades": r["entrades"],
    } for r in conn.execute(
        """
        SELECT cp.encontre_copa_id, cp.ordre, cp.local_nom, cp.local_caramboles,
               cp.visitant_nom, cp.visitant_caramboles, cp.entrades
        FROM copa_partides cp JOIN copa_encontres ce ON ce.id = cp.encontre_copa_id
        WHERE ce.edicio_id = ?
        """, (ed,))
    ]
    counts = {}
    counts["copa_encontres"] = _upsert(sb, "copa_encontres", enc_rows, "encontre_id", prog)
    counts["copa_partides"] = _upsert(sb, "copa_partides", part_rows, "encontre_id,ordre", prog)
    conn.close()
    return counts


def publish_open_partides(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja les partides de grups i eliminatòries, mapejades a l'open_id intern."""
    from collections import defaultdict

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    idmap = {
        (r["torneig_id_extern"], r["divisio_id_extern"]): r["id"]
        for r in conn.execute(
            "SELECT id, torneig_id_extern, divisio_id_extern FROM torneigs_individuals"
        )
    }
    counter: dict = defaultdict(int)
    rows = []
    for r in conn.execute("SELECT * FROM torneig_partides"):
        oid = idmap.get((r["torneig_id_extern"], r["divisio_id_extern"]))
        if oid is None:
            continue
        key = (oid, r["fase_id"])
        counter[key] += 1
        rows.append({
            "open_id": oid, "fase_id": r["fase_id"], "ordre": counter[key],
            "jugador_local": r["player1_nom"], "caramboles_local": r["caramboles1"],
            "jugador_visitant": r["player2_nom"], "caramboles_visitant": r["caramboles2"],
            "entrades": r["entrades"],
        })
    n = _upsert(sb, "open_partides", rows, "open_id,fase_id,ordre", prog)
    conn.close()
    return {"open_partides": n}


def publish_open_ranking(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Rànquing Català d'Opens 3 bandes (Art. XVIII: suma dels 5 millors opens)."""
    from collections import defaultdict

    from fcb_opens.reglament.puntuacio import points_for_position

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    import unicodedata as _ud

    def _nm(s):
        s = "".join(c for c in _ud.normalize("NFD", s or "") if _ud.category(c) != "Mn")
        return " ".join(s.strip().lower().split())

    def _sig(p1, c1, p2, c2, e):
        return (frozenset({(_nm(p1), c1), (_nm(p2), c2)}), e)

    # Un open és del circuit de 3 bandes si diu OPEN i no porta cap altra modalitat
    # (alguns es diuen "OPEN MATARO"/"OPEN COSTA DAURADA", sense "TRES BANDES").
    _no3b = ("QUADRE", "LLIURE", "BANDA", "QUILLES", "ARTISTIC", "BIATHL", "600", "71/2", "47/2")
    open_rows = [
        o
        for o in conn.execute(
            "SELECT id, nom, torneig_id_extern, divisio_id_extern FROM torneigs_individuals"
        ).fetchall()
        if "OPEN" in (o["nom"] or "").upper() and not any(b in (o["nom"] or "").upper() for b in _no3b)
    ]
    if not open_rows:
        conn.close()
        return {"open_ranking": 0}
    open_ids = {o["id"] for o in open_rows}

    # Data de cada partida individual (per signatura) → data de cada open.
    gdate: dict = {}
    for r in conn.execute(
        """
        SELECT g.data_partida d, p1.nom n1, g.caramboles1 c1, p2.nom n2, g.caramboles2 c2, g.entrades e
        FROM games g JOIN competicions comp ON comp.id = g.competicio_id
        JOIN players p1 ON p1.id = g.player1_id JOIN players p2 ON p2.id = g.player2_id
        WHERE comp.nom = 'INDIVIDUAL'
        """
    ):
        gdate[_sig(r["n1"], r["c1"], r["n2"], r["c2"], r["e"])] = r["d"]
    idmap = {
        (r["torneig_id_extern"], r["divisio_id_extern"]): r["id"]
        for r in conn.execute("SELECT id, torneig_id_extern, divisio_id_extern FROM torneigs_individuals")
    }
    open_date: dict = defaultdict(str)
    for r in conn.execute("SELECT * FROM torneig_partides"):
        tid = idmap.get((r["torneig_id_extern"], r["divisio_id_extern"]))
        if tid not in open_ids:
            continue
        d = gdate.get(_sig(r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"]))
        if d and d > open_date[tid]:
            open_date[tid] = d

    import re as _re

    onom = {
        o["id"]: _re.sub(r"\s*-\s*[ÚU]NICA\s*$", "", o["nom"], flags=_re.I).strip() for o in open_rows
    }
    tnom = {
        r["id"]: r["temp"]
        for r in conn.execute(
            "SELECT ti.id, te.nom AS temp FROM torneigs_individuals ti LEFT JOIN temporades te ON te.id = ti.temporada_id"
        )
    }

    # Participants per open
    parts: dict = defaultdict(list)
    ph = ",".join("?" * len(open_ids))
    for r in conn.execute(
        f"""
        SELECT tp.torneig_id AS oid, p.fcb_id, p.nom, tp.posicio, tp.club_text
        FROM torneig_participants tp JOIN players p ON p.id = tp.player_id
        WHERE tp.torneig_id IN ({ph}) AND tp.posicio IS NOT NULL
        """,
        list(open_ids),
    ):
        parts[r["oid"]].append((r["fcb_id"], r["nom"], r["club_text"], r["posicio"]))

    # GENERAL = opens NO femenins (els femenins tenen taula de punts pròpia, pendent).
    # Cronologia: divisio_id_extern (la FCB l'assigna creixent per cada open disputat).
    divid = {o["id"]: o["divisio_id_extern"] for o in open_rows}
    gen_ids = [o["id"] for o in open_rows if "FEMENI" not in (o["nom"] or "").upper()]
    ordered = sorted(gen_ids, key=lambda t: divid.get(t, 0))

    # Desempat #3 (Art. XVIII): mitjana 3 bandes més recent per jugador.
    mitj: dict = {}
    for r in conn.execute(
        """SELECT p.fcb_id, re.mitjana_general FROM ranking_entries re
        JOIN rankings rk ON rk.id = re.ranking_id JOIN players p ON p.id = re.player_id
        JOIN modalitats m ON m.id = rk.modalitat_id WHERE m.codi_fcb = 1 ORDER BY rk.num_seq DESC"""
    ):
        if r["fcb_id"] not in mitj and r["mitjana_general"] is not None:
            mitj[r["fcb_id"]] = r["mitjana_general"]

    def _ddet(oid, pos, pp):
        return {"open": onom.get(oid), "temp": tnom.get(oid), "data": open_date.get(oid) or None, "pos": pos, "punts": pp}

    # Un snapshot per ronda: finestra mòbil dels últims 5 opens fins a la ronda i.
    all_rows = []
    for i in range(1, len(ordered) + 1):
        window = ordered[max(0, i - 5):i]
        pp_player: dict = defaultdict(dict)  # fcb -> {oid: (pos, pts)}
        info: dict = {}  # fcb -> (nom, club)
        for oid in window:
            for fcb, nom, club, pos in parts.get(oid, []):
                pp_player[fcb][oid] = (pos, points_for_position(pos))
                info[fcb] = (nom, club)
        last_open = ordered[i - 1]
        rows_r = []
        for fcb, (nom, club) in info.items():
            det, total, njug, maxs = [], 0, 0, 0
            for oid in window:  # tots els opens de la finestra (0 si no hi participa)
                if oid in pp_player[fcb]:
                    pos, pp = pp_player[fcb][oid]
                    det.append(_ddet(oid, pos, pp))
                    total += pp
                    njug += 1
                    maxs = max(maxs, pp)
                else:
                    det.append(_ddet(oid, None, 0))
            rows_r.append((fcb, nom, club, total, njug, det, maxs))
        # Desempat: punts ↓, millor open ↓, mitjana ↓, nom ↑
        rows_r.sort(key=lambda x: (-x[3], -x[6], -mitj.get(x[0], 0.0), x[1] or ""))
        for posicio, (fcb, nom, club, total, njug, det, maxs) in enumerate(rows_r, start=1):
            all_rows.append({
                "genere": "general", "ronda": i, "ronda_nom": onom.get(last_open),
                "ronda_data": open_date.get(last_open) or None, "ronda_temp": tnom.get(last_open),
                "posicio": posicio, "player_fcb_id": fcb, "jugador": _disp(nom),
                "club": club, "opens_jugats": njug, "punts": total,
                "detall": det, "provisional": False,
            })
    # Penalitzacions del PDF oficial (Art. IV): -20 no presentat injustificat,
    # 0 justificat, None no inscrit. Només a la ronda actual (el PDF és la finestra vigent).
    #
    # La FCB publica la CLASSIFICACIÓ final d'un open abans de refrescar el PDF del
    # RÀNQUING. Hi ha doncs una finestra de temps en què la nostra ronda vigent ja
    # inclou l'open més recent (amb els punts de la seva classificació final) però el
    # PDF encara llista la finestra anterior. Com que el PDF té sempre 5 columnes,
    # aplicar-lo POSICIONALMENT desplaçaria totes les columnes (l'open nou robaria els
    # punts del darrer del PDF). Per detectar-ho casem les columnes del PDF amb la
    # nostra finestra per paraula-clau de seu (map_pdf_columns_to_window): el PDF està
    # AL DIA només si totes les columnes casen amb la mateixa posició de la finestra
    # (mapping identitat). Si no, NO apliquem el PDF i marquem la ronda PROVISIONAL.
    max_ronda = len(ordered)
    window = ordered[max(0, max_ronda - 5):max_ronda]
    prov_latest = True
    try:
        import httpx
        from fcb_opens.reglament.open_match import map_pdf_columns_to_window
        from fcb_opens.scraper.official_pdf import OFFICIAL_RANKING_URL, parse_official_ranking

        off = parse_official_ranking(
            httpx.get(OFFICIAL_RANKING_URL, timeout=30, follow_redirects=True).content,
            source_url=OFFICIAL_RANKING_URL,
        )
        window_names = [onom.get(oid, "") for oid in window]
        colmap = map_pdf_columns_to_window([o.full_name for o in off.opens], window_names)
        identity = {i: i for i in range(len(window))}
        pdf_is_current = len(off.opens) == len(window) and colmap == identity
        window_complete = all(parts.get(oid) for oid in window)
        if max_ronda and window_complete and pdf_is_current:  # alineació posicional segura
            pdf = {_nm(e.display_name): (e.total_points, tuple(e.points_per_open)) for e in off.entries}
            for row in all_rows:
                if row["ronda"] != max_ronda:
                    continue
                hit = pdf.get(_nm(row["jugador"]))
                if not hit:
                    continue
                total, ppo = hit
                for i, d in enumerate(row["detall"]):
                    pts = ppo[i] if i < len(ppo) else None
                    if pts is None:  # no inscrit
                        d["punts"], d["pos"] = 0, None
                    else:
                        d["punts"] = pts
                        if pts < 0:  # penalització injustificada
                            d["pos"], d["penal"] = None, True
                        elif pts == 0:  # absència justificada
                            d["pos"], d["absent"] = None, True
                row["punts"] = total
                row["opens_jugats"] = sum(1 for v in ppo if v is not None and v > 0)
            latest = [r for r in all_rows if r["ronda"] == max_ronda]
            latest.sort(key=lambda r: (-r["punts"], -mitj.get(r["player_fcb_id"], 0.0), r["jugador"] or ""))
            for posicio, r in enumerate(latest, start=1):
                r["posicio"] = posicio
            prov_latest = False
            prog("ok", f"penalitzacions oficials aplicades ({len(off.entries)} entrades PDF)")
        elif not window_complete:
            prog("ok", "ronda provisional: l'open més recent encara no té classificació final")
        else:
            prog("ok", "ronda provisional: el rànquing oficial encara no inclou l'open més recent")
    except Exception as exc:  # noqa: BLE001
        prog("warn", f"penalitzacions: PDF no aplicat ({exc}); ronda marcada provisional")

    # Marca la ronda vigent com a PROVISIONAL (punts des de la classificació final,
    # pendents que la federació actualitzi el rànquing oficial) i n'assenyala l'open
    # més recent al desglossament perquè el frontend hi pugui pintar "(prov.)".
    if prov_latest and max_ronda:
        for row in all_rows:
            if row["ronda"] != max_ronda:
                continue
            row["provisional"] = True
            det = row.get("detall") or []
            if det and det[-1].get("pos") is not None:
                det[-1]["prov"] = True

    n = _upsert(sb, "open_ranking", all_rows, "genere,ronda,player_fcb_id", prog)
    conn.close()
    return {"open_ranking": n}


def publish_open_ranking_femeni(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Rànquing del Circuit Català Tres Bandes Femení (genere='femeni').

    Independent del general: proves femenines (Campionat + Opens) amb taula de
    punts pròpia (Art. XVI) i finestra de 5 proves (Art. XVII). Vegeu
    `fcbillar.opens_femeni`."""
    from fcbillar.opens_femeni import femeni_ranking_rows

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = femeni_ranking_rows(conn)
    conn.close()
    for r in rows:
        r["jugador"] = _disp(r["jugador"])
        r.setdefault("provisional", False)
    if not rows:
        prog("ok", "open_ranking (femeni): 0 files")
        return {"open_ranking_femeni": 0}
    sb = get_client()
    n = _upsert(sb, "open_ranking", rows, "genere,ronda,player_fcb_id", prog)
    return {"open_ranking_femeni": n}


def _date_dist(a: str | None, b: str | None) -> int:
    """Distància en dies entre dues dates ISO; gran si alguna és buida/dolenta."""
    from datetime import date

    def _p(s: str | None):
        try:
            y, m, d = str(s).split("-")[:3]
            return date(int(y), int(m), int(d))
        except Exception:  # noqa: BLE001
            return None

    da, db = _p(a), _p(b)
    return abs((da - db).days) if (da and db) else 10**6


def publish_estadistiques_computa(
    db_path: Path | None = None,
    on_progress: Progress | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Marca `public.partides.computa` i `computa_prox` (app Estadístiques).

    Per a cada jugador seguit (`EST_USERS`) i modalitat (`EST_MOD_BY_FCB`) escriu DOS
    flags, casant cada partida oficial amb la d'Estadístiques per signatura (caramboles
    propis, del rival, entrades) + data més propera (les dates d'Estadístiques estan
    entrades a mà i poden anar desplaçades):

    - `computa`: la finestra OFICIAL vigent (`ranking_game_links` del darrer rànquing).
    - `computa_prox`: la finestra PROJECTADA del PROPER rànquing (les 15 que computaran
      després de l'actualització) = els games existents que hi resten
      (`ranking_provisional.window_game_ids`) + les partides pendents encara no
      publicades (`pending_games`). Sense partides pendents, coincideix amb `computa`.

    Reescriu els dos flags sencers a cada execució (idempotent). Amb `dry_run=True`
    només informa, no escriu.
    """
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    pub = get_public_client()  # cal per llegir partides fins i tot en dry-run
    sb = get_client()  # schema fcbillar: ranking_provisional + pending_games

    def _sigs_for_gids(the_fcb: str, gids: list[str]) -> list[tuple]:
        """Signatures (co, copp, e, data) dels games locals de `gids`, vistos des de
        `the_fcb` (per casar la finestra projectada amb les partides d'Estadístiques)."""
        if not gids:
            return []
        ph = ",".join("?" * len(gids))
        out: list[tuple] = []
        for g in conn.execute(
            f"""SELECT CASE WHEN p1.fcb_id = ? THEN g.caramboles1 ELSE g.caramboles2 END co,
                       CASE WHEN p1.fcb_id = ? THEN g.caramboles2 ELSE g.caramboles1 END copp,
                       g.entrades e, g.data_partida d
                FROM games g JOIN players p1 ON p1.id = g.player1_id
                WHERE g.id IN ({ph})""",
            (the_fcb, the_fcb, *gids),
        ):
            if g["co"] is not None and g["copp"] is not None and g["e"]:
                out.append((g["co"], g["copp"], g["e"], g["d"]))
        return out

    def _match_window(by_sig: dict[tuple, list[dict]], items: list[tuple]) -> list:
        """Casa una finestra (llista de (co, copp, e, data|None)) amb les partides
        d'Estadístiques, bijectiu, desempatant per data més propera. Torna els ids
        casats. `used` és propi de la crida (les finestres actual/propera es casen de
        forma independent: una partida pot ser d'ambdues)."""
        used: set = set()
        matched: list = []
        for co, copp, e, d in items:
            cand = [p for p in by_sig.get((co, copp, e), []) if p["id"] not in used]
            if not cand:
                continue
            if len(cand) > 1:
                cand.sort(key=lambda p: _date_dist(p.get("data"), d))
            used.add(cand[0]["id"])
            matched.append(cand[0]["id"])
        return matched

    total_true = 0
    total_prox = 0
    total_unmatched = 0
    for est_uid, fcb_id in EST_USERS.items():
        for codi_fcb, est_mod in EST_MOD_BY_FCB.items():
            rk = conn.execute(
                """SELECT r.id, r.num_seq FROM rankings r JOIN modalitats m ON m.id = r.modalitat_id
                   WHERE m.codi_fcb = ? ORDER BY r.num_seq DESC LIMIT 1""",
                (codi_fcb,),
            ).fetchone()
            # Finestra OFICIAL vigent (games que computen al darrer rànquing).
            window: list[tuple[int, int, int, str]] = []
            if rk is not None:
                for g in conn.execute(
                    """SELECT CASE WHEN p1.fcb_id = ? THEN g.caramboles1 ELSE g.caramboles2 END co,
                              CASE WHEN p1.fcb_id = ? THEN g.caramboles2 ELSE g.caramboles1 END copp,
                              g.entrades e, g.data_partida d
                       FROM ranking_game_links l JOIN games g ON g.id = l.game_id
                       JOIN players p1 ON p1.id = g.player1_id
                       JOIN players p2 ON p2.id = g.player2_id
                       JOIN players po ON po.id = l.player_id_origen
                       WHERE l.ranking_id = ? AND po.fcb_id = ?""",
                    (fcb_id, fcb_id, rk["id"], fcb_id),
                ):
                    if g["co"] is not None and g["copp"] is not None and g["e"]:
                        window.append((g["co"], g["copp"], g["e"], g["d"]))

            # Finestra PROJECTADA del proper rànquing: games que hi resten
            # (ranking_provisional.window_game_ids) + partides pendents (pending_games).
            # Sense fila a ranking_provisional (cap partida nova) → igual que l'actual.
            try:
                rp = (
                    sb.table("ranking_provisional")
                    .select("window_game_ids")
                    .eq("player_fcb_id", fcb_id)
                    .eq("modalitat_codi", codi_fcb)
                    .execute()
                    .data
                )
            except Exception:  # noqa: BLE001
                rp = None
            if rp:
                prox = _sigs_for_gids(fcb_id, rp[0].get("window_game_ids") or [])
                try:
                    pend = (
                        sb.table("pending_games")
                        .select("caramboles,caramboles_opp,entrades")
                        .eq("player_fcb_id", fcb_id)
                        .eq("modalitat_codi", codi_fcb)
                        .execute()
                        .data
                        or []
                    )
                except Exception:  # noqa: BLE001
                    pend = []
                for pr in pend:
                    if (
                        pr.get("caramboles") is not None
                        and pr.get("caramboles_opp") is not None
                        and pr.get("entrades")
                    ):
                        prox.append(
                            (pr["caramboles"], pr["caramboles_opp"], pr["entrades"], None)
                        )
            else:
                prox = list(window)

            rows = (
                pub.table("partides")
                .select("id,caramboles,caramboles_oponent,entrades,data")
                .eq("usuari_id", est_uid)
                .eq("modalitat_id", est_mod)
                .execute()
                .data
                or []
            )
            if not rows:
                continue

            # casa cada partida de la finestra amb una d'Estadístiques (bijectiu)
            by_sig: dict[tuple, list[dict]] = {}
            for p in rows:
                by_sig.setdefault(
                    (p["caramboles"], p["caramboles_oponent"], p["entrades"]), []
                ).append(p)
            matched = _match_window(by_sig, window)
            matched_prox = _match_window(by_sig, prox)
            unmatched = len(window) - len(matched)

            total_true += len(matched)
            total_prox += len(matched_prox)
            total_unmatched += unmatched
            prog(
                "ok",
                f"computa[u{est_uid}/mod{codi_fcb}]: oficial={len(window)}→{len(matched)} "
                f"proper={len(prox)}→{len(matched_prox)} sense_match={unmatched} "
                f"(de {len(rows)} partides)" + ("  [DRY]" if dry_run else ""),
            )
            if dry_run:
                continue

            font = f"fcbillar:rk{rk['id']}" if rk is not None else None
            # reset a false tot el conjunt usuari+modalitat, després marca les casades
            pub.table("partides").update(
                {
                    "computa": False,
                    "computa_font": None,
                    "computa_prox": False,
                    "computa_prox_font": None,
                }
            ).eq("usuari_id", est_uid).eq("modalitat_id", est_mod).execute()
            for chunk in _chunks([{"id": i} for i in matched]):
                ids = [r["id"] for r in chunk]
                pub.table("partides").update(
                    {"computa": True, "computa_font": font}
                ).in_("id", ids).execute()
            for chunk in _chunks([{"id": i} for i in matched_prox]):
                ids = [r["id"] for r in chunk]
                pub.table("partides").update(
                    {"computa_prox": True, "computa_prox_font": font}
                ).in_("id", ids).execute()

    conn.close()
    return {
        "estadistiques_computa": total_true,
        "estadistiques_computa_prox": total_prox,
        "estadistiques_sense_match": total_unmatched,
    }


def publish_estadistiques_fitxa(
    on_progress: Progress | None = None, *, dry_run: bool = False
) -> dict[str, int]:
    """Publica a `public.estadistiques_fitxa` el resum de la fitxa federativa de 3
    Bandes de cada jugador seguit (`EST_USERS`), perquè l'app Estadístiques mostri
    els MATEIXOS indicadors que la fitxa de FCBillar (consistents, del càlcul oficial;
    no recalculats a c3b):

      - `ranking`   : posició i mitjana OFICIAL i PROVISIONAL (`ranking_provisional`).
      - `opens`     : posició i punts al Rànquing d'Opens 3B + millor posició
                      històrica (`open_ranking`) i millor resultat en un open
                      (`open_classifications`).
      - `radar`     : rendiment per nivell d'oponent (`player_rating_buckets` +
                      `player_rating_index`).
      - `palmares`  : podis (1r-3r) a opens/campionats (`open_classifications`+`opens`).

    Escriu un únic JSON per `usuari_id` (upsert idempotent). Amb `dry_run=True` només
    informa. Modalitat: 3 Bandes (codi_fcb 1)."""
    from datetime import datetime, timezone

    prog: Progress = on_progress or (lambda level, msg: None)
    sb = get_client()  # schema fcbillar
    pub = get_public_client()  # schema public (app Estadístiques)
    fetched_at = datetime.now(timezone.utc).isoformat()
    MOD = 1  # 3 Bandes

    # Mapa num_seq → (any, mes) del rànquing 3B i fites de temporada (agost-juliol),
    # per calcular la posició d'INICI de temporada i la del club (compartit).
    rk_dates = sb.table("rankings").select("num_seq,mes_pub,any_pub").execute().data or []
    seqdate: dict[int, tuple[int, int]] = {}
    for r in rk_dates:
        if r.get("any_pub") is not None and r.get("mes_pub") is not None:
            seqdate[r["num_seq"]] = (r["any_pub"], r["mes_pub"])
    latest_seq = max(seqdate) if seqdate else None

    def _in_season(d: tuple[int, int], start_year: int) -> bool:
        return (d[0] == start_year and d[1] >= 8) or (d[0] == start_year + 1 and d[1] <= 7)

    def _first_seq(start_year: int) -> int | None:
        c = [(s, d) for s, d in seqdate.items() if _in_season(d, start_year)]
        return min(c, key=lambda x: (x[1][0], x[1][1], x[0]))[0] if c else None

    def _last_seq(start_year: int) -> int | None:
        c = [(s, d) for s, d in seqdate.items() if _in_season(d, start_year)]
        return max(c, key=lambda x: (x[1][0], x[1][1], x[0]))[0] if c else None

    # Any d'inici de la temporada en curs, derivat del darrer rànquing publicat.
    cur_year = None
    if latest_seq is not None:
        a, m = seqdate[latest_seq]
        cur_year = a if m >= 8 else a - 1
    seq_ini_cur = _first_seq(cur_year) if cur_year is not None else None
    seq_last_cur = latest_seq
    seq_last_prev = _last_seq(cur_year - 1) if cur_year is not None else None

    def _club_position(the_fcb: str, temporada: str, num_seq: int | None) -> dict | None:
        """Posició del jugador dins del rànquing 3B dels membres del seu CLUB ACTUAL
        (taula `players.club_fcb_id`, tot el planter federat: inclou els qui aquest
        any no han jugat però segueixen al club, i tots els equips A/B/C), rankejats
        per mitjana al rànquing `num_seq`. NO usem `player_clubs` (només recull els qui
        han jugat la lliga → infravalora). Torna {nom, temporada, posicio, total}."""
        if not temporada or num_seq is None:
            return None
        p = (
            sb.table("players").select("club_fcb_id")
            .eq("fcb_id", the_fcb).execute().data
        )
        club = p[0].get("club_fcb_id") if p else None
        if not club:
            return None
        members = (
            sb.table("players").select("fcb_id").eq("club_fcb_id", club).execute().data or []
        )
        ids = [m["fcb_id"] for m in members]
        if not ids:
            return None
        ent = (
            sb.table("ranking_entries").select("player_fcb_id,mitjana_general")
            .eq("modalitat_codi", MOD).eq("num_seq", num_seq)
            .in_("player_fcb_id", ids).execute().data or []
        )
        ranked = sorted(
            (e for e in ent if e.get("mitjana_general") is not None),
            key=lambda e: -e["mitjana_general"],
        )
        pos = next((i for i, e in enumerate(ranked, 1) if e["player_fcb_id"] == the_fcb), None)
        if pos is None:
            return None
        return {"nom": club, "temporada": temporada, "posicio": pos, "total": len(ranked)}

    temp_cur = f"{cur_year}-{cur_year + 1}" if cur_year is not None else None
    temp_prev = f"{cur_year - 1}-{cur_year}" if cur_year is not None else None

    rows: list[dict] = []
    for est_uid, fcb_id in EST_USERS.items():
        # Rànquing oficial + provisional (proper).
        rp = (
            sb.table("ranking_provisional")
            .select(
                "posicio_oficial,mitjana_oficial,posicio_provisional,"
                "mitjana_provisional,partides_post"
            )
            .eq("player_fcb_id", fcb_id)
            .eq("modalitat_codi", MOD)
            .execute()
            .data
        )
        ranking = dict(rp[0]) if rp else None
        # Millor posició i millor mitjana històriques al rànquing 3B, APARELLADES:
        # de la millor posició en guardem la mitjana d'aquell moment, i de la millor
        # mitjana la posició que donava (de tot l'historial d'`ranking_entries`).
        if ranking is not None:
            hist = (
                sb.table("ranking_entries")
                .select("num_seq,posicio,mitjana_general")
                .eq("player_fcb_id", fcb_id)
                .eq("modalitat_codi", MOD)
                .execute()
                .data
                or []
            )
            valid = [
                h for h in hist
                if h.get("posicio") is not None and h.get("mitjana_general") is not None
            ]
            if valid:
                best_pos = min(valid, key=lambda h: h["posicio"])
                best_mj = max(valid, key=lambda h: h["mitjana_general"])
                ranking["millor_posicio"] = best_pos["posicio"]
                ranking["millor_posicio_mitjana"] = best_pos["mitjana_general"]
                ranking["millor_mitjana"] = best_mj["mitjana_general"]
                ranking["millor_mitjana_posicio"] = best_mj["posicio"]
            # Posició a l'INICI de la temporada en curs (primer rànquing de la temporada).
            if seq_ini_cur is not None:
                pos_by_seq = {
                    h["num_seq"]: h["posicio"]
                    for h in hist
                    if h.get("num_seq") is not None and h.get("posicio") is not None
                }
                ranking["posicio_inici_temporada"] = pos_by_seq.get(seq_ini_cur)

        # Rànquing d'Opens 3B (general): darrera ronda + millor posició històrica.
        orr = (
            sb.table("open_ranking")
            .select("ronda,posicio,punts")
            .eq("player_fcb_id", fcb_id)
            .eq("genere", "general")
            .execute()
            .data
            or []
        )
        opens = None
        if orr:
            latest = max(orr, key=lambda r: r["ronda"])
            best_pos = min(
                (r["posicio"] for r in orr if r["posicio"] is not None), default=None
            )
            oc_all = (
                sb.table("open_classifications")
                .select("open_id,posicio")
                .eq("player_fcb_id", fcb_id)
                .execute()
                .data
                or []
            )
            oc_valid = [c for c in oc_all if c.get("posicio") is not None]
            best_open = best_open_nom = None
            if oc_valid:
                best_row = min(oc_valid, key=lambda c: c["posicio"])
                best_open = best_row["posicio"]
                om = (
                    sb.table("opens")
                    .select("nom")
                    .eq("open_id", best_row["open_id"])
                    .execute()
                    .data
                )
                if om:
                    # Nom net: treu el sufix de modalitat (" - TRES BANDES", etc.).
                    import re as _re

                    best_open_nom = _re.sub(
                        r"\s*-\s*(TRES BANDES|3 BANDES|LLIURE|BANDA|QUADRE[^-]*)\s*$",
                        "",
                        (om[0].get("nom") or "").strip(),
                        flags=_re.IGNORECASE,
                    ).strip()
            opens = {
                "posicio": latest["posicio"],
                "punts": latest["punts"],
                "millor_posicio": best_pos,
                "millor_en_open": best_open,
                "millor_en_open_nom": best_open_nom,
            }

        # Radar: rendiment per nivell d'oponent (trams de mitjana del rival).
        rb = (
            sb.table("player_rating_buckets")
            .select("bucket_order,label,wins,losses,draws")
            .eq("player_fcb_id", fcb_id)
            .eq("modalitat_codi", MOD)
            .order("bucket_order")
            .execute()
            .data
            or []
        )
        ri = (
            sb.table("player_rating_index")
            .select("weighted_index,crossover,total_games")
            .eq("player_fcb_id", fcb_id)
            .eq("modalitat_codi", MOD)
            .execute()
            .data
        )
        radar = {"buckets": rb, "index": ri[0] if ri else None} if rb else None

        # Palmarès: podis (1r-3r) a opens/campionats.
        podiums = (
            sb.table("open_classifications")
            .select("open_id,posicio,club")
            .eq("player_fcb_id", fcb_id)
            .gte("posicio", 1)
            .lte("posicio", 3)
            .execute()
            .data
            or []
        )
        palmares: list[dict] = []
        if podiums:
            open_ids = list({p["open_id"] for p in podiums})
            meta = (
                sb.table("opens")
                .select("open_id,nom,temporada")
                .in_("open_id", open_ids)
                .execute()
                .data
                or []
            )
            by_id = {o["open_id"]: o for o in meta}
            for p in sorted(podiums, key=lambda x: x["posicio"]):
                o = by_id.get(p["open_id"])
                if not o:
                    continue
                nom = (o.get("nom") or "").strip()
                up = nom.upper()
                tipus = (
                    "open"
                    if "OPEN" in up
                    else ("campionat" if "CAMPIONAT" in up or "CATALUNYA" in up else "torneig")
                )
                palmares.append(
                    {
                        "nom": nom,
                        "temporada": o.get("temporada") or "",
                        "posicio": p["posicio"],
                        "tipus": tipus,
                    }
                )

        # Posició dins del rànquing del club de cada temporada (per mitjana). La
        # temporada actual pren el rànquing vigent; l'anterior, el darrer de la seva.
        club_actual = _club_position(fcb_id, temp_cur, seq_last_cur) if temp_cur else None
        club_anterior = _club_position(fcb_id, temp_prev, seq_last_prev) if temp_prev else None

        payload = {
            "fcb_id": fcb_id,
            "modalitat": "3 Bandes",
            "ranking": ranking,
            "opens": opens,
            "radar": radar,
            "palmares": palmares,
            "club_actual": club_actual,
            "club_anterior": club_anterior,
        }
        rows.append(
            {"usuari_id": est_uid, "payload_json": payload, "updated_at": fetched_at}
        )
        prog(
            "ok",
            f"fitxa u{est_uid} (fcb {fcb_id}): rànquing={'sí' if ranking else 'no'} "
            f"opens={'sí' if opens else 'no'} radar={len(rb)} trams "
            f"palmarès={len(palmares)}" + ("  [DRY]" if dry_run else ""),
        )

    if not dry_run and rows:
        pub.table("estadistiques_fitxa").upsert(rows, on_conflict="usuari_id").execute()
    return {"estadistiques_fitxa": len(rows)}


def publish_player_clubs(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Històric de clubs per jugador i temporada (de les classificacions d'opens)."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    best: dict = {}  # (fcb, temp) -> (club, n)
    for r in conn.execute(
        """
        SELECT p.fcb_id AS fcb, te.nom AS temp, tp.club_text AS club, COUNT(*) AS n
        FROM torneig_participants tp
        JOIN torneigs_individuals ti ON ti.id = tp.torneig_id
        JOIN temporades te ON te.id = ti.temporada_id
        JOIN players p ON p.id = tp.player_id
        WHERE p.fcb_id NOT LIKE 'name:%' AND tp.club_text IS NOT NULL AND TRIM(tp.club_text) <> ''
        GROUP BY p.fcb_id, te.nom, tp.club_text
        """
    ):
        key = (r["fcb"], r["temp"])
        if key not in best or r["n"] > best[key][1]:
            best[key] = (r["club"], r["n"])

    # Clubs de lliga (Catalana): omplen les temporades sense dades d'opens.
    import re as _re

    lliga: dict = {}  # (fcb, temp) -> (club, n)
    try:
        for r in conn.execute(
            """
            SELECT p.fcb_id AS fcb, lpc.temporada AS temp, lpc.club AS club, COUNT(*) AS n
            FROM lliga_player_clubs lpc JOIN players p ON p.id = lpc.player_id
            WHERE p.fcb_id NOT LIKE 'name:%' AND lpc.club IS NOT NULL AND TRIM(lpc.club) <> ''
            GROUP BY p.fcb_id, lpc.temporada, lpc.club
            """
        ):
            key = (r["fcb"], r["temp"])
            club = _re.sub(r"\.\s+", ".", r["club"])  # "C.B. LLINARS" → "C.B.LLINARS"
            if key not in lliga or r["n"] > lliga[key][1]:
                lliga[key] = (club, r["n"])
    except sqlite3.OperationalError:
        pass
    conn.close()

    rows = [
        {
            "player_fcb_id": fcb,
            "temporada": temp,
            "club": best[(fcb, temp)][0] if (fcb, temp) in best else lliga[(fcb, temp)][0],
        }
        for (fcb, temp) in set(best) | set(lliga)
    ]

    # Canonicalitza els noms de club: neteja (Descansa/sufixos/codis/AMISTAT),
    # agrupa pel nucli i aplica el mapping manual de clubs_list.txt.
    from collections import Counter
    from pathlib import Path as _Path

    def _clean_club(name):
        n = name or ""
        n = _re.sub(r"[“”‘’]", '"', n)
        n = _re.sub(r"\s+Descansa\s+.*$", "", n, flags=_re.I)
        n = _re.sub(r"\(\s*AMISTAT\s*\)", "", n, flags=_re.I)
        n = _re.sub(r"^\d+\s*", "", n)  # codi inicial "01 "
        n = _re.sub(r'\s*"[A-Z]"', "", n)  # sufix d'equip "A"
        n = _re.sub(r"\s+[A-D]$", "", n)  # sufix d'equip lletra final
        n = _re.sub(r"\.\s+", ".", n)  # "C.B. X" → "C.B.X"
        return n.strip()

    def _club_key(name):
        n = _clean_club(name).upper()
        n = _re.sub(r"^([A-Z]\.)+", "", n)  # treu prefix d'inicials (C.B., S.B.F., ...)
        return _re.sub(r"[^A-Z0-9]", "", n)  # nucli

    keycount: dict = {}
    for r in rows:
        cl = _clean_club(r["club"])
        if cl:
            keycount.setdefault(_club_key(r["club"]), Counter())[cl] += 1
    canon = {}
    for k, cnt in keycount.items():
        prefixed = {nm: c for nm, c in cnt.items() if _re.match(r"^[A-Z]\.", nm)}
        pool = prefixed or dict(cnt)
        canon[k] = max(pool.items(), key=lambda x: x[1])[0]

    # Mapping manual (variant = nom bo), resolt transitivament.
    usermap: dict = {}
    mapf = _Path(__file__).resolve().parents[2] / "clubs_list.txt"
    if mapf.exists():
        for line in mapf.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                left, right = line.split("=", 1)
                if left.strip() and right.strip():
                    usermap[left.strip()] = right.strip()

    def _resolve(name):
        seen = set()
        while name in usermap and name not in seen and usermap[name] != name:
            seen.add(name)
            name = usermap[name]
        return name

    # Dedueix la resta: agrupa per nucli SENSE accents ni sufix "zona N" i tria
    # la millor forma (target manual > amb prefix > més accentuada).
    import unicodedata as _ud2

    def _noacc(s):
        return "".join(c for c in _ud2.normalize("NFD", s) if not _ud2.combining(c))

    def _naccents(s):
        return sum(1 for c in _ud2.normalize("NFD", s) if _ud2.combining(c))

    def _smart(name):
        n = _noacc(_clean_club(name)).upper()
        n = _re.sub(r"\b(ZONA\s*\d+|Z\d+)\b", "", n)
        n = _re.sub(r"^([A-Z]\.)+", "", n)
        return _re.sub(r"[^A-Z0-9]", "", n)

    targets = set(usermap.values())
    allc = set(canon.values())
    inter = {c: _resolve(c) for c in allc}
    grp: dict = {}
    for c in allc:
        grp.setdefault(_smart(inter[c]), []).append(inter[c])
    bestof = {}
    for k, names in grp.items():
        bestof[k] = max(
            set(names),
            key=lambda nm: (nm in targets, bool(_re.match(r"^[A-Z]\.", nm)), _naccents(nm), nm),
        )
    final = {c: bestof[_smart(inter[c])] for c in allc}

    for r in rows:
        mc = canon.get(_club_key(r["club"]), _clean_club(r["club"]))
        r["club"] = final.get(mc, _resolve(mc))

    # Filtra els "no club" (Cap / Independent / buit).
    _noclub = {"CAP", "INDEPENDENT", "INDEPENDIENT", ""}
    rows = [r for r in rows if (r["club"] or "").strip().upper() not in _noclub]

    n = _upsert(sb, "player_clubs", rows, "player_fcb_id,temporada", prog)
    return {"player_clubs": n}


# --------------------------------------------------------------------------- #
# Opens EN DIRECTE (seguiment en temps real)
# --------------------------------------------------------------------------- #
#
# A diferència de la resta de publishers (que llegeixen la SQLite local), aquest
# raspa la federació EN VIU i en bolca l'estat a `fcbillar.open_live` (una fila
# per divisió en curs). Pensat per executar-se sovint (cada pocs minuts) des
# d'un job programat — només pàgines públiques, sense login. Quan un Open
# s'acaba (la FCB publica classificació final) se'n treu la fila d'aquí: ja
# apareixerà a `opens`/`open_classifications` un cop ingerit com a acabat.


def _open_modality(name: str) -> str:
    """Modalitat (disciplina) derivada del nom de l'Open. Mirall de la detecció
    del frontend perquè el web etiqueti i tracti cada modalitat correctament."""
    n = name.upper()
    if "TRES BANDES" in n or "3 BANDES" in n:
        return "Tres Bandes"
    if "QUADRE 47/2" in n:
        return "Quadre 47/2"
    if "QUADRE 71/2" in n:
        return "Quadre 71/2"
    if "BANDA" in n:
        return "Banda"
    if "LLIURE" in n:
        return "Lliure"
    return ""


def _open_match_key(name: str) -> str:
    """Clau estable d'un open per casar la *projecció* amb l'open real.

    Els dos noms difereixen (la projecció ve del PDF 'RÀNQUING INICIAL', amb el
    subtítol del memorial entre cometes i sovint sense la modalitat; el nom viu
    ve del llistat de la federació, normalment amb 'TRES BANDES'). Reduïm tots
    dos a la part comuna i estable: edició + seu, sense accents, modalitat,
    'OPEN'/'MEMORIAL' ni el subtítol entre cometes.
    """
    import re
    import unicodedata

    s = name.split('"')[0]  # descarta el subtítol del memorial entre cometes
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().upper()
    for w in (
        "TRES BANDES", "3 BANDES", "QUADRE 47/2", "QUADRE 71/2",
        "BANDA", "LLIURE", "OPEN", "MEMORIAL", "UNICA",
    ):
        s = s.replace(w, " ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _projection_superseded_by(
    proj_row: dict, active: list[tuple[set[str], str]]
) -> bool:
    """Diu si una projecció (id negatiu) ja té l'open REAL en curs publicat.

    El nom del PDF ('XIV OPEN LES SANTES DE MATARO') i el del llistat de la
    federació ('OPEN TRES BANDES MATARO') NO coincideixen: el primer porta
    edició + festa + seu; el segon, sovint només la seu + modalitat. Per això no
    casem per IGUALTAT de claus (mai coincidirien) sinó per CONTINÈNCIA: la clau
    de l'open real (típicament només la seu) ha de ser un subconjunt no buit dels
    tokens de la projecció, i amb la mateixa modalitat. Els Opens femenins mai es
    publiquen en directe → cap open real pot substituir una projecció femenina.
    """
    if "FEMENI" in (proj_row.get("name") or "").upper():
        return False
    proj_tokens = set(_open_match_key(proj_row.get("name") or "").split())
    if not proj_tokens:
        return False
    proj_mod = proj_row.get("modality") or ""
    for real_tokens, real_mod in active:
        if not real_tokens:
            continue
        if proj_mod and real_mod and proj_mod != real_mod:
            continue
        if real_tokens <= proj_tokens:
            return True
    return False


def _phase_code(label: str, kind: str = "") -> str:
    """Codi estable d'una fase per casar la REAL (web FCB) amb la PROJECTADA.

    Els noms difereixen en accents i plural: la real ve "PRE-PRE-PREVIA" i la
    projectada "Pre-pre-prèvies". Es compten els prefixos "PRE" abans de l'arrel
    "PREVI" → P / PP / PPP. Qualsevol fase KO (setzens…final) es col·lapsa a
    "FINAL" perquè, quan la federació publiqui el quadre final real, substitueixi
    la projectada encara que en digui "SETZENS" i no "Fase Final".
    """
    import re
    import unicodedata

    s = unicodedata.normalize("NFD", label or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z]", "", s)
    if kind == "ko" or any(
        k in s for k in ("FINAL", "SETZENS", "VUITENS", "QUARTS", "SEMIFINAL", "SEMIS")
    ):
        return "FINAL"
    i = s.find("PREVI")
    if i >= 0:
        return "P" * (i // 3 + 1)
    return s or "?"


def _matching_projection_payload(
    real_name: str, real_mod: str, proj_rows_full: list[dict]
) -> dict | None:
    """Payload d'open_live de la projecció que casa amb un open real (o None).

    Mateixa regla de continència que `_projection_superseded_by`: la clau de
    l'open real (típicament la seu) ha de ser subconjunt dels tokens de la
    projecció, amb la mateixa modalitat i excloent les projeccions femenines.
    """
    real_tokens = set(_open_match_key(real_name).split())
    if not real_tokens:
        return None
    for p in proj_rows_full:
        if "FEMENI" in (p.get("name") or "").upper():
            continue
        pmod = p.get("modality") or ""
        if real_mod and pmod and real_mod != pmod:
            continue
        if real_tokens <= set(_open_match_key(p.get("name") or "").split()):
            return p.get("payload_json")
    return None


def _merge_projected_phases(
    real_phases: list[dict], template_phases: list[dict] | None
) -> list[dict]:
    """Fon fases reals i projectades en un sol open (id positiu).

    `template_phases` marca l'ordre i el conjunt complet de fases: pot ser el
    payload d'una projecció (fases del PDF) o el payload REAL previ del mateix
    open (que ja arrossega les fases projectades d'abans, quan la projecció ja
    s'ha plegat i esborrat). Per a cada fase del template: si la federació ja té
    la fase real (mateix `_phase_code`), guanya la REAL; si no, es manté la del
    template marcada `projected=True`. Les fases reals que el template no conté
    (p.ex. una ronda KO nova) s'afegeixen al final. Sense template, es tornen
    les fases reals tal qual.
    """
    if not template_phases:
        return real_phases
    real_by_code: dict[str, dict] = {}
    for ph in real_phases:
        real_by_code.setdefault(_phase_code(ph.get("label", ""), ph.get("kind", "")), ph)
    merged: list[dict] = []
    used: set[str] = set()
    for tph in template_phases:
        code = _phase_code(tph.get("label", ""), tph.get("kind", ""))
        if code in used:
            continue
        used.add(code)
        if code in real_by_code:
            rp = dict(real_by_code[code])
            rp.pop("projected", None)
            merged.append(rp)
        else:
            pp = dict(tph)
            pp["projected"] = True
            merged.append(pp)
    for ph in real_phases:
        code = _phase_code(ph.get("label", ""), ph.get("kind", ""))
        if code not in used:
            used.add(code)
            rp = dict(ph)
            rp.pop("projected", None)
            merged.append(rp)
    return merged


def _autobuild_projection_payload(
    division_id: int,
    division_name: str,
    fetched_at: str,
    *,
    live_phases: "list | None" = None,
    force: bool = True,
) -> dict | None:
    """Construeix la projecció d'un open des dels PDFs PÚBLICS de la federació.

    Sense que l'usuari pugi res: localitza a la secció Documents d'Opens el PDF
    'RÀNQUING INICIAL' de l'open (i 'HORARIS' si hi és), en genera el quadre
    projectat (sembra Art. XVIII + fases del reglament) i el torna en forma de
    payload d'open_live per fondre'l com a fases projectades. Retorna None si no
    hi ha el PDF o el generador no cobreix el nombre d'inscrits (N parell dins
    [64,128]). Tot embolcallat: qualsevol error de xarxa/format degrada a None
    (l'open segueix mostrant les seves fases reals, sense projecció).
    """
    import os
    import tempfile
    import unicodedata

    from fcb_opens.projection import (
        build_projection_from_seeded,
        projection_to_live_payload,
    )
    from fcb_opens.scraper.open_live import (
        fetch_doc_pdf,
        fetch_opens_docs,
        filter_docs_for_division,
    )
    from fcb_opens.scraper.ranking_inicial_pdf import parse_ranking_inicial_pdf

    def _n(t: str) -> str:
        return unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().upper()

    def _pdf_tempfile(doc_id: int) -> str | None:
        try:
            data, _fn = fetch_doc_pdf(doc_id, force=force)
        except Exception:  # noqa: BLE001
            return None
        fd, path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return path

    try:
        docs = fetch_opens_docs(force=force)
    except Exception:  # noqa: BLE001
        return None
    open_docs = [
        d
        for d in filter_docs_for_division(docs, division_id, division_name)
        if "FEMENI" not in _n(d.title)
    ]
    rank_docs = [
        d for d in open_docs
        if "RANQUING INICIAL" in _n(d.title) or "RANKING INICIAL" in _n(d.title)
    ]
    if not rank_docs:
        return None
    rpath = _pdf_tempfile(rank_docs[0].doc_id)
    if rpath is None:
        return None
    try:
        ranking = parse_ranking_inicial_pdf(rpath)
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            os.unlink(rpath)
        except OSError:
            pass
    if ranking.num_players == 0:
        return None

    # Horaris (opcional): enganxa dia/billar/hores a cada grup projectat.
    sched = None
    hor_docs = [d for d in open_docs if "HORARIS" in _n(d.title)]
    if hor_docs:
        hpath = _pdf_tempfile(hor_docs[0].doc_id)
        if hpath is not None:
            try:
                from fcb_opens.scraper.horaris_pdf import parse_horaris_pdf

                sched = parse_horaris_pdf(hpath)
            except Exception:  # noqa: BLE001
                sched = None
            finally:
                try:
                    os.unlink(hpath)
                except OSError:
                    pass

    try:
        proj = build_projection_from_seeded(ranking, season=None)
    except Exception:  # noqa: BLE001 — NotImplementedError si N fora de rang, etc.
        return None

    # Resol la RONDA SEGÜENT: omple els placeholders '<k>-<fase>' de cada fase de
    # grups projectada amb els guanyadors SEGURS reals de la ronda viva
    # corresponent, ordenats per punts→mitjana→sèrie major (fcb_opens.next_round).
    # Així, en comptes de "Guanyador Grup X", es veu qui s'ha classificat de veritat
    # abans que la FCB dibuixi el sorteig. Placeholders sense guanyador segur queden.
    if live_phases:
        from fcb_opens.next_round import (
            rank_winners,
            resolve_next_round,
            secured_winners,
        )

        winners_by_code: dict[str, list] = {}
        for lp in live_phases:
            code = _phase_code(lp.ref.label, lp.ref.kind)
            w = rank_winners(secured_winners(lp))
            if w:
                winners_by_code[code] = w
        # La font dels placeholders d'una fase de grups és la fase inferior:
        # P (Prèvies) ← PP, PP (Pre-prèvies) ← PPP.
        _from_phase = {"P": "PP", "PP": "PPP"}
        for phdict in proj.get("phases", []):
            src = _from_phase.get(phdict.get("name"))
            if src and src in winners_by_code:
                phdict["groups"], _, _ = resolve_next_round(
                    phdict["groups"], winners_by_code[src], src
                )

    return projection_to_live_payload(
        proj,
        division_id=-abs(division_id),
        fetched_at=fetched_at,
        schedule_by_group=sched,
    )


def _open_schedule_by_group(
    division_id: int, division_name: str, *, force: bool = True
) -> dict | None:
    """Dia/billar/hores per grup (bare label, p.ex. 'AG', 'Q', 'B') des del PDF
    HORARIS de l'open, o None si no hi ha PDF o falla. Cau amb gràcia."""
    import os
    import tempfile
    import unicodedata

    from fcb_opens.scraper.horaris_pdf import parse_horaris_pdf
    from fcb_opens.scraper.open_live import (
        fetch_doc_pdf,
        fetch_opens_docs,
        filter_docs_for_division,
    )

    def _n(t: str) -> str:
        return unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().upper()

    try:
        docs = fetch_opens_docs(force=force)
    except Exception:  # noqa: BLE001
        return None
    hor = [
        d
        for d in filter_docs_for_division(docs, division_id, division_name)
        if "FEMENI" not in _n(d.title) and "HORARIS" in _n(d.title)
    ]
    if not hor:
        return None
    try:
        data, _fn = fetch_doc_pdf(hor[0].doc_id, force=force)
    except Exception:  # noqa: BLE001
        return None
    fd, path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    try:
        return parse_horaris_pdf(path)
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


_P_KEYS = set("ABCDEFGHIJKLMNOP")  # P (Prèvies): grups A..P
_PP_KEYS = {"Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA", "AB", "AC", "AD", "AE", "AF"}


def _attach_schedules(phases: list[dict], schedule_by_group: dict | None) -> None:
    """Enganxa `schedule` (dia/billar/hores) i `venue` a cada grup, in-place, perquè
    els grups de l'open EN CURS mostrin quan i on juga cadascú. Els grups que ja en
    porten (projecció) no es toquen.

    Els labels de P (A..P) i PP (Q..AF) del seguiment en viu casen directament amb
    les claus del HORARIS. El PPP és l'excepció: la FCB l'etiqueta 'A' en viu però al
    HORARIS/generador és 'AG'.., i 'A' allà és PRÈVIA — casar per label cru donaria la
    data equivocada. Per això el PPP s'assigna per ORDRE a les claus del HORARIS que
    no són ni de P ni de PP (les 'AG'..)."""
    if not schedule_by_group:
        return
    ppp_keys = sorted(k for k in schedule_by_group if k not in _P_KEYS and k not in _PP_KEYS)
    for ph in phases:
        code = _phase_code(ph.get("label", ""), ph.get("kind", ""))
        ppp_i = 0
        for g in ph.get("groups", []):
            if g.get("schedule"):
                continue
            if code == "PPP":
                s = schedule_by_group.get(ppp_keys[ppp_i]) if ppp_i < len(ppp_keys) else None
                ppp_i += 1
            else:
                bare = (g.get("label") or "").replace("Grup ", "").strip()
                s = schedule_by_group.get(bare)
            if not s:
                continue
            g["schedule"] = s
            billar = s.get("billar")
            if billar and not g.get("venue"):
                g["venue"] = f"Billar {billar}"


def _enrich_real_groups_with_projection(
    real_phases: list[dict], proj_phases: list[dict]
) -> int:
    """Completa els grups de les fases REALS de grups afegint-hi els jugadors que la
    projecció ja té RESOLTS (guanyadors segurs de la ronda inferior) però que la FCB
    encara no ha col·locat al grup — p.ex. el 3r de cada grup de PRÈVIA = guanyador de
    PRE-PRÈVIA, quan la PP ja s'ha jugat però la FCB no ha penjat la composició final.

    Casa fase per `_phase_code` i grup per label; afegeix (marcat `incoming`) només
    noms que no hi siguin i que NO siguin placeholders sense resoldre. Retorna quants
    n'ha afegit. Idempotent: quan la FCB col·loca el jugador, el nom ja hi és → no es
    duplica."""
    import re
    import unicodedata

    def _nm(s: str) -> str:
        # Treu accents I tota la puntuació/espais: la FCB en viu escriu "COGNOM,
        # NOM" i el PDF de vegades "COGNOM,NOM" (sense espai) → cal casar-los.
        s = "".join(
            c
            for c in unicodedata.normalize("NFD", s or "")
            if unicodedata.category(c) != "Mn"
        )
        return re.sub(r"[^A-Za-z0-9]", "", s).upper()

    proj_by_code = {
        _phase_code(p.get("label", ""), p.get("kind", "")): p for p in proj_phases
    }
    added = 0
    for ph in real_phases:
        if ph.get("kind") != "group":
            continue
        pph = proj_by_code.get(_phase_code(ph.get("label", ""), ph.get("kind", "")))
        if not pph:
            continue
        pg_by_label = {g.get("label"): g for g in pph.get("groups", [])}
        for g in ph.get("groups", []):
            pg = pg_by_label.get(g.get("label"))
            if not pg:
                continue
            proj_players = [s for s in pg.get("standings", []) if not s.get("placeholder")]
            standings = g.setdefault("standings", [])
            # Grup ja complet (tants o més jugadors que la projecció): no hi toquem.
            if len(standings) >= len(proj_players):
                continue
            have = {_nm(s.get("player_name")) for s in standings}
            for ps in proj_players:
                nm = _nm(ps.get("player_name"))
                if nm and nm not in have:
                    standings.append({**ps, "incoming": True})
                    have.add(nm)
                    added += 1
    return added


def _reservat_match_key(name: str, club: str) -> tuple[str, str, str]:
    """Clau robusta per casar un cap de sèrie RESERVAT entre la projecció (PDF
    RÀNQUING INICIAL) i el viu (HTML FCB): (club, 1r cognom, inicial del nom).

    El PDF de vegades ABREUJA el 2n cognom ("HERNÁNDEZ HDEZ" vs "HERNÁNDEZ
    HERNÁNDEZ") o s'oblida l'espai després de la coma ("GARCIA ALARCÓN,RICARDO"),
    així que casar per nom sencer normalitzat falla i afegiria duplicats. El 1r
    cognom + inicial + club és estable entre les dues fonts."""
    import re
    import unicodedata

    def _strip(s: str) -> str:
        return "".join(
            c
            for c in unicodedata.normalize("NFD", s or "")
            if unicodedata.category(c) != "Mn"
        ).upper()

    parts = (name or "").split(",")
    surnames = _strip(parts[0]).split()
    given = _strip(parts[1]).strip() if len(parts) > 1 else ""
    surname1 = re.sub(r"[^A-Z]", "", surnames[0]) if surnames else ""
    given_initial = given[0] if given else ""
    club_key = re.sub(r"[^A-Z0-9]", "", _strip(club))
    return (club_key, surname1, given_initial)


def _complete_first_ko_reservats(state, proj_phases: list[dict]) -> int:
    """Completa els RESERVATS del primer KO de l'estat en viu amb els que la
    projecció (RÀNQUING INICIAL) coneix però la FCB encara no ha llistat al grup
    "RESERVATS" en directe. Muta `state` in-place; retorna quants n'ha afegit.

    Cas real: a l'inici d'un open la llista "RESERVATS" del web sovint va per
    darrere del quadre (p.ex. 15 dels 16 caps de sèrie), de manera que als setzens
    en falta un. La projecció els té tots (`source='reservat'` a la fase KO), així
    que hi afegim els que hi manquen (casant per `_reservat_match_key`)."""
    import re

    from fcb_opens.scraper.open_live import GroupStanding, augment_state_reservats

    proj_reservats = [
        p
        for ph in proj_phases
        if ph.get("kind") == "ko"
        for p in ph.get("provisional_players", [])
        if p.get("source") == "reservat"
    ]
    if not proj_reservats:
        return 0
    have = {
        _reservat_match_key(s.player_name, s.club) for s in state.reservats
    }
    extra: list[GroupStanding] = []
    for p in proj_reservats:
        key = _reservat_match_key(p.get("name") or "", p.get("club") or "")
        if key in have:
            continue
        have.add(key)
        # Normalitza l'espai després de la coma perquè casi amb el `seeding`
        # (rànquing d'Opens) i el reservat quedi ben ordenat entre els caps de sèrie.
        nom = re.sub(r",\s*", ", ", p.get("name") or "")
        extra.append(
            GroupStanding(
                player_name=nom,
                club=p.get("club") or "",
                punts=0,
                mitjana=0.0,
            )
        )
    augment_state_reservats(state, extra)
    return len(extra)


def _seed_first_ko_by_projection(state, proj_phases: list[dict]) -> bool:
    """Sembra els 16 caps de sèrie del primer KO per l'ordre del RÀNQUING INICIAL
    (Posició 1..16 del PDF), no pel rànquing d'Opens VIGENT. Muta `state` in-place;
    retorna si ha reordenat.

    Per què: el sorteig del primer KO empara els caps de sèrie 1..16 amb els pitjors
    classificats (piràmide 1-N). L'ordre dels caps de sèrie és el que la FEDERACIÓ va
    fixar en publicar el RÀNQUING INICIAL d'AQUEST open (columna Posició), no el
    rànquing d'Opens d'ara: entre la publicació i les eliminatòries s'hi juguen més
    opens i el rànquing viu deriva (p.ex. a Mataró, Jiménez Vasco és Posició 5 però ja
    ha caigut al 8 del rànquing viu). La projecció ja porta els reservats en ordre de
    Posició; en derivem una sembra pròpia i recalculem el pool del primer KO.
    """
    from fcb_opens.scraper.open_live import (
        _attach_ko_provisional_players,
        _norm_name,
    )

    proj_reservats = [
        p
        for ph in proj_phases
        if ph.get("kind") == "ko"
        for p in ph.get("provisional_players", [])
        if p.get("source") == "reservat"
    ]
    if not proj_reservats:
        return False
    # Posició (1..16) per cap de sèrie, casada de forma robusta amb el viu.
    pos_by_key: dict[tuple[str, str, str], int] = {}
    for idx, p in enumerate(proj_reservats, 1):
        pos_by_key.setdefault(
            _reservat_match_key(p.get("name") or "", p.get("club") or ""), idx
        )
    seeding = dict(state.seeding or {})  # rànquing viu com a fallback
    reseeded = False
    for s in state.reservats:
        pos = pos_by_key.get(_reservat_match_key(s.player_name, s.club))
        if pos is not None:
            seeding[_norm_name(s.player_name)] = pos
            reseeded = True
    if not reseeded:
        return False
    state.seeding = seeding
    state.phases = _attach_ko_provisional_players(
        state.phases, state.reservats, seeding
    )
    return True


def _enrich_live_payload(
    payload: dict, sb, open_name: str = "", division_id: int | None = None
) -> None:
    """Enriqueix el payload en viu (in-place):
      - PJ/caramboles/entrades per jugador a cada classificació i classificat,
        calculats des de les partides JUGADES del grup (l'HTML de la FCB només
        dóna jugador/club/punts/mitjana).
      - `player_ids`: mapa nom→fcb_id (taula `players` de Supabase) perquè el web
        pugui enllaçar cada jugador a la seva fitxa.
    """
    import re
    import unicodedata

    # 1) Agregats PJ/C/E per (grup, jugador) des de les partides jugades.
    for ph in payload.get("phases", []):
        agg_by_group: dict[str, dict[str, list[int]]] = {}
        for g in ph.get("groups", []):
            agg: dict[str, list[int]] = {}
            for m in g.get("matches", []):
                if not m.get("is_played"):
                    continue
                ent = int(m.get("entrades") or 0)
                for name, car in (
                    (m.get("player_a"), m.get("caramboles_a")),
                    (m.get("player_b"), m.get("caramboles_b")),
                ):
                    if not name:
                        continue
                    x = agg.setdefault(name, [0, 0, 0])
                    x[0] += 1
                    x[1] += int(car or 0)
                    x[2] += ent
            agg_by_group[g.get("label", "")] = agg
            for s in g.get("standings", []):
                pj, c, en = agg.get(s["player_name"], [0, 0, 0])
                s["pj"], s["caramboles"], s["entrades"] = pj, c, en
        for q in ph.get("provisional_qualifiers", []):
            pj, c, en = agg_by_group.get(q.get("group_label", ""), {}).get(
                q.get("player_name", ""), [0, 0, 0]
            )
            q["pj"], q["caramboles"], q["entrades"] = pj, c, en

    # 2) Resolució nom→fcb_id (exacte o variant amb coma normalitzada; només quan
    #    el match és únic, per no enllaçar homònims). Mirall de
    #    DataSource.resolve_player_fcb_ids, però contra Supabase.
    names: set[str] = set()
    for ph in payload.get("phases", []):
        for g in ph.get("groups", []):
            for s in g.get("standings", []):
                names.add(s["player_name"])
            for m in g.get("matches", []):
                names.add(m.get("player_a") or "")
                names.add(m.get("player_b") or "")
        for m in ph.get("ko_matches", []):
            names.add(m.get("player_a") or "")
            names.add(m.get("player_b") or "")
        for q in ph.get("provisional_qualifiers", []):
            names.add(q.get("player_name") or "")
        # Caps de sèrie reservats i emparellaments calculats del KO: també han de
        # resoldre l'fcb_id (si no, un reservat que encara no juga cap grup —p.ex.
        # el cap de sèrie nº1— es queda sense enllaç ni rànquing 3B → banda 181+).
        for p in ph.get("provisional_players", []):
            names.add(p.get("name") or "")
        for m in ph.get("provisional_matches", []):
            names.add(m.get("player_a") or "")
            names.add(m.get("player_b") or "")
    # Files de la classificació (inclou els que encara juguen, com els reservats).
    for row in payload.get("classification", []):
        names.add(row.get("player_name") or "")
    names.discard("")
    if not names:
        payload["player_ids"] = {}
        return

    norm = {n: re.sub(r",\s*", ", ", n) for n in names}
    variants = sorted(set(names) | set(norm.values()))
    by_nom: dict[str, list[str]] = {}
    for i in range(0, len(variants), 80):
        chunk = variants[i : i + 80]
        try:
            res = sb.table("players").select("nom,fcb_id").in_("nom", chunk).execute()
        except Exception:  # noqa: BLE001
            continue
        for r in res.data or []:
            by_nom.setdefault(r["nom"], []).append(r["fcb_id"])
    player_ids: dict[str, str] = {}
    for n in names:
        ids = by_nom.get(n) or by_nom.get(norm[n])
        if ids and len(ids) == 1:
            player_ids[n] = ids[0]

    # Fallback SENSE accents per als noms que no han casat exacte: els noms que
    # venen del PDF (RÀNQUING INICIAL → caps de sèrie reservats, fases projectades)
    # de vegades escriuen l'accent diferent de la taska `players` (cas real:
    # "GARCIA ALARCÓN" al PDF vs "GARCÍA ALARCÓN" a players → el nº4 del rànquing 3B
    # queia a la banda "181+"). Es casa per nom normalitzat (sense accents, majúscules,
    # espai després de la coma) i NOMÉS quan el match és únic (no enllaça homònims).
    unresolved = [n for n in names if n not in player_ids]
    if unresolved:

        def _key(s: str) -> str:
            s = "".join(
                c
                for c in unicodedata.normalize("NFD", s or "")
                if unicodedata.category(c) != "Mn"
            )
            return re.sub(r",\s*", ", ", " ".join(s.split())).upper()

        by_key: dict[str, set[str]] = {}
        try:
            allp = sb.table("players").select("nom,fcb_id").execute().data or []
        except Exception:  # noqa: BLE001
            allp = []
        for r in allp:
            by_key.setdefault(_key(r["nom"]), set()).add(r["fcb_id"])
        for n in unresolved:
            ids = by_key.get(_key(n))
            if ids and len(ids) == 1:
                player_ids[n] = next(iter(ids))

    payload["player_ids"] = player_ids

    # 3) Rànquing de TRES BANDES (modalitat_codi=1, seqüència vigent) per jugador,
    #    i premis especials de la classificació de l'open:
    #      · "millor classificat d'entre els del rànquing 3B 61-180"
    #      · "millor classificat d'entre els del 181 fins al final (i no rankejats)"
    #    Cada fila de la classificació rep `rank3b` (per mostrar-lo) i la fila
    #    guanyadora de cada banda rep `prize`. NOMÉS per a opens de TRES BANDES:
    #    els premis per banda de rànquing i el rànquing 3B no apliquen a la resta de
    #    modalitats (quadre, banda, lliure).
    _nm = (open_name or payload.get("name") or "").upper()
    is_3b = "TRES BANDES" in _nm or "3 BANDES" in _nm or "3B" in _nm
    classification = payload.get("classification") or []
    if classification and is_3b:
        # Rànquing 3B per als premis: el FIXAT per a aquest open (vigent en el
        # moment de la convocatòria) o, si no n'hi ha cap, el darrer publicat.
        pinned = _load_prize_pins().get(division_id) if division_id is not None else None
        used_seq = pinned if pinned is not None else _latest_3b_num_seq(sb)
        if used_seq is not None:
            # El web hi ancora el selector de premis (mostra el mes correcte).
            payload["prize_num_seq"] = used_seq
        rank3b = _ranking_3b_by_fcb_id(sb, used_seq)
        best_a: tuple[int, dict] | None = None  # banda 61-180
        best_b: tuple[int, dict] | None = None  # banda 181+ / no rankejat
        for row in classification:
            fid = player_ids.get(row.get("player_name", ""))
            pos3b = rank3b.get(fid) if fid else None
            if pos3b is not None:
                row["rank3b"] = pos3b
            op = row.get("position")
            if not isinstance(op, int):
                continue
            if pos3b is not None and 61 <= pos3b <= 180:
                if best_a is None or op < best_a[0]:
                    best_a = (op, row)
            elif pos3b is None or pos3b >= 181:
                if best_b is None or op < best_b[0]:
                    best_b = (op, row)
        if best_a is not None:
            best_a[1]["prize"] = "Millor 61-180"
        if best_b is not None:
            best_b[1]["prize"] = "Millor 181+"


def _latest_3b_num_seq(sb) -> int | None:
    """num_seq més alt del rànquing de TRES BANDES (modalitat_codi=1)."""
    try:
        r = (
            sb.table("rankings").select("num_seq")
            .eq("modalitat_codi", 1).order("num_seq", desc=True).limit(1).execute()
        )
        return int(r.data[0]["num_seq"]) if r.data else None
    except Exception:  # noqa: BLE001
        return None


def _ranking_3b_by_fcb_id(sb, num_seq: int | None = None) -> dict[str, int]:
    """{player_fcb_id: posicio} del rànquing de TRES BANDES (modalitat_codi=1) per a
    la seqüència `num_seq` indicada; si és None, la vigent (num_seq més alt). Font
    dels premis especials per banda de rànquing dels opens."""
    try:
        if num_seq is None:
            num_seq = _latest_3b_num_seq(sb)
        if num_seq is None:
            return {}
        out: dict[str, int] = {}
        res = (
            sb.table("ranking_entries").select("player_fcb_id,posicio")
            .eq("modalitat_codi", 1).eq("num_seq", num_seq).execute()
        )
        for r in res.data or []:
            if r.get("player_fcb_id") and r.get("posicio") is not None:
                out[r["player_fcb_id"]] = int(r["posicio"])
        return out
    except Exception:  # noqa: BLE001
        return {}


# --- Pin del rànquing 3B per als premis, per open (divisió) ------------------
# El premi per banda s'ha de calcular amb el rànquing 3B vigent EN EL MOMENT DE
# LA CONVOCATÒRIA, que sovint NO és el darrer publicat. Es desa per
# `fcb_division_id` en un JSON local (només cal a la màquina que publica). Sense
# pin → darrer rànquing (comportament anterior).


def _prize_pin_path() -> Path:
    return PROJECT_ROOT / "data" / "open_prize_ranking.json"


def _load_prize_pins() -> dict[int, int]:
    import json

    p = _prize_pin_path()
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {int(k): int(v) for k, v in raw.items()}
    except Exception:  # noqa: BLE001
        return {}


def set_open_prize_num_seq(division_id: int, num_seq: int | None) -> None:
    """Fixa (o esborra, amb num_seq=None) el rànquing 3B (num_seq) per als premis
    d'un open. La propera publicació (`publish-live-opens`) hi aplicarà aquest
    rànquing en comptes del darrer."""
    import json

    pins = _load_prize_pins()
    if num_seq is None:
        pins.pop(division_id, None)
    else:
        pins[division_id] = int(num_seq)
    p = _prize_pin_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({str(k): v for k, v in sorted(pins.items())}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def publish_live_opens(
    on_progress: Progress | None = None, *, force: bool = True
) -> dict[str, int]:
    """Bolca l'estat en viu de TOTS els Opens en curs a `fcbillar.open_live`.

    Inclou totes les modalitats (Tres Bandes, Quadre, Banda, Lliure); només
    s'exclouen els Opens femenins (format diferent) i els ja tancats. Idempotent:
    upsert per `fcb_division_id` i esborrat de les files d'Opens que ja no
    estiguin en curs. Retorna comptadors {live_opens, removed, errors}.
    """
    from datetime import datetime, timezone

    from fcb_opens.scraper.open_live import (
        fetch_has_final_classification,
        fetch_individuals_llistat,
        fetch_live_state,
    )
    from fcb_opens.snapshot_live import _state_payload, opens_ranking_by_name

    prog: Progress = on_progress or (lambda level, msg: None)
    sb = get_client()
    fetched_at = datetime.now(timezone.utc).isoformat()
    # Ordre de sorteig dels grups encara no jugats = ordre del rànquing d'Opens
    # (`get_client()` ja està lligat a l'esquema `fcbillar`, on viu `open_ranking`).
    rank_by_name = opens_ranking_by_name(sb)

    # Fonts per fondre les fases PROJECTADES (encara no penjades al web per la
    # FCB) amb les reals: la projecció desada (id negatiu) i, si ja s'ha plegat i
    # esborrat, el payload REAL previ (que les arrossega). Vegeu
    # `_merge_projected_phases`.
    try:
        _live_rows = (
            sb.table("open_live")
            .select("fcb_division_id,name,modality,payload_json")
            .execute()
            .data
            or []
        )
    except Exception:  # noqa: BLE001
        _live_rows = []
    proj_full = [r for r in _live_rows if (r.get("fcb_division_id") or 0) < 0]
    prev_real = {
        r["fcb_division_id"]: r.get("payload_json")
        for r in _live_rows
        if (r.get("fcb_division_id") or 0) > 0
    }

    try:
        entries = fetch_individuals_llistat(force=force)
    except Exception as exc:  # noqa: BLE001
        prog("warn", f"no s'ha pogut llegir el llistat d'individuals: {exc}")
        return {"live_opens": 0, "removed": 0, "errors": 1}

    rows: list[dict] = []
    active_ids: list[int] = []
    errors = 0
    for e in entries:
        name_upper = e.name.upper()
        if "OPEN" not in name_upper:
            continue
        if "FEMENI" in name_upper:
            # Els Opens femenins tenen un format propi que no seguim en directe.
            continue
        # Saltar els ja tancats (classificació final publicada): aquests
        # pertanyen a l'històric, no al directe.
        try:
            if fetch_has_final_classification(e.division_id, force=force):
                continue
        except Exception:  # noqa: BLE001 — si la sonda falla, el tractem com a en curs
            pass
        try:
            state = fetch_live_state(
                e.division_id, force=force, rank_by_name=rank_by_name
            )
        except Exception as exc:  # noqa: BLE001
            prog("warn", f"#{e.division_id} {e.name}: {exc}")
            errors += 1
            continue
        # Sense fases publicades encara (sorteig no penjat): res a mostrar.
        if not state.phases:
            continue

        # AUTO-construeix la projecció (RÀNQUING INICIAL + HORARIS), amb la RONDA
        # SEGÜENT resolta pels guanyadors SEGURS vius (punts→mitjana→SM). Serveix per:
        #  (a) COMPLETAR els RESERVATS del primer KO que la FCB encara no ha llistat;
        #  (b) COMPLETAR els grups reals incomplets — el 3r que la FCB encara no ha
        #      col·locat (guanyador de la ronda inferior); i
        #  (c) FONDRE les fases que la FCB encara no ha publicat.
        # Es re-fa a cada publicació (barat: PDFs en cau) perquè es re-resolgui a
        # mesura que es tanquen grups. Fallbacks (desada / prèvia) només per fondre.
        auto = _autobuild_projection_payload(
            e.division_id,
            state.structure.name,
            fetched_at,
            live_phases=state.phases,
            force=force,
        )
        auto_phases = (auto or {}).get("phases")
        # (a) Completa els caps de sèrie RESERVATS del primer KO ABANS de serialitzar,
        # perquè tant els "classificats per a la ronda" com la classificació provisional
        # comptin els 16 (i no els 15 que la FCB de vegades té llistats al principi).
        if auto_phases:
            _complete_first_ko_reservats(state, auto_phases)
            # (a-bis) Sembra els caps de sèrie del primer KO per la Posició del
            # RÀNQUING INICIAL (l'ordre oficial d'aquest open), no pel rànquing
            # d'Opens vigent (que ja ha derivat des del sorteig).
            _seed_first_ko_by_projection(state, auto_phases)

        payload = _state_payload(state, fetched_at)
        _enrich_live_payload(payload, sb, open_name=state.structure.name, division_id=e.division_id)
        modality = _open_modality(state.structure.name)

        # Dia/billar/hores a cada grup de l'open EN CURS (grups reals), des del PDF
        # HORARIS de la federació (l'HTML en directe no els porta).
        _attach_schedules(
            payload["phases"],
            _open_schedule_by_group(e.division_id, state.structure.name, force=force),
        )

        if auto_phases:
            _enrich_real_groups_with_projection(payload["phases"], auto_phases)
            payload["phases"] = _merge_projected_phases(payload["phases"], auto_phases)
        else:
            template = _matching_projection_payload(state.structure.name, modality, proj_full)
            template_phases = (template or {}).get("phases")
            if not template_phases:
                prev_phases = (prev_real.get(e.division_id) or {}).get("phases") or []
                if any(p.get("projected") for p in prev_phases):
                    template_phases = prev_phases
            if template_phases:
                payload["phases"] = _merge_projected_phases(payload["phases"], template_phases)
        rows.append({
            "fcb_division_id": e.division_id,
            "name": state.structure.name,
            "modality": modality,
            "payload_json": payload,
            "captured_at": fetched_at,
            "updated_at": fetched_at,
        })
        active_ids.append(e.division_id)
        prog("ok", f"#{e.division_id} {state.structure.name} ({len(state.phases)} fases)")

    if rows:
        _upsert(sb, "open_live", rows, "fcb_division_id", prog)

    # Treu els Opens REALS que ja no són en curs (acabats o desapareguts del
    # llistat). Només toca ids POSITIUS: les projeccions (id sintètic negatiu,
    # publicades per `project-open-ranking`) es protegeixen amb `.gt(...,0)` i es
    # retiren a part més avall. `not in (active_ids)`; si no n'hi ha cap actiu,
    # usem [-1] (id impossible) perquè el filtre 'not in' no quedi buit.
    removed = 0
    try:
        res = (
            sb.table("open_live")
            .delete()
            .gt("fcb_division_id", 0)
            .not_.in_("fcb_division_id", active_ids or [-1])
            .execute()
        )
        removed = len(res.data or [])
        if removed:
            prog("ok", f"open_live: {removed} files retirades (ja no en curs)")
    except Exception as exc:  # noqa: BLE001
        prog("warn", f"no s'han pogut retirar files antigues: {exc}")

    # Retira les PROJECCIONS (id negatiu) que ja tenen l'open real en curs: quan
    # la federació publica el sorteig, el seguiment real (id positiu) substitueix
    # la projecció (casant pel nom d'open, no per l'id, que la federació assigna
    # de nou cada edició).
    superseded = 0
    try:
        proj_rows = (
            sb.table("open_live").select("fcb_division_id,name,modality")
            .lt("fcb_division_id", 0).execute().data or []
        )
        # Cada open REAL actiu, reduït a (tokens de la clau estable, modalitat).
        active = [
            (set(_open_match_key(r["name"]).split()), r.get("modality") or "")
            for r in rows
        ]
        stale = [
            p["fcb_division_id"] for p in proj_rows
            if _projection_superseded_by(p, active)
        ]
        if stale:
            sb.table("open_live").delete().in_("fcb_division_id", stale).execute()
            superseded = len(stale)
            prog("ok", f"open_live: {superseded} projeccions retirades (sorteig real ja publicat)")
    except Exception as exc:  # noqa: BLE001
        prog("warn", f"no s'han pogut retirar projeccions superades: {exc}")

    return {
        "live_opens": len(rows),
        "removed": removed,
        "superseded": superseded,
        "errors": errors,
    }
