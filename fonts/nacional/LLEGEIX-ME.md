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

De moment només es llegeix la Primera Divisió: la Divisió d'Honor i la Segona
tenen una altra disposició.

No s'hi ha de guardar l'«orden de fuerza» tal com arriba: porta telèfons i correus
de directius.
