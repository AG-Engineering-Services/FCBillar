"""Avisos push de resultats nous a la PWA (la campana de la capçalera).

Dues fonts, cadascuna enganxada on les dades ja són a la memòria:

- `avisa_opens`: des de `publish_live_opens`, a cada passada de ~2 min del cap de
  setmana. Partides acabades dels opens en directe: totes les de 3 bandes, i les
  dels jugadors del Banyoles de qualsevol modalitat.
- `avisa_reingesta`: després de `publish-cloud`, a la reingesta. Encontres de lliga
  i de Copa del Banyoles, i partides dels seus jugadors als campionats de Catalunya.

Cada resultat té una clau estable. Les ja avisades es desen a `avisos_enviats`, i
cada subscripció només rep els tipus que té marcats (els identificadors de
`TIPUS` han de coincidir amb web/src/lib/avisos.ts). Un missatge per open o
competició i per passada: en un open de 3 bandes hi ha massa partides per a una
notificació cadascuna.

La primera vegada que corre una font no envia res: marca com a avisat tot el que
ja hi ha. Sense això, el primer tret hauria enviat tota la temporada.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

TIPUS = ("opens_3b", "banyoles_lliga", "banyoles_opens", "banyoles_copa_camp")

# El `sub` del VAPID: els serveis de push (Apple, Google) hi escriuen si cal.
# L'adreça del web i no un correu personal.
VAPID_SUB = "https://seguiment-lliga-open.vercel.app"

# Si una passada de reingesta en troba més de nous que això, gairebé segur que
# no són resultats nous sinó claus que han canviat (una base refeta): es marquen
# sense enviar. Els opens en directe en poden donar molts de cop legítimament.
MAX_NOUS_REINGESTA = 40
LINIES_PER_MISSATGE = 8

Progress = Callable[[str, str], None]


@dataclass
class Resultat:
    clau: str
    tipus: frozenset[str]
    grup: str  # un missatge per grup: un open, una lliga, una competició
    titol: str
    linia: str
    url: str
    destacat: bool = False  # hi juga el Banyoles: va al davant i amb estrella
    ordre: int = field(default=0, compare=False)


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def es_banyoles(text: str | None) -> bool:
    return "BANYOLES" in _norm(text)


def _curt(nom: str | None) -> str:
    """«GARRIGA COMAS, JORDI» → «Garriga Comas»: a la notificació hi cap poc."""
    cognoms = (nom or "?").split(",")[0].strip()
    return cognoms.title()


def _equip(nom: str | None) -> str:
    """«C.B.BANYOLES A» → «Banyoles A»."""
    s = re.sub(r"^\s*(C\.?\s*B\.?|B\.?\s*C\.?|C\.?\s*E\.?|A\.?\s*B\.?)\s*", "", nom or "?")
    return s.replace('"', "").strip().title()


# --- Opens en directe --------------------------------------------------------


def _es_3b(nom: str, modalitat: str | None) -> bool:
    if modalitat == "Tres Bandes":
        return True
    return bool(re.search(r"TRES ?BANDES|3 ?BANDES|\b3B\b", _norm(nom)))


def _decidida(m: dict) -> bool:
    # Jugada, o guanyada per incompareixença (punts sense entrades).
    return bool(m.get("is_played")) or (m.get("punts_a") or 0) + (m.get("punts_b") or 0) > 0


def _clubs_del_payload(payload: dict) -> dict[str, str]:
    clubs: dict[str, str] = {}
    for c in payload.get("classification") or []:
        if c.get("player_name") and c.get("club"):
            clubs[c["player_name"]] = c["club"]
    for ph in payload.get("phases") or []:
        for g in ph.get("groups") or []:
            for s in g.get("standings") or []:
                if s.get("player_name") and s.get("club"):
                    clubs.setdefault(s["player_name"], s["club"])
    return clubs


def _linia_partida(prefix: str, m: dict) -> str:
    a, b = _curt(m.get("player_a")), _curt(m.get("player_b"))
    ca, cb = m.get("caramboles_a"), m.get("caramboles_b")
    entr = m.get("entrades")
    if not m.get("is_played"):
        return f"{prefix}{a} - {b}: incompareixença"
    cola = f" ({entr} e.)" if entr else ""
    return f"{prefix}{a} {ca}-{cb} {b}{cola}"


def resultats_opens(
    files_open_live: Iterable[dict],
    banyoles_noms: set[str] = frozenset(),
    banyoles_ids: set[str] = frozenset(),
) -> list[Resultat]:
    """Partides decidides dels opens en directe que interessen a algun tipus.

    El club del payload sovint ve buit (el portal no el dona a totes les fases):
    per això també es mira si el jugador és als afiliats del Banyoles
    (`banyoles_noms`, normalitzats) o si el seu id hi és (`banyoles_ids`).
    """
    out: list[Resultat] = []
    for row in files_open_live:
        div = row.get("fcb_division_id")
        nom = row.get("name") or "Open"
        payload = row.get("payload_json") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        es3b = _es_3b(nom, row.get("modality"))
        clubs = _clubs_del_payload(payload)
        ids = payload.get("player_ids") or {}

        def del_banyoles(nom: str, clubs=clubs, ids=ids) -> bool:
            return (
                es_banyoles(clubs.get(nom))
                or _norm(nom) in banyoles_noms
                or str(ids.get(nom, "")) in banyoles_ids
            )

        n = 0
        for ph in payload.get("phases") or []:
            fase = ph.get("label") or ""
            blocs = [(g.get("label") or "", g.get("matches") or []) for g in ph.get("groups") or []]
            blocs.append(("", ph.get("ko_matches") or []))
            for grup, partides in blocs:
                for m in partides:
                    if not _decidida(m):
                        continue
                    a, b = m.get("player_a") or "", m.get("player_b") or ""
                    banyoles = del_banyoles(a) or del_banyoles(b)
                    tipus = set()
                    if es3b:
                        tipus.add("opens_3b")
                    if banyoles:
                        tipus.add("banyoles_opens")
                    if not tipus:
                        continue
                    on = grup or fase
                    n += 1
                    out.append(
                        Resultat(
                            clau=f"open:{div}:{fase}:{grup}:{'|'.join(sorted((a, b)))}",
                            tipus=frozenset(tipus),
                            grup=f"open:{div}",
                            titol=nom.title(),
                            linia=_linia_partida(f"{on}: " if on else "", m),
                            url=f"/opens/directe/{div}",
                            destacat=banyoles,
                            ordre=n,
                        )
                    )
    return out


# --- Reingesta: lliga, Copa i campionats --------------------------------------


def _llegeix(fes: Callable[[], object]) -> list[dict]:
    """Totes les files paginant. La consulta ha de dur un ordre total: si no, les
    pàgines es trepitgen i surten files repetides i d'altres perdudes."""
    from fcbillar.cloud_sync import _totes_amb

    return _totes_amb(fes)


def _partides_guanyades(partides: list[dict]) -> tuple[int, int]:
    gl = sum(
        1
        for p in partides
        if (p.get("caramboles_local") or 0) > (p.get("caramboles_visitant") or 0)
    )
    gv = sum(
        1
        for p in partides
        if (p.get("caramboles_visitant") or 0) > (p.get("caramboles_local") or 0)
    )
    return gl, gv


def _resultats_lliga(sb, prefix: str, nom_lliga: str) -> list[Resultat]:
    taula = f"{prefix}_encontres"
    files = _llegeix(
        lambda: (
            sb.table(taula)
            .select(
                "encontre_id,divisio_id,grup_id,data,equip_local,equip_visitant,gols_local,gols_visitant"
            )
            .or_("equip_local.ilike.*BANYOLES*,equip_visitant.ilike.*BANYOLES*")
            .not_.is_("gols_local", "null")
            .lt("encontre_id", 10_000_000)  # els de sota són els jugats; els altres, provisionals
            .order("encontre_id")
        )
    )
    if not files:
        return []
    tots_grups = _llegeix(
        lambda: (
            sb.table(f"{prefix}_groups")
            .select("divisio_id,grup_id,divisio_nom,grup_nom,temporada")
            .order("divisio_id")
            .order("grup_id")
        )
    )
    # La taula també guarda les temporades passades: només la d'ara.
    actual = max((g.get("temporada") or "" for g in tots_grups), default="")
    grups = {
        (g["divisio_id"], g["grup_id"]): g
        for g in tots_grups
        if (g.get("temporada") or "") == actual
    }
    files = [f for f in files if (f["divisio_id"], f["grup_id"]) in grups]
    if not files:
        return []
    ids = [f["encontre_id"] for f in files]
    partides: dict[int, list[dict]] = {}
    for i in range(0, len(ids), 200):
        tros = ids[i : i + 200]
        for p in _llegeix(
            lambda tros=tros: (
                sb.table(f"{prefix}_partides")
                .select("encontre_id,ordre,caramboles_local,caramboles_visitant")
                .in_("encontre_id", tros)
                .order("encontre_id")
                .order("ordre")
            )
        ):
            partides.setdefault(p["encontre_id"], []).append(p)
    out = []
    for f in files:
        g = grups.get((f["divisio_id"], f["grup_id"])) or {}
        on = " ".join(x for x in (g.get("divisio_nom"), g.get("grup_nom")) if x).title()
        pl, pv = _partides_guanyades(partides.get(f["encontre_id"], []))
        marcador = f"{pl}-{pv}" if (pl or pv) else f"{f['gols_local']}-{f['gols_visitant']}"
        punts = f" · {f['gols_local']}-{f['gols_visitant']} punts" if (pl or pv) else ""
        out.append(
            Resultat(
                clau=f"{prefix}:{f['encontre_id']}",
                tipus=frozenset({"banyoles_lliga"}),
                grup=prefix,
                titol=f"{nom_lliga}: encontres del Banyoles",
                linia=(
                    f"{on + ': ' if on else ''}{_equip(f['equip_local'])} {marcador} "
                    f"{_equip(f['equip_visitant'])}{punts}"
                ),
                url="/lliga",
                destacat=True,
            )
        )
    return out


def _resultats_copa(sb) -> list[Resultat]:
    files = _llegeix(
        lambda: (
            sb.table("copa_encontres")
            .select("jornada,grup_id,grup_nom,equip_local,equip_visitant,gols_local,gols_visitant")
            .or_("equip_local.ilike.*BANYOLES*,equip_visitant.ilike.*BANYOLES*")
            .not_.is_("gols_local", "null")
            .order("encontre_id")
        )
    )
    out = []
    for f in files:
        # `encontre_id` de la Copa és l'autoincrement de la base local: no és estable.
        clau = f"copa:{f['jornada']}:{f['grup_id']}:{f['equip_local']}|{f['equip_visitant']}"
        on = (f.get("grup_nom") or "").title()
        out.append(
            Resultat(
                clau=clau,
                tipus=frozenset({"banyoles_copa_camp"}),
                grup="copa",
                titol="Copa: encontres del Banyoles",
                linia=(
                    f"{on + ': ' if on else ''}{_equip(f['equip_local'])} "
                    f"{f['gols_local']}-{f['gols_visitant']} {_equip(f['equip_visitant'])}"
                ),
                url="/copa",
                destacat=True,
            )
        )
    return out


def banyoles_de_la_temporada(sb) -> tuple[set[str], set[str]]:
    """(noms normalitzats, ids) dels jugadors del Banyoles d'ara."""
    noms: set[str] = set()
    darrer = (
        sb.table("afiliacions")
        .select("temporada")
        .order("temporada", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if darrer:
        noms = _jugadors_banyoles(sb, darrer[0]["temporada"])
    ids = {
        str(f["fcb_id"])
        for f in _llegeix(
            lambda: (
                sb.table("players")
                .select("fcb_id")
                .eq("club_fcb_id", "C.B.BANYOLES")
                .order("fcb_id")
            )
        )
    }
    return noms, ids


def _jugadors_banyoles(sb, temporada: str) -> set[str]:
    """Noms normalitzats dels afiliats al Banyoles aquesta temporada."""
    temporada_barra = temporada.replace("-", "/")
    files = _llegeix(
        lambda: (
            sb.table("afiliacions")
            .select("jugador")
            .eq("temporada", temporada_barra)
            .ilike("club", "*BANYOLES*")
            .order("jugador")
            .order("competicio")
        )
    )
    return {_norm(f["jugador"]) for f in files if f.get("jugador")}


def _resultats_campionats(sb) -> list[Resultat]:
    darrer = (
        sb.table("opens").select("temporada").order("temporada", desc=True).limit(1).execute().data
    )
    if not darrer:
        return []
    temporada = darrer[0]["temporada"]
    campionats = {
        o["open_id"]: o
        for o in _llegeix(
            lambda: (
                sb.table("opens")
                .select("open_id,nom,temporada")
                .eq("tipus", "campionat")
                .eq("temporada", temporada)
                .order("open_id")
            )
        )
    }
    if not campionats:
        return []
    nostres = _jugadors_banyoles(sb, temporada)
    if not nostres:
        return []
    ids = list(campionats)
    fases = {
        (f["open_id"], f["fase_id"]): f.get("nom") or ""
        for f in _llegeix(
            lambda: (
                sb.table("open_fases")
                .select("open_id,fase_id,nom")
                .in_("open_id", ids)
                .order("open_id")
                .order("fase_id")
            )
        )
    }
    out = []
    for p in _llegeix(
        lambda: (
            sb.table("open_partides")
            .select(
                "open_id,fase_id,ordre,grup_nom,jugador_local,caramboles_local,jugador_visitant,caramboles_visitant,entrades"
            )
            .in_("open_id", ids)
            .order("open_id")
            .order("fase_id")
            .order("ordre")
        )
    ):
        a, b = p.get("jugador_local") or "", p.get("jugador_visitant") or ""
        if _norm(a) not in nostres and _norm(b) not in nostres:
            continue
        camp = campionats[p["open_id"]]
        fase = fases.get((p["open_id"], p["fase_id"]), "")
        on = " ".join(x for x in (fase.title(), p.get("grup_nom") or "") if x)
        entr = p.get("entrades")
        out.append(
            Resultat(
                # Pel nom i la temporada, no per `open_id`, que és l'id de la base local.
                clau=(
                    f"camp:{camp['temporada']}:{camp['nom']}:{fase}:{p.get('grup_nom') or ''}:"
                    f"{'|'.join(sorted((a, b)))}"
                ),
                tipus=frozenset({"banyoles_copa_camp"}),
                grup=f"camp:{p['open_id']}",
                titol=f"Camp. Catalunya: {camp['nom']}",
                linia=(
                    f"{on + ': ' if on else ''}{_curt(a)} {p.get('caramboles_local')}-"
                    f"{p.get('caramboles_visitant')} {_curt(b)}{f' ({entr} e.)' if entr else ''}"
                ),
                url="/campionats",
                destacat=True,
            )
        )
    return out


def resultats_reingesta(sb, prog: Progress) -> list[Resultat]:
    out: list[Resultat] = []
    fonts = (
        ("lliga", lambda: _resultats_lliga(sb, "lliga", "Lliga")),
        ("lliga4m", lambda: _resultats_lliga(sb, "lliga4m", "Lliga 4 Modalitats")),
        ("copa", lambda: _resultats_copa(sb)),
        ("campionats", lambda: _resultats_campionats(sb)),
    )
    for nom, font in fonts:
        # Una font que falla no ha d'impedir avisar de les altres.
        try:
            out.extend(font())
        except Exception as exc:
            prog("warn", f"avisos: no s'han pogut llegir els resultats de {nom}: {exc}")
    return out


# --- Missatges i enviament ------------------------------------------------------


def missatges(tipus_subscrits: Iterable[str], nous: list[Resultat]) -> list[dict]:
    """Un missatge per grup amb els resultats nous que toquen a aquesta subscripció."""
    volguts = set(tipus_subscrits)
    per_grup: dict[str, list[Resultat]] = {}
    for r in nous:
        if r.tipus & volguts:
            per_grup.setdefault(r.grup, []).append(r)
    out = []
    for rs in per_grup.values():
        rs = sorted(rs, key=lambda r: (not r.destacat, r.ordre))
        linies = [("★ " if r.destacat and len(rs) > 1 else "") + r.linia for r in rs]
        if len(linies) > LINIES_PER_MISSATGE:
            resta = len(linies) - (LINIES_PER_MISSATGE - 1)
            linies = [*linies[: LINIES_PER_MISSATGE - 1], f"i {resta} més"]
        titol = rs[0].titol
        if len(rs) > 1:
            titol += f" · {len(rs)} resultats"
        out.append({"title": titol, "body": "\n".join(linies), "url": rs[0].url, "tag": None})
    return out


def _ja_avisades(sb, claus: list[str]) -> set[str]:
    vistes: set[str] = set()
    for i in range(0, len(claus), 150):
        tros = claus[i : i + 150]
        dades = sb.table("avisos_enviats").select("clau").in_("clau", tros).execute().data or []
        vistes.update(d["clau"] for d in dades)
    return vistes


def _marca(sb, claus: list[str]) -> None:
    from fcbillar.cloud_sync import _MINIM

    for i in range(0, len(claus), 500):
        sb.table("avisos_enviats").upsert(
            [{"clau": c} for c in claus[i : i + 500]],
            on_conflict="clau",
            ignore_duplicates=True,
            returning=_MINIM,
        ).execute()


def _envia_un(sub: dict, missatge: dict, clau_privada: str) -> int | None:
    """Envia un missatge. Retorna el codi HTTP si el servei el rebutja."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            },
            data=json.dumps(missatge, ensure_ascii=False),
            vapid_private_key=clau_privada,
            vapid_claims={"sub": VAPID_SUB},
            ttl=6 * 3600,
            timeout=20,
        )
        return None
    except WebPushException as exc:
        return exc.response.status_code if exc.response is not None else -1


def _avisa(
    sb,
    origen: str,
    resultats: list[Resultat],
    prog: Progress,
    *,
    max_nous: int | None,
    clau_privada: str | None,
) -> dict[str, int]:
    from fcbillar.cloud_sync import esquema_encara_no_hi_es

    compte = {"avisos_nous": 0, "avisos_enviats": 0, "avisos_errors": 0}
    clau_privada = clau_privada or os.environ.get("VAPID_PRIVATE_KEY")
    if not clau_privada:
        prog("warn", "avisos: falta VAPID_PRIVATE_KEY; no s'avisa de res")
        return compte
    base = f"base:{origen}"
    try:
        claus = sorted({r.clau for r in resultats})
        vistes = _ja_avisades(sb, [base, *claus])
    except Exception as exc:
        if esquema_encara_no_hi_es(exc):
            prog("warn", "avisos: el Data API encara no veu `avisos_enviats`; no s'avisa de res")
            return compte
        raise
    if base not in vistes:
        _marca(sb, [*claus, base])
        prog(
            "ok", f"avisos ({origen}): primera passada, {len(claus)} resultats marcats sense avisar"
        )
        return compte
    nous = [r for r in resultats if r.clau not in vistes]
    # Un mateix resultat pot sortir dues vegades a la llista: un sol avís.
    unics = list({r.clau: r for r in nous}.values())
    compte["avisos_nous"] = len(unics)
    if not unics:
        return compte
    if max_nous is not None and len(unics) > max_nous:
        _marca(sb, [r.clau for r in unics])
        prog(
            "warn",
            f"avisos ({origen}): {len(unics)} resultats nous de cop, més de {max_nous}. "
            "Semblen claus canviades, no resultats: es marquen sense avisar.",
        )
        return compte
    subs = (
        sb.table("push_subscripcions")
        .select("endpoint,p256dh,auth,tipus")
        .neq("tipus", "{}")
        .execute()
        .data
        or []
    )
    for sub in subs:
        for m in missatges(sub.get("tipus") or [], unics):
            codi = _envia_un(sub, m, clau_privada)
            if codi is None:
                compte["avisos_enviats"] += 1
            elif codi in (404, 410):
                # El dispositiu s'ha donat de baixa pel seu compte: fora.
                sb.table("push_subscripcions").delete().eq("endpoint", sub["endpoint"]).execute()
                prog("ok", "avisos: subscripció caducada retirada")
                break
            else:
                compte["avisos_errors"] += 1
                prog("warn", f"avisos: el servei de push ha respost {codi}")
    # Es marquen encara que algun enviament falli: repetir-los a cada passada de
    # dos minuts seria pitjor que perdre'n un.
    _marca(sb, [r.clau for r in unics])
    prog(
        "ok",
        f"avisos ({origen}): {len(unics)} resultats nous, {compte['avisos_enviats']} missatges enviats",
    )
    return compte


def avisa_opens(
    sb, files_open_live: list[dict], prog: Progress, clau_privada: str | None = None
) -> dict[str, int]:
    try:
        noms, ids = banyoles_de_la_temporada(sb)
    except Exception as exc:
        prog("warn", f"avisos: no s'han pogut llegir els jugadors del Banyoles: {exc}")
        noms, ids = set(), set()
    return _avisa(
        sb,
        "opens",
        resultats_opens(files_open_live, noms, ids),
        prog,
        max_nous=None,
        clau_privada=clau_privada,
    )


def avisa_reingesta(sb, prog: Progress, clau_privada: str | None = None) -> dict[str, int]:
    return _avisa(
        sb,
        "reingesta",
        resultats_reingesta(sb, prog),
        prog,
        max_nous=MAX_NOUS_REINGESTA,
        clau_privada=clau_privada,
    )
