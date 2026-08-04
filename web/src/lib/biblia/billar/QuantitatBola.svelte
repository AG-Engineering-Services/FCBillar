<script lang="ts">
	/**
	 * Diagrama de quantitat de bola (두께) per a un valor donat: encavalcament
	 * de la bola jugadora sobre l'objectiu. Mateixa convenció que billiard-bible
	 * (gruix > 0 → objectiu a l'esquerra, jugadora a la dreta).
	 */
	interface Props {
		gruix: number; // -8..+8
		titol?: string;
	}
	let { gruix, titol }: Props = $props();

	const R = 24;
	const FRACCIONS: Record<number, string> = {
		0: '1/1', 1: '7/8', 2: '3/4', 3: '5/8', 4: '1/2', 5: '3/8', 6: '1/4', 7: '1/8', 8: 'vora'
	};

	const absG = $derived(Math.min(8, Math.abs(gruix)));
	const signe = $derived(gruix > 0 ? 1 : gruix < 0 ? -1 : 0);
	const cueCx = $derived(75 + signe * (absG / 8) * 2 * R);
	const fraccio = $derived(FRACCIONS[absG] ?? `${absG}/8`);
	const costat = $derived(gruix < 0 ? "per l'esquerra" : gruix > 0 ? 'per la dreta' : '');
	const descripcio = $derived(absG === 0 ? 'bola plena' : absG === 8 ? 'molt fina' : `${fraccio} de bola`);
</script>

<div class="q">
	<svg viewBox="0 0 150 90" role="img" aria-label="Quantitat de bola">
		<circle cx="75" cy="45" r={R} class="obj" />
		<circle cx={cueCx} cy="45" r={R} class="jug" />
	</svg>
	{#if titol}<div class="titol">{titol}</div>{/if}
	<div class="valor">{descripcio}{signe !== 0 && costat ? ` ${costat}` : ''}</div>
</div>

<style>
	.q {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.2rem;
	}
	svg {
		width: 100%;
		max-width: 140px;
		height: auto;
	}
	.titol {
		font-size: 0.72rem;
		color: var(--text-suau);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.valor {
		font-size: 0.82rem;
		font-weight: 600;
		text-align: center;
	}
	.obj {
		fill: #e10000;
		stroke: #14110c;
		stroke-width: 1.4;
	}
	.jug {
		fill: #f5f5f5;
		fill-opacity: 0.82;
		stroke: #14110c;
		stroke-width: 1.4;
	}
</style>
