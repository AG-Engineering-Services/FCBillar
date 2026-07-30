<script lang="ts">
	/**
	 * Cara de la bola per triar/mostrar l'efecte (당점): rellotge amb el punt
	 * d'impacte. Pot ser interactiva (clicar per posar el punt) i mostrar el
	 * punt correcte (revelació del quiz). Mateixa convenció que billiard-bible.
	 */
	interface Punt {
		x: number; // hora 0-12
		y: number; // radi 0-3
	}
	interface Props {
		/** Punt triat/mostrat (fosc). */
		punt?: Punt | null;
		/** Punt correcte (verd), per a la revelació. */
		correcte?: Punt | null;
		interactiu?: boolean;
		onpica?: (p: Punt) => void;
	}
	let { punt = null, correcte = null, interactiu = false, onpica }: Props = $props();

	const R = 34;
	const hores = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
	const numHores = [
		{ t: '12', x: 45, y: 45 - (R - 9) },
		{ t: '3', x: 45 + (R - 9), y: 45 },
		{ t: '6', x: 45, y: 45 + (R - 9) },
		{ t: '9', x: 45 - (R - 9), y: 45 }
	];

	function pos(p: Punt): { x: number; y: number } {
		const a = (p.x / 12) * 2 * Math.PI;
		const radi = (p.y / 3) * (R - 8);
		return { x: 45 + radi * Math.sin(a), y: 45 - radi * Math.cos(a) };
	}

	let svgEl: SVGSVGElement;
	function pica(ev: MouseEvent) {
		if (!interactiu || !onpica) return;
		const ctm = svgEl.getScreenCTM();
		if (!ctm) return;
		const p = new DOMPoint(ev.clientX, ev.clientY).matrixTransform(ctm.inverse());
		const dx = p.x - 45;
		const dy = p.y - 45;
		let radi = Math.hypot(dx, dy);
		const maxR = R - 8;
		if (radi > maxR) radi = maxR;
		const a = Math.atan2(dx, -dy); // 0 = a dalt, horari
		let x = ((a / (2 * Math.PI)) * 12 + 12) % 12;
		const y = (radi / maxR) * 3;
		onpica({ x, y });
	}

	const pPunt = $derived(punt ? pos(punt) : null);
	const pCorr = $derived(correcte ? pos(correcte) : null);
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<svg
	bind:this={svgEl}
	viewBox="0 0 90 90"
	class:interactiu
	role={interactiu ? 'button' : 'img'}
	tabindex={interactiu ? 0 : undefined}
	aria-label={interactiu ? "Tria l'efecte" : 'Efecte'}
	onclick={pica}
	onkeydown={(e) => {
		if (interactiu && (e.key === 'Enter' || e.key === ' ')) e.preventDefault();
	}}
>
	<circle cx="45" cy="45" r={R} class="cara" />
	<line x1={45 - R + 3} y1="45" x2={45 + R - 3} y2="45" class="creu" />
	<line x1="45" y1={45 - R + 3} x2="45" y2={45 + R - 3} class="creu" />
	{#each hores as h (h)}
		{@const a = (h / 12) * 2 * Math.PI}
		<line
			x1={45 + R * Math.sin(a)}
			y1={45 - R * Math.cos(a)}
			x2={45 + (R - 3) * Math.sin(a)}
			y2={45 - (R - 3) * Math.cos(a)}
			class="tick"
		/>
	{/each}
	{#each numHores as n (n.t)}
		<text x={n.x} y={n.y} class="hora">{n.t}</text>
	{/each}
	<circle cx="45" cy="45" r="1.4" class="centre" />
	{#if pCorr}
		<circle cx={pCorr.x} cy={pCorr.y} r="5.5" class="correcte" />
	{/if}
	{#if pPunt}
		<circle cx={pPunt.x} cy={pPunt.y} r="5.5" class="punt" />
	{/if}
</svg>

<style>
	svg {
		width: 100%;
		height: auto;
		display: block;
	}
	svg.interactiu {
		cursor: crosshair;
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
	.correcte {
		fill: none;
		stroke: #2fbf5b;
		stroke-width: 2.4;
	}
</style>
