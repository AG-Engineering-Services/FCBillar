// Quins quatre jugadors d'un club és més probable que formin UN equip concret.
//
// L'ordre del club el fixa la federació a la llista d'inscrits i és fix tota la
// temporada. Aquell ordre diu a quins equips pot jugar cadascú:
//
//   del 1r al 3r    només a l'A
//   del 4t al 8è    a l'A i al B
//   del 9è al 12è   fins al C
//   del 13è al 16è  fins al D
//   del 17è endavant fins a l'E
//
// Repartint de dalt a baix, l'A s'endú el 1r, 2n i 3r —que no poden jugar
// enlloc més— i el millor que li queda, el 4t; al B li toquen del 5è al 8è. Que
// acabin sent blocs de quatre és la conseqüència, no la regla: els trams no són
// tots iguals (1-3 en són tres i 4-8 en són cinc) i amb un club curt de gent el
// repartiment ja no coincideix.
//
// No és cap alineació oficial: la federació no en publica cap.
//
// NOTA: NouProjecte té la seva versió d'això, amb un règim més que aquí no es
// pot fer —quan un equip ja porta unes quantes jornades, manen els que hi
// juguen de debò. Allà se sap de quin equip és cada partida; aquí el rànquing
// individual és per club i per grup, i no distingeix l'A del B.

/** Quants jugadors formen un equip a la lliga de tres bandes. */
export const PER_EQUIP = 4;

/** A partir de quina posició del club es pot jugar a cada equip. */
export const PRIMERA_POSICIO: Readonly<Record<string, number>> = {
	A: 1,
	B: 4,
	C: 9,
	D: 13,
	E: 17
};

/**
 * La lletra d'un equip: de «C.B. MATARO "B"», la B.
 *
 * Un club amb un sol equip no en porta —«C.B. BORGES»— i llavors és l'A: és
 * l'únic que té i s'enduu els primers.
 */
export function lletraEquip(nom: string): string {
	return /"([A-Z])"\s*$/.exec((nom ?? '').toUpperCase())?.[1] ?? 'A';
}

/** Si qui ocupa aquesta posició del club pot jugar en aquest equip. */
export function potJugarA(posicio: number, lletra: string): boolean {
	const minim = PRIMERA_POSICIO[lletra];
	// Una lletra que no coneixem no restringeix: val més marcar de més que amagar.
	return minim === undefined || posicio >= minim;
}

/**
 * Els quatre que li toquen a un equip repartint de dalt a baix.
 *
 * `posicions` són les que publica la federació. Es prenen tal com vénen i no es
 * renumeren: si la llista en salta alguna, el que val és el número escrit.
 */
export function repartiment(lletra: string, posicions: readonly number[]): number[] {
	const lletres = Object.keys(PRIMERA_POSICIO);
	const fins = lletres.indexOf(lletra);
	if (fins < 0) return [];

	const lliures = new Set(posicions);
	let seves: number[] = [];
	for (const l of lletres.slice(0, fins + 1)) {
		seves = [...lliures]
			.sort((a, b) => a - b)
			.filter((p) => potJugarA(p, l))
			.slice(0, PER_EQUIP);
		for (const p of seves) lliures.delete(p);
	}
	return seves;
}

/** Un inscrit, amb el número que li dona la federació. */
export interface Inscrit {
	jugador: string;
	posicio: number;
}

/** Els noms dels quatre que s'esperen en aquest equip. */
export function titulars(equip: string, plantilla: readonly Inscrit[]): Set<string> {
	const tocades = new Set(repartiment(lletraEquip(equip), plantilla.map((j) => j.posicio)));
	return new Set(plantilla.filter((j) => tocades.has(j.posicio)).map((j) => j.jugador));
}
