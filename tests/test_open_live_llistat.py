"""Quins opens hi ha, llegits del web nou de la federació.

És el primer pas de `publish-live-opens`, i mentre no funcionava no en funcionava
cap altre: la comanda petava amb un error d'SSL abans de mirar res —el domini
antic ja no té certificat vàlid— i, com que peta abans, tampoc no podia retirar
els opens que ja no estan en curs. Per això l'Open de Mataró del juliol va estar
dos mesos sortint com a «en directe» a /opens, i la vista calculada que en
sortia tapava el rànquing oficial.

Dues coses van canviar amb el web d'agost de 2026: el frontal viu a
`intranet.fcbillar.cat/frontend/…`, i el nom del torneig ha deixat de ser un
botó per ser un enllaç dins d'una taula.
"""

from __future__ import annotations

from fcb_opens.scraper.open_live import BASE, LLISTAT_URL, parse_individuals_llistat

#: Retallat de la pàgina de debò. El que importa és que l'enllaç NO porta
#: class="button", que és el que el lector demanava abans.
LLISTAT_NOU = """
<table class="table">
  <thead><tr><th>Torneig</th><th>Organitzador</th><th>Estat</th></tr></thead>
  <tbody>
    <tr>
      <td><a href="https://intranet.fcbillar.cat/frontend/individuals/divisions/217">OPEN LLIURE PUNT D'ATAC</a></td>
      <td>Cap</td><td>Activa</td>
      <td><a href="https://intranet.fcbillar.cat/frontend/individuals/inscripcions/217">Inscripcions</a></td>
    </tr>
    <tr>
      <td><a href="https://intranet.fcbillar.cat/frontend/individuals/divisions/216">TRES BANDES INDIVIDUAL</a></td>
      <td>Cap</td><td>Activa</td>
      <td><a href="https://intranet.fcbillar.cat/frontend/individuals/inscripcions/216">Inscripcions</a></td>
    </tr>
  </tbody>
</table>
"""

#: Com era abans del canvi de web, que ha de seguir funcionant: les pàgines
#: velles encara són a la memòria cau del disc.
LLISTAT_VELL = """
<div>
  <a class="button" href="/ca/individuals/divisions/211">OPEN TRES BANDES MATARO</a>
  <a class="button" href="/ca/individuals/divisions/209">OPEN TRES BANDES COSTA DAURADA</a>
</div>
"""


def test_llegeix_el_llistat_del_web_nou() -> None:
    entrades = parse_individuals_llistat(LLISTAT_NOU)
    assert [(e.division_id, e.name) for e in entrades] == [
        (217, "OPEN LLIURE PUNT D'ATAC"),
        (216, "TRES BANDES INDIVIDUAL"),
    ]


def test_l_enllaç_d_inscripcions_no_es_una_competicio() -> None:
    """Cada fila en porta dos, d'enllaços, i només un mena a la divisió."""
    entrades = parse_individuals_llistat(LLISTAT_NOU)
    assert len(entrades) == 2


def test_segueix_llegint_el_format_vell() -> None:
    entrades = parse_individuals_llistat(LLISTAT_VELL)
    assert [e.division_id for e in entrades] == [211, 209]


def test_no_repeteix_una_competicio_enllaçada_dues_vegades() -> None:
    doble = LLISTAT_NOU + LLISTAT_NOU
    assert len(parse_individuals_llistat(doble)) == 2


def test_apunta_a_l_intranet_i_no_al_domini_mort() -> None:
    """www.fcbillar.cat ja no té ni certificat vàlid."""
    assert BASE == "https://intranet.fcbillar.cat/frontend"
    assert LLISTAT_URL.endswith("/frontend/individuals/llistat")
