<script lang="ts">
	/**
	 * Imatge combinada efecte + quantitat de bola, com l'original billiard-bible:
	 * la bola TIRADORA amb el rellotge d'efecte (당점) i el punt d'impacte, i la
	 * bola OBJECTIU superposada mostrant la quantitat de bola (두께). Només mostra
	 * (per a les opcions del test).
	 */
	interface Punt {
		x: number; // hora 0-12
		y: number; // radi 0-3
	}
	interface Props {
		punt?: Punt | null;
		gruix?: number; // -8..+8
	}
	let { punt = null, gruix = 0 }: Props = $props();

	const R = 23; // radi de bola
	const CX = 75;
	const CY = 46;
	const hores = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
	const numHores = [
		{ t: '12', x: CX, y: CY - (R - 7) },
		{ t: '3', x: CX + (R - 7), y: CY },
		{ t: '6', x: CX, y: CY + (R - 7) },
		{ t: '9', x: CX - (R - 7), y: CY }
	];

	function pos(p: Punt): { x: number; y: number } {
		const a = (p.x / 12) * 2 * Math.PI;
		const radi = (p.y / 3) * (R - 6);
		return { x: CX + radi * Math.sin(a), y: CY - radi * Math.cos(a) };
	}
	const pPunt = $derived(punt ? pos(punt) : null);

	const absG = $derived(Math.min(8, Math.abs(gruix)));
	const signe = $derived(gruix > 0 ? 1 : gruix < 0 ? -1 : 0);
	// Objectiu encavalca la tiradora: gruix 0 = plena (concèntrica), 8 = a la vora
	// (només es toquen). Mateix criteri que billiard-bible (gruix>0 → objectiu a
	// l'esquerra).
	const objCx = $derived(CX - signe * (absG / 8) * 2 * R);

	const FRACCIONS: Record<number, string> = {
		0: 'plena',
		1: '7/8',
		2: '3/4',
		3: '5/8',
		4: '1/2',
		5: '3/8',
		6: '1/4',
		7: '1/8',
		8: 'vora'
	};
	const costat = $derived(signe > 0 ? ' dreta' : signe < 0 ? ' esquerra' : '');
	const etiqueta = $derived((FRACCIONS[absG] ?? '') + (absG > 0 && absG < 8 ? costat : ''));
</script>

<svg viewBox="0 0 150 100" role="img" aria-label="Efecte i quantitat de bola">
	<!-- Bola objectiu (vermella) al darrere: l'encavalcament amb la tiradora
	     indica la quantitat de bola -->
	<circle cx={objCx} cy={CY} r={R} class="obj" />
	<!-- Bola tiradora (blanca) en primer pla, amb el rellotge d'efecte -->
	<circle cx={CX} cy={CY} r={R} class="cara" />
	<line x1={CX - R + 2} y1={CY} x2={CX + R - 2} y2={CY} class="creu" />
	<line x1={CX} y1={CY - R + 2} x2={CX} y2={CY + R - 2} class="creu" />
	{#each hores as h (h)}
		{@const a = (h / 12) * 2 * Math.PI}
		<line
			x1={CX + R * Math.sin(a)}
			y1={CY - R * Math.cos(a)}
			x2={CX + (R - 2.5) * Math.sin(a)}
			y2={CY - (R - 2.5) * Math.cos(a)}
			class="tick"
		/>
	{/each}
	{#each numHores as n (n.t)}
		<text x={n.x} y={n.y} class="hora">{n.t}</text>
	{/each}
	<circle cx={CX} cy={CY} r="1.2" class="centre" />
	{#if pPunt}
		<circle cx={pPunt.x} cy={pPunt.y} r="4.6" class="punt" />
	{/if}

	<text x={CX} y="94" class="etiqueta">{etiqueta}</text>
</svg>

<style>
	svg {
		width: 100%;
		height: auto;
		display: block;
	}
	.cara {
		fill: #f3efe6;
		stroke: #14110c;
		stroke-width: 1.4;
	}
	.creu {
		stroke: #c4bcac;
		stroke-width: 0.7;
		stroke-dasharray: 2 2;
	}
	.tick {
		stroke: #8a8172;
		stroke-width: 0.8;
	}
	.hora {
		fill: #6f675a;
		font-size: 6px;
		font-family: system-ui, sans-serif;
		text-anchor: middle;
		dominant-baseline: middle;
	}
	.centre {
		fill: #b9b0a0;
	}
	.punt {
		fill: #16233a;
		stroke: #fff;
		stroke-width: 1.2;
	}
	.obj {
		fill: #e10000;
		stroke: #14110c;
		stroke-width: 1.4;
	}
	.etiqueta {
		fill: var(--text-suau);
		font-size: 8px;
		font-weight: 600;
		font-family: system-ui, sans-serif;
		text-anchor: middle;
	}
</style>
