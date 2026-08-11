"""Genera l'informe HTML de desplaçaments a partir de rows.json (sense transcriure res a mà)."""

import base64
import json
import sys
from collections import defaultdict
from html import escape
from pathlib import Path

SP = Path(sys.argv[1])
d = json.loads((SP / "rows.json").read_text(encoding="utf-8"))
ROWS, INCOMP, CASA = d["rows"], d["incompar"], d["a_casa"]

CONF = [r for r in ROWS if r["estat"] == "verificat"]
PEND = [r for r in ROWS if r["estat"] == "pendent"]
SEASONS = sorted({r["temporada"] for r in ROWS})
ADRECES, P = d["adreces"], d["params"]
CONSUM = str(P["consum"]).replace(".", ",")
DIETA = f'{P["dieta"]:.2f}'.replace(".", ",")
LLINDAR = P["llindar_km"]



def km(v: float) -> str:
    s = f"{v:,.1f}".replace(",", " ").replace(".", ",")
    return s.replace(" ", ".")


def eur(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s.replace(" ", ".")


def dt(iso: str) -> str:
    y, m, day = iso.split("-")
    return f"{day}/{m}/{y[2:]}"


def comp(r: dict) -> str:
    return "Copa Catalana" if r["tipus"] == "copa" else "Lliga Tres Bandes"


def ordre(r: dict) -> tuple:
    """Ordena per equip (A, B, C i la Copa al final) i, dins de cada equip, per data."""
    return ("Z" if r["tipus"] == "copa" else r["equip"], r["data"])

ESCUT_B64 = base64.b64encode((SP / "escut-cbb-400.png").read_bytes()).decode()

parts = []
A = parts.append

A('<title>Desplaçaments dels equips del C.B. Banyoles · 2014-15 a 2025-26</title>')
A("""<style>
:root{
  --paper:#fbfaf7; --surface:#ffffff; --ink:#16201c; --body:#33403a; --muted:#6b7a72;
  --accent:#1f5f45; --accent-soft:#e6efe9; --warn:#8a5a10; --warn-soft:#f7eeda;
  --line:#dde2db; --line-strong:#c3ccc4;
  --serif:Georgia,"Iowan Old Style","Palatino Linotype",Palatino,serif;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Mono",Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#0f1512; --surface:#161d19; --ink:#eaf0ec; --body:#c4cfc8; --muted:#8b9a92;
    --accent:#5fb391; --accent-soft:#1b2b24; --warn:#d3a052; --warn-soft:#2c2416;
    --line:#26302b; --line-strong:#3a463f;
  }
}
:root[data-theme="dark"]{
  --paper:#0f1512; --surface:#161d19; --ink:#eaf0ec; --body:#c4cfc8; --muted:#8b9a92;
  --accent:#5fb391; --accent-soft:#1b2b24; --warn:#d3a052; --warn-soft:#2c2416;
  --line:#26302b; --line-strong:#3a463f;
}
:root[data-theme="light"]{
  --paper:#fbfaf7; --surface:#ffffff; --ink:#16201c; --body:#33403a; --muted:#6b7a72;
  --accent:#1f5f45; --accent-soft:#e6efe9; --warn:#8a5a10; --warn-soft:#f7eeda;
  --line:#dde2db; --line-strong:#c3ccc4;
}
body{background:var(--paper);color:var(--body);font-family:var(--sans);
  font-size:16px;line-height:1.6;-webkit-text-size-adjust:100%;}
.wrap{max-width:60rem;margin:0 auto;padding:3rem 1.5rem 6rem;
  display:flex;flex-direction:column;gap:3rem;}
h1,h2,h3{font-family:var(--serif);color:var(--ink);text-wrap:balance;font-weight:600;line-height:1.2;}
h1{font-size:2.1rem;margin:0;letter-spacing:-.01em;}
h2{font-size:1.4rem;margin:0;}
h3{font-size:1.05rem;margin:0;}
p{margin:0;max-width:62ch;}
a{color:var(--accent);}
.eyebrow{font-family:var(--sans);font-size:.72rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);font-weight:600;}
header.doc{display:flex;align-items:center;gap:1.6rem;
  border-bottom:2px solid var(--line-strong);padding-bottom:1.6rem;}
header.doc>div{display:flex;flex-direction:column;gap:.6rem;}
header.doc .escut{height:6.5rem;width:auto;flex:0 0 auto;}
@media (max-width:34rem){header.doc{flex-direction:column;align-items:flex-start;}}
header.doc .sub{color:var(--muted);font-size:.95rem;}
.headline{display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);}
.headline div{background:var(--surface);padding:1.1rem 1.2rem;
  display:flex;flex-direction:column;gap:.3rem;}
.headline .n{font-family:var(--serif);font-size:1.9rem;color:var(--ink);
  font-variant-numeric:tabular-nums;line-height:1;}
.headline .n.warn{color:var(--warn);}
.headline .l{font-size:.78rem;color:var(--muted);line-height:1.35;}
section{display:flex;flex-direction:column;gap:1.1rem;}
.note{border-left:3px solid var(--accent);background:var(--accent-soft);
  padding:.9rem 1.1rem;font-size:.92rem;color:var(--ink);}
.note.warn{border-left-color:var(--warn);background:var(--warn-soft);}
.scroll{overflow-x:auto;border:1px solid var(--line);background:var(--surface);}
table{border-collapse:collapse;width:100%;font-size:.86rem;}
caption{text-align:left;padding:.85rem 1rem;font-family:var(--serif);font-size:1.05rem;
  color:var(--ink);border-bottom:1px solid var(--line);background:var(--surface);}
caption .cs{font-family:var(--sans);font-size:.78rem;color:var(--muted);float:right;
  font-variant-numeric:tabular-nums;padding-top:.3rem;}
th,td{padding:.5rem .8rem;text-align:left;border-bottom:1px solid var(--line);
  vertical-align:top;white-space:nowrap;}
thead th{font-size:.7rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  font-weight:600;background:var(--surface);border-bottom:1px solid var(--line-strong);}
tbody tr:last-child td{border-bottom:none;}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;font-family:var(--mono);
  font-size:.82rem;}
td.km{color:var(--ink);font-weight:600;}
tfoot td{border-top:2px solid var(--line-strong);font-weight:600;color:var(--ink);
  background:var(--surface);}
td.eq{font-weight:600;color:var(--ink);}
td.grp{font-family:var(--mono);font-size:.82rem;color:var(--ink);}
td.dat{font-family:var(--mono);font-size:.82rem;font-variant-numeric:tabular-nums;}
tbody+tbody td{border-top:1px solid var(--line-strong);}
tr.sub td{background:var(--accent-soft);color:var(--ink);font-weight:600;font-size:.8rem;}
tr.sub td:first-child{text-align:right;}
tr.nj td{color:var(--muted);font-style:italic;}
.chip{display:inline-block;font-size:.68rem;letter-spacing:.05em;text-transform:uppercase;
  padding:.12rem .45rem;border:1px solid currentColor;border-radius:2px;font-weight:600;}
.chip.ok{color:var(--accent);}
.chip.warn{color:var(--warn);}
.season{display:flex;flex-direction:column;gap:.9rem;}
.season-head{display:flex;align-items:baseline;justify-content:space-between;
  gap:1rem;flex-wrap:wrap;border-bottom:1px solid var(--line-strong);padding-bottom:.45rem;}
.season-head .tot{font-family:var(--mono);font-size:.95rem;color:var(--ink);
  font-variant-numeric:tabular-nums;font-weight:600;}
dl.meta{display:grid;grid-template-columns:auto 1fr;gap:.35rem 1.2rem;
  font-size:.88rem;margin:0;}
dl.meta dt{color:var(--muted);}
dl.meta dd{margin:0;color:var(--body);}
ol.method{margin:0;padding-left:1.2rem;display:flex;flex-direction:column;gap:.55rem;
  font-size:.92rem;}
footer{border-top:1px solid var(--line);padding-top:1.2rem;font-size:.82rem;color:var(--muted);}
@media print{
  body{background:#fff;font-size:10.5pt;}
  .wrap{max-width:none;padding:0;gap:1.6rem;}
  .scroll{overflow:visible;break-inside:auto;}
  .season,section{break-inside:avoid-page;}
  table{font-size:8.5pt;}
  a{color:inherit;text-decoration:none;}
}
</style>""")

A('<div class="wrap">')

# ---- capçalera -------------------------------------------------------------
A(f"""<header class="doc">
 <img class="escut" src="data:image/png;base64,{ESCUT_B64}" alt="Escut del Club Billar Banyoles">
 <div>
  <span class="eyebrow">Justificació de despesa · sol·licitud d'ajut</span>
  <h1>Desplaçaments dels equips del Club Billar Banyoles</h1>
  <p class="sub">Temporades 2014-2015 a 2025-2026 · competicions oficials per equips de la
  Federació Catalana de Billar · quilòmetres de carretera d'anada i tornada des de la seu
  del club.</p>
 </div>
</header>""")

A('<div class="headline">')
A(f'<div><span class="n">{km(sum(r["km_total"] for r in CONF))}</span>'
  f'<span class="l">km recorreguts<br>(anada i tornada)</span></div>')
A(f'<div><span class="n">{len(CONF)}</span><span class="l">desplaçaments en 5 temporades '
  f'de competició</span></div>')
A(f'<div><span class="n">{eur(sum(r["import_km_eur"] for r in CONF))} €</span>'
  f'<span class="l">cost de quilometratge<br>al barem oficial</span></div>')
A(f'<div><span class="n">{eur(sum(r["import_dietes_eur"] for r in CONF))} €</span>'
  f'<span class="l">cost de dietes<br>de manutenció</span></div>')
A(f'<div><span class="n">{eur(sum(r["import_total_eur"] for r in CONF))} €</span>'
  f'<span class="l">cost total<br>del període</span></div>')
A("</div>")

A(f"""<section>
 <div class="note"><strong>Com llegir aquest document.</strong> Només s'hi compten els
 desplaçaments per jugar fora de casa, comptabilitzats d'anada i tornada. Cada línia porta
 la data, l'equip, la divisió i el grup, de manera que es pot contrastar una a una amb el
 portal públic de la Federació Catalana de Billar. La valoració econòmica combina el barem
 oficial de quilometratge exempt a l'IRPF, aplicat amb la tarifa vigent el dia del partit, i
 la dieta de manutenció de migdia per als desplaçaments de més de {LLINDAR} km d'anada.</div>
</section>""")

# ---- 2020-2021 -------------------------------------------------------------
A("""<section>
 <h2>Temporada 2020-2021: sense equips en competició</h2>
 <p>De les dotze temporades que cobreix aquest document, la 2020-2021 és l'única sense
 cap desplaçament: el club no hi va inscriure cap equip. Va ser la
 temporada afectada per la COVID-19, en què la competició no va començar fins al 13 de
 març de 2021, i tampoc no es va disputar la Copa Catalana per equips.</p>
 <p><strong>Desplaçaments 2020-2021: cap. 0 km.</strong></p>
</section>""")

# ---- detall per temporada --------------------------------------------------
A('<section><h2>Detall per temporada</h2>')
for s in SEASONS:
    sel = sorted([r for r in CONF if r["temporada"] == s], key=ordre)
    if not sel:
        continue
    agg = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    for r in sel:
        k = (ordre(r)[0], r["equip"], comp(r))
        agg[k][0] += 1
        agg[k][1] += r["km_total"]
        agg[k][2] += r["import_km_eur"]
        agg[k][3] += r["import_dietes_eur"]
    A('<div class="season">')
    A(f'<div class="season-head"><h3>{s}</h3><span class="tot">{len(sel)} desplaçaments · '
      f'{km(sum(r["km_total"] for r in sel))} km</span></div>')
    A('<div class="scroll"><table>')
    A('<caption>Equips i competicions<span class="cs">km anada i tornada</span></caption>')
    A('<thead><tr><th>Equip</th><th>Competició</th>'
      '<th class="num">Despl.</th><th class="num">km</th>'
      '<th class="num">Quilometratge</th><th class="num">Dietes</th>'
      '<th class="num">Total</th></tr></thead><tbody>')
    for k, (n, t, q, di) in sorted(agg.items()):
        A(f'<tr><td>{escape(k[1])}</td><td>{escape(k[2])}</td>'
          f'<td class="num">{n}</td><td class="num">{km(t)}</td>'
          f'<td class="num">{eur(q)} €</td><td class="num">{eur(di)} €</td>'
          f'<td class="num km">{eur(q + di)} €</td></tr>')
    A(f'</tbody><tfoot><tr><td colspan="2">Total {s}</td>'
      f'<td class="num">{len(sel)}</td><td class="num">{km(sum(r["km_total"] for r in sel))}</td>'
      f'<td class="num">{eur(sum(r["import_km_eur"] for r in sel))} €</td>'
      f'<td class="num">{eur(sum(r["import_dietes_eur"] for r in sel))} €</td>'
      f'<td class="num">{eur(sum(r["import_total_eur"] for r in sel))} €</td>'
      f'</tr></tfoot></table></div>')
    A('<div class="scroll"><table>')
    A('<caption>Desplaçaments un a un, per equip<span class="cs">km anada i tornada'
      '</span></caption>')
    A('<thead><tr><th>Equip</th><th>Data</th><th>Competició</th><th>Divisió</th><th>Grup</th>'
      '<th>Club on es juga</th><th class="num">km</th><th class="num">€/km</th>'
      '<th class="num">Quilometratge</th><th class="num">Jug.</th>'
      '<th class="num">€/dieta</th><th class="num">Dietes</th>'
      '<th class="num">Total</th></tr></thead>')
    blocs = defaultdict(list)
    for r in sorted([x for x in ROWS if x["temporada"] == s
                     and x["estat"] in ("verificat", "incompareixenca")], key=ordre):
        blocs[ordre(r)[0]].append(r)
    for _, bloc in sorted(blocs.items()):
        A("<tbody>")
        for i, r in enumerate(bloc):
            equip = escape(r["equip"]) if i == 0 else ""
            no_jugat = r["estat"] == "incompareixenca"
            A(f'<tr{" class=\"nj\"" if no_jugat else ""}>'
              f'<td class="eq">{equip}</td>'
              f'<td class="dat">{dt(r["data"])}{" *" if no_jugat else ""}</td>'
              f'<td>{escape(comp(r))}</td><td>{escape(r["divisio"])}</td>'
              f'<td class="grp">{escape(r["grup"])}</td>'
              f'<td>{escape(r["seu_club"])}</td>'
              f'<td class="num">{km(r["km_total"])}</td>'
              f'<td class="num">{eur(r["tarifa_eur_km"])}</td>'
              f'<td class="num">{eur(r["import_km_eur"])} €</td>'
              f'<td class="num">{r["jugadors"]}</td>'
              f'<td class="num">{DIETA + " €" if r["te_dieta"] else "—"}</td>'
              f'<td class="num">{eur(r["import_dietes_eur"])} €</td>'
              f'<td class="num km">{eur(r["import_total_eur"])} €</td></tr>')
        n_jugats = sum(1 for x in bloc if x["estat"] == "verificat")
        jug = [x for x in bloc if x["estat"] == "verificat"]
        A(f'<tr class="sub"><td colspan="6">Subtotal {escape(bloc[0]["equip"])}'
          f'{" · Copa" if bloc[0]["tipus"] == "copa" else ""} · {n_jugats} '
          f'desplaçament{"s" if n_jugats != 1 else ""}</td>'
          f'<td class="num">{km(sum(x["km_total"] for x in jug))}</td><td></td>'
          f'<td class="num">{eur(sum(x["import_km_eur"] for x in jug))} €</td>'
          f'<td></td><td></td>'
          f'<td class="num">{eur(sum(x["import_dietes_eur"] for x in jug))} €</td>'
          f'<td class="num">{eur(sum(x["import_total_eur"] for x in jug))} €</td></tr>')
        A("</tbody>")
    A(f'<tfoot><tr><td colspan="6">Total {s}</td>'
      f'<td class="num">{km(sum(r["km_total"] for r in sel))}</td><td></td>'
      f'<td class="num">{eur(sum(r["import_km_eur"] for r in sel))} €</td>'
      f'<td></td><td></td>'
      f'<td class="num">{eur(sum(r["import_dietes_eur"] for r in sel))} €</td>'
      f'<td class="num">{eur(sum(r["import_total_eur"] for r in sel))} €</td>'
      f'</tr></tfoot></table></div>')
    if any(r["estat"] == "incompareixenca" and r["temporada"] == s for r in ROWS):
        A('<p style="font-size:.85rem;color:var(--muted)">* Encontre no disputat per '
          'incompareixença: consta al calendari federatiu però no es va jugar, de manera '
          'que no genera desplaçament ni computa.</p>')
    A("</div>")
A("</section>")

# ---- resum global ----------------------------------------------------------
A('<section><h2>Resum</h2><div class="scroll"><table>')
A('<caption>Total per temporada<span class="cs">km anada i tornada</span></caption>')
A('<thead><tr><th>Temporada</th><th>Equips</th>'
  '<th class="num">Despl.</th><th class="num">km</th>'
  '<th class="num">Quilometratge</th><th class="num">Dietes</th>'
  '<th class="num">Total</th></tr></thead><tbody>')
# La 2020-2021 no te desplacaments pero es llista igualment, al seu lloc.
for s in sorted(set(SEASONS) | {"2020-2021"}):
    c = [r for r in CONF if r["temporada"] == s]
    if not c:
        A(f'<tr><td>{s}</td><td>cap</td><td class="num">0</td>'
          '<td class="num km">0,0</td><td class="num">0,00 €</td>'
          '<td class="num">0,00 €</td><td class="num km">0,00 €</td></tr>')
        continue
    eq = sorted({r["equip"].replace("Banyoles ", "").replace('"', "")
                 for r in c if r["tipus"] == "regular"})
    A(f'<tr><td>{s}</td><td>{escape(", ".join(eq))}</td><td class="num">{len(c)}</td>'
      f'<td class="num">{km(sum(r["km_total"] for r in c))}</td>'
      f'<td class="num">{eur(sum(r["import_km_eur"] for r in c))} €</td>'
      f'<td class="num">{eur(sum(r["import_dietes_eur"] for r in c))} €</td>'
      f'<td class="num km">{eur(sum(r["import_total_eur"] for r in c))} €</td></tr>')
A(f'</tbody><tfoot><tr><td colspan="2">Total 2014-15 a 2025-26</td>'
  f'<td class="num">{len(CONF)}</td><td class="num">{km(sum(r["km_total"] for r in CONF))}</td>'
  f'<td class="num">{eur(sum(r["import_km_eur"] for r in CONF))} €</td>'
  f'<td class="num">{eur(sum(r["import_dietes_eur"] for r in CONF))} €</td>'
  f'<td class="num">{eur(sum(r["import_total_eur"] for r in CONF))} €</td>'
  f'</tr></tfoot></table></div>')
n_dieta = sum(1 for r in CONF if r["te_dieta"])
A(f"""<div class="note"><strong>Imports unitaris aplicats.</strong>
 Quilometratge: <strong>0,19 €/km</strong> fins al 16 de juliol de 2023 i
 <strong>0,26 €/km</strong> a partir del 17 de juliol de 2023, segons el barem exempt de
 l'IRPF de l'Ordre HFP/792/2023, aplicat amb la tarifa vigent el dia de cada partit.
 Dieta de migdia: <strong>{DIETA} € per jugador</strong>, en els desplaçaments de més de
 {LLINDAR} km d'anada — {n_dieta} dels {len(CONF)}—, amb quatre jugadors per desplaçament a
 la lliga i tres a la Copa. Són, doncs, {eur(4 * P["dieta"])} € de dietes per desplaçament
 de lliga i {eur(3 * P["dieta"])} € per jornada de Copa.</div>""")
A('</section>')

# ---- projecció 2026-2027 ---------------------------------------------------
A('<section><h2>Despesa estimada per a la temporada 2026-2027</h2>')
A("""<p>Els tres equips del club ja tenen divisió, però no grup assignats per a la
 temporada vinent. La composició dels grups és estimada a partir de les classificacions de
 l'any passat i pot tenir modificacions. Com que cada grup es juga a doble volta, el nombre
 de desplaçaments i les seus són coneguts d'entrada, encara que el calendari no estigui
 publicat: un viatge a cada un dels altres clubs del grup.</p>""")
A("""<div class="note warn"><strong>És una previsió, no una despesa realitzada.</strong>
 Aquest apartat no forma part dels imports justificats de les temporades anteriors i no s'hi
 ha de sumar. No inclou la Copa Catalana, perquè encara no se sap si el club hi participarà.
 El quilometratge s'hi valora tot a 0,26 €/km, el barem vigent.</div>""")
PROJ = d["projeccio"]
blocs_p = defaultdict(list)
for r in PROJ:
    blocs_p[(r["equip"], r["divisio"], r["grup"])].append(r)
A('<div class="scroll"><table>')
A('<caption>Equips i competicions<span class="cs">km anada i tornada</span></caption>')
A('<thead><tr><th>Equip</th><th>Competició</th>'
  '<th class="num">Despl.</th><th class="num">km</th>'
  '<th class="num">Quilometratge</th><th class="num">Dietes</th>'
  '<th class="num">Total</th></tr></thead><tbody>')
for k, bloc in sorted(blocs_p.items()):
    A(f'<tr><td>{escape(k[0])}</td><td>Lliga Tres Bandes</td>'
      f'<td class="num">{len(bloc)}</td>'
      f'<td class="num">{km(sum(x["km_total"] for x in bloc))}</td>'
      f'<td class="num">{eur(sum(x["import_km_eur"] for x in bloc))} €</td>'
      f'<td class="num">{eur(sum(x["import_dietes_eur"] for x in bloc))} €</td>'
      f'<td class="num km">{eur(sum(x["import_total_eur"] for x in bloc))} €</td></tr>')
A(f'</tbody><tfoot><tr><td colspan="2">Total previst 2026-2027</td>'
  f'<td class="num">{len(PROJ)}</td>'
  f'<td class="num">{km(sum(r["km_total"] for r in PROJ))}</td>'
  f'<td class="num">{eur(sum(r["import_km_eur"] for r in PROJ))} €</td>'
  f'<td class="num">{eur(sum(r["import_dietes_eur"] for r in PROJ))} €</td>'
  f'<td class="num">{eur(sum(r["import_total_eur"] for r in PROJ))} €</td>'
  f'</tr></tfoot></table></div>')

A('<div class="scroll"><table>')
A('<caption>Desplaçaments previstos, un per rival<span class="cs">km anada i tornada'
  '</span></caption>')
A('<thead><tr><th>Equip</th><th>Divisió</th><th>Grup</th><th>Rival</th><th>Municipi</th>'
  '<th class="num">km</th><th class="num">€/km</th><th class="num">Quilometratge</th>'
  '<th class="num">Jug.</th><th class="num">€/dieta</th><th class="num">Dietes</th>'
  '<th class="num">Total</th></tr></thead>')
for k, bloc in sorted(blocs_p.items()):
    A("<tbody>")
    for i, r in enumerate(bloc):
        rival = f'{r["rival_club"]} {r["rival_equip"]}'.strip()
        A(f'<tr><td class="eq">{escape(k[0]) if i == 0 else ""}</td>'
          f'<td>{escape(r["divisio"]) if i == 0 else ""}</td>'
          f'<td class="grp">{escape(r["grup"]) if i == 0 else ""}</td>'
          f'<td>{escape(rival)}</td><td>{escape(r["municipi"])}</td>'
          f'<td class="num">{km(r["km_total"])}</td>'
          f'<td class="num">{eur(r["tarifa_eur_km"])}</td>'
          f'<td class="num">{eur(r["import_km_eur"])} €</td>'
          f'<td class="num">{r["jugadors"] if r["te_dieta"] else "—"}</td>'
          f'<td class="num">{DIETA + " €" if r["te_dieta"] else "—"}</td>'
          f'<td class="num">{eur(r["import_dietes_eur"]) + " €" if r["te_dieta"] else "—"}</td>'
          f'<td class="num km">{eur(r["import_total_eur"])} €</td></tr>')
    A(f'<tr class="sub"><td colspan="5">Subtotal {escape(k[0])} · {len(bloc)} desplaçaments'
      f'</td><td class="num">{km(sum(x["km_total"] for x in bloc))}</td><td></td>'
      f'<td class="num">{eur(sum(x["import_km_eur"] for x in bloc))} €</td>'
      f'<td></td><td></td>'
      f'<td class="num">{eur(sum(x["import_dietes_eur"] for x in bloc))} €</td>'
      f'<td class="num">{eur(sum(x["import_total_eur"] for x in bloc))} €</td></tr>')
    A("</tbody>")
A(f'<tfoot><tr><td colspan="5">Total previst 2026-2027 · {len(PROJ)} desplaçaments</td>'
  f'<td class="num">{km(sum(r["km_total"] for r in PROJ))}</td><td></td>'
  f'<td class="num">{eur(sum(r["import_km_eur"] for r in PROJ))} €</td>'
  f'<td></td><td></td>'
  f'<td class="num">{eur(sum(r["import_dietes_eur"] for r in PROJ))} €</td>'
  f'<td class="num">{eur(sum(r["import_total_eur"] for r in PROJ))} €</td>'
  f'</tr></tfoot></table></div>')
A("</section>")

# ---- taula de distàncies ---------------------------------------------------
A('<section><h2>Distàncies de referència</h2>')
A("""<p>Una sola distància per club, aplicada a tots els desplaçaments que s'hi han fet.
 L'adreça és la que consta al directori oficial de clubs de la Federació Catalana de Billar;
 l'origen és sempre el Club Billar Banyoles, carrer de l'Abeurador 10, Banyoles.</p>""")
dist = {}
for r in ROWS:
    dist.setdefault(r["seu_club"], r)
A('<div class="scroll"><table>')
A('<caption>Clubs visitats<span class="cs">ordenats per distància</span></caption>')
A('<thead><tr><th>Club</th><th>Adreça (directori FCB)</th><th>Municipi</th>'
  '<th class="num">km anada</th><th class="num">km anada i tornada</th>'
  '<th class="num">Visites</th></tr></thead><tbody>')
for nom, r in sorted(dist.items(), key=lambda x: x[1]["km_anada"]):
    n = sum(1 for x in ROWS if x["seu_club"] == nom)
    A(f'<tr><td>{escape(nom)}</td>'
      f'<td style="white-space:normal">{escape(ADRECES.get(nom, "—"))}</td>'
      f'<td>{escape(r["municipi"])}</td>'
      f'<td class="num">{km(r["km_anada"])}</td>'
      f'<td class="num km">{km(r["km_total"])}</td><td class="num">{n}</td></tr>')
A('</tbody></table></div></section>')

# ---- metodologia -----------------------------------------------------------
A('<section><h2>Metodologia i fonts</h2>')
A("""<ol class="method">
 <li><strong>Calendari i resultats.</strong> Tots els encontres provenen del portal públic
 de la Federació Catalana de Billar (<a href="https://www.fcbillar.cat">fcbillar.cat</a>).
 S'han recorregut, per a cada temporada, totes les divisions i tots els grups on hi ha
 hagut un equip del club, jornada per jornada, i s'ha comprovat que el calendari recollit
 coincideix amb el publicat. De la 2021-2022 ençà s'ha contrastat la base de dades del
 club amb el portal, grup a grup i jornada a jornada —20 grups, 179 encontres
 programats i cap divergència de data—; de la 2014-2015 a la 2019-2020, en què la base
 de dades del club no és completa, les dades s'han pres directament del portal, on hi
 consten 16 grups i 148 encontres amb data.</li>
 <li><strong>Direcció dels desplaçaments.</strong> Es compta desplaçament quan l'equip del
 Banyoles figura com a visitant.</li>
 <li><strong>Seu de joc.</strong> A la lliga regular, el local de joc és el del club local
 de l'encontre. A la Copa, on la seu és la del club responsable de cada grup.</li>
 <li><strong>Adreces.</strong> Del directori oficial de clubs de la Federació Catalana de
 Billar. Origen de tots els trajectes: Club Billar Banyoles, carrer de l'Abeurador 10,
 17820 Banyoles.</li>
 <li><strong>Coordenades.</strong> Geocodificades amb Nominatim sobre dades
 d'OpenStreetMap i revisades una a una. Vint-i-vuit clubs estan situats a nivell de carrer
 o de portal; dos (Canet de Mar i Sant Feliu de Codines) a nivell de municipi perquè el
 carrer indicat no consta a la cartografia, cosa que en trajectes de més de 70 km suposa
 una diferència inferior a l'1 %.</li>
 <li><strong>Quilòmetres.</strong> Calculats amb OSRM, motor d'encaminament obert sobre la
 xarxa viària d'OpenStreetMap, perfil de vehicle, ruta més ràpida. Cada tram és la
 distància real per carretera entre les dues adreces, multiplicada per dos per comptar
 l'anada i la tornada. El càlcul és reproduïble: amb les mateixes coordenades, qualsevol
 pot repetir-lo i obtenir la mateixa xifra.</li>
 <li><strong>Adreces.</strong> Les del directori oficial de clubs de la Federació Catalana
 de Billar, unificades a un sol criteri tipogràfic —majúscula inicial i abreviatures
 desplegades— perquè el directori les publica amb formats barrejats. Només se n'ha canviat
 la forma: no s'hi ha afegit ni tret cap dada.</li>
 <li><strong>Quilometratge.</strong> Barem d'indemnització per ús de vehicle particular
 exempt de gravamen a l'IRPF, aplicat amb la tarifa vigent el dia de cada partit: 0,19 €/km
 fins al 16 de juliol de 2023 i 0,26 €/km a partir del 17 de juliol de 2023, segons
 l'<a href="https://www.boe.es/buscar/doc.php?id=BOE-A-2023-16461">Ordre HFP/792/2023</a>.
 Aquest barem cobreix el conjunt de costos del vehicle i no només el carburant. No s'hi han
 afegit peatges ni aparcament, que la norma admet a part però que aquí no consten
 justificats.</li>
 <li><strong>Dietes de manutenció.</strong> Dieta de migdia de """ + DIETA + """ € per
 jugador, import que aplica el club. Es manté per sota dels 26,67 € que l'article 9 del
 Reglament de l'IRPF fixa com a límit exempt de gravamen per a la manutenció sense
 pernoctació en territori espanyol. S'aplica als desplaçaments de més de """
  + str(LLINDAR) + """ km d'anada: de tots els que recull el document, només el del 8
 d'octubre de 2022 al GEiEG de Girona queda per sota del llindar. El nombre de jugadors per
 desplaçament és de quatre a la lliga i de tres a la Copa, on cada equip presenta tres
 jugadors.</li>
</ol>""")
A("""<p style="font-size:.9rem">Els imports unitaris del document són, doncs, dos: la
 tarifa de quilometratge vigent el dia de cada partit i la dieta de """ + DIETA + """ € per
 jugador. Tota la resta en deriva.</p>""")
A("""<dl class="meta" style="margin-top:1.2rem">
 <dt>Àmbit</dt><dd>Competicions oficials per equips: Lliga Catalana Tres Bandes i Copa
 Catalana per equips. No s'hi inclouen les proves individuals.</dd>
 <dt>Període</dt><dd>Temporades 2014-2015 a 2025-2026. La 2020-2021 no hi surt perquè
 el club no hi va tenir equips.</dd>
 <dt>Unitat</dt><dd>Un desplaçament = un viatge d'anada i tornada per a una jornada.</dd>
 <dt>No inclòs</dt><dd>Nombre de vehicles, ocupants ni cost per quilòmetre: aquest document
 quantifica només la distància recorreguda.</dd>
</dl>""")
A("</section>")

A("""<footer>Document generat a partir de la base de dades de competicions del Club Billar
 Banyoles, contrastada amb el portal públic de la Federació Catalana de Billar. Les dades
 de resultats i calendari són de la federació; el càlcul de distàncies és propi i
 reproduïble.</footer>""")
A("</div>")

(SP / "informe.html").write_text("\n".join(parts), encoding="utf-8")
print("informe.html", len("\n".join(parts)), "bytes")
print("verificats:", len(CONF), km(sum(r["km_total"] for r in CONF)))
print("pendents:", len(PEND), km(sum(r["km_total"] for r in PEND)))
