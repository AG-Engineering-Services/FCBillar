# Resultats internacionals

Mundials i copes del món de la UMB (`umb-carom.org`, PDF de resultats) i
campionats d'Europa de la CEB (`eurobillard.org`, resultats dins del HTML de cada
prova). Tot es baixa a `data/cache/umb/` i `data/cache/ceb/`, que no es versionen.

    fcbillar umb-descarrega     # descobreix i baixa, en sèrie i amb pausa d'un segon
    fcbillar umb-carrega        # llegeix i desa a la BBDD local (reemplaça, no duplica)
    fcbillar umb-candidats      # proposa lligams a fitxes.csv
    fcbillar publish-umb        # puja a Neon (després d'aplicar la migració 0037)

Els ids de la CEB es desen com `100000 + id` perquè no xoquin amb els de la UMB.

## Els jugadors que tenen fitxa al cens català

`fitxes.csv` diu quin `umb_id` és quina fitxa del cens. Els candidats són els
jugadors espanyols (ES) de les proves, proposats amb el mateix criteri que la
Lliga Nacional (`nacional_fitxes`). A la columna `validat` s'hi posa `si` o `no`;
tornar-ho a executar afegeix els candidats nous i no toca els que ja hi són.

Un `umb_id` que comença per `x:` no el dona la UMB: la CEB i els PDF del 2018 no
en porten, i es fabrica amb el nom i la nacionalitat. Si el mateix jugador surt
amb id a una altra prova, aquest id s'hi copia.

Res d'aquí compta per a cap rànquing ni mitjana catalana.
