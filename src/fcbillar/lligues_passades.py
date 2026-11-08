"""Les lligues de temporades passades: anàlisi, controls i publicació.

Les taules en viu del núvol (`lliga_*`, `lliga4m_*`) guarden cada fila amb el seu
`lliga_id`, però només s'hi publicava la lliga de la temporada en curs. La base
local, en canvi, té els encontres i les partides de lliga des del 2014-15.

Publicar-les és fàcil; publicar-les BÉ no tant, perquè les dades velles tenen
forats que les d'ara no tenen: lligues sense resultat d'encontre (les de Tres
Bandes del 2015-16 al 2018-19 es van ingerir des del rànquing), partides girades,
fases d'estiu amb el `temporada_id` de la temporada següent, una regla de punts
de matx que va canviar el 2021 (2-1-0 abans, 3-1-0 després)… Per això aquí res
no es publica sense passar abans per `analitza`, i el que no la supera no surt.

Els controls, de més greu a menys:

- ERROR (la lliga no es publica): mena o temporada desconegudes, grups sense
  nom, encontres sense resultat (més d'un 2 %), equips que no existeixen o que
  juguen contra ells mateixos, partides d'una modalitat que no és la de la
  lliga, caramboles negatives, un jugador contra ell mateix, o una
  classificació que no quadra amb l'oficial en més d'un 10 % dels equips.
- AVÍS (es publica, i surt a l'informe): encontres sense les quatre partides,
  parcials que no expliquen el resultat, partides sense entrades o sense
  sèrie, sèries més llargues que les caramboles (es publiquen buides), punts de
  partida que no diuen el mateix que el guanyador, mitjanes impossibles,
  partides que només surten a l'acta, i cada equip on la classificació oficial i la nostra no diuen el
  mateix (pot ser una sanció federativa).

La classificació oficial de cada grup es llegeix de la web de la federació (és
pública), i és el control més fort: és una font independent dels encontres.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from fcbillar import en_curs

#: Per sobre d'aquesta proporció d'encontres sense resultat, la lliga no surt.
MAX_SENSE_RESULTAT = 0.02
#: Per sobre d'aquesta proporció d'equips que no quadren amb l'oficial, tampoc.
MAX_EQUIPS_DESQUADRATS = 0.10
#: Una mitjana de partida per sobre d'això és un error de picat, no una gesta.
MITJANA_IMPOSSIBLE = {en_curs.MENA_3B: 3.5, en_curs.MENA_4M: 60.0}

ERROR = "error"
AVIS = "avis"


@dataclass
class Incidencia:
    nivell: str  # ERROR o AVIS
    tipus: str  # clau curta i estable, per comptar-les
    on: str  # encontre, partida o equip, llegible
    detall: str


@dataclass
class InformeLliga:
    lliga_id: int
    mena: str | None = None
    temporada: str | None = None
    encontres: int = 0
    amb_resultat: int = 0
    partides: int = 0
    grups: int = 0
    grups_amb_oficial: int = 0
    equips_comparats: int = 0
    equips_desquadrats: int = 0
    #: Grups on la taula oficial és la d'una altra fase: es publiquen amb la
    #: classificació calculada dels encontres, no amb l'oficial.
    grups_oficial_d_altra_fase: set[tuple[int, int]] = field(default_factory=set)
    incidencies: list[Incidencia] = field(default_factory=list)

    def afegeix(self, nivell: str, tipus: str, on: str, detall: str) -> None:
        self.incidencies.append(Incidencia(nivell, tipus, on, detall))

    @property
    def errors(self) -> list[Incidencia]:
        return [i for i in self.incidencies if i.nivell == ERROR]

    @property
    def publicable(self) -> bool:
        return not self.errors

    def resum(self) -> dict[str, int]:
        return dict(Counter(f"{i.nivell}:{i.tipus}" for i in self.incidencies))


# --- Quines lligues ---------------------------------------------------------


def lligues_en_curs(conn: sqlite3.Connection) -> set[int]:
    """Les lligues d'ara, que NO es toquen des d'aquí (les publica la nocturna)."""
    vives: set[int] = set()
    for mena in (en_curs.MENA_3B, en_curs.MENA_4M):
        vives.add(en_curs.lliga_en_curs(conn, mena))
    return vives


def lligues_passades(conn: sqlite3.Connection) -> list[int]:
    """Totes les lligues de la base local menys les de la temporada en curs.

    Si no se sap quines són les d'ara, `en_curs.NoDeterminat`: sense això no hi
    ha manera de garantir que no se'n toca cap de viva.
    """
    vives = lligues_en_curs(conn)
    totes = {r[0] for r in conn.execute("SELECT DISTINCT lliga_id FROM encontres_lliga")}
    # Una lliga més nova que les d'ara no és «passada»: és que el llistat va tard.
    sostre = min(vives)
    return sorted(i for i in totes - vives if i < sostre)


def mena_per_dades(conn: sqlite3.Connection, lliga_id: int) -> str | None:
    """'3B' o '4M' segons les modalitats que s'hi han jugat, no segons el nom.

    De les lligues velles no tenim el nom de la lliga (el llistat de la
    federació només ensenya les obertes). Les partides sí que ho diuen: a Tres
    Bandes totes són de tres bandes, i a 4 Modalitats cada encontre en juga
    diverses. Si no és clar, `None`, i la lliga no es publica.
    """
    files = conn.execute(
        """
        SELECT g.encontre_lliga_id AS eid, m.codi_fcb AS mod
        FROM games g
        JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
        JOIN modalitats m ON m.id = g.modalitat_id
        WHERE en.lliga_id = ?
        """,
        (lliga_id,),
    ).fetchall()
    if not files:
        return None
    mods = Counter(r[1] for r in files)
    if set(mods) == {1}:
        return en_curs.MENA_3B
    per_encontre: dict[int, set[int]] = defaultdict(set)
    for eid, mod in files:
        per_encontre[eid].add(mod)
    multi = sum(1 for s in per_encontre.values() if len(s) > 1)
    # 4 Modalitats: la gran majoria d'encontres amb més d'una modalitat.
    if multi >= 0.8 * len(per_encontre):
        return en_curs.MENA_4M
    return None


def temporada_de_lliga(conn: sqlite3.Connection, lliga_id: int) -> str | None:
    """'2018-2019': la de la primera data, que és sempre a la tardor."""
    any_inici = en_curs.any_d_inici_de_lliga_id(conn, lliga_id)
    return en_curs.amb_guio(any_inici) if any_inici is not None else None


# --- L'anàlisi --------------------------------------------------------------


def _punts_extres(text: str | None) -> tuple[int | None, int | None]:
    try:
        d = json.loads(text or "{}")
    except (ValueError, TypeError):
        return None, None
    return d.get("punts1"), d.get("punts2")


def analitza(
    conn: sqlite3.Connection,
    lliga_id: int,
    oficial: dict[tuple[int, int], list] | None = None,
) -> InformeLliga:
    """Revisa una lliga encontre per encontre i partida per partida.

    `oficial` és la classificació de la federació per grup, com la torna
    `cloud_sync._fetch_official_lliga_standings`. Sense ella no es pot fer el
    control de la classificació, i això sol ja és un ERROR: és el que garanteix
    que el que publiquem és el que la federació va donar per bo.
    """
    conn.row_factory = sqlite3.Row
    inf = InformeLliga(lliga_id)
    inf.mena = mena_per_dades(conn, lliga_id)
    inf.temporada = temporada_de_lliga(conn, lliga_id)
    if inf.mena is None:
        inf.afegeix(ERROR, "mena", f"lliga {lliga_id}", "no se sap si és de 3B o de 4M")
    if inf.temporada is None:
        inf.afegeix(ERROR, "temporada", f"lliga {lliga_id}", "cap encontre amb data")

    noms = {
        (r["divisio_id"], r["grup_id"]): r["nom"]
        for r in conn.execute(
            "SELECT divisio_id, grup_id, nom FROM lliga_noms WHERE lliga_id = ?", (lliga_id,)
        )
    }
    equips = {
        r["id"]: f"{r['nom']} {r['lletra'] or ''}".strip()
        for r in conn.execute(
            "SELECT e.id, e.lletra, c.nom FROM equips e JOIN clubs c ON c.id = e.club_id"
        )
    }
    from fcbillar.cloud_sync import es_descans

    encs = [
        e
        for e in conn.execute("SELECT * FROM encontres_lliga WHERE lliga_id = ?", (lliga_id,))
        # Les jornades de descans no són encontres i no es publiquen.
        if not es_descans(equips.get(e["equip_local_id"]))
        and not es_descans(equips.get(e["equip_visitant_id"]))
    ]
    inf.encontres = len(encs)
    grups = sorted({(e["divisio_id"], e["grup_id"]) for e in encs if e["grup_id"]})
    inf.grups = len(grups)

    for div, gid in grups:
        if (div, 0) not in noms or (div, gid) not in noms:
            inf.afegeix(ERROR, "grup_sense_nom", f"{div}/{gid}", "falta el nom a lliga_noms")

    games_per: dict[int, list] = defaultdict(list)
    for g in conn.execute(
        """
        SELECT g.*, m.codi_fcb AS mod, p1.fcb_id AS fcb1, p2.fcb_id AS fcb2
        FROM games g
        JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
        LEFT JOIN modalitats m ON m.id = g.modalitat_id
        LEFT JOIN players p1 ON p1.id = g.player1_id
        LEFT JOIN players p2 ON p2.id = g.player2_id
        WHERE en.lliga_id = ?
        """,
        (lliga_id,),
    ):
        games_per[g["encontre_lliga_id"]].append(g)

    actes = _actes_que_es_publicarien(conn, lliga_id)
    for e in encs:
        on = f"encontre {e['encontre_id_extern'] or e['id']} ({e['divisio_id']}/{e['grup_id']})"
        _analitza_encontre(inf, e, games_per.get(e["id"], []), equips, on)
        for a in actes.get(e["id"], []):
            _analitza_acta(inf, a, on)
        n = len(games_per.get(e["id"], [])) + len(actes.get(e["id"], []))
        if n != 4:
            inf.afegeix(AVIS, "partides_incompletes", on, f"{n} partides de 4")

    if inf.encontres and (inf.encontres - inf.amb_resultat) / inf.encontres > MAX_SENSE_RESULTAT:
        inf.afegeix(
            ERROR,
            "sense_resultat_massius",
            f"lliga {lliga_id}",
            f"{inf.encontres - inf.amb_resultat} de {inf.encontres} encontres sense resultat",
        )

    _compara_amb_oficial(conn, inf, lliga_id, grups, encs, oficial)
    return inf


def _analitza_encontre(inf: InformeLliga, e, games: list, equips: dict, on: str) -> None:
    loc, vis = e["equip_local_id"], e["equip_visitant_id"]
    if loc not in equips or vis not in equips:
        inf.afegeix(ERROR, "equip_desconegut", on, f"equips {loc} / {vis}")
    if loc == vis:
        inf.afegeix(ERROR, "equip_contra_si_mateix", on, equips.get(loc, str(loc)))
    if e["p_match_local"] is None or e["p_match_visitant"] is None:
        inf.afegeix(AVIS, "sense_resultat", on, "l'encontre no té resultat")
    else:
        inf.amb_resultat += 1
    if not e["data"]:
        inf.afegeix(AVIS, "sense_data", on, "l'encontre no té data")

    inf.partides += len(games)

    parcials_l = parcials_v = 0
    parcials_ok = True
    vistes: set[tuple] = set()
    for g in games:
        _analitza_partida(inf, g, on)
        sig = (g["player1_id"], g["player2_id"], g["caramboles1"], g["caramboles2"], g["entrades"])
        if sig in vistes:
            inf.afegeix(AVIS, "partida_duplicada", on, f"{sig}")
        vistes.add(sig)
        girada = g["equip1_id"] is not None and g["equip1_id"] == vis
        w = g["guanyador_id"]
        if w is None:
            x, y = 1, 1
        elif w == g["player1_id"]:
            x, y = 2, 0
        elif w == g["player2_id"]:
            x, y = 0, 2
        else:
            parcials_ok = False
            continue
        if girada:
            x, y = y, x
        parcials_l += x
        parcials_v += y

    ppl, ppv = e["p_parcials_local"], e["p_parcials_visitant"]
    if len(games) == 4 and parcials_ok and ppl is not None and ppv is not None:
        if (parcials_l, parcials_v) == (ppl, ppv):
            return
        if (parcials_l, parcials_v) == (ppv, ppl):
            inf.afegeix(
                AVIS,
                "partides_girades",
                on,
                f"les partides donen {parcials_l}-{parcials_v} i l'encontre {ppl}-{ppv}",
            )
        else:
            inf.afegeix(
                AVIS,
                "parcials_no_quadren",
                on,
                f"les partides donen {parcials_l}-{parcials_v} i l'encontre {ppl}-{ppv}",
            )


def _actes_que_es_publicarien(conn: sqlite3.Connection, lliga_id: int) -> dict[int, list]:
    """Les partides de l'acta (`lliga_pending_partides`) que el rànquing no té.

    `publish_lliga_encontres` publica les dues fonts amb dedup per signatura; les
    que no són duplicat també surten al web, i també s'han de revisar.
    """
    from fcbillar.cloud_sync import _sig_partida_lliga

    vistes: dict[int, set[str]] = defaultdict(set)
    for r in conn.execute(
        """
        SELECT g.encontre_lliga_id AS eid, p1.nom AS j1, g.caramboles1 AS c1,
               p2.nom AS j2, g.caramboles2 AS c2, g.entrades AS e
        FROM games g JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
        JOIN players p1 ON p1.id = g.player1_id JOIN players p2 ON p2.id = g.player2_id
        WHERE en.lliga_id = ?
        """,
        (lliga_id,),
    ):
        vistes[r["eid"]].add(_sig_partida_lliga(r["j1"], r["c1"], r["j2"], r["c2"], r["e"]))
    per: dict[int, list] = defaultdict(list)
    for r in conn.execute(
        """
        SELECT lp.rowid AS id, lp.* FROM lliga_pending_partides lp
        JOIN encontres_lliga en ON en.id = lp.encontre_lliga_id
        WHERE en.lliga_id = ?
        """,
        (lliga_id,),
    ):
        sig = _sig_partida_lliga(
            r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"]
        )
        if sig in vistes[r["encontre_lliga_id"]]:
            continue
        vistes[r["encontre_lliga_id"]].add(sig)
        per[r["encontre_lliga_id"]].append(r)
    return per


def _analitza_acta(inf: InformeLliga, a, on: str) -> None:
    """Una partida que només surt a l'acta: menys camps, els mateixos controls."""
    p = f"{on}, partida de l'acta ({a['player1_nom']} - {a['player2_nom']})"
    inf.partides += 1
    inf.afegeix(AVIS, "partida_nomes_a_l_acta", p, "el rànquing federatiu no la té")
    c1, c2, ent = a["caramboles1"], a["caramboles2"], a["entrades"]
    if inf.mena == en_curs.MENA_3B and a["modalitat_codi"] not in (None, 1):
        inf.afegeix(ERROR, "modalitat", p, f"modalitat {a['modalitat_codi']}")
    if c1 is None or c2 is None or c1 < 0 or c2 < 0:
        inf.afegeix(ERROR, "caramboles", p, f"{c1} / {c2}")
        return
    if _nom(a["player1_nom"]) == _nom(a["player2_nom"]):
        inf.afegeix(ERROR, "jugador_contra_si_mateix", p, a["player1_nom"])
    if not ent or ent <= 0:
        inf.afegeix(AVIS, "sense_entrades", p, f"entrades {ent}")
    elif max(c1, c2) / ent > MITJANA_IMPOSSIBLE.get(inf.mena or "", 60.0):
        inf.afegeix(AVIS, "mitjana_impossible", p, f"{max(c1, c2)} caramboles en {ent} entrades")
    for s, c, qui in ((a["serie1"], c1, "1"), (a["serie2"], c2, "2")):
        if s is not None and s > c:
            inf.afegeix(
                AVIS,
                "serie_impossible",
                p,
                f"jugador {qui}: sèrie {s} amb {c} caramboles; es publica buida",
            )


def _nom(n: str | None) -> str:
    from fcbillar.cloud_sync import _nm_simple

    return _nm_simple(n or "")


def _analitza_partida(inf: InformeLliga, g, on: str) -> None:
    p = f"{on}, partida {g['id']}"
    c1, c2, ent = g["caramboles1"], g["caramboles2"], g["entrades"]
    mena = inf.mena
    if mena == en_curs.MENA_3B and g["mod"] != 1:
        inf.afegeix(ERROR, "modalitat", p, f"modalitat {g['mod']} en una lliga de tres bandes")
    if c1 is None or c2 is None or c1 < 0 or c2 < 0:
        inf.afegeix(ERROR, "caramboles", p, f"{c1} / {c2}")
        return
    if g["player1_id"] == g["player2_id"]:
        inf.afegeix(ERROR, "jugador_contra_si_mateix", p, str(g["player1_id"]))
    if not ent or ent <= 0:
        inf.afegeix(AVIS, "sense_entrades", p, f"entrades {ent}")
    else:
        limit = MITJANA_IMPOSSIBLE.get(mena or "", 60.0)
        if max(c1, c2) / ent > limit:
            inf.afegeix(
                AVIS, "mitjana_impossible", p, f"{max(c1, c2)} caramboles en {ent} entrades"
            )
    for s, c, qui in ((g["serie_max1"], c1, "1"), (g["serie_max2"], c2, "2")):
        if s is None:
            inf.afegeix(AVIS, "sense_serie", p, f"jugador {qui}")
        elif s > c:
            inf.afegeix(
                AVIS,
                "serie_impossible",
                p,
                f"jugador {qui}: sèrie {s} amb {c} caramboles; es publica buida",
            )
    if not g["fcb1"] or not g["fcb2"]:
        inf.afegeix(AVIS, "jugador_sense_llicencia", p, "no sortirà al rànquing de jugadors")
    pu1, pu2 = _punts_extres(g["extras_json"])
    w = g["guanyador_id"]
    esperat = (2, 0) if w == g["player1_id"] else (0, 2) if w == g["player2_id"] else (1, 1)
    if pu1 is None or pu2 is None:
        inf.afegeix(AVIS, "sense_punts", p, "la partida no porta els punts")
    elif (pu1, pu2) != esperat:
        inf.afegeix(AVIS, "punts_vs_guanyador", p, f"punts {pu1}-{pu2}, guanyador {w}")
    # En una partida de lliga guanya qui fa més caramboles (mateixa distància).
    if mena == en_curs.MENA_3B and w is not None and c1 != c2:
        per_caramboles = g["player1_id"] if c1 > c2 else g["player2_id"]
        if w != per_caramboles:
            inf.afegeix(AVIS, "guanyador_vs_caramboles", p, f"{c1}-{c2} i guanya {w}")


def _compara_amb_oficial(
    conn: sqlite3.Connection,
    inf: InformeLliga,
    lliga_id: int,
    grups: list[tuple[int, int]],
    encs: list,
    oficial: dict[tuple[int, int], list] | None,
) -> None:
    """La classificació que surt dels encontres contra la de la federació."""
    from fcbillar import cloud_sync
    from fcbillar.db.repository import Repository

    if oficial is None:
        inf.afegeix(ERROR, "sense_oficial", f"lliga {lliga_id}", "no s'ha llegit l'oficial")
        return
    equips = {
        r["id"]: (r["nom"], r["fcb_id"], r["lletra"], r["club_id"])
        for r in conn.execute(
            "SELECT e.id, e.lletra, e.club_id, c.nom, c.fcb_id "
            "FROM equips e JOIN clubs c ON c.id = e.club_id"
        )
    }
    repo = Repository(conn)

    def _stats(filtre) -> dict[int, dict]:
        out: dict[int, dict] = defaultdict(lambda: {"pj": 0, "pf": 0, "ppf": 0})
        for e in encs:
            if not filtre(e) or e["p_match_local"] is None:
                continue
            for eq, pm, pp in (
                (e["equip_local_id"], e["p_match_local"], e["p_parcials_local"]),
                (e["equip_visitant_id"], e["p_match_visitant"], e["p_parcials_visitant"]),
            ):
                out[eq]["pj"] += 1
                out[eq]["pf"] += pm or 0
                out[eq]["ppf"] += pp or 0
        return out

    def _difs(r, s) -> list[str]:
        difs = []
        # Les classificacions velles porten la columna de jugats a zero: no diu res.
        if r.j and r.j != s["pj"]:
            difs.append(f"jugats {s['pj']} i l'oficial {r.j}")
        if r.pm != s["pf"]:
            difs.append(f"punts {s['pf']} i l'oficial {r.pm}")
        if r.pp is not None and r.pp != s["ppf"]:
            difs.append(f"parcials {s['ppf']} i l'oficial {r.pp}")
        return difs

    for div, gid in grups:
        off_rows = oficial.get((div, gid))
        if not off_rows:
            inf.afegeix(AVIS, "grup_sense_oficial", f"{div}/{gid}", "la federació no en dona cap")
            continue
        inf.grups_amb_oficial += 1
        stats = _stats(lambda e, div=div, gid=gid: (e["divisio_id"], e["grup_id"]) == (div, gid))
        # Algunes fases finals arrosseguen els punts de la fase regular: es
        # comparen també amb el total de la divisió.
        de_la_divisio = _stats(lambda e, div=div: e["divisio_id"] == div)
        # I algunes (finals i promocions de les temporades velles) ensenyen
        # directament la taula d'una ALTRA fase, on l'equip havia jugat abans.
        altres_fases = [
            _stats(lambda e, k=k: (e["divisio_id"], e["grup_id"]) == k)
            for k in grups
            if k != (div, gid)
        ]
        d_altra_fase = 0
        casats = cloud_sync._match_official_rows(off_rows, stats, equips, repo)
        per_fila = {id(r): eid for eid, r in casats.items()}
        for r in off_rows:
            on = f"{div}/{gid} {r.equip}"
            eid = per_fila.get(id(r)) or cloud_sync._equip_id_oficial(r.equip, equips, repo)
            inf.equips_comparats += 1
            if eid is None or eid not in stats:
                inf.equips_desquadrats += 1
                inf.afegeix(AVIS, "equip_oficial_sense_casar", on, "no és a cap encontre nostre")
                continue
            difs = _difs(r, stats[eid])
            if difs and not _difs(r, de_la_divisio[eid]):
                inf.afegeix(AVIS, "fase_amb_punts_acumulats", on, "l'oficial suma la fase regular")
                continue
            if difs and any(eid in a and not _difs(r, a[eid]) for a in altres_fases):
                d_altra_fase += 1
                inf.afegeix(
                    AVIS,
                    "oficial_d_una_altra_fase",
                    on,
                    "la taula oficial és la d'una altra fase; es publica la calculada",
                )
                continue
            if difs:
                inf.equips_desquadrats += 1
                inf.afegeix(AVIS, "classificacio_no_quadra", on, "; ".join(difs))
                # Els jugats no els canvia cap sanció: si no quadren, la taula
                # oficial no és la d'aquesta fase.
                if r.j and r.j != stats[eid]["pj"]:
                    d_altra_fase += 1
        if d_altra_fase:
            inf.grups_oficial_d_altra_fase.add((div, gid))
    if inf.equips_comparats and (
        inf.equips_desquadrats / inf.equips_comparats > MAX_EQUIPS_DESQUADRATS
    ):
        inf.afegeix(
            ERROR,
            "classificacio_massa_desquadrada",
            f"lliga {lliga_id}",
            f"{inf.equips_desquadrats} de {inf.equips_comparats} equips no quadren amb l'oficial",
        )


# --- L'informe --------------------------------------------------------------


def informe_markdown(informes: list[InformeLliga], *, detall_max: int = 40) -> str:
    """Un informe llegible: una taula de resum i, per lliga, les incidències."""
    out = ["# Lligues passades: anàlisi abans de publicar", ""]
    out.append(
        "| Lliga | Temporada | Mena | Encontres | Amb resultat | Partides | Grups (oficial) "
        "| Equips desquadrats | Errors | Avisos | Es publica |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i in informes:
        avisos = len(i.incidencies) - len(i.errors)
        out.append(
            f"| {i.lliga_id} | {i.temporada or '?'} | {i.mena or '?'} | {i.encontres} "
            f"| {i.amb_resultat} | {i.partides} | {i.grups} ({i.grups_amb_oficial}) "
            f"| {i.equips_desquadrats}/{i.equips_comparats} | {len(i.errors)} | {avisos} "
            f"| {'sí' if i.publicable else '**no**'} |"
        )
    for i in informes:
        out += ["", f"## Lliga {i.lliga_id} · {i.temporada or '?'} · {i.mena or '?'}", ""]
        if not i.incidencies:
            out.append("Cap incidència.")
            continue
        for clau, n in sorted(i.resum().items()):
            out.append(f"- `{clau}`: {n}")
        out.append("")
        per_tipus: dict[str, list[Incidencia]] = defaultdict(list)
        for inc in i.incidencies:
            per_tipus[inc.tipus].append(inc)
        for tipus, llista in sorted(per_tipus.items()):
            out.append(f"### {tipus}")
            for inc in llista[:detall_max]:
                out.append(f"- [{inc.nivell}] {inc.on}: {inc.detall}")
            if len(llista) > detall_max:
                out.append(f"- … i {len(llista) - detall_max} més")
            out.append("")
    return "\n".join(out) + "\n"


# --- Publicar i comprovar ---------------------------------------------------


def publica(db_path, inf: InformeLliga, prog) -> dict[str, int]:
    """Publica una lliga passada que ha superat `analitza`, i ho comprova.

    Les mateixes funcions que la nocturna, amb tres diferències: es compta tota
    la lliga (no un sol `temporada_id`), no s'arxiva res (l'arxivat donaria per
    passada la lliga d'ara) i al final es torna a llegir el núvol per veure que
    hi ha exactament el que s'hi ha enviat.
    """
    from fcbillar import cloud_sync as cs

    if not inf.publicable:
        raise ValueError(f"lliga {inf.lliga_id}: no ha superat l'anàlisi; no es publica")
    taules = cs._TAULES_3B if inf.mena == en_curs.MENA_3B else cs._TAULES_4M
    counts: dict[str, int] = {}
    counts.update(
        cs.publish_lliga(
            db_path,
            prog,
            True,
            inf.lliga_id,
            taules=taules,
            tota_la_lliga=True,
            arxiva=False,
            ignora_oficial=inf.grups_oficial_d_altra_fase,
        )
    )
    counts.update(
        cs.publish_lliga_encontres(
            db_path, prog, lliga_id=inf.lliga_id, taules=taules, tota_la_lliga=True
        )
    )
    if inf.mena == en_curs.MENA_3B:
        # El rànquing de jugadors per grup només existeix per a Tres Bandes.
        counts.update(
            cs.publish_lliga_player_rankings(db_path, prog, inf.lliga_id, tota_la_lliga=True)
        )
    verifica(db_path, inf, taules, counts)
    return counts


class VerificacioFallida(RuntimeError):
    """El núvol no té el que s'hi acaba d'enviar."""


def verifica(db_path, inf: InformeLliga, taules, counts: dict[str, int]) -> None:
    """Torna a llegir el núvol i compara amb la base local, taula per taula."""
    from fcbillar import cloud_sync as cs

    sb = cs.get_client()
    conn = sqlite3.connect(str(db_path))
    try:
        divisions = sorted(
            {
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT divisio_id FROM encontres_lliga WHERE lliga_id = ?",
                    (inf.lliga_id,),
                )
            }
        )
        from fcbillar.cloud_sync import es_descans

        n_encontres = sum(
            1
            for loc, vis in conn.execute(
                "SELECT cl.nom, cv.nom FROM encontres_lliga e "
                "LEFT JOIN equips l ON l.id = e.equip_local_id "
                "LEFT JOIN clubs cl ON cl.id = l.club_id "
                "LEFT JOIN equips v ON v.id = e.equip_visitant_id "
                "LEFT JOIN clubs cv ON cv.id = v.club_id WHERE e.lliga_id = ?",
                (inf.lliga_id,),
            )
            if not es_descans(loc) and not es_descans(vis)
        )
    finally:
        conn.close()

    problemes: list[str] = []
    grups = cs._totes_amb(
        lambda: sb.table(taules.groups).select("grup_id,temporada").eq("lliga_id", inf.lliga_id)
    )
    if len(grups) != counts.get(taules.groups, -1):
        problemes.append(
            f"{taules.groups}: {len(grups)} al núvol i {counts.get(taules.groups)} enviats"
        )
    temporades = {g.get("temporada") for g in grups if "temporada" in g}
    if temporades and temporades != {inf.temporada}:
        problemes.append(f"{taules.groups}: temporades {temporades}, s'esperava {inf.temporada}")
    classif = cs._totes_amb(
        lambda: sb.table(taules.standings).select("grup_id").eq("lliga_id", inf.lliga_id)
    )
    if len(classif) < counts.get(taules.standings, 0):
        problemes.append(
            f"{taules.standings}: {len(classif)} al núvol i {counts.get(taules.standings)} enviats"
        )
    encs = cs._totes_amb(
        lambda: sb.table(taules.encontres).select("encontre_id").in_("divisio_id", divisions)
    )
    if len(encs) != n_encontres or len(encs) != counts.get(taules.encontres, -1):
        problemes.append(
            f"{taules.encontres}: {len(encs)} al núvol, {counts.get(taules.encontres)} enviats "
            f"i {n_encontres} a la base"
        )
    ids = [e["encontre_id"] for e in encs]
    partides = 0
    for i in range(0, len(ids), 200):
        tram = ids[i : i + 200]
        partides += len(
            cs._totes_amb(
                lambda tram=tram: sb.table(taules.partides).select("ordre").in_("encontre_id", tram)
            )
        )
    if partides != counts.get(taules.partides, -1):
        problemes.append(
            f"{taules.partides}: {partides} al núvol i {counts.get(taules.partides)} enviades"
        )
    if problemes:
        raise VerificacioFallida(f"lliga {inf.lliga_id}: " + " · ".join(problemes))
