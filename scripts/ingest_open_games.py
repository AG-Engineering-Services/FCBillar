"""Ingest dels resultats reals (partides) dels opens/campionats individuals.

Per cada (torneig, divisió), segueix els enllaços reals publicats:
  - fases → eliminatòries
  - fases → grups → partides de grup

S'accepten tant els subenllaços actuals `/individuals/...` com els històrics
`/historial/...Individual/...`. Les dades es substitueixen divisió a divisió
només quan s'ha pogut llegir com a mínim una pàgina de fases.

Dos formats de partit:
  - eliminatòria: capçalera + 2 files (1 jugador cadascuna) + fila àrbitre/entrades
  - grup: capçalera + 1 fila amb els dos jugadors + àrbitre/entrades
El parser unificat detecta quants jugadors hi ha a la primera fila.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from contextlib import suppress
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient

BASE = "https://www.fcbillar.cat"
_PLAYER_RE = re.compile(r"(.+?)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)(?=\s|$)")
_GROUP_PHASE_RE = re.compile(r"/(?:individuals/grups|historial/grupsIndividual)/", re.I)
_GAME_PAGE_RE = re.compile(
    r"/(?:individuals/partides(?:grups|eliminatoria)|"
    r"historial/partides(?:grups|eliminatoria)Individual)/",
    re.I,
)


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


def linked_pages(html: str, pattern: re.Pattern[str]) -> list[str]:
    """Retorna, sense duplicats, els enllaços de navegació que compleixen el patró."""
    soup = BeautifulSoup(html, "lxml")
    pages: list[str] = []
    seen: set[str] = set()
    for link in soup.select("a[href]"):
        href = link.get("href", "").strip()
        if not pattern.search("/" + href.lstrip("/")):
            continue
        url = urljoin(f"{BASE}/", href)
        if url not in seen:
            seen.add(url)
            pages.append(url)
    return pages


def page_id(url: str) -> int:
    return int(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tournaments",
        help="IDs externs separats per comes; per defecte processa tots els torneigs",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Permet servir HTML de la cache (per defecte, fresc per detectar partides noves)",
    )
    args = parser.parse_args()
    selected = (
        {int(value) for value in args.tournaments.split(",")}
        if args.tournaments
        else None
    )
    use_cache = args.cache

    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    opens = conn.execute(
        "SELECT DISTINCT torneig_id_extern, divisio_id_extern FROM torneigs_individuals"
    ).fetchall()
    if selected is not None:
        opens = [row for row in opens if row["torneig_id_extern"] in selected]
    total = 0
    with ScraperClient(s) as cl:
        for i, o in enumerate(opens, 1):
            t, d = o["torneig_id_extern"], o["divisio_id_extern"]
            phase_html: list[str] = []
            with suppress(Exception):
                phase_html.append(
                    cl.fetch_html(f"{BASE}/ca/individuals/fases/{t}/{d}", use_cache=use_cache)
                )
            with suppress(Exception):
                phase_html.append(
                    cl.fetch_html(
                        f"{BASE}/ca/historial/fasesIndividual/{t}/{d}", use_cache=use_cache
                    )
                )
            if not phase_html:
                print(f"[{i}/{len(opens)}] {t}/{d}: FAIL fases", flush=True)
                continue

            pages: list[str] = []
            group_pages: list[str] = []
            for html in phase_html:
                pages.extend(linked_pages(html, _GAME_PAGE_RE))
                group_pages.extend(linked_pages(html, _GROUP_PHASE_RE))
            for group_url in dict.fromkeys(group_pages):
                try:
                    group_html = cl.fetch_html(group_url, use_cache=use_cache)
                except Exception:
                    continue
                pages.extend(linked_pages(group_html, _GAME_PAGE_RE))

            games: list[tuple] = []
            seen_games: set[tuple] = set()
            for url in dict.fromkeys(pages):
                try:
                    html = cl.fetch_html(url, use_cache=use_cache)
                except Exception:
                    continue
                for g in parse_partides(html):
                    row = (
                        t, d, page_id(url), g["p1"], g["car1"], g["serie1"], g["punts1"],
                        g["p2"], g["car2"], g["serie2"], g["punts2"], g["entrades"],
                    )
                    signature = row[2:]
                    if signature not in seen_games:
                        seen_games.add(signature)
                        games.append(row)

            conn.execute(
                "DELETE FROM torneig_partides WHERE torneig_id_extern=? AND divisio_id_extern=?",
                (t, d),
            )
            conn.executemany(
                """INSERT INTO torneig_partides
                (torneig_id_extern, divisio_id_extern, fase_id,
                 player1_nom, caramboles1, serie1, punts1,
                 player2_nom, caramboles2, serie2, punts2, entrades)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                games,
            )
            conn.commit()
            total += len(games)
            print(
                f"[{i}/{len(opens)}] {t}/{d}: {len(games)} partides "
                f"({len(dict.fromkeys(pages))} pàgines)",
                flush=True,
            )
    print(f"FET. total partides: {total}", flush=True)


if __name__ == "__main__":
    main()
