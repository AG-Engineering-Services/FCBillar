"""Detecta i repara noms doblement codificats (UTF-8 → cp1252/surrogateescape)
a les taules del núvol Supabase (esquemes `fcbillar` i `fcb_opens`).

Context. Històricament alguns noms amb accents/ñ/ª es van desar al núvol
doblement codificats: bytes UTF-8 rellegits com a Windows-1252 amb
`errors='surrogateescape'`. Ex.: "GONZÁLEZ" → "GONZÃ\udc81LEZ"
(la "Á" = C3 81; C3→'Ã', 81 indefinit a cp1252 → substitut solitari U+DC81).

La inversa exacta de la corrupció és `s.encode('cp1252','surrogateescape')`
(reconstrueix els bytes UTF-8 originals) `.decode('utf-8')` (els rellegeix bé).
El try/except evita tocar cadenes ja correctes: si els bytes no formen UTF-8
vàlid, no era aquesta corrupció i es deixa l'original (p. ex. un "JOÃO" real,
on C3 va seguit d'un byte que no és continuació, NO es toca).

NOTA. El camí d'escriptura actual (supabase-py 2.31 + httpx 0.28, que serialitza
el cos com a UTF-8 correcte) ja desa net — verificat amb un round-trip viu. Totes
les taules netes a data d'avui. Aquest script és, doncs, una eina de verificació
i una xarxa de seguretat per a una eventual reaparició o files antigues residuals.

Ús:
    uv run python scripts/repair_supabase_encoding.py            # escaneig (dry-run)
    uv run python scripts/repair_supabase_encoding.py --apply    # repara in situ
"""

from __future__ import annotations

import os
import sys

# El terminal de Windows usa cp1252 quan la sortida va a un pipe; força UTF-8
# perquè els ✓/accents dels missatges no facin petar el print (com fa la CLI).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# --------------------------------------------------------------------------- #
# Detecció + reparació
# --------------------------------------------------------------------------- #


def repair_name(s):
    """Inverteix la doble codificació UTF-8→cp1252/surrogateescape d'una cadena.

    Retorna `s` sense tocar si no sembla corrupta o si la inversa no produeix
    UTF-8 vàlid (no era aquesta corrupció)."""
    if not s:
        return s
    # Només si sembla corrupte: 'Ã'/'Â' o substituts solitaris (surrogateescape).
    if (
        "Ã" not in s
        and "Â" not in s
        and not any(0xDC80 <= ord(c) <= 0xDCFF for c in s)
    ):
        return s
    try:
        return s.encode("cp1252", errors="surrogateescape").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s  # no era aquesta corrupció: deixa l'original


def repair_json(obj):
    """Aplica `repair_name` recursivament a tota cadena (claus i valors) d'un
    objecte JSON (dict/list/str)."""
    if isinstance(obj, str):
        return repair_name(obj)
    if isinstance(obj, list):
        return [repair_json(x) for x in obj]
    if isinstance(obj, dict):
        return {
            (repair_name(k) if isinstance(k, str) else k): repair_json(v)
            for k, v in obj.items()
        }
    return obj


# --------------------------------------------------------------------------- #
# Quines columnes mirar a cada taula
#   keys: columnes (sempre ASCII netes) per identificar la fila a l'UPDATE
#   text: columnes de text pla
#   json: columnes jsonb (es recorren amb repair_json)
# --------------------------------------------------------------------------- #

TARGETS = [
    # --- esquema fcbillar (escrit per src/fcbillar/cloud_sync.py) ---
    ("fcbillar", "players", ["fcb_id"], ["nom"], []),
    ("fcbillar", "clubs", ["fcb_id"], ["nom"], []),
    ("fcbillar", "games", ["id"], ["player1_nom", "player2_nom"], []),
    ("fcbillar", "pending_games",
     ["player_fcb_id", "modalitat_codi", "signatura"], ["opponent_nom"], []),
    ("fcbillar", "player_clubs", ["player_fcb_id", "temporada"], ["club"], []),
    ("fcbillar", "open_classifications",
     ["open_id", "player_fcb_id"], ["jugador", "club"], []),
    ("fcbillar", "opens", ["open_id"], ["nom"], []),
    ("fcbillar", "open_ranking",
     ["genere", "ronda", "posicio"], ["jugador", "club", "ronda_nom"], ["detall"]),
    ("fcbillar", "open_live", ["fcb_division_id"], ["name"], ["payload_json"]),
    # --- esquema fcb_opens (escrit per src/fcb_opens/supabase_sync.py i snapshot_live.py) ---
    ("fcb_opens", "players", ["id"], ["display_name", "current_club"], []),
    ("fcb_opens", "opens", ["id"], ["name"], []),
    ("fcb_opens", "open_classifications", ["id"], ["club"], []),
    ("fcb_opens", "monthly_ranking_entries", ["id"], ["club"], []),
    ("fcb_opens", "leagues", ["id"], ["name"], []),
    ("fcb_opens", "league_divisions", ["id"], ["name"], []),
    ("fcb_opens", "league_groups", ["id"], ["name"], []),
    ("fcb_opens", "league_team_standings", ["id"], ["team_name"], []),
    ("fcb_opens", "league_encontres", ["id"], ["home_team_name", "away_team_name"], []),
    ("fcb_opens", "open_live_snapshots", ["id"], [], ["payload_json"]),
]

PAGE = 1000


def _client():
    """Crea el client Supabase (service-role) amb credencials del .env.

    El client base permet adreçar qualsevol esquema amb `.schema(nom)`."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from fcbillar.cloud_sync import _env

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("Falten SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (.env).")
    # Exposa-les també a l'entorn per si algun mòdul les llegeix d'allà.
    os.environ.setdefault("SUPABASE_URL", url)
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", key)

    from supabase import create_client

    return create_client(url, key)


def _patch_for(row, text_cols, json_cols):
    """Diccionari {columna: valor_reparat} només per a les columnes que canvien."""
    patch = {}
    for c in text_cols:
        v = row.get(c)
        nv = repair_name(v)
        if nv != v:
            patch[c] = nv
    for c in json_cols:
        v = row.get(c)
        nv = repair_json(v)
        if nv != v:
            patch[c] = nv
    return patch


def _cps(s):
    return " ".join(f"U+{ord(c):04X}" for c in s if isinstance(s, str) and ord(c) > 127)


def main(apply: bool) -> int:
    """Retorna un codi de sortida: 0 = net / tot reparat, 2 = queda corrupció.

    Pensat per fer de porta al cron setmanal: en mode escaneig (sense --apply)
    surt amb 2 si troba mojibake, perquè el pas quedi marcat com a FALLAT al log."""
    base = _client()

    grand_corrupt = 0
    grand_fixed = 0
    sample_shown = 0

    for schema, table, keys, text_cols, json_cols in TARGETS:
        client = base.schema(schema)
        cols = list(dict.fromkeys(keys + text_cols + json_cols))
        total = corrupt = fixed = skipped_key = 0
        start = 0
        try:
            while True:
                rows = (
                    client.table(table)
                    .select(",".join(cols))
                    .range(start, start + PAGE - 1)
                    .execute()
                    .data
                )
                if not rows:
                    break
                for row in rows:
                    total += 1
                    patch = _patch_for(row, text_cols, json_cols)
                    if not patch:
                        continue
                    corrupt += 1
                    if sample_shown < 8:
                        col0 = next(iter(patch))
                        before = row.get(col0)
                        if isinstance(before, str):
                            print(
                                f"    · {schema}.{table}.{col0}: "
                                f"[{_cps(before)}] → {patch[col0]!r}"
                            )
                            sample_shown += 1
                    if apply:
                        # Construeix el filtre amb les claus (sempre ASCII netes).
                        if any(row.get(k) is None for k in keys):
                            skipped_key += 1
                            continue
                        q = client.table(table).update(patch)
                        for k in keys:
                            q = q.eq(k, row[k])
                        q.execute()
                        fixed += 1
                if len(rows) < PAGE:
                    break
                start += PAGE
        except Exception as exc:  # noqa: BLE001 — taula inexistent o sense permisos
            print(f"  {schema}.{table}: OMÈS ({str(exc)[:90]})")
            continue

        grand_corrupt += corrupt
        grand_fixed += fixed
        flag = "" if corrupt == 0 else f"  ⚠ {corrupt} corruptes"
        extra = f", {skipped_key} sense clau (manual)" if skipped_key else ""
        print(f"  {schema}.{table}: {total} files{flag}"
              + (f" → {fixed} reparades" if apply and corrupt else "")
              + extra)

    print()
    if grand_corrupt == 0:
        print("✓ Cap valor doblement codificat. El núvol és net.")
        return 0
    if apply:
        print(f"✓ Reparades {grand_fixed}/{grand_corrupt} files corruptes.")
        if grand_fixed < grand_corrupt:
            print("  (algunes files sense clau identificable; cal repassar-les a mà)")
            return 2
        return 0
    print(f"⚠ {grand_corrupt} files corruptes detectades. "
          f"Executa amb --apply per reparar-les.")
    return 2


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv))
