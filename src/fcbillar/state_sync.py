"""Round-trip de l'estat canònic (BD + sessió) amb Cloudflare R2.

El núvol (GitHub Actions) passa a ser la còpia CANÒNICA de tres blobs:

  - data/fcbillar.db            BD principal (rànquings, partides, clubs…)
  - data/fcb_opens.db           BD d'opens (mòdul fcb_opens)
  - session/storage_state.json  sessió de login (la produeix el PC amb captcha;
                                el núvol només la CONSUMEIX, no la pot renovar)

El job de reingesta fa `pull` al començar i `push` al final. El PC fa `push`
de la sessió després de cada re-login (`fcbillar login`), i pot fer `pull`/`push`
de les BD per a edicions curades. Es trien R2 i no Supabase Storage perquè R2 no
cobra egress, aguanta fitxers grans (la BD ~169MB) i el PC també hi pot escriure.

Guardó de divergència PC↔núvol: un comptador `generation` (objecte tip a R2). El
job l'incrementa després de pujar les BD; `state pull` desa el valor baixat a
`data/.state_gen`; `state push --check-generation` es nega si el núvol ha avançat
respecte d'aquell valor (cal fer `pull` primer, o `--force`).

Credencials (entorn o .env, reaprofitant `cloud_sync._env`):
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
Endpoint S3: https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from fcbillar.cloud_sync import _env
from fcbillar.config import PROJECT_ROOT, get_settings

log = logging.getLogger(__name__)

# Claus dels objectes a R2 i comptador de generació.
KEY_DB = "fcbillar.db"
KEY_OPENS_DB = "fcb_opens.db"
KEY_SESSION = "storage_state.json"
KEY_GENERATION = "generation"

# Noms lògics que accepten les comandes `state pull/push`.
ALL = ("db", "opens-db", "session")

_GEN_FILE = PROJECT_ROOT / "data" / ".state_gen"


def _local_path(which: str) -> Path:
    """Ruta local resolta per a cada blob (respecta FCB_* i FCB_OPENS_DB)."""
    if which == "db":
        return get_settings().db_path
    if which == "session":
        return get_settings().storage_state_path
    if which == "opens-db":
        from fcb_opens.paths import resolve_db_path

        return resolve_db_path(None)
    raise ValueError(f"blob desconegut: {which!r} (tria entre {ALL})")


def _remote_key(which: str) -> str:
    return {"db": KEY_DB, "opens-db": KEY_OPENS_DB, "session": KEY_SESSION}[which]


def _r2(name: str) -> str:
    val = _env(name)
    if not val:
        raise RuntimeError(f"Falta {name} (entorn o .env) per parlar amb R2.")
    return val


def _bucket() -> str:
    return _r2("R2_BUCKET")


def _client():
    """Client S3 apuntant a l'endpoint de Cloudflare R2."""
    import boto3

    account = _r2("R2_ACCOUNT_ID")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=_r2("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_r2("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _is_missing(exc: Exception) -> bool:
    """True si l'error de boto3 és un 404/NoSuchKey (objecte inexistent)."""
    code = getattr(exc, "response", {}).get("Error", {}).get("Code")
    return code in {"404", "NoSuchKey", "NoSuchBucket"}


# --------------------------------------------------------------------------- #
# Generació (guardó de divergència)
# --------------------------------------------------------------------------- #


def remote_generation(cli=None) -> int:
    cli = cli or _client()
    try:
        obj = cli.get_object(Bucket=_bucket(), Key=KEY_GENERATION)
        return int(obj["Body"].read().decode("utf-8").strip() or "0")
    except Exception as exc:
        if _is_missing(exc):
            return 0
        raise


def _set_remote_generation(cli, value: int) -> None:
    cli.put_object(
        Bucket=_bucket(),
        Key=KEY_GENERATION,
        Body=str(value).encode("utf-8"),
        ContentType="text/plain",
    )


def local_generation() -> int:
    try:
        return int(_GEN_FILE.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def _write_local_generation(value: int) -> None:
    _GEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _GEN_FILE.write_text(str(value), encoding="utf-8")


# --------------------------------------------------------------------------- #
# pull / push
# --------------------------------------------------------------------------- #


def pull(names: tuple[str, ...] = ALL) -> dict[str, str]:
    """Baixa els blobs demanats de R2 a les rutes locals (escriptura atòmica).

    Un blob remot inexistent és un avís suau (p.ex. la primera vegada). Desa la
    generació remota a `data/.state_gen`. Retorna un mapa blob → estat.
    """
    cli = _client()
    bucket = _bucket()
    out: dict[str, str] = {}
    for which in names:
        dest = _local_path(which)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            cli.download_file(bucket, _remote_key(which), str(tmp))
            os.replace(tmp, dest)
            out[which] = "baixat"
            log.info("R2 pull %s → %s", _remote_key(which), dest)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            if _is_missing(exc):
                out[which] = "remot inexistent (omès)"
                log.warning("R2 pull: %s no existeix encara", _remote_key(which))
            else:
                raise
    _write_local_generation(remote_generation(cli))
    return out


def push(
    names: tuple[str, ...] = ALL,
    *,
    check_generation: bool = False,
    force: bool = False,
) -> dict[str, str]:
    """Puja els blobs demanats a R2. Incrementa `generation` si es puja cap BD.

    - `session`: se salta si el SHA256 local coincideix amb el de l'objecte remot
      (evita repujar una sessió que no ha canviat).
    - `check_generation`: si el núvol ha avançat respecte de `data/.state_gen`,
      es nega (tret de `force`) per no trepitjar canvis fets en una altra banda.
    """
    cli = _client()
    bucket = _bucket()

    if check_generation and not force:
        rg = remote_generation(cli)
        lg = local_generation()
        if rg > lg:
            raise RuntimeError(
                f"El núvol ha avançat (generation remota={rg} > local={lg}). "
                "Fes `fcbillar state pull` primer, o `--force` per sobreescriure."
            )

    out: dict[str, str] = {}
    pushed_db = False
    for which in names:
        src = _local_path(which)
        key = _remote_key(which)
        if not src.exists():
            out[which] = "local inexistent (omès)"
            log.warning("R2 push: %s no existeix localment", src)
            continue
        if which == "session":
            local_sha = _sha256(src)
            try:
                head = cli.head_object(Bucket=bucket, Key=key)
                if head.get("Metadata", {}).get("sha256") == local_sha:
                    out[which] = "sense canvis (omès)"
                    continue
            except Exception as exc:
                if not _is_missing(exc):
                    raise
            cli.upload_file(
                str(src), bucket, key, ExtraArgs={"Metadata": {"sha256": local_sha}}
            )
        else:
            cli.upload_file(str(src), bucket, key)
            pushed_db = True
        out[which] = "pujat"
        log.info("R2 push %s → %s", src, key)

    if pushed_db:
        new_gen = remote_generation(cli) + 1
        _set_remote_generation(cli, new_gen)
        _write_local_generation(new_gen)
        out["generation"] = str(new_gen)
    return out


def status() -> dict[str, object]:
    """Resum de l'estat: generació local/remota i mida dels objectes remots."""
    cli = _client()
    bucket = _bucket()
    info: dict[str, object] = {
        "local_generation": local_generation(),
        "remote_generation": remote_generation(cli),
    }
    for which in ALL:
        key = _remote_key(which)
        try:
            head = cli.head_object(Bucket=bucket, Key=key)
            info[key] = f"{head['ContentLength'] / 1e6:.1f} MB"
        except Exception as exc:
            info[key] = "—" if _is_missing(exc) else f"error: {exc}"
    return info
