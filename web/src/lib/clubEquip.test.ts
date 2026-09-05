// De quin club és un equip.
//
// Els noms venen de dos documents de la federació que no s'escriuen igual, i no
// hi ha cap identificador que els lligui. Aquestes són les parelles reals de la
// temporada 26/27: cadascuna trenca d'una manera diferent.

import { describe, expect, it } from 'vitest';

import { clubDeLEquip, paraules } from './clubEquip';

/** Els clubs tal com els escriu el cens de FCBillar. */
const CENS = [
  'B.LA UNIÓ CORAL',
  'C.B.2000 CERDANYOLA',
  'C.B. BORGES',
  'C.B.BANYOLES',
  'C.B.BLANES',
  'C.B.CANET DE MAR',
  'C.B.LLEIDA',
  'C.B.LLINARS',
  "C.B.LLIÇÀ D'AMUNT",
  'C.B.MANRESA',
  'C.B.MATADEPERA',
  'C.B.MATARÓ',
  'C.B.MOLLET',
  'C.B.MONFORTE',
  'C.B.MONT-ROIG',
  'C.B.SANT ADRIÀ',
  'C.B.SANT BOI',
  'C.B.SANT FELIU',
  'C.B.SANTS',
  'S.B.CORAL COLÓN',
  'S.B.F.MOLINS',
  'S.B.LA GRAN PENYA'
];

describe('paraules', () => {
  it('deixa fora la lletra de l’equip: és el mateix club', () => {
    expect(paraules('C.B. BANYOLES "A"')).toEqual(['BANYOLES']);
    expect(paraules('C.B. BANYOLES "D"')).toEqual(['BANYOLES']);
  });

  it('deixa fora sigles, números i articles', () => {
    expect(paraules('C.B.2000 CERDANYOLA')).toEqual(['CERDANYOLA']);
    expect(paraules('S.B.LA GRAN PENYA')).toEqual(['GRAN', 'PENYA']);
  });
});

describe('clubDeLEquip', () => {
  it.each([
    ['C.B. MANRESA "A"', 'C.B.MANRESA'],
    ['C.B. MATARO "B"', 'C.B.MATARÓ'], // el calendari no accentua
    ['C.B. CANET "A"', 'C.B.CANET DE MAR'], // el cens en diu més
    ['C.B. LLIÇA "A"', "C.B.LLIÇÀ D'AMUNT"],
    ['C.B. MONTROIG "C"', 'C.B.MONT-ROIG'], // el cens ho parteix amb guionet
    ['S.B. GRAN PENYA "A"', 'S.B.LA GRAN PENYA'], // i aquí hi posa un article
    ['C.B. CERDANYOLA "B"', 'C.B.2000 CERDANYOLA'], // i aquí un any
    ['UNIO CORAL "C"', 'B.LA UNIÓ CORAL'], // sense sigles al calendari
    ['S.B. CORAL COLON "A"', 'S.B.CORAL COLÓN'],
    ['S.B.F. MOLINS "B"', 'S.B.F.MOLINS'],
    ['C.B. SANT ADRIA "C"', 'C.B.SANT ADRIÀ'],
    ['C.B. SANT FELIU "B"', 'C.B.SANT FELIU'],
    ['C.B. BORGES', 'C.B. BORGES'], // hi ha equips sense lletra
    ['C.B. MATADEPERA', 'C.B.MATADEPERA']
  ])('%s és de %s', (equip, club) => {
    expect(clubDeLEquip(equip, CENS)).toBe(club);
  });

  it('«SANTS» no és cap dels «SANT ...»', () => {
    expect(clubDeLEquip('C.B. SANTS "A"', CENS)).toBe('C.B.SANTS');
  });

  it('un equip d’un club que no tenim no s’assigna a cap', () => {
    expect(clubDeLEquip('C.B. INVENTAT "A"', CENS)).toBeNull();
  });

  it('davant del dubte no se’n tria cap', () => {
    // Dos clubs amb el mateix nom significatiu: no hi ha manera de saber quin és.
    expect(clubDeLEquip('C.B. BESSONS "A"', ['C.B.BESSONS', 'S.B.BESSONS'])).toBeNull();
  });

  it('un nom buit no casa amb res', () => {
    expect(clubDeLEquip('', CENS)).toBeNull();
  });
});

// Els 31 equips del calendari 26/27 contra els 39 clubs del cens, tal com
// s'escriuen tots dos. És l'única manera de saber que no se n'escapa cap: cada
// parella trenca per un motiu diferent i no hi ha cap regla que els cobreixi tots
// per construcció.
const CENS_SENCER = [
  'B.C.GRANOLLERS',
  'B.LA UNIÓ CORAL',
  'BC OLESA',
  'BILLAR EL MASNOU',
  'C.B. BORGES',
  'C.B.2000 CERDANYOLA',
  'C.B.ALBA',
  'C.B.BANYOLES',
  'C.B.BARCELONA',
  'C.B.BLANES',
  'C.B.CANET DE MAR',
  'C.B.CARDONA',
  'C.B.LLEIDA',
  'C.B.LLINARS',
  "C.B.LLIÇÀ D'AMUNT",
  'C.B.MANRESA',
  'C.B.MATADEPERA',
  'C.B.MATARÓ',
  'C.B.MOLLET',
  'C.B.MONFORTE',
  'C.B.MONT-ROIG',
  'C.B.PRAT',
  'C.B.PREMIÀ',
  "C.B.PUNT D'ATAC",
  'C.B.SANT ADRIÀ',
  'C.B.SANT BOI',
  'C.B.SANT FELIU',
  'C.B.SANTS',
  'C.B.TARRAGONA',
  'C.B.VIC',
  'C.B.VILANOVA',
  'INDEPENDENT',
  'S.B. GEiEG',
  'S.B.CORAL COLÓN',
  "S.B.ESPLUGUES L'AVENÇ",
  'S.B.F.MOLINS',
  'S.B.LA GRAN PENYA',
  'S.B.P.E.CENTELLES',
  'S.E.CASAL CERVERA'
];

const EQUIPS_2627 = [
  'C.B. BANYOLES "A"',
  'C.B. BANYOLES "B"',
  'C.B. BANYOLES "C"',
  'C.B. BANYOLES "D"',
  'C.B. BLANES "A"',
  'C.B. BLANES "B"',
  'C.B. BORGES',
  'C.B. CANET "A"',
  'C.B. CERDANYOLA "B"',
  'C.B. CERDANYOLA "C"',
  'C.B. LLEIDA "B"',
  'C.B. LLEIDA "C"',
  'C.B. LLINARS "D"',
  'C.B. LLIÇA "A"',
  'C.B. MANRESA "A"',
  'C.B. MATADEPERA',
  'C.B. MATARO "B"',
  'C.B. MATARO "D"',
  'C.B. MOLLET "B"',
  'C.B. MONFORTE "E"',
  'C.B. MONTROIG "C"',
  'C.B. MONTROIG "D"',
  'C.B. SANT ADRIA "C"',
  'C.B. SANT FELIU "B"',
  'C.B. SANTS "A"',
  'C.B. SANTS "C"',
  'S.B. CORAL COLON "A"',
  'S.B. GRAN PENYA "A"',
  'S.B. GRAN PENYA "C"',
  'S.B.F. MOLINS "B"',
  'UNIO CORAL "C"'
];

describe('tots els equips del calendari 26/27', () => {
  it.each(EQUIPS_2627)('%s troba el seu club', (equip) => {
    expect(clubDeLEquip(equip, CENS_SENCER)).not.toBeNull();
  });

  it('les lletres d’un mateix club van al mateix lloc', () => {
    const banyoles = EQUIPS_2627.filter((e) => e.includes('BANYOLES')).map((e) =>
      clubDeLEquip(e, CENS_SENCER)
    );
    expect(new Set(banyoles)).toEqual(new Set(['C.B.BANYOLES']));
  });
});
