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
        }
        for r in conn.execute(
            """
            SELECT m.codi_fcb AS modalitat_codi, r.num_seq, r.any_pub, r.mes_pub
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
        games_by: dict[str, list[tuple[str, int | None, int | None]]] = {}
        for r in conn.execute(
            """SELECT p1.fcb_id f1, g.caramboles1 c1, p2.fcb_id f2, g.caramboles2 c2,
                      g.entrades e, g.data_partida d
               FROM games g JOIN players p1 ON p1.id = g.player1_id
               JOIN players p2 ON p2.id = g.player2_id WHERE g.modalitat_id = ?""",
            (mod_id,),
        ):
            if r["d"] and r["d"] >= age_cutoff:
                games_by.setdefault(r["f1"], []).append((r["d"], r["c1"], r["e"]))
                games_by.setdefault(r["f2"], []).append((r["d"], r["c2"], r["e"]))

        # pending per jugador (de Supabase, publicat per publish_pending_games abans).
        pend: dict[str, list[tuple[int | None, int | None]]] = {}
        pdata = (
            sb.table("pending_games")
            .select("player_fcb_id, caramboles, entrades")
            .eq("modalitat_codi", mod)
            .execute()
            .data
            or []
        )
        for pr in pdata:
            pend.setdefault(pr["player_fcb_id"], []).append((pr["caramboles"], pr["entrades"]))

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
                computed.append({"fcb": fcb, "pos": off_pos, "mj": off_mj, "def": proj_def,
                                 "proj": None, "n": 0, "eff": off_mj or 0.0})
                continue
            window = list(pg[:15])
            recent = sorted(games_by.get(fcb, []), key=lambda x: x[0], reverse=True)
            window += [(c, en) for _d, c, en in recent[: max(0, 15 - len(window))]]
            car = ent = 0
            for c, en in window:
                if c is not None and en is not None:
                    car += c
                    ent += en
            proj = (car / ent) if ent else None
            eff = proj if proj is not None else (off_mj or 0.0)
            computed.append({"fcb": fcb, "pos": off_pos, "mj": off_mj, "def": proj_def,
                             "proj": proj, "n": n_pending, "eff": eff})

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
                "detall": det,
            })
    # Penalitzacions del PDF oficial (Art. IV): -20 no presentat injustificat,
    # 0 justificat, None no inscrit. Només a la ronda actual (el PDF és la finestra vigent).
    try:
        import httpx
        from fcb_opens.scraper.official_pdf import OFFICIAL_RANKING_URL, parse_official_ranking

        off = parse_official_ranking(
            httpx.get(OFFICIAL_RANKING_URL, timeout=30, follow_redirects=True).content,
            source_url=OFFICIAL_RANKING_URL,
        )
        max_ronda = len(ordered)
        window = ordered[max(0, max_ronda - 5):max_ronda]
        if max_ronda and len(off.opens) == len(window):  # alineació posicional segura
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
            prog("ok", f"penalitzacions oficials aplicades ({len(off.entries)} entrades PDF)")
    except Exception as exc:  # noqa: BLE001
        prog("warn", f"penalitzacions: PDF no aplicat ({exc})")

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
    if not rows:
        prog("ok", "open_ranking (femeni): 0 files")
        return {"open_ranking_femeni": 0}
    sb = get_client()
    n = _upsert(sb, "open_ranking", rows, "genere,ronda,player_fcb_id", prog)
    return {"open_ranking_femeni": n}


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


def _enrich_live_payload(payload: dict, sb, open_name: str = "") -> None:
    """Enriqueix el payload en viu (in-place):
      - PJ/caramboles/entrades per jugador a cada classificació i classificat,
        calculats des de les partides JUGADES del grup (l'HTML de la FCB només
        dóna jugador/club/punts/mitjana).
      - `player_ids`: mapa nom→fcb_id (taula `players` de Supabase) perquè el web
        pugui enllaçar cada jugador a la seva fitxa.
    """
    import re

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
        rank3b = _ranking_3b_by_fcb_id(sb)
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


def _ranking_3b_by_fcb_id(sb) -> dict[str, int]:
    """{player_fcb_id: posicio} del rànquing vigent de TRES BANDES (modalitat_codi=1,
    num_seq més alt). Font dels premis especials per banda de rànquing dels opens."""
    try:
        seqs = (
            sb.table("rankings").select("num_seq")
            .eq("modalitat_codi", 1).order("num_seq", desc=True).limit(1).execute()
        )
        if not seqs.data:
            return {}
        latest = seqs.data[0]["num_seq"]
        out: dict[str, int] = {}
        res = (
            sb.table("ranking_entries").select("player_fcb_id,posicio")
            .eq("modalitat_codi", 1).eq("num_seq", latest).execute()
        )
        for r in res.data or []:
            if r.get("player_fcb_id") and r.get("posicio") is not None:
                out[r["player_fcb_id"]] = int(r["posicio"])
        return out
    except Exception:  # noqa: BLE001
        return {}


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
        payload = _state_payload(state, fetched_at)
        _enrich_live_payload(payload, sb, open_name=state.structure.name)
        rows.append({
            "fcb_division_id": e.division_id,
            "name": state.structure.name,
            "modality": _open_modality(state.structure.name),
            "payload_json": payload,
            "captured_at": fetched_at,
            "updated_at": fetched_at,
        })
        active_ids.append(e.division_id)
        prog("ok", f"#{e.division_id} {state.structure.name} ({len(state.phases)} fases)")

    if rows:
        _upsert(sb, "open_live", rows, "fcb_division_id", prog)

    # Treu els Opens que ja no són en curs (acabats o desapareguts del llistat).
    # `not in (active_ids)`; si no n'hi ha cap actiu, esborra-ho tot (usem [-1],
    # un id impossible, perquè el filtre 'not in' no quedi buit).
    removed = 0
    try:
        res = (
            sb.table("open_live")
            .delete()
            .not_.in_("fcb_division_id", active_ids or [-1])
            .execute()
        )
        removed = len(res.data or [])
        if removed:
            prog("ok", f"open_live: {removed} files retirades (ja no en curs)")
    except Exception as exc:  # noqa: BLE001
        prog("warn", f"no s'han pogut retirar files antigues: {exc}")

    return {"live_opens": len(rows), "removed": removed, "errors": errors}
