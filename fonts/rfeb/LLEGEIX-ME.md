# Fulls de desenvolupament de la RFEB

La RFEB porta el desenvolupament de moltes proves en fulls de Google i els
enllaça des de la pàgina de cada prova: els play-offs de la Lliga Nacional, les
seleccions autonòmiques, els campionats sub-15, els GPE de la web nova… Hi ha
les partides una a una, que la classificació final en PDF no té.

- `fulls.csv`: un full per fila. Hi diu de quina prova és (temporada,
  modalitat, categoria, tipus, títol), quines pestanyes es llegeixen i amb quin
  lector (`actes`: una partida per fila; `parelles`: una fila per jugador). Les
  pestanyes de classificació no s'hi posen: tenen la forma d'una partida i no
  ho són.
- `fulls/<id del full>/<pestanya>.csv`: cada pestanya tal com es va baixar.

Un full nou: afegeix-lo a `fulls.csv` i executa

```bash
uv run fcbillar rfeb-fulls --baixa tots
uv run fcbillar nacional-candidats   # proposa els lligams dels noms nous
```

Els que tenen `viu` a `si` (una prova que s'està jugant) es tornen a baixar
cada nit. Quan la prova s'acaba, es treu el `si` i es desa la darrera baixada.

Els fulls de cinc quilles no hi són: es puntuen d'una altra manera i no porten
caramboles ni entrades.
