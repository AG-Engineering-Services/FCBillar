/** Una partida d'una prova UMB o CEB d'un jugador amb fitxa (vista umb_partides_fitxa). */
export interface UmbPartidaRow {
	fcb_id: string;
	esdeveniment_id: number;
	esdeveniment: string;
	disciplina: string | null;
	lloc: string | null;
	data_inici: string | null;
	fase: string;
	grup: string;
	ordre: number;
	caramboles: number | null;
	entrades: number | null;
	punts: number | null;
	serie: number | null;
	rival: string;
	rival_caramboles: number | null;
	rival_punts: number | null;
	rival_fcb_id: string | null;
}

/** La posició final en una prova (vista umb_classificacions_fitxa). */
export interface UmbClassificacioRow {
	fcb_id: string;
	esdeveniment_id: number;
	esdeveniment: string;
	lloc: string | null;
	data_inici: string | null;
	posicio: number;
	ronda: string | null;
	mitjana: number | null;
	participants: number;
}

export interface UmbProva {
	id: number;
	nom: string;
	lloc: string | null;
	data: string | null;
	any: string | null;
	classificacio: UmbClassificacioRow | null;
	partides: UmbPartidaRow[];
	pj: number;
	g: number;
	e: number;
	p: number;
	mitjana: number | null;
}

/** Guanya qui té més punts de partida; si la font no en dona, qui fa més caramboles. */
export function resultatUmb(r: Pick<UmbPartidaRow, 'punts' | 'rival_punts' | 'caramboles' | 'rival_caramboles'>): 'G' | 'E' | 'P' {
	const [a, b] =
		r.punts != null && r.rival_punts != null ? [r.punts, r.rival_punts] : [r.caramboles ?? 0, r.rival_caramboles ?? 0];
	return a > b ? 'G' : a < b ? 'P' : 'E';
}

/** Una entrada per prova, de la més nova a la més antiga, amb les partides en l'ordre del PDF. */
export function agrupaUmb(partides: UmbPartidaRow[], classificacions: UmbClassificacioRow[]): UmbProva[] {
	const proves = new Map<number, UmbProva>();
	const nova = (id: number, nom: string, lloc: string | null, data: string | null): UmbProva => ({
		id, nom, lloc, data, any: data ? data.slice(0, 4) : null, classificacio: null, partides: [], pj: 0, g: 0, e: 0, p: 0, mitjana: null
	});
	for (const r of partides) {
		if (!proves.has(r.esdeveniment_id)) proves.set(r.esdeveniment_id, nova(r.esdeveniment_id, r.esdeveniment, r.lloc, r.data_inici));
		proves.get(r.esdeveniment_id)!.partides.push(r);
	}
	for (const c of classificacions) {
		if (!proves.has(c.esdeveniment_id)) proves.set(c.esdeveniment_id, nova(c.esdeveniment_id, c.esdeveniment, c.lloc, c.data_inici));
		proves.get(c.esdeveniment_id)!.classificacio = c;
	}
	for (const pr of proves.values()) {
		pr.partides.sort((a, b) => a.ordre - b.ordre);
		let car = 0, ent = 0;
		for (const r of pr.partides) {
			pr.pj++;
			pr[{ G: 'g', E: 'e', P: 'p' }[resultatUmb(r)] as 'g' | 'e' | 'p']++;
			if (r.caramboles != null && r.entrades) { car += r.caramboles; ent += r.entrades; }
		}
		pr.mitjana = ent ? car / ent : null;
	}
	return [...proves.values()].sort((a, b) => (b.data ?? '').localeCompare(a.data ?? '') || b.id - a.id);
}
