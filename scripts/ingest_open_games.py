"""Ingest dels resultats reals (partides) dels opens/campionats individuals.

Per cada (torneig, divisió):
  - fases → eliminatòries  (/individuals/partideseliminatoria/t/d/fase)
  - fases → grups → partides de grup (/individuals/partidesgrups/t/d/fase/grup)

Dos formats de partit:
  - eliminatòria: capçalera + 2 files (1 jugador cadascuna) + fila àrbitre/entrades
  - grup: capçalera + 1 fila amb els dos jugadors + àrbitre/entrades
El parser unificat detecta quants jugadors hi ha a la primera fila.
"""

from __future__ import annotations

import re
import sqlite3

from bs4 import BeautifulSoup

from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient

BASE = "https://www.fcbillar.cat"
_PLAYER_RE = re.compile(r"(.+?)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)(?=\s|$)")


def _players(txt: str):
    core = re.split(r"\bÀrbitre|\bArbitre", txt)[0]
    return _PLAYER_RE.findall(core)


def parse_partides(html: str):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for box in soup.select("div.row.box.black"):
        sib1 = box.find_next_sibling("div")
        if sib1 is None:
            continue
        txt1 = sib1.get_text(" ", strip=True)
        pls = _players(txt1)
        ent_txt = txt1
        if len(pls) >= 2:
            p1, p2 = pls[0], pls[1]
        elif len(pls) == 1:
            sib2 = sib1.find_next_sibling("div")
            if sib2 is None:
                continue
            m2 = _players(sib2.get_text(" ", strip=True))
            if not m2:
                continue
            p1, p2 = pls[0], m2[0]
            sib3 = sib2.find_next_sibling("div")
            ent_txt = sib3.get_text(" ", strip=True) if sib3 else ""
        else:
            continue
        em = re.search(r"Entrades:\s*(\d+)", ent_txt)
        out.append({
            "p1": p1[0].strip(), "punts1": int(p1[1]), "serie1": int(p1[2]), "car1": int(p1[3]),
            "p2": p2[0].strip(), "punts2": int(p2[1]), "serie2": int(p2[2]), "car2": int(p2[3]),
            "entrades": int(em.group(1)) if em else None,
        })
    return out


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    opens = conn.execute(
        "SELECT DISTINCT torneig_id_extern, divisio_id_extern FROM torneigs_individuals"
    ).fetchall()
    conn.execute("DELETE FROM torneig_partides")
    conn.commit()
    total = 0
    with ScraperClient(s) as cl:
        for i, o in enumerate(opens, 1):
            t, d = o["torneig_id_extern"], o["divisio_id_extern"]
            try:
                fases_html = cl.fetch_html(f"{BASE}/ca/individuals/fases/{t}/{d}")
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(opens)}] {t}/{d}: FAIL fases {e}", flush=True)
                continue
            soup = BeautifulSoup(fases_html, "lxml")
            elim, grupfases = set(), set()
            for a in soup.select("a"):
                h = a.get("href", "")
                m = re.search(r"partideseliminatoria/\d+/\d+/(\d+)", h)
                if m:
                    elim.add(int(m.group(1)))
                m = re.search(r"/individuals/grups/\d+/\d+/(\d+)", h)
                if m:
                    grupfases.add(int(m.group(1)))

            pages: list[tuple[int, str]] = []  # (fase_id, url)
            for f in sorted(elim):
                pages.append((f, f"{BASE}/ca/individuals/partideseliminatoria/{t}/{d}/{f}"))
            for f in sorted(grupfases):
                try:
                    ghtml = cl.fetch_html(f"{BASE}/ca/individuals/grups/{t}/{d}/{f}")
                except Exception:  # noqa: BLE001
                    continue
                for a in BeautifulSoup(ghtml, "lxml").select("a"):
                    m = re.search(r"partidesgrups/\d+/\d+/\d+/(\d+)", a.get("href", ""))
                    if m:
                        gid = int(m.group(1))
                        pages.append((gid, f"{BASE}/ca/individuals/partidesgrups/{t}/{d}/{f}/{gid}"))

            n = 0
            for fase_id, url in pages:
                try:
                    html = cl.fetch_html(url)
                except Exception:  # noqa: BLE001
                    continue
                for g in parse_partides(html):
                    conn.execute(
                        """INSERT INTO torneig_partides
                        (torneig_id_extern, divisio_id_extern, fase_id,
                         player1_nom, caramboles1, serie1, punts1,
                         player2_nom, caramboles2, serie2, punts2, entrades)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (t, d, fase_id, g["p1"], g["car1"], g["serie1"], g["punts1"],
                         g["p2"], g["car2"], g["serie2"], g["punts2"], g["entrades"]),
                    )
                    n += 1
            conn.commit()
            total += n
            print(f"[{i}/{len(opens)}] {t}/{d}: {n} partides", flush=True)
    print(f"FET. total partides: {total}", flush=True)


if __name__ == "__main__":
    main()
