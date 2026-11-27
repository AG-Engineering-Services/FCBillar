import { describe, expect, it } from 'vitest';
import { arreglaCodificacio } from './codificacio';

describe('arreglaCodificacio', () => {
	it('desfà el doble codificat', () => {
		expect(arreglaCodificacio('LEÃ“N PUIG, ESTEBAN')).toBe('LEÓN PUIG, ESTEBAN');
		expect(arreglaCodificacio('GARCÃ\udc8dA ALARCÃ“N, RICARDO')).toBe('GARCÍA ALARCÓN, RICARDO');
	});
	it('deixa els noms bons com són', () => {
		expect(arreglaCodificacio('GÓMEZ AMETLLER, ALBERT')).toBe('GÓMEZ AMETLLER, ALBERT');
		expect(arreglaCodificacio('PUIG LATRE, ISAAC')).toBe('PUIG LATRE, ISAAC');
		expect(arreglaCodificacio('NADAL FONT, JOSEP Mª')).toBe('NADAL FONT, JOSEP Mª');
	});
});
