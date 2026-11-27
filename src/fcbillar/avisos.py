"""Avisos push de resultats nous a la PWA (la campana de la capçalera).

Cada dispositiu tria tipus i té una llista de seguiments amb prefix: «j:278»
(jugador), «c:C.B.BANYOLES» (club) i «e:C.B.BANYOLES A» (equip). Els tipus
(`TIPUS`, iguals que a web/src/lib/avisos.ts):

- `opens_3b`: totes les partides acabades de qualsevol open de 3 bandes.
- `clubs_seguits`: el resultat dels encontres de lliga i de Copa dels clubs
  seguits (tots els seus equips) i dels equips seguits.
- `jugadors_seguits`: les partides dels jugadors seguits a les competicions
  individuals (opens i campionats de Catalunya).

Dues fonts, cadascuna enganxada on les dades ja són a la memòria:

- `avisa_opens`: des de `publish_live_opens`, a cada passada de ~2 min del cap de
  setmana.
- `avisa_reingesta`: després de `publish-cloud`, a la reingesta (encontres dels
  clubs i equips seguits, i campionats dels jugadors seguits).

Cada resultat té una clau estable; les ja avisades es desen a `avisos_enviats`.
Un missatge per open o competició i per passada.

La primera vegada que corre una font no envia res: marca com a avisat tot el que
ja hi ha. El mateix per a cada seguiment nou: començar a seguir algú a mitja
temporada no envia tot el que ja ha jugat.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

TIPUS = ("opens_3b", "clubs_seguits", "jugadors_seguits")
# Quins seguiments compten per a cada tipus.
PREFIXOS_DEL_TIPUS = {
    "clubs_seguits": ("c:", "e:"),
    "jugadors_seguits": ("j:",),
}

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
    ordre: int = field(default=0, compare=False)
    # Seguiments que hi intervenen («j:…», «c:…», «e:…»). Un resultat
    # sense cap `tipus` només arriba als dispositius que en segueixen algun.
    seguiments: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        # Les claus van dins d'un filtre `in.(...)` de PostgREST, que no admet
        # cometes als valors: «C.B.BLANES "B"» feia petar la passada sencera.
        self.clau = re.sub(r'[",()]', "", self.clau)


def arregla_codificacio(s: str) -> str:
    """Desfà el doble codificat: «LEÃ“N» (UTF-8 llegit com a cp1252) → «LEÓN».

    Molts noms de `players` i dels rànquings hi són així, i els de les partides
    i les afiliacions no: sense això no casarien mai. Un nom que ja és bo no es
    pot recodificar i es torna tal qual."""
    try:
        return s.encode("cp1252", errors="surrogateescape").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", arregla_codificacio(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def compacte(s: str | None) -> str:
    """«C.B. BANYOLES "A"» → «CBBANYOLESA»: per comparar equips i clubs, que la
    federació escriu amb punts, espais i cometes diferents segons la pàgina."""
    return re.sub(r"[^A-Z0-9]", "", _norm(s))


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


def _linia_partida(prefix: str, m: dict) -> str:
    a, b = _curt(m.get("player_a")), _curt(m.get("player_b"))
    ca, cb = m.get("caramboles_a"), m.get("caramboles_b")
    entr = m.get("entrades")
    if not m.get("is_played"):
        return f"{prefix}{a} - {b}: incompareixença"
    cola = f" ({entr} e.)" if entr else ""
    return f"{prefix}{a} {ca}-{cb} {b}{cola}"


def resultats_opens(files_open_live: Iterable[dict], seguits: Iterable[str] = ()) -> list[Resultat]:
    """Partides decidides dels opens en directe: les de 3 bandes, i les dels
    jugadors que algú segueix (`seguits`, amb prefix) de qualsevol modalitat."""
    seguits = set(seguits)
    out: list[Resultat] = []
    for row in files_open_live:
        div = row.get("fcb_division_id")
        nom = row.get("name") or "Open"
        payload = row.get("payload_json") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        es3b = _es_3b(nom, row.get("modality"))
        ids = payload.get("player_ids") or {}
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
                    seg = {f"j:{ids[x]}" for x in (a, b) if ids.get(x)} & seguits
                    if not es3b and not seg:
                        continue
                    on = grup or fase
                    n += 1
                    out.append(
                        Resultat(
                            clau=f"open:{div}:{fase}:{grup}:{'|'.join(sorted((a, b)))}",
                            tipus=frozenset({"opens_3b"}) if es3b else frozenset(),
                            grup=f"open:{div}",
                            titol=nom.title(),
                            linia=_linia_partida(f"{on}: " if on else "", m),
                            url=f"/opens/directe/{div}",
                            ordre=n,
                            seguiments=frozenset(seg),
                        )
                    )
    return out


# --- Reingesta: encontres dels clubs i equips, campionats dels jugadors --------


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


def _grups_actuals(sb, prefix: str) -> dict[tuple, dict]:
    """Grups de la temporada d'ara: la taula també guarda les passades."""
    tots = _llegeix(
        lambda: (
            sb.table(f"{prefix}_groups")
            .select("divisio_id,grup_id,divisio_nom,grup_nom,temporada")
            .order("divisio_id")
            .order("grup_id")
        )
    )
    actual = max((g.get("temporada") or "" for g in tots), default="")
    return {
        (g["divisio_id"], g["grup_id"]): g for g in tots if (g.get("temporada") or "") == actual
    }


class Equips:
    """Decideix quins seguiments toca un equip: el seu club, si se segueix, i
    l'equip mateix, si se segueix."""

    def __init__(self, clubs: Iterable[str], equips: Iterable[str], oficials: dict[str, str]):
        # El més llarg primer: «C.B.SANT ADRIÀ» abans que un hipotètic «C.B.SANT».
        self.clubs = sorted(clubs, key=lambda c: -len(compacte(c)))
        self.equips = {compacte(e): e for e in equips}
        # Equip compactat → club, segons la classificació de la federació.
        self.oficials = oficials

    def club(self, equip: str | None) -> str | None:
        """El club seguit de l'equip: el que hi assigna la federació o, si no en
        diu res, aquell pel nom del qual comença («C.B.BANYOLES A»)."""
        oficial = self.oficials.get(compacte(equip))
        if oficial is not None:
            return next((c for c in self.clubs if compacte(c) == compacte(oficial)), None)
        eq = compacte(equip)
        return next((c for c in self.clubs if compacte(c) and eq.startswith(compacte(c))), None)

    def seguiments(self, *equips: str | None) -> frozenset[str]:
        out = set()
        for e in equips:
            if (c := self.club(e)) is not None:
                out.add(f"c:{c}")
            if (seguit := self.equips.get(compacte(e))) is not None:
                out.add(f"e:{seguit}")
        return frozenset(out)


def _clubs_lliga(
    sb, prefix: str, nom_lliga: str, clubs: set[str], equips: set[str]
) -> list[Resultat]:
    grups = _grups_actuals(sb, prefix)
    if not grups:
        return []
    grup_ids = sorted({g for _, g in grups})
    oficials = {
        compacte(s["equip"]): s["club_fcb_id"]
        for s in _llegeix(
            lambda: (
                sb.table(f"{prefix}_standings")
                .select("divisio_id,grup_id,equip,club_fcb_id")
                .in_("grup_id", grup_ids)
                .order("divisio_id")
                .order("grup_id")
                .order("equip")
            )
        )
        if s.get("equip") and s.get("club_fcb_id")
    }
    qui = Equips(clubs, equips, oficials)
    encontres = []
    for f in _llegeix(
        lambda: (
            sb.table(f"{prefix}_encontres")
            .select(
                "encontre_id,divisio_id,grup_id,equip_local,equip_visitant,gols_local,gols_visitant"
            )
            .in_("grup_id", grup_ids)
            .not_.is_("gols_local", "null")
            .lt("encontre_id", 10_000_000)  # els de sota són els jugats; els altres, provisionals
            .order("encontre_id")
        )
    ):
        if (f["divisio_id"], f["grup_id"]) not in grups:
            continue
        seg = qui.seguiments(f["equip_local"], f["equip_visitant"])
        if seg:
            encontres.append((f, seg))
    ids = [f["encontre_id"] for f, _ in encontres]
    partides: dict[int, list[dict]] = {}
    for i in range(0, len(ids), 150):
        tros = ids[i : i + 150]
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
    for f, seg in encontres:
        g = grups[(f["divisio_id"], f["grup_id"])]
        on = " ".join(x for x in (g.get("divisio_nom"), g.get("grup_nom")) if x).title()
        pl, pv = _partides_guanyades(partides.get(f["encontre_id"], []))
        marcador = f"{pl}-{pv}" if (pl or pv) else f"{f['gols_local']}-{f['gols_visitant']}"
        punts = f" · {f['gols_local']}-{f['gols_visitant']} punts" if (pl or pv) else ""
        out.append(
            Resultat(
                clau=f"{prefix}:{f['encontre_id']}",
                tipus=frozenset(),
                grup=prefix,
                titol=f"{nom_lliga}: clubs i equips seguits",
                linia=(
                    f"{on + ': ' if on else ''}{_equip(f['equip_local'])} {marcador} "
                    f"{_equip(f['equip_visitant'])}{punts}"
                ),
                url="/lliga",
                seguiments=seg,
            )
        )
    return out


def _clubs_copa(sb, clubs: set[str], equips: set[str]) -> list[Resultat]:
    # La Copa no diu de quin club és cada equip: pel nom.
    qui = Equips(clubs, equips, {})
    out = []
    for f in _llegeix(
        lambda: (
            sb.table("copa_encontres")
            .select("jornada,grup_id,grup_nom,equip_local,equip_visitant,gols_local,gols_visitant")
            .not_.is_("gols_local", "null")
            .order("encontre_id")
        )
    ):
        seg = qui.seguiments(f["equip_local"], f["equip_visitant"])
        if not seg:
            continue
        on = (f.get("grup_nom") or "").title()
        out.append(
            Resultat(
                # `encontre_id` de la Copa és l'autoincrement de la base local: no és estable.
                clau=f"copa:{f['jornada']}:{f['grup_id']}:{f['equip_local']}|{f['equip_visitant']}",
                tipus=frozenset(),
                grup="copa",
                titol="Copa: clubs i equips seguits",
                linia=(
                    f"{on + ': ' if on else ''}{_equip(f['equip_local'])} "
                    f"{f['gols_local']}-{f['gols_visitant']} {_equip(f['equip_visitant'])}"
                ),
                url="/copa",
                seguiments=seg,
            )
        )
    return out


def _jugadors_per_id(sb, ids: Iterable[str]) -> list[dict]:
    ids = sorted({str(i) for i in ids})
    files: list[dict] = []
    for i in range(0, len(ids), 150):
        tros = ids[i : i + 150]
        files += sb.table("players").select("fcb_id,nom").in_("fcb_id", tros).execute().data or []
    return [f for f in files if f.get("nom")]


def _campionats_jugadors(sb, seguits: dict[str, str]) -> list[Resultat]:
    """Partides dels jugadors seguits (`seguits`: nom normalitzat → id) als
    campionats de Catalunya d'aquesta temporada."""
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
                "open_id,fase_id,ordre,grup_nom,jugador_local,caramboles_local,"
                "jugador_visitant,caramboles_visitant,entrades"
            )
            .in_("open_id", ids)
            .order("open_id")
            .order("fase_id")
            .order("ordre")
        )
    ):
        a, b = p.get("jugador_local") or "", p.get("jugador_visitant") or ""
        jug = {seguits.get(_norm(x)) for x in (a, b)}
        jug.discard(None)
        if not jug:
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
                tipus=frozenset(),
                grup=f"camp:{p['open_id']}",
                titol=f"Camp. Catalunya: {camp['nom']}",
                linia=(
                    f"{on + ': ' if on else ''}{_curt(a)} {p.get('caramboles_local')}-"
                    f"{p.get('caramboles_visitant')} {_curt(b)}{f' ({entr} e.)' if entr else ''}"
                ),
                url="/campionats",
                seguiments=frozenset(f"j:{j}" for j in jug),
            )
        )
    return out


def resultats_reingesta(sb, prog: Progress, seguits: Iterable[str] = ()) -> list[Resultat]:
    seguits = set(seguits)
    clubs = {s[2:] for s in seguits if s.startswith("c:")}
    equips = {s[2:] for s in seguits if s.startswith("e:")}
    ids = {s[2:] for s in seguits if s.startswith("j:")}
    per_nom = {_norm(f["nom"]): str(f["fcb_id"]) for f in _jugadors_per_id(sb, ids)} if ids else {}
    fonts = []
    if clubs or equips:
        fonts += [
            ("lliga", lambda: _clubs_lliga(sb, "lliga", "Lliga", clubs, equips)),
            (
                "lliga4m",
                lambda: _clubs_lliga(sb, "lliga4m", "Lliga 4 Modalitats", clubs, equips),
            ),
            ("copa", lambda: _clubs_copa(sb, clubs, equips)),
        ]
    if per_nom:
        fonts.append(("campionats", lambda: _campionats_jugadors(sb, per_nom)))
    out: list[Resultat] = []
    for nom, font in fonts:
        # Una font que falla no ha d'impedir avisar de les altres.
        try:
            out.extend(font())
        except Exception as exc:
            prog("warn", f"avisos: no s'han pogut llegir els resultats de {nom}: {exc}")
    return out


# --- Missatges i enviament ------------------------------------------------------


def seguits_de(sub: dict) -> set[str]:
    """Els seguiments d'una subscripció que compten pels tipus que té marcats."""
    prefixos = tuple(p for t in sub.get("tipus") or [] for p in PREFIXOS_DEL_TIPUS.get(t, ()))
    if not prefixos:
        return set()
    return {s for s in sub.get("seguiments") or [] if s.startswith(prefixos)}


def missatges(
    tipus_subscrits: Iterable[str], nous: list[Resultat], seguits: Iterable[str] = ()
) -> list[dict]:
    """Un missatge per grup amb els resultats nous que toquen a aquesta subscripció:
    pels tipus que té marcats o pels seus seguiments (`seguits`, ja filtrats)."""
    volguts = set(tipus_subscrits)
    els_seus = set(seguits)
    per_grup: dict[str, list[Resultat]] = {}
    for r in nous:
        if r.tipus & volguts or r.seguiments & els_seus:
            per_grup.setdefault(r.grup, []).append(r)

    def destacat(r: Resultat) -> bool:
        # Un jugador, un club o un equip seguit: al davant i amb estrella.
        return bool(r.seguiments & els_seus)

    out = []
    for rs in per_grup.values():
        rs = sorted(rs, key=lambda r: (not destacat(r), r.ordre))
        linies = [("★ " if destacat(r) and len(rs) > 1 else "") + r.linia for r in rs]
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


def _subscripcions(sb) -> list[dict]:
    """Els dispositius que volen algun avís. Sense la columna `seguiments` (abans
    de la migració 0047, o mentre el Data API no la veu) es llegeixen sense."""

    def llegeix(columnes: str) -> list[dict]:
        return (
            sb.table("push_subscripcions").select(columnes).neq("tipus", "{}").execute().data or []
        )

    try:
        return llegeix("endpoint,p256dh,auth,tipus,seguiments")
    except Exception as exc:
        if "seguiments" not in str(exc):
            raise
        return llegeix("endpoint,p256dh,auth,tipus")


def _avisa(
    sb,
    origen: str,
    resultats: list[Resultat] | Callable[[set[str]], list[Resultat]],
    prog: Progress,
    *,
    max_nous: int | None,
    clau_privada: str | None,
) -> dict[str, int]:
    """Envia els resultats nous i els marca.

    `resultats` pot ser la llista o una funció que la construeix a partir dels
    seguiments de tots els dispositius: les subscripcions es llegeixen primer
    perquè només es vagi a buscar el que algú segueix.
    """
    from fcbillar.cloud_sync import esquema_encara_no_hi_es

    compte = {"avisos_nous": 0, "avisos_enviats": 0, "avisos_errors": 0}
    clau_privada = clau_privada or os.environ.get("VAPID_PRIVATE_KEY")
    if not clau_privada:
        prog("warn", "avisos: falta VAPID_PRIVATE_KEY; no s'avisa de res")
        return compte
    try:
        subs = _subscripcions(sb)
    except Exception as exc:
        if esquema_encara_no_hi_es(exc):
            prog(
                "warn", "avisos: el Data API encara no veu `push_subscripcions`; no s'avisa de res"
            )
            return compte
        raise
    seguits: set[str] = set().union(*(seguits_de(s) for s in subs)) if subs else set()
    if callable(resultats):
        resultats = resultats(seguits)

    base = f"base:{origen}"
    # Una base per seguiment: el primer cop que surt, el que ja s'ha jugat es
    # marca sense enviar. Si no, seguir algú a mitja temporada enviaria tot el seu.
    bases = {s: f"base:{origen}:{s}" for s in seguits}
    claus = sorted({r.clau for r in resultats})
    try:
        vistes = _ja_avisades(sb, [base, *bases.values(), *claus])
    except Exception as exc:
        if esquema_encara_no_hi_es(exc):
            prog("warn", "avisos: el Data API encara no veu `avisos_enviats`; no s'avisa de res")
            return compte
        raise
    if base not in vistes:
        _marca(sb, [*claus, base, *bases.values()])
        prog(
            "ok", f"avisos ({origen}): primera passada, {len(claus)} resultats marcats sense avisar"
        )
        return compte
    nous_seguits = {s for s, b in bases.items() if b not in vistes}

    nous = [r for r in resultats if r.clau not in vistes]
    # Un mateix resultat pot sortir dues vegades a la llista: un sol avís.
    unics = list({r.clau: r for r in nous}.values())
    # Els que només interessen per seguiments que s'acaben de començar.
    silenciats = [r for r in unics if not r.tipus and r.seguiments and r.seguiments <= nous_seguits]
    enviables = [r for r in unics if r not in silenciats]
    compte["avisos_nous"] = len(enviables)
    marcar = [r.clau for r in unics] + [bases[s] for s in nous_seguits]
    if silenciats:
        prog(
            "ok",
            f"avisos ({origen}): {len(silenciats)} resultats de seguiments nous, "
            "marcats sense avisar",
        )
    if not enviables:
        if marcar:
            _marca(sb, marcar)
        return compte
    if max_nous is not None and len(enviables) > max_nous:
        _marca(sb, marcar)
        prog(
            "warn",
            f"avisos ({origen}): {len(enviables)} resultats nous de cop, més de {max_nous}. "
            "Semblen claus canviades, no resultats: es marquen sense avisar.",
        )
        return compte
    for sub in subs:
        for m in missatges(sub.get("tipus") or [], enviables, seguits_de(sub)):
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
    _marca(sb, marcar)
    prog(
        "ok",
        f"avisos ({origen}): {len(enviables)} resultats nous, "
        f"{compte['avisos_enviats']} missatges enviats",
    )
    return compte


def avisa_opens(
    sb, files_open_live: list[dict], prog: Progress, clau_privada: str | None = None
) -> dict[str, int]:
    return _avisa(
        sb,
        "opens",
        lambda seguits: resultats_opens(files_open_live, seguits),
        prog,
        max_nous=None,
        clau_privada=clau_privada,
    )


def avisa_reingesta(sb, prog: Progress, clau_privada: str | None = None) -> dict[str, int]:
    return _avisa(
        sb,
        "reingesta",
        lambda seguits: resultats_reingesta(sb, prog, seguits),
        prog,
        max_nous=MAX_NOUS_REINGESTA,
        clau_privada=clau_privada,
    )
