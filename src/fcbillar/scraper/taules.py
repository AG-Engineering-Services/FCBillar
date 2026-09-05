"""Lectura de les taules del web nou de la FCB.

Des del canvi d'agost de 2026 (vegeu `docs/canvi-web-fcb-2026.md`) totes les
pàgines de competició tenen la mateixa forma: targetes Bootstrap amb un títol
i, a dins, una taula amb `<thead>` de debò.

```html
<div class="card">
  <div class="card-header">Lliga</div>
  <div class="card-body">
    <table class="table table-bordered table-hover">
      <thead><tr><th>Data</th><th>Local</th>…</tr></thead>
      <tbody><tr><td>2026-03-15</td>…</tr></tbody>
    </table>
```

Abans cada pàgina feia servir una graella diferent i calia un parser a mida per
a cadascuna. Ara n'hi ha prou amb llegir les taules i mirar-ne el títol, així
que aquest mòdul és la base de tots els parsers: `taules()` retorna la pàgina
convertida en dades i els parsers només s'ocupen del significat de cada columna.

Les capçaleres es normalitzen (minúscules, sense accents ni signes) perquè
`fila["arbitre"]` funcioni tant si la federació escriu «Àrbitre» com «ARBITRE».
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup, Tag

# Text que el portal posa quan una taula no té dades. No és una fila: és un
# `<td colspan>` amb un missatge, i s'ha d'ignorar.
_BUIDA = "no hi ha registres disponibles"

_RE_ESPAIS = re.compile(r"\s+")
# Les targetes porten el comptador enganxat al títol: "GRUP A - ENCONTRES 3 registres".
_RE_COMPTADOR = re.compile(r"\s*(mostrant\s+)?\d+\s+registres\s*$", re.IGNORECASE)


def normalitza(s: str) -> str:
    """'Data límit inscripció' -> 'data limit inscripcio'."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("·", "").replace("/", " ").replace(".", " ")
    return _RE_ESPAIS.sub(" ", s).strip().lower()


def text_de(tag: Tag | None) -> str:
    if tag is None:
        return ""
    return _RE_ESPAIS.sub(" ", tag.get_text(" ", strip=True)).strip()


def enter(s: str | None) -> int | None:
    """Enter tolerant: '' i '-' són None, i els punts de miler no molesten."""
    if s is None:
        return None
    s = s.strip().replace(".", "").replace(",", "")
    if not s or s == "-":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def decimal(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip().replace(",", ".")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def data_iso(s: str | None) -> date | None:
    """El portal escriu sempre 'YYYY-MM-DD'."""
    if not s:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parell(s: str | None, sep: str = "/") -> tuple[int | None, int | None]:
    """Cel·les del tipus '5 / 3' o '28 / 30' -> (5, 3)."""
    if not s:
        return None, None
    parts = [p.strip() for p in s.split(sep)]
    if len(parts) != 2:
        return None, None
    return enter(parts[0]), enter(parts[1])


@dataclass(frozen=True)
class Fila:
    """Una fila de taula, accessible per nom de columna o per posició."""

    cel_les: tuple[Tag, ...]
    _index: dict[str, int]

    def __len__(self) -> int:
        return len(self.cel_les)

    def cel_la(self, col: str | int) -> Tag | None:
        i = col if isinstance(col, int) else self._index.get(normalitza(col), -1)
        if i < 0 or i >= len(self.cel_les):
            return None
        return self.cel_les[i]

    def __getitem__(self, col: str | int) -> str:
        return text_de(self.cel_la(col))

    def te(self, col: str) -> bool:
        return normalitza(col) in self._index

    def enter(self, col: str | int) -> int | None:
        return enter(self[col])

    def decimal(self, col: str | int) -> float | None:
        return decimal(self[col])

    def data(self, col: str | int) -> date | None:
        return data_iso(self[col])

    def parell(self, col: str | int) -> tuple[int | None, int | None]:
        return parell(self[col])

    def enllac(self, col: str | int | None = None) -> str | None:
        """Primer href de la cel·la, o de tota la fila si no es diu quina."""
        arrels = [self.cel_la(col)] if col is not None else list(self.cel_les)
        for arrel in arrels:
            if arrel is None:
                continue
            a = arrel.find("a", href=True)
            if a is not None:
                return str(a["href"])
        return None

    def enllacos(self) -> list[str]:
        return [str(a["href"]) for c in self.cel_les for a in c.find_all("a", href=True)]


@dataclass(frozen=True)
class Taula:
    """Una taula amb el títol de la targeta que la conté, si en té."""

    titol: str | None
    capcaleres: tuple[str, ...]
    files: tuple[Fila, ...]

    def __len__(self) -> int:
        return len(self.files)

    def __iter__(self):
        return iter(self.files)

    @property
    def titol_norm(self) -> str:
        return normalitza(self.titol or "")


def _titol_de(taula: Tag) -> str | None:
    """Text de la `.card-header` que embolcalla la taula, si n'hi ha."""
    for pare in taula.parents:
        if not isinstance(pare, Tag):
            continue
        classes = pare.get("class") or []
        if "card" in classes:
            capcalera = pare.find(class_="card-header")
            return _RE_COMPTADOR.sub("", text_de(capcalera)).strip() or None
        if pare.name == "body":
            break
    return None


def taules(html: str) -> list[Taula]:
    """Totes les taules de la pàgina, en ordre d'aparició."""
    soup = BeautifulSoup(html, "lxml")
    out: list[Taula] = []
    for taula in soup.find_all("table"):
        capcaleres = tuple(text_de(th) for th in taula.select("thead th"))
        if not capcaleres:
            # Sense <thead>: la capçalera és la primera fila que només té <th>.
            primera = taula.find("tr")
            if primera is not None and primera.find("th") is not None:
                capcaleres = tuple(text_de(th) for th in primera.find_all("th"))
        index = {normalitza(h): i for i, h in enumerate(capcaleres) if h}
        files: list[Fila] = []
        cos = taula.find("tbody") or taula
        for tr in cos.find_all("tr"):
            if tr.find("th") is not None:
                continue  # capçalera repetida
            cel_les = tr.find_all("td", recursive=False) or tr.find_all("td")
            if not cel_les:
                continue
            if len(cel_les) == 1 and _BUIDA in normalitza(text_de(cel_les[0])):
                continue
            files.append(Fila(tuple(cel_les), index))
        out.append(Taula(_titol_de(taula), capcaleres, tuple(files)))
    return out


def taula_amb(html_o_taules: str | list[Taula], *columnes: str) -> Taula | None:
    """La primera taula que tingui totes les columnes demanades.

    Serveix per no dependre de l'ordre en què la federació posa les targetes:
    demanem la taula per allò que en volem llegir, no per la posició.
    """
    llista = taules(html_o_taules) if isinstance(html_o_taules, str) else html_o_taules
    volgudes = [normalitza(c) for c in columnes]
    for t in llista:
        presents = {normalitza(h) for h in t.capcaleres}
        if all(c in presents for c in volgudes):
            return t
    return None


def taules_amb(html_o_taules: str | list[Taula], *columnes: str) -> list[Taula]:
    """Totes les taules que tenen les columnes demanades."""
    llista = taules(html_o_taules) if isinstance(html_o_taules, str) else html_o_taules
    volgudes = [normalitza(c) for c in columnes]
    return [t for t in llista if all(c in {normalitza(h) for h in t.capcaleres} for c in volgudes)]
