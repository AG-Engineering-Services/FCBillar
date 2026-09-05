"""Porta a la BD del PC el que només té la còpia del núvol.

Hi ha dues automatitzacions que escriuen a la mateixa base i es reparteixen la
feina: el PC fa la part LOGADA (rànquings i partides, que volen login federatiu
amb captcha) i el núvol la NO-LOGADA (lliga, copa, opens). El repartiment
funciona mentre les dues es passen la BD pel GitHub Release `fcb-state`, i el
PC la puja tal com la té: `weekly_reingest.ps1` fa `gh release upload` sense
baixar-la abans.

Això vol dir que si el núvol ha anat ingerint i el PC fa dies que no puja, pujar
la del PC s'endú el que el núvol havia trobat mentrestant. És el que va passar:
el núvol va enganxar el 29 d'agost la temporada 26/27 i els seus 41 torneigs,
i la del PC no els tenia.

Aquest guió fa el pas que faltava —portar-se del release el que no es té— abans
de pujar. NO és una sincronització: només afegeix files que no hi són. El que
s'ha esborrat a posta al PC no torna, i per això els clubs no s'hi toquen: els
duplicats fusionats hi tornarien a entrar.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from fcbillar.clubs import canonic
from fcbillar.config import get_settings


def _dic(conn: sqlite3.Connection, sql: str) -> dict:
    return {r[0]: r[1] for r in conn.execute(sql)}


def fusiona(local: sqlite3.Connection, release: sqlite3.Connection) -> dict[str, int]:
    """Afegeix a `local` les files que només té `release`. Torna què ha entrat."""
    local.execute("PRAGMA foreign_keys = ON")
    fets: dict[str, int] = {}

    # --- temporades: per nom, que és el que les identifica de debò ---
    temp_rel = _dic(release, "SELECT id, nom FROM temporades")
    temp_loc = _dic(local, "SELECT nom, id FROM temporades")
    noves = [n for n in temp_rel.values() if n not in temp_loc]
    for nom in noves:
        local.execute("INSERT INTO temporades (nom) VALUES (?)", (nom,))
    temp_loc = _dic(local, "SELECT nom, id FROM temporades")
    fets["temporades"] = len(noves)
    #: id del release -> id local
    mapa_temp = {i: temp_loc[n] for i, n in temp_rel.items() if n in temp_loc}

    # --- modalitats i clubs: no se'n creen, només es lliguen ---
    mod_rel = _dic(release, "SELECT id, nom FROM modalitats")
    mod_loc = _dic(local, "SELECT nom, id FROM modalitats")
    mapa_mod = {i: mod_loc[n] for i, n in mod_rel.items() if n in mod_loc}

    club_rel = _dic(release, "SELECT id, fcb_id FROM clubs")
    club_rel_nom = _dic(release, "SELECT id, nom FROM clubs")
    club_loc = _dic(local, "SELECT fcb_id, id FROM clubs")
    # Els clubs que el PC ha fusionat ja no hi són amb el seu `fcb_id` vell: la
    # fila es va esborrar. El que en queda és el nom, i `canonic()` és qui sap
    # que dos noms diferents són el mateix club.
    club_loc_canonic = {canonic(nom): i for i, nom in local.execute("SELECT id, nom FROM clubs")}

    def club_local(id_rel):
        fcb = club_rel.get(id_rel)
        if fcb is not None and fcb in club_loc:
            return club_loc[fcb]
        nom = club_rel_nom.get(id_rel)
        return club_loc_canonic.get(canonic(nom)) if nom else None

    # --- players: per fcb_id i, si no, pel nom ---
    # Un `fcb_id` que comença per «name:» no és cap identificador federatiu: és el
    # farciment que es posa quan no s'ha pogut resoldre qui és, i `cloud_sync` ja
    # els descarta. Importar-los crearia una segona fila del mateix jugador, i
    # llavors surt dos cops a la plantilla del seu club.
    play_loc = _dic(local, "SELECT fcb_id, id FROM players")
    play_nom = _dic(local, "SELECT nom, id FROM players")
    mapa_play: dict[int, int] = {}
    nous_jugadors = 0
    farciment = 0
    for pid, fcb, nom, club_id in release.execute("SELECT id, fcb_id, nom, club_id FROM players"):
        seu = play_loc.get(fcb)
        if seu is None:
            seu = play_nom.get(nom)
            if seu is not None:
                farciment += 1
            elif str(fcb).startswith("name:"):
                # No el tenim ni per id ni per nom, i tampoc no en sabem la
                # llicència: no serveix de res afegir-lo.
                continue
            else:
                cur = local.execute(
                    "INSERT INTO players (fcb_id, nom, club_id) VALUES (?, ?, ?)",
                    (fcb, nom, club_local(club_id)),
                )
                seu = cur.lastrowid
                play_loc[fcb] = seu
                play_nom[nom] = seu
                nous_jugadors += 1
        mapa_play[pid] = seu
    fets["players"] = nous_jugadors
    fets["players (ja hi eren, lligats pel nom)"] = farciment

    # --- torneigs individuals ---
    # La clau de debò és (torneig_id_extern, divisio_id_extern): l'`id` és nostre
    # i les dues bases no l'han de tenir igual per força.
    def clau_torneig(r):
        return (r[1], r[2])

    tor_loc = {
        clau_torneig(r): r[0]
        for r in local.execute(
            "SELECT id, torneig_id_extern, divisio_id_extern FROM torneigs_individuals"
        )
    }
    mapa_tor: dict[int, int] = {}
    nous_torneigs = 0
    for tid, ext, div, nom, mod, temp in release.execute(
        "SELECT id, torneig_id_extern, divisio_id_extern, nom, modalitat_id, temporada_id "
        "FROM torneigs_individuals"
    ):
        seu = tor_loc.get((ext, div))
        if seu is None:
            cur = local.execute(
                "INSERT INTO torneigs_individuals "
                "(torneig_id_extern, divisio_id_extern, nom, modalitat_id, temporada_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (ext, div, nom, mapa_mod.get(mod), mapa_temp.get(temp)),
            )
            seu = cur.lastrowid
            tor_loc[(ext, div)] = seu
            nous_torneigs += 1
        mapa_tor[tid] = seu
    fets["torneigs_individuals"] = nous_torneigs

    # --- participants dels torneigs ---
    cols = [r[1] for r in release.execute("PRAGMA table_info(torneig_participants)")]
    resta = [c for c in cols if c not in ("torneig_id", "player_id")]
    te = {
        (r[0], r[1])
        for r in local.execute("SELECT torneig_id, player_id FROM torneig_participants")
    }
    nous_part = 0
    for fila in release.execute(
        f"SELECT torneig_id, player_id, {','.join(resta)} FROM torneig_participants"
    ):
        tor, jug = mapa_tor.get(fila[0]), mapa_play.get(fila[1])
        if tor is None or jug is None or (tor, jug) in te:
            continue
        local.execute(
            f"INSERT INTO torneig_participants (torneig_id, player_id, {','.join(resta)}) "
            f"VALUES ({','.join('?' * (2 + len(resta)))})",
            (tor, jug, *fila[2:]),
        )
        te.add((tor, jug))
        nous_part += 1
    fets["torneig_participants"] = nous_part

    # --- encontres de lliga ---
    # Els equips tenen `id` propi a cada base: es lliguen per club i lletra.
    eq_rel = {
        eid: (club_rel.get(club_id), lletra)
        for eid, club_id, lletra in release.execute("SELECT id, club_id, lletra FROM equips")
    }
    fcb_de_club = {i: f for f, i in club_loc.items()}
    eq_loc = {
        (fcb_de_club.get(club_id), lletra): eid
        for eid, club_id, lletra in local.execute("SELECT id, club_id, lletra FROM equips")
    }

    def equip_local(id_rel):
        clau = eq_rel.get(id_rel)
        if clau is None or clau[0] is None:
            return None
        return eq_loc.get(clau)

    clau_enc = "lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern"
    te_enc = {tuple(r) for r in local.execute(f"SELECT {clau_enc} FROM encontres_lliga")}
    nous_enc = 0
    for fila in release.execute(
        f"SELECT {clau_enc}, data, temporada_id, equip_local_id, equip_visitant_id, "
        "p_parcials_local, p_match_local, p_parcials_visitant, p_match_visitant "
        "FROM encontres_lliga"
    ):
        if tuple(fila[:5]) in te_enc:
            continue
        local.execute(
            f"INSERT INTO encontres_lliga ({clau_enc}, data, temporada_id, "
            "equip_local_id, equip_visitant_id, p_parcials_local, p_match_local, "
            "p_parcials_visitant, p_match_visitant) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                *fila[:6],
                mapa_temp.get(fila[6]),
                equip_local(fila[7]),
                equip_local(fila[8]),
                *fila[9:],
            ),
        )
        nous_enc += 1
    fets["encontres_lliga"] = nous_enc
    return fets


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("ús: fusiona_release.py <fcbillar.db del release> [<BD destí, per provar>]")
        return 2
    cami = Path(sys.argv[1])
    if not cami.exists():
        print(f"no hi és: {cami}")
        return 2
    # El segon argument és per assajar-ho sobre una còpia abans de tocar la bona.
    desti = Path(sys.argv[2]) if len(sys.argv) == 3 else get_settings().db_path

    local = sqlite3.connect(desti)
    release = sqlite3.connect(f"file:{cami}?mode=ro", uri=True)
    abans = local.execute("SELECT COUNT(*) FROM clubs").fetchone()[0]
    try:
        local.execute("BEGIN IMMEDIATE")
        fets = fusiona(local, release)
        despres = local.execute("SELECT COUNT(*) FROM clubs").fetchone()[0]
        if despres != abans:
            local.execute("ROLLBACK")
            print(f"ABORTAT: els clubs han passat de {abans} a {despres}. No s'hi han de tocar.")
            return 1
        local.execute("COMMIT")
    except Exception:
        local.execute("ROLLBACK")
        raise

    for taula, n in fets.items():
        print(f"  {taula:<24} +{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
