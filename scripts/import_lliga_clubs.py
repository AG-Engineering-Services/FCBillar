"""Importa el club de cada jugador per temporada a partir de la lliga històrica.

Recorre historial: llistatLliga → divisionsLliga → grupsLliga → jornadesLliga
→ encontresLliga (equips local/visitant) → partidesLliga (alineacions).
Local→equip local, visitant→equip visitant. El club = nom d'equip sense el
sufix d'equip ("A"/"B"/…). Desa a lliga_player_clubs (player_id, temporada, club).
Resumible: salta encontres ja processats.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata

from bs4 import BeautifulSoup

from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient

BASE = "https://www.fcbillar.cat"
_MOD = r"(?:Tres bandes|Lliure|Banda|Quadre \d+/\d+)"
_PAIR_RE = re.compile(
    rf"Modalitat {_MOD} (.+?) Caramboles -?\d+ S[èe]rie major -?\d+ Punts -?\d+ (.+?) Caramboles"
)
_TEAMS_RE = re.compile(r"Encontres (.+?) P\. Parcials \d+ P\. Match \d+ (.+?) P\. Parcials")


def _nm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    return " ".join(s.strip().lower().split())


def _club(team: str) -> str:
    return re.sub(r'\s*"[^"]*"\s*$', "", team).strip()


def _flat(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _links(html: str, pat: str) -> list[str]:
    out, seen = [], set()
    for a in BeautifulSoup(html, "lxml").select("a"):
        h = a.get("href", "")
        if re.search(pat, h) and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lliga_player_clubs "
        "(player_id INTEGER, temporada TEXT, club TEXT, encontre TEXT, "
        "PRIMARY KEY (player_id, temporada, club, encontre))"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS lliga_done_encontres (url TEXT PRIMARY KEY)")
    conn.commit()

    pmap = {_nm(r["nom"]): r["id"] for r in conn.execute("SELECT id, nom FROM players")}
    done = {r["url"] for r in conn.execute("SELECT url FROM lliga_done_encontres")}

    def get_pid(nom: str) -> int:
        key = _nm(nom)
        if key in pmap:
            return pmap[key]
        conn.execute(
            "INSERT OR IGNORE INTO players(fcb_id, nom, created_at, updated_at) "
            "VALUES (?,?,datetime('now'),datetime('now'))",
            ("name:" + key, nom),
        )
        pid = conn.execute("SELECT id FROM players WHERE fcb_id=?", ("name:" + key,)).fetchone()[0]
        pmap[key] = pid
        return pid

    total = 0
    with ScraperClient(s) as cl:
        hist = cl.fetch_html(f"{BASE}/ca/historial")
        for surl in _links(hist, r"llistatLliga/\d"):
            season = surl.rstrip("/").split("/")[-1]
            try:
                lst = cl.fetch_html(f"{BASE}/{surl.lstrip('/')}")
            except Exception:  # noqa: BLE001
                continue
            for dvurl in _links(lst, r"divisionsLliga/\d"):
                try:
                    dv = cl.fetch_html(f"{BASE}/{dvurl.lstrip('/')}")
                except Exception:  # noqa: BLE001
                    continue
                for gurl in _links(dv, r"grupsLliga/\d"):
                    try:
                        gp = cl.fetch_html(f"{BASE}/{gurl.lstrip('/')}")
                    except Exception:  # noqa: BLE001
                        continue
                    for jurl in _links(gp, r"jornadesLliga/\d"):
                        try:
                            jr = cl.fetch_html(f"{BASE}/{jurl.lstrip('/')}")
                        except Exception:  # noqa: BLE001
                            continue
                        for eurl in _links(jr, r"encontresLliga/\d"):
                            if eurl in done:
                                continue
                            try:
                                enc = cl.fetch_html(f"{BASE}/{eurl.lstrip('/')}")
                            except Exception:  # noqa: BLE001
                                continue
                            tm = _TEAMS_RE.search(_flat(enc))
                            purls = _links(enc, r"partidesLliga/\d")
                            done.add(eurl)
                            conn.execute("INSERT OR IGNORE INTO lliga_done_encontres(url) VALUES (?)", (eurl,))
                            if not tm or not purls:
                                continue
                            local_club, visit_club = _club(tm.group(1)), _club(tm.group(2))
                            try:
                                par = cl.fetch_html(f"{BASE}/{purls[0].lstrip('/')}")
                            except Exception:  # noqa: BLE001
                                continue
                            for loc, vis in _PAIR_RE.findall(_flat(par)):
                                for nom, club in ((loc, local_club), (vis, visit_club)):
                                    conn.execute(
                                        "INSERT OR IGNORE INTO lliga_player_clubs"
                                        "(player_id, temporada, club, encontre) VALUES (?,?,?,?)",
                                        (get_pid(nom.strip()), season, club, eurl),
                                    )
                                    total += 1
                            conn.commit()
            print(f"{season}: fet (acumulat {total} assignacions)", flush=True)
    print(f"FET. assignacions: {total}", flush=True)


if __name__ == "__main__":
    main()
