# Brief: extract three-cushion billiard systems from a book

The book: `/root/.claude/uploads/48eb9a5d-ae5d-50c0-86d1-4366745dd131/ac1f97f9-sistemas-de-billar-pdf_compress.pdf`
(356 pages, Spanish, mostly by José Lazo, 2010; many diagrams). Plain-text extraction per page is at
`/tmp/claude-0/-home-user-FCBillar/48eb9a5d-ae5d-50c0-86d1-4366745dd131/scratchpad/pdf/pages/NNN.txt` (NNN = PDF page, 001..356).

Use the text files to find content quickly, but the numbers along the rails and the paths live in the drawings:
look at the pages with the Read tool on the PDF using `pages` (max 20 pages per call; e.g. "40-52"). Look at every
page that carries a numbering diagram or a worked example. Do not use web search or outside knowledge to fill
gaps: if the book doesn't say it, put it in `uncertain`.

## Goal
A faithful synthesis of every system in your page range, so a Catalan-speaking club player can study it in an
interactive page that draws each system's numbering on a table. Be exact with numbers.

## Output
Write ONE JSON file per system to `/tmp/claude-0/-home-user-FCBillar/48eb9a5d-ae5d-50c0-86d1-4366745dd131/scratchpad/systems/<id>.json`
(id: short kebab-case, e.g. `base-30`). Text fields in **Catalan**, plain and short (book quotes may stay in Spanish
inside `quotes`). Schema:

```json
{
  "id": "base-30",
  "name": "La base 30",
  "group": "Teoria de diamants | Sistema Plus | Efecte contrari | Pase bola | Altres",
  "attributed_to": "who the book credits (e.g. 'Verworst'), or null",
  "pages": [1, 18],
  "purpose": "one sentence: what shot it solves (e.g. 'tres bandes llarga-curta-llarga sortint de la banda llarga')",
  "shot": { "first_cushion": "llarga|curta|bola", "cushions": "e.g. L-K-L", "effect": "...", "stroke": "golpe/velocitat", "ball": "presa de bola if relevant" },
  "formula": "e.g. 'Atac = Sortida − Llegada' (use the book's terms translated: Sortida, Atac, Llegada, Arribada...) or null",
  "steps": ["how to apply it, 2-6 short steps"],
  "numberings": [
    { "name": "Sortida", "role": "sortida|atac|llegada|arribada|altre",
      "points": [ { "x": 0, "y": 8, "v": 50 } ],
      "note": "optional" }
  ],
  "corrections": ["each correction/exception rule, with numbers"],
  "examples": [ { "text": "e.g. 'Sortida 50, llegada 20 → atac 30'", "page": 12,
                  "path": [ {"x":0,"y":8}, {"x":4,"y":5}, {"x":0,"y":2} ] } ],
  "tips": ["practical advice from the book"],
  "quotes": ["at most 2 short key quotes in Spanish"],
  "uncertain": ["what you could not read or the book leaves ambiguous"]
}
```

### Coordinate frame (important; every system uses the same one)
Table in **portrait**, measured in diamonds: `x` from 0 (left long rail) to 4 (right long rail), `y` from 0 (top
short rail) to 8 (bottom short rail). A point on the left long rail has x=0; on the top short rail y=0, etc.
Corners are (0,0), (4,0), (0,8), (4,8). If the book's drawing is landscape, rotate it to portrait so that the
**cue ball's first cushion and the starting rail keep their relation**, and say how you rotated in `numberings[].note`
once. Place points at the rail position the number marks (cloth edge), with fractions (e.g. y = 5.5) where numbers
sit between diamonds. `path` in examples: cue ball position first, then each cushion contact in order (only if the
drawing makes it readable; omit otherwise).

Keep `numberings` to what the system really numbers. If a system has no numbering (pure effect/position drills),
leave `numberings` empty and describe it in `steps`/`examples`. Non-numeric drill collections (e.g. 'posiciones Nº
11-20') can be one JSON entry summarising the patterns, not one per drill.

Final message: list the files you wrote with one line each, and anything important you couldn't resolve. Keep it short.
