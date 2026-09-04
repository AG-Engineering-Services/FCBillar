"""Si ja s'ha disputat la primera partida de la temporada, i quina.

Del setembre fins que es juga la primera jornada, la web va amb bastides: els
grups i els enfrontaments surten del PDF del calendari —la federació no publica
els encontres fins que es juguen— i les plantilles dels rivals són una
estimació. Tot això va marcat com a provisional a la pantalla.

Saber quan cauen les bastides no es pot mirar a ull cada dia, i el senyal no és
una data del calendari sinó que hi hagi un resultat: la federació endarrereix
jornades i el PDF ja ha portat dates equivocades altres vegades.

Això ho diu cada reingesta al resum del job. No atura res ni canvia res: només
avisa que a partir d'aquell dia la ingesta porta competició de debò.
"""

from __future__ import annotations

import sqlite3

from fcbillar.config import get_settings


def temporada_en_curs(conn: sqlite3.Connection) -> str | None:
    """La temporada del calendari de lliga que tenim carregat."""
    fila = conn.execute("SELECT MAX(temporada) FROM lliga_calendari").fetchone()
    return fila[0] if fila else None


def primera_de_lliga(conn: sqlite3.Connection, temporada: str) -> tuple[str, str] | None:
    """La primera partida de lliga amb resultat, si n'hi ha cap.

    Es demana un resultat i no un encontre: la federació dona d'alta els
    encontres de la temporada abans que es juguin —ja en tenim de la 26/27 sense
    jugar— i tenir-los no vol dir que hi hagi hagut cap partida.
    """
    fila = conn.execute(
        """
        SELECT g.data_partida, pa.nom || ' - ' || pb.nom
          FROM games g
          JOIN encontres_lliga e ON e.id = g.encontre_lliga_id
          JOIN temporades t ON t.id = e.temporada_id
          LEFT JOIN players pa ON pa.id = g.player1_id
          LEFT JOIN players pb ON pb.id = g.player2_id
         WHERE t.nom = ? AND g.entrades IS NOT NULL AND g.entrades > 0
         ORDER BY g.data_partida
         LIMIT 1
        """,
        (temporada.replace("/", "-"),),
    ).fetchone()
    return (fila[0], fila[1] or "?") if fila else None


def primera_individual(conn: sqlite3.Connection, temporada: str) -> tuple[str, str] | None:
    """La primera partida del campionat individual amb resultat."""
    fila = conn.execute(
        """
        SELECT g.data_partida, ti.nom
          FROM games g
          JOIN torneigs_individuals ti ON ti.id = g.torneig_id
          JOIN temporades t ON t.id = ti.temporada_id
         WHERE t.nom = ? AND g.entrades IS NOT NULL AND g.entrades > 0
         ORDER BY g.data_partida
         LIMIT 1
        """,
        (temporada.replace("/", "-"),),
    ).fetchone()
    return (fila[0], fila[1] or "?") if fila else None


def main() -> int:
    conn = sqlite3.connect(get_settings().db_path)
    temporada = temporada_en_curs(conn)
    if not temporada:
        print("### Primera partida\n\nNo hi ha cap calendari de lliga carregat.")
        return 0

    lliga = primera_de_lliga(conn, temporada)
    individual = primera_individual(conn, temporada)

    print(f"### Primera partida de la {temporada}\n")
    if lliga:
        print(f"- **Lliga**: {lliga[0]} · {lliga[1]}")
    else:
        print("- **Lliga**: encara cap. Els grups surten del PDF del calendari.")
    if individual:
        print(f"- **Individual**: {individual[0]} · {individual[1]}")
    else:
        print("- **Individual**: encara cap.")

    if lliga or individual:
        print(
            "\n**Ja s'ha jugat.** Les bastides de pretemporada —grups del PDF, "
            "plantilles estimades, avisos de provisional— es poden treure."
        )
    else:
        print("\nPretemporada: la web va amb el calendari provisional.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
