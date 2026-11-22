"""Les proves espanyoles de Kozoom, a les taules de la RFEB (àmbit Espanya).

Kozoom té campionats d'Espanya, la final de la Lliga, el Gran Premi i torneigs
d'invitació jugats a Espanya. No són internacionals: a la fitxa han d'anar amb
les proves de la RFEB, no amb les de la UMB. Per això no es desen a
`umb_esdeveniments` sinó a `rfeb_proves`, `rfeb_classificacions` i
`rfeb_partides`.

Es desen en dues bases separades, perquè cada publicació reemplaça per prova:

- `noves`: les proves que la RFEB no té, amb id `kozoom/<id>`. Porten prova,
  classificació i partides, i es publiquen amb `publish_rfeb_individuals` i
  `publish_rfeb_partides`.
- `partides`: les partides de Kozoom d'una prova que la RFEB ja té però sense
  cap partida. Porta la fila de la prova tal com és al núvol i les partides, i
  només es publica amb `publish_rfeb_partides`. Si hi anés la classificació, la
  publicació deixaria la de la RFEB amb la de Kozoom.

Una prova que la RFEB ja té amb partides no es toca.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from fcbillar.kozoom import Titol
from fcbillar.umb import Llegit

_ESPANYOLA = re.compile(r"spain|spanish|españa", re.I)
_INTERNACIONAL = re.compile(r"world|europ|\bcup\b", re.I)

_MODALITATS = [
    (r"3[- ]{0,2}cushion|three[- ]?cushion", "3b"),
    (r"1[- ]{0,2}cushion|one[- ]?cushion", "banda"),
    (r"47[/-]2", "47_2"),
    (r"71[/-]2", "71_2"),
    (r"free|libre", "lliure"),
    (r"artisti", "artistic"),
]


def es_espanyola(titol: Titol) -> bool:
    """Una prova espanyola: campionat d'Espanya, lliga, gran premi o torneig jugat a Espanya.

    Els mundials i europeus jugats a Espanya són internacionals i no ho són.
    """
    if modalitat(titol) is None:
        return False  # «Carom Series» i altres que no són cap modalitat de carambola
    if _ESPANYOLA.search(titol.nom):
        return True
    return "(ESP)" in titol.lloc.upper() and not _INTERNACIONAL.search(titol.nom)


def modalitat(titol: Titol) -> str | None:
    text = f"{titol.disciplina} {titol.nom}"
    for patro, valor in _MODALITATS:
        if re.search(patro, text, re.I):
            return valor
    return None


def categoria(titol: Titol) -> str:
    n = titol.nom.lower()
    if "u21" in n or "under 21" in n:
        return "sub21"
    if "junior" in n:
        return "junior"
    if "ladies" in n or "women" in n:
        return "femeni"
    return "absolut"


def tipus(titol: Titol) -> str:
    n = titol.nom.lower()
    if "national" in n and "championship" in n:  # «Spain National Junior Championship»
        return "ce"
    if "grand prix" in n:
        return "gpe"
    if "league" in n:
        return "lliga"
    return "altres"


def temporada(d: date) -> str:
    a = d.year if d.month >= 8 else d.year - 1
    return f"{a}-{a + 1}"


def lloc(titol: Titol) -> str | None:
    net = re.sub(r"\(\w{3}\)", "", titol.lloc).strip(" -")
    return re.sub(r"\s+", " ", net) or None


def _sense_accents(text: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


@dataclass
class Existent:
    id: str
    partides: int


def ja_hi_es(titol: Titol, existents: list[dict]) -> Existent | None:
    """La prova de la RFEB que és aquesta: mateixa temporada, modalitat, tipus i categoria.

    Un gran premi se'n juga més d'un per temporada: ha de començar a menys d'una
    setmana. Les proves d'«altres» no es casen mai (cada torneig té el seu nom).
    """
    if titol.inici is None:
        return None
    t, m, ti, cat = temporada(titol.inici), modalitat(titol), tipus(titol), categoria(titol)
    if ti == "altres":
        return None
    for r in existents:
        if (r["temporada"], r["modalitat"], r["tipus"]) != (t, m, ti):
            continue
        # El «Junior» de Kozoom és el sub-17 de la RFEB (setembre-octubre).
        cats = {cat, "sub17"} if cat == "junior" else {cat}
        if r["categoria"] not in cats:
            continue
        if ti == "gpe":
            if r.get("data_inici"):
                if abs((date.fromisoformat(r["data_inici"][:10]) - titol.inici).days) > 7:
                    continue
            else:
                # Sense data, la ciutat: la RFEB la porta a l'id («res_gpe_3b_madrid»).
                ciutat = _sense_accents((lloc(titol) or "").split()[0] if lloc(titol) else "")
                if not ciutat or ciutat not in _sense_accents(f"{r['id']} {r.get('titol') or ''}"):
                    continue
        return Existent(r["id"], r.get("partides") or 0)
    return None


def _font(pid: str) -> str:
    return (
        "https://web.archive.org/web/2020/https://www.kozoom.com/en/billiard-carom/"
        f"results/{pid}/rankings.html"
    )


def _desa_partides(conn: sqlite3.Connection, prova_id: str, ll: Llegit) -> int:
    conn.execute("DELETE FROM rfeb_partides WHERE prova_id = ?", (prova_id,))
    files = [
        (
            prova_id, p.fase or "", p.grup or "", p.ordre, None, None,
            p.a.jugador, None, p.a.caramboles, p.a.serie, p.a.punts,
            p.b.jugador, None, p.b.caramboles, p.b.serie, p.b.punts,
            p.a.entrades,
        )
        for p in ll.partides
        if p.a.caramboles is not None and p.b.caramboles is not None and p.a.entrades
    ]  # fmt: skip
    conn.executemany(
        "INSERT OR IGNORE INTO rfeb_partides (prova_id, fase, grup, ordre, data, modalitat, "
        "jugador_a, equip_a, caramboles_a, serie_a, punts_a, jugador_b, equip_b, caramboles_b, "
        "serie_b, punts_b, entrades) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        files,
    )
    return len(files)


def desa_nova(conn: sqlite3.Connection, pid: str, titol: Titol, ll: Llegit) -> tuple[str, int, int]:
    """Desa una prova que la RFEB no té. Torna (id, classificats, partides)."""
    prova_id = f"kozoom/{pid}"
    conn.execute(
        "INSERT OR REPLACE INTO rfeb_proves (id, temporada, modalitat, categoria, tipus, titol, "
        "lloc, data_inici, data_fi, font) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            prova_id,
            temporada(titol.inici),
            modalitat(titol),
            categoria(titol),
            tipus(titol),
            titol.nom,
            lloc(titol),
            titol.inici.isoformat() if titol.inici else None,
            (titol.fi or titol.inici).isoformat() if titol.inici else None,
            _font(pid),
        ),
    )
    conn.execute("DELETE FROM rfeb_classificacions WHERE prova_id = ?", (prova_id,))
    if tipus(titol) == "lliga":
        # La classificació de la Lliga és d'equips («PAIPORTA», «C.B. MONTMELO»), no
        # de jugadors: només hi van les partides.
        return prova_id, 0, _desa_partides(conn, prova_id, ll)
    conn.executemany(
        "INSERT OR IGNORE INTO rfeb_classificacions (prova_id, posicio, jugador, caramboles, "
        "entrades, mitjana, serie_major, punts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (prova_id, c.posicio, c.jugador, c.caramboles, c.entrades, c.mitjana, c.serie1, c.punts)
            for c in ll.classificacio
        ],
    )
    return prova_id, len(ll.classificacio), _desa_partides(conn, prova_id, ll)


def desa_partides(conn: sqlite3.Connection, existent: dict, ll: Llegit) -> int:
    """Les partides de Kozoom d'una prova de la RFEB que no en té cap.

    La fila de la prova va tal com és al núvol (`publish_rfeb_partides` la torna a pujar).
    """
    cols = ("id", "temporada", "modalitat", "categoria", "tipus", "titol", "lloc",
            "data_inici", "data_fi", "font")  # fmt: skip
    conn.execute(
        f"INSERT OR REPLACE INTO rfeb_proves ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        tuple(existent.get(c) for c in cols),
    )
    return _desa_partides(conn, existent["id"], ll)


_TAULES_RFEB = ("rfeb_proves", "rfeb_classificacions", "rfeb_partides")


def crea_taules(conn: sqlite3.Connection) -> None:
    """Les tres taules de la RFEB, amb l'esquema de la base local."""
    from pathlib import Path

    esquema = (Path(__file__).parent / "db" / "schema.sql").read_text(encoding="utf-8")
    for taula in _TAULES_RFEB:
        m = re.search(rf"CREATE TABLE IF NOT EXISTS {taula} \(.*?\n\);", esquema, re.S)
        conn.execute(m.group(0))


@dataclass
class Carregada:
    pid: str
    nom: str
    estat: str  # nova | partides | ja_hi_es | buida
    detall: str = ""


def carrega(
    cache,
    ids: list[str],
    existents: list[dict],
    noves: sqlite3.Connection,
    partides: sqlite3.Connection,
) -> list[Carregada]:
    """Llegeix les proves `ids` de la carpeta de Kozoom i les desa a `noves` o a `partides`.

    `existents` són les proves de la RFEB del núvol (totes les columnes de
    `rfeb_proves` i `partides`, quantes en té).
    """
    from fcbillar.kozoom_carrega import llegeix_prova

    for c in (noves, partides):
        crea_taules(c)
    out: list[Carregada] = []
    for pid in ids:
        titol, ll = llegeix_prova(cache, pid)
        if titol is None or titol.inici is None:
            out.append(Carregada(pid, "", "buida", "sense títol o data"))
            continue
        nom = f"{titol.nom} · {titol.disciplina} · {titol.inici}"
        e = ja_hi_es(titol, existents)
        if e is None:
            if not (ll.classificacio or ll.partides):
                out.append(Carregada(pid, nom, "buida"))
                continue
            prova_id, nc, np_ = desa_nova(noves, pid, titol, ll)
            out.append(
                Carregada(pid, nom, "nova", f"{prova_id}: {nc} classificats, {np_} partides")
            )
        elif e.partides == 0 and ll.partides:
            fila = next(r for r in existents if r["id"] == e.id)
            n = desa_partides(partides, fila, ll)
            out.append(Carregada(pid, nom, "partides", f"{n} partides a {e.id}"))
        else:
            out.append(Carregada(pid, nom, "ja_hi_es", f"{e.id} ({e.partides} partides)"))
    noves.commit()
    partides.commit()
    return out
