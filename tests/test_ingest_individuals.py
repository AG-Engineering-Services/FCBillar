"""Ingesta dels campionats i opens individuals contra el web nou de la FCB.

Fins al setembre de 2026 la ingesta anava a buscar `/individuals/classificaciofinal`,
que el web d'agost va retirar. Responia 404 divisió per divisió, cada fallada
es registrava per separat i el pas nocturn sortia verd amb zero participants:
de la temporada 26/27 no n'hi va haver mai res ni a la BD ni al web.

Aquests tests recorren la jerarquia que el portal publica de debò —fases →
grups → classificació i partides— amb un client fals que serveix la fixture de
cada nivell, contra una BD d'usar i llençar.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.pipeline import (
    _classifica,
    _punts_de_partida,
    _StatsJugador,
    ingest_individuals_temporada,
)

FX = Path(__file__).resolve().parent / "fixtures" / "nou"


def _rd(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8", errors="ignore")


pytestmark = pytest.mark.skipif(
    not (FX / "individuals_fases_211_447.html").exists(),
    reason="falten les fixtures d'individuals",
)


class _FakeClient:
    """Serveix una fixture per cada nivell de la jerarquia d'individuals."""

    def __init__(self, settings, sense_fases: set[int] | None = None):
        self.settings = settings
        #: Torneigs que encara no tenen cap fase publicada (pàgina buida).
        self.sense_fases = sense_fases or set()
        self.urls: list[str] = []

    def fetch_html(self, url: str, use_cache: bool = True) -> str:
        self.urls.append(url)
        # L'ordre importa: "partides-grup" també conté "grups".
        if url.endswith("/individuals/llistat"):
            return _rd("individuals_llistat.html")
        if "/individuals/divisions/" in url:
            return _rd("individuals_divisions_211.html")
        if "/individuals/fases/" in url:
            torneig = int(url.rstrip("/").split("/")[-2])
            return (
                "<html></html>"
                if torneig in self.sense_fases
                else _rd("individuals_fases_211_447.html")
            )
        if "/individuals/partides-grup/" in url:
            return _rd("individuals_partides_grup_211_447_799_5100.html")
        if "/individuals/partides-eliminatories/" in url:
            return _rd("individuals_partides_eliminatories_211_447_1185.html")
        if "/individuals/grups/" in url:
            return _rd("individuals_grups_211_447_799.html")
        raise AssertionError(f"URL d'individuals no prevista al test: {url}")


def _settings(tmp_path):
    return types.SimpleNamespace(
        base_url="https://intranet.example.test", db_path=tmp_path / "ind.db"
    )


def test_ingest_individuals_recorre_fases_grups_i_partides(tmp_path):
    settings = _settings(tmp_path)
    client = _FakeClient(settings)

    res = ingest_individuals_temporada(client, settings=settings, use_cache=False)

    # El llistat porta dos torneigs i cadascun una divisió, amb 8 fases: 3 de
    # grups (1 grup de 3 jugadors i 3 partides) i 5 eliminatòries (1 partida).
    assert res.torneigs_processed == 2
    assert res.torneigs_failed == 0
    assert res.fases == 16
    assert res.grups == 18  # 2 torneigs × 3 fases de grups × 3 jugadors
    assert res.partides == 28  # 2 × (3 fases × 3 partides + 5 eliminatòries)

    conn = ensure_schema(settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM torneigs_individuals").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM torneig_fases").fetchone()[0] == 16

    # La classificació del grup arriba sencera: posició, punts i mitjana, i el
    # dia i la seu, que són l'única data que publica el portal.
    fila = conn.execute(
        "SELECT grup_nom, jugador_nom, ordre, punts, mitjana, data, club_organitzador "
        "FROM torneig_fase_grups ORDER BY ordre LIMIT 1"
    ).fetchone()
    assert tuple(fila) == (
        "Grup A",
        "MAS CANADELL, JOSEP Mª",
        1,
        4,
        1.4634,
        "2026-07-10",
        "C.B.MATARÓ",
    )

    # Les partides de grup porten grup i data; les d'eliminatòria, només la fase.
    grup = conn.execute(
        "SELECT punts1, punts2, grup_nom, data, estat FROM torneig_partides "
        "WHERE player1_nom = 'MAS CANADELL, JOSEP Mª' LIMIT 1"
    ).fetchone()
    assert tuple(grup) == (2, 0, "Grup A", "2026-07-10", "Finalitzada")
    # El client fals serveix la fixture de la FINAL a totes les eliminatòries;
    # el que es comprova és que el grup d'una partida de KO és el nom de la
    # fase i que no en surt cap data, perquè el portal no en publica.
    ko = conn.execute(
        "SELECT grup_nom, data FROM torneig_partides WHERE fase_id = 1185 LIMIT 1"
    ).fetchone()
    assert tuple(ko) == ("FINAL", None)


def test_classificacio_posa_primer_qui_ha_arribat_mes_lluny(tmp_path):
    """Qui perd la final va davant de qui va guanyar el seu grup a la prèvia."""
    settings = _settings(tmp_path)
    ingest_individuals_temporada(_FakeClient(settings), settings=settings, use_cache=False)

    conn = ensure_schema(settings.db_path)
    ordre = [
        r[0]
        for r in conn.execute(
            "SELECT p.nom FROM torneig_participants tp JOIN players p ON p.id = tp.player_id "
            "JOIN torneigs_individuals ti ON ti.id = tp.torneig_id "
            "WHERE ti.torneig_id_extern = 216 ORDER BY tp.posicio"
        )
    ]
    assert ordre == [
        "GARRIGA COMAS, JORDI",  # guanya la final
        "HERNÁNDEZ PARRA, ANTONI",  # la perd
        "MAS CANADELL, JOSEP Mª",  # 1r del grup de la prèvia
        "SÁNCHEZ MARTÍNEZ, PASCUAL",
        "SANTIAGO ROMERO, JUAN",
    ]


def test_ingest_individuals_es_idempotent(tmp_path):
    """Reingerir no ha de duplicar ni grups ni partides: es reescriuen."""
    settings = _settings(tmp_path)
    client = _FakeClient(settings)
    ingest_individuals_temporada(client, settings=settings, use_cache=False)
    ingest_individuals_temporada(client, settings=settings, use_cache=False)

    conn = ensure_schema(settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM torneig_fase_grups").fetchone()[0] == 18
    assert conn.execute("SELECT COUNT(*) FROM torneig_partides").fetchone()[0] == 28
    assert conn.execute("SELECT COUNT(*) FROM torneig_participants").fetchone()[0] == 10


def test_una_divisio_sense_fases_no_es_desa(tmp_path):
    """El portal té la pàgina de les divisions que no es juguen fins al maig."""
    settings = _settings(tmp_path)
    client = _FakeClient(settings, sense_fases={217})

    res = ingest_individuals_temporada(client, settings=settings, use_cache=False)

    assert res.torneigs_processed == 2  # els dos s'han mirat...
    conn = ensure_schema(settings.db_path)
    # ...però només se n'ha desat el que té competició.
    noms = [r[0] for r in conn.execute("SELECT torneig_id_extern FROM torneigs_individuals")]
    assert noms == [216]


def test_punts_de_partida():
    assert _punts_de_partida(40, 25) == (2, 0)
    assert _punts_de_partida(25, 40) == (0, 2)
    assert _punts_de_partida(30, 30) == (1, 1)  # art. VII.1: l'empat dona 1 a cadascú
    assert _punts_de_partida(None, 30) == (None, None)


def test_classifica_desempata_per_punts_i_mitjana_de_la_fase():
    a = _StatsJugador(nom="A", fase_ordre=2, fase_punts=2, fase_mitjana_pub=0.8)
    b = _StatsJugador(nom="B", fase_ordre=2, fase_punts=2, fase_mitjana_pub=0.9)
    c = _StatsJugador(nom="C", fase_ordre=3, fase_punts=0, fase_mitjana_pub=0.1)
    assert [s.nom for s in _classifica({"A": a, "B": b, "C": c})] == ["C", "B", "A"]
