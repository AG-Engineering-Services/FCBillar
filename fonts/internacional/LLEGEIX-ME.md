# Resultats internacionals

Mundials i copes del món de la UMB (`umb-carom.org`, PDF de resultats) i
campionats d'Europa de la CEB (`eurobillard.org`, resultats dins del HTML de cada
prova). Tot es baixa a `data/cache/umb/` i `data/cache/ceb/`, que no es versionen.

    fcbillar umb-descarrega     # descobreix i baixa, en sèrie i amb pausa d'un segon
    fcbillar ceb-antic-descarrega  # PDF d'abans del 2008 del web vell d'eurobillard.org (Wayback)
    fcbillar umb-carrega        # llegeix i desa a la BBDD local (reemplaça, no duplica)
    fcbillar umb-candidats      # proposa lligams a fitxes.csv
    fcbillar publish-umb        # puja a Neon (després d'aplicar la migració 0037)

Els ids de la CEB es desen com `100000 + id` perquè no xoquin amb els de la UMB, i
els del web vell d'eurobillard.org (`data/cache/eb_antic/`) com `200000 + id`.

Els mundials per equips nacionals de 3 bandes (2022 en endavant) es desen com a
partides individuals; `umb_partides.nacio_a` i `nacio_b` diuen amb quina selecció
juga cada costat (migració 0038, que s'ha d'aplicar a Neon abans de publicar).

## Els jugadors que tenen fitxa al cens català

`fitxes.csv` diu quin `umb_id` és quina fitxa del cens. Els candidats són els
jugadors espanyols (ES) de les proves, proposats amb el mateix criteri que la
Lliga Nacional (`nacional_fitxes`). A la columna `validat` s'hi posa `si` o `no`;
tornar-ho a executar afegeix els candidats nous i no toca els que ja hi són.

Un `0000` als PDF vol dir «sense identificador» i no es desa mai com a id. Si un id
surt amb dos noms sense res en comú, el menys freqüent perd l'id.

`espanyols_sense_candidat.csv` (el genera `umb-candidats`) porta els espanyols que no
tenen ni lligam ni candidat, amb fins a tres fitxes del cens que s'hi assemblen pel
cognom, per revisar-los a mà. No és cap lligam.

Un `umb_id` que comença per `x:` no el dona la UMB: la CEB i els PDF del 2018 no
en porten, i es fabrica amb el nom i la nacionalitat. Si el mateix jugador surt
amb id a una altra prova, aquest id s'hi copia.

Res d'aquí compta per a cap rànquing ni mitjana catalana.
