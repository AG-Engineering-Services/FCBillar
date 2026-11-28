# Second pass: trainer spec + a drawn path for every example

The page now needs (1) a trainer for EVERY system and (2) a drawn path for EVERY example.
Edit your own JSON files in place (same folder). Keep everything already there; add/complete what follows.
Write Catalan text. Use the book only (re-look at pages when needed).

## 1. Every example gets a `path`
- If the drawing is readable to about ±0.2 diamond, measure it as before.
- If the drawing is too busy, or the example is text only, BUILD the path from the system itself: cue ball
  position (from the drawing, or a plausible spot on the shot line), then the rail points that the example's
  values mark on your numberings, in contact order. Add `"path_built": true` to that example so the page can say
  "recorregut construït a partir dels valors".
- Shots that hit a ball first: the contact with that ball is a path point; also add `"balls": [{"x":..,"y":..,"c":"red|yellow|white"}]`
  for the object balls when the drawing shows them (for any example, if readable).
- If an example truly has no geometry (e.g. a general rule), turn it into one that does, or drop it into `tips`.

## 2. Add a `trainer` object to every file

```json
"trainer": {
  "calc": {
    "vars": {
      "S": { "label": "Sortida", "numbering": "Sortida" },
      "A": { "label": "Atac",    "numbering": "Atac" },
      "L": { "label": "Llegada", "numbering": "Llegada" },
      "E": { "label": "Efecte",  "values": [1, 2, 3, 4] }
    },
    "inputs": { "S": [50, 45, 40, 35, 30], "L": [10, 15, 20, 25, 30] },
    "relations": [
      { "solve": "A", "expr": "S - L" },
      { "solve": "L", "expr": "S - A" }
    ],
    "tables": { "corr": { "60": 12.5, "70": 15 } },
    "valid": "A >= 0 && A <= 50",
    "round": 1,
    "path": ["S", "A", "L"],
    "note": "optional: what the generated shot assumes"
  },
  "quiz": [
    { "q": "question", "options": ["a", "b", "c", "d"], "answer": 0,
      "explain": "short why, with the book's numbers", "page": 57,
      "path": [ {"x":..,"y":..} ], "balls": [ ... ] }
  ]
}
```

### `calc` (only for systems with a real formula or lookup)
- `vars`: one letter per quantity. `numbering` must equal the `name` of one of the file's `numberings` (then the
  value has a position on the table and can be drawn/tapped). Quantities with no rail position use `values`.
- `inputs`: the values the trainer may pick for each var it uses as an input (choose realistic, book-consistent
  sets; 4–12 values each). Every var that appears on the right side of some relation needs an `inputs` entry,
  except the one being solved.
- `relations`: each is a way the system is used; the trainer picks one, takes the other vars from `inputs`,
  computes `solve` with `expr`. `expr` is a JavaScript arithmetic expression over the var letters, `Math.*`,
  and tables written `T.corr[S]` (keys are strings of the value, e.g. "60"; use exact values present in inputs).
  Include the inverse forms the book uses (e.g. given S and A, find L).
- `valid`: JS condition over the vars; generated questions that fail it are discarded (keep the result inside the
  numbering's range, respect the book's limits/zones).
- `path`: the vars (with numbering) in contact order to draw the generated shot (start rail first). Omit if it would
  not make geometric sense.
- Corrections that depend on a case can be separate relations with a `when` JS condition, e.g.
  `{ "solve": "A", "expr": "S - L + 2", "when": "S < 25", "label": "cas A" }`.
- Test your expressions mentally against at least two of the book's examples; put any mismatch in `uncertain`.

### `quiz` (ALL systems, 4–8 items; drills/position systems rely on it entirely)
Questions a player should be able to answer after studying that system from the book: which effect, which
stroke, where to aim, what correction applies, what result an example gives, which zone, when NOT to use it.
Exactly one correct option; distractors plausible and from the same domain. Give a `path` (and `balls` if useful)
whenever the question is about a shot, so the trainer can draw it. `answer` is the index of the correct option.

Final message: per file, one line: `calc` yes/no (+ relations count), quiz count, examples with path / total,
and anything you could not do.
