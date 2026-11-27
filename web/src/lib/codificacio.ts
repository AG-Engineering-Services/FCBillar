// Molts noms de `players` són UTF-8 llegit com a cp1252: «LEÃ“N» per «LEÓN».
// Això els desfà: torna a fer els bytes amb cp1252 i els llegeix com a UTF-8.
// Un nom que ja és bo no forma UTF-8 vàlid en fer-ho i es torna tal qual.
// És la mateixa reparació que `arregla_codificacio` de src/fcbillar/avisos.py.

// Els caràcters de cp1252 entre 0x80 i 0x9F, que no coincideixen amb Latin-1.
const CP1252: Record<string, number> = {
	'€': 0x80, '‚': 0x82, 'ƒ': 0x83, '„': 0x84, '…': 0x85, '†': 0x86, '‡': 0x87,
	'ˆ': 0x88, '‰': 0x89, 'Š': 0x8a, '‹': 0x8b, 'Œ': 0x8c, 'Ž': 0x8e, '‘': 0x91,
	'’': 0x92, '“': 0x93, '”': 0x94, '•': 0x95, '–': 0x96, '—': 0x97, '˜': 0x98,
	'™': 0x99, 'š': 0x9a, '›': 0x9b, 'œ': 0x9c, 'ž': 0x9e, 'Ÿ': 0x9f
};

const decoder = new TextDecoder('utf-8', { fatal: true });

export function arreglaCodificacio(s: string): string {
	if (!s || !/[\u0080-￿]/.test(s)) return s;
	const bytes: number[] = [];
	for (const c of s) {
		const code = c.codePointAt(0)!;
		if (code < 0x100) bytes.push(code);
		else if (c in CP1252) bytes.push(CP1252[c]);
		// Bytes que cp1252 no defineix (0x81, 0x8D…): arriben com a substituts aïllats.
		else if (code >= 0xdc80 && code <= 0xdcff) bytes.push(code - 0xdc00);
		else return s;
	}
	try {
		return decoder.decode(new Uint8Array(bytes));
	} catch {
		return s;
	}
}
