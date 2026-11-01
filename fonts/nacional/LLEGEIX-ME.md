# Els PDF de la Lliga Nacional

La RFEB no té web de competició: de cada jornada en fa un PDF, i a part un amb la
classificació de jugadors. Els de temporades passades són a `rfeb.org`; els de la
temporada en curs arriben per correu als clubs i triguen a penjar-se.

Aquí es guarden els que encara no són enlloc més, un cop per temporada i divisió:

    fonts/nacional/<temporada>/<divisió>/

- `<temporada>` amb guió: `2026-2027`.
- `<divisió>`: `honor`, `1` o `2`.
- El nom del fitxer és indiferent. Cada PDF es reconeix sol: una jornada porta el
  seu número i la seva data, i la classificació de jugadors és acumulada, o sigui
  que només cal l'última.

El procés de cada nit (`fcbillar ingest-nacional-fonts`) els torna a llegir tots i
els publica. Per afegir una jornada n'hi ha prou amb pujar-ne el PDF.

Es llegeixen les tres divisions: Honor, Primera i Segona. De cadascuna, les
jornades, la classificació de jugadors i el calendari.

La Segona té quatre grups i la RFEB en fa dos PDF per jornada: un del grup A
(`liga_nal_2a_j3.pdf`) i un dels grups B, C i D (`liga_nal_2_j3.pdf`). Tots dos
van a la mateixa carpeta, `2`, i cal guardar-los tots dos: porten el mateix
número de jornada, però cadascun només reemplaça els seus grups. Quan es pugen
des de l'aplicació queden com a `liga_nal_2_j3_A.pdf` i `liga_nal_2_j3_BCD.pdf`.

Un encontre que el PDF dona per «SUSPENDIDO» es desa com si encara s'hagués de
jugar: sense resultat ni partides.

## Pujar-los des de l'aplicació

Un administrador d'un club que juga la lliga pot pujar el PDF des de la seva
aplicació (Admin → Lliga Nacional). El document va a un magatzem de pas, i el
procés `nacional-puja` (`.github/workflows/nacional-puja.yml`) el reconeix
(`fcbillar nacional-puja`), el deixa en aquesta carpeta amb el seu nom, el desa
al repositori i publica només la Lliga Nacional. Si no és cap dels documents que
sabem llegir, no en queda res enlloc i l'aplicació ho diu.

## El calendari

El calendari de la temporada (`calendari.pdf`) s'hi guarda com qualsevol altre
PDF: no porta dades de ningú. Omple les jornades que encara no s'han jugat, amb
el dia i els encontres de cada grup, i és el que deixa passar-les totes
endavant i enrere. Quan arriba el PDF de resultats d'una jornada, mana aquell.

## Les alineacions

L'«orden de fuerza» **no s'hi ha de guardar tal com arriba**: porta adreces,
telèfons i correus de directius. Se'n treu un CSV net amb només el grup, l'equip,
el número d'ordre i el jugador, i és aquell el que es guarda:

    fcbillar nacional-alineacions "Orden de fuerza Primera.pdf"         fonts/nacional/2026-2027/1/alineacions.csv

El procés de cada nit llegeix l'`alineacions.csv` de cada carpeta. És el que fa
que d'un equip es puguin ensenyar tots els jugadors, i no només els que ja han
jugat alguna partida.
