// De quin club és un equip.
//
// NOTA: NouProjecte té el mateix mòdul, a src/lib/utils/club-equip.ts. Són dues
// apps separades i el creuament és el mateix: si aquí falla un nom, allà també.
//
// Els dos noms venen de la federació però no del mateix document, i no
// s'escriuen igual. Al calendari els equips van amb el nom curt, sense accents i
// amb la lletra de l'equip: «C.B. MATARO "B"», «S.B. GRAN PENYA "A"». Al cens de
// clubs hi ha el nom llarg i accentuat: «C.B.MATARÓ», «S.B.LA GRAN PENYA».
//
// No hi ha cap identificador que els lligui: `lliga_calendari` porta el nom tal
// com surt al PDF i prou. O sigui que s'han de casar pel nom, i pel nom no
// coincideixen mai exactament.
//
// La comparació es fa per paraules amb contingut —fora accents, fora les sigles
// del davant, fora els articles— i, per als noms que el cens parteix amb guionet
// («C.B.MONT-ROIG») i el calendari no («C.B. MONTROIG»), també per la
// concatenació. Si un equip casa amb més d'un club no se n'inventa cap: val més
// dir que no se sap que ensenyar la plantilla equivocada.

/** Paraules que no distingeixen cap club: sigles, articles i preposicions. */
const BUIDES = new Set(['LA', 'EL', 'DE', 'DEL', 'DELS', 'LES', 'ELS']);

/** Fora accents i majúscules, que és com es compara tot això. */
function senseAccents(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
}

/**
 * Les paraules amb contingut d'un nom de club o d'equip.
 *
 * Cau la lletra de l'equip —«C.B. BANYOLES "A"» i «C.B. BANYOLES "B"» són el
 * mateix club—, les sigles (C.B., S.B., B.C.) i els números («C.B.2000
 * CERDANYOLA» és el mateix que «C.B. CERDANYOLA»).
 */
export function paraules(nom: string): string[] {
  return senseAccents(nom)
    .replace(/"[A-Z]"\s*$/, '')
    .split(/[^A-Z0-9]+/)
    .filter((p) => p.length >= 3 && !/^\d+$/.test(p) && !BUIDES.has(p));
}

/** Totes les paraules seguides: per als noms que el cens parteix i el calendari no. */
function junt(nom: string): string {
  return paraules(nom).join('');
}

/**
 * El club d'un equip, d'entre els noms del cens. `null` si no se sap del cert.
 *
 * Casa quan les paraules de l'equip són totes al nom del club —el cens en pot
 * dir més, «C.B.CANET DE MAR» per «C.B. CANET»— o quan, tot seguit, l'un és
 * l'inici de l'altre.
 */
export function clubDeLEquip(equip: string, clubs: Iterable<string>): string | null {
  const seves = paraules(equip);
  if (seves.length === 0) return null;
  const seuJunt = junt(equip);

  const candidats: string[] = [];
  for (const club of clubs) {
    const del = new Set(paraules(club));
    const totesHiSon = seves.every((p) => del.has(p));
    const delJunt = junt(club);
    if (totesHiSon || delJunt === seuJunt || delJunt.startsWith(seuJunt)) candidats.push(club);
  }

  if (candidats.length === 1) return candidats[0] ?? null;
  if (candidats.length === 0) return null;

  // Més d'un: mana el que casa exactament. Si tampoc no en desempata cap, no es
  // tria: ensenyar la plantilla d'un altre club seria pitjor que no ensenyar-ne.
  const exactes = candidats.filter((c) => junt(c) === seuJunt);
  return exactes.length === 1 ? (exactes[0] ?? null) : null;
}
