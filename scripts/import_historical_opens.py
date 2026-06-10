"""Importa les classificacions dels opens 3 bandes de totes les temporades passades.

Font: /ca/historial → llistatIndividual/{temp} → divisionsIndividual/{torneig}
      → classificaciofinalIndividual/{torneig}/{divisio}

Les partides ja són a la BD (partideshome); aquí només associem la classificació
(posició per jugador) per poder calcular el Rànquing d'Opens (finestra de 5).
Els jugadors es lliguen per nom; si no existeixen, es crea un sintètic 'name:...'.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata

from bs4 import BeautifulSoup

from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient

BASE = "https://www.fcbillar.cat"
TRES_BANDES_MID = 1


def _nm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    return " ".join(s.strip().lower().split())


# Un open és del circuit de 3 bandes si diu OPEN i NO porta cap altra modalitat.
# (alguns es diuen "OPEN MATARO"/"OPEN COSTA DAURADA", sense "TRES BANDES")
_NO_3B = ("QUADRE", "LLIURE", "BANDA", "QUILLES", "ARTISTIC", "BIATHL", "600", "71/2", "47/2")


def is_3b_open(nom: str) -> bool:
    u = (nom or "").upper()
    if "OPEN" not in u:
        return False
    return not any(b in u for b in _NO_3B)


def modality_codi_of(nom: str) -> int:
    """Dedueix la modalitat (codi_fcb) del nom de la competició individual."""
    u = (nom or "").upper()
    if "TRES BANDES" in u or "3 BANDES" in u or "3B" in u:
        return 1
    if "47/2" in u:
        return 3
    if "71/2" in u:
        return 6
    if "LLIURE" in u:
        return 2
    if "QUADRE" in u:
        return 3
    if "BANDA" in u:  # després de "TRES BANDES"
        return 4
    return 1  # opens sense modalitat al nom = 3 bandes (per defecte)


def parse_classif(html: str):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tr in soup.select("table tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
        if len(tds) >= 9 and tds[0].isdigit():
            out.append({"pos": int(tds[0]), "nom": tds[1], "club": tds[2]})
    return out


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row

    pmap = {_nm(r["nom"]): r["id"] for r in conn.execute("SELECT id, nom FROM players")}
    have = {
        (r["torneig_id_extern"], r["divisio_id_extern"])
        for r in conn.execute("SELECT torneig_id_extern, divisio_id_extern FROM torneigs_individuals")
    }
    tmap = {r["nom"]: r["id"] for r in conn.execute("SELECT id, nom FROM temporades")}
    modmap = {r["codi_fcb"]: r["id"] for r in conn.execute("SELECT id, codi_fcb FROM modalitats")}
    next_id = conn.execute("SELECT MAX(id) FROM torneigs_individuals").fetchone()[0] or 0

    def get_pid(nom, club):
        key = _nm(nom)
        if key in pmap:
            return pmap[key]
        fcb = "name:" + key
        conn.execute(
            "INSERT OR IGNORE INTO players(fcb_id, nom, created_at, updated_at) "
            "VALUES (?,?,datetime('now'),datetime('now'))",
            (fcb, nom),
        )
        pid = conn.execute("SELECT id FROM players WHERE fcb_id=?", (fcb,)).fetchone()[0]
        pmap[key] = pid
        return pid

    def get_temporada(nom):
        if nom in tmap:
            return tmap[nom]
        conn.execute("INSERT INTO temporades(nom) VALUES (?)", (nom,))
        tid = conn.execute("SELECT id FROM temporades WHERE nom=?", (nom,)).fetchone()[0]
        tmap[nom] = tid
        return tid

    total_opens = 0
    with ScraperClient(s) as cl:
        hist = cl.fetch_html(f"{BASE}/ca/historial")
        seasons = [
            a.get("href") for a in BeautifulSoup(hist, "lxml").select("a") if "llistatIndividual" in a.get("href", "")
        ]
        for surl in seasons:
            season = surl.rstrip("/").split("/")[-1]
            tid_season = get_temporada(season)
            try:
                lst = cl.fetch_html(f"{BASE}/{surl.lstrip('/')}")
            except Exception as e:  # noqa: BLE001
                print(f"{season}: FAIL {e}", flush=True)
                continue
            for a in BeautifulSoup(lst, "lxml").select("a"):
                t = a.get_text(strip=True)
                if "divisionsIndividual" not in a.get("href", ""):
                    continue  # TOTES les competicions individuals (opens + campionats, totes modalitats)
                m = re.search(r"divisionsIndividual/(\d+)", a.get("href", ""))
                if not m:
                    continue
                torneig = int(m.group(1))
                try:
                    dv = cl.fetch_html(f"{BASE}/ca/historial/divisionsIndividual/{torneig}")
                except Exception:  # noqa: BLE001
                    continue
                for a2 in BeautifulSoup(dv, "lxml").select("a"):
                    m2 = re.search(r"classificaciofinalIndividual/(\d+)/(\d+)", a2.get("href", ""))
                    if not m2:
                        continue
                    tt, dd = int(m2.group(1)), int(m2.group(2))
                    if (tt, dd) in have:
                        continue
                    try:
                        cf = cl.fetch_html(f"{BASE}/ca/historial/classificaciofinalIndividual/{tt}/{dd}")
                    except Exception:  # noqa: BLE001
                        continue
                    rows = parse_classif(cf)
                    if not rows:
                        continue
                    have.add((tt, dd))
                    next_id += 1
                    internal = next_id
                    mod_id = modmap.get(modality_codi_of(t), modmap.get(1, TRES_BANDES_MID))
                    conn.execute(
                        "INSERT INTO torneigs_individuals(id, torneig_id_extern, divisio_id_extern, nom, modalitat_id, temporada_id) "
                        "VALUES (?,?,?,?,?,?)",
                        (internal, tt, dd, t, mod_id, tid_season),
                    )
                    for row in rows:
                        pid = get_pid(row["nom"], row["club"])
                        conn.execute(
                            "INSERT OR IGNORE INTO torneig_participants(torneig_id, player_id, posicio, club_text) "
                            "VALUES (?,?,?,?)",
                            (internal, pid, row["pos"], row["club"]),
                        )
                    conn.commit()
                    total_opens += 1
                    print(f"{season} · {t[:32]} ({tt}/{dd}): {len(rows)} jugadors", flush=True)
    print(f"FET. opens importats: {total_opens}", flush=True)


if __name__ == "__main__":
    main()
