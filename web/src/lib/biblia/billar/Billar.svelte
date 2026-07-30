<script lang="ts">
	import {
		diamantAPixel,
		pixelADiamant,
		limitaADins,
		ajustaAGraella,
		MARGE,
		ESCALA,
		RADI_BOLA_DIAMANTS,
		DIAMANTS_X,
		DIAMANTS_Y,
		AMPLADA_JOC,
		ALCADA_JOC,
		AMPLADA_VIEWBOX,
		ALCADA_VIEWBOX
	} from './geometria';
	import type { Boles, PuntTraj, EstatTirada, TipusPunt } from './tipus';

	/** Un camí complet d'una bola (per als tirs analitzats), en diamants. */
	interface Traca {
		color: string;
		punts: { x: number; y: number }[];
	}

	interface Props {
		/** Les tres boles en coordenades de diamants. */
		boles: Boles;
		/** Punts de contacte de la trajectòria (el primer segment surt de b1). */
		trajectoria?: PuntTraj[];
		/** Camins complets de les boles (tirs analitzats). Es dibuixen sota les boles. */
		traces?: Traca[];
		/** 'visor' només mostra; 'editor' permet arrossegar i afegir punts. */
		mode?: 'visor' | 'editor';
		/** Mostra la numeració dels diamants al marc. */
		mostraNumeros?: boolean;
		/** S'emet amb l'estat complet cada cop que canvia alguna cosa. */
		oncanvi?: (estat: EstatTirada) => void;
	}

	let {
		boles = $bindable(),
		trajectoria = $bindable([]),
		traces = [],
		mode = 'visor',
		mostraNumeros = false,
		oncanvi
	}: Props = $props();

	let svgEl: SVGSVGElement;

	// Element que s'està arrossegant en mode editor.
	let arrossegant = $state<{ tipus: 'bola' | 'punt'; id: 'b1' | 'b2' | 'b3' | number } | null>(null);
	// Distingeix un arrossegament d'un clic per no afegir punts en deixar anar.
	let haMogut = $state(false);

	const RADI_BOLA = RADI_BOLA_DIAMANTS * ESCALA;

	// Línies centrals de cada rail, on es dibuixen els diamants.
	const cyBaix = MARGE + ALCADA_JOC + MARGE / 2;
	const cyAlt = MARGE / 2;
	const cxEsq = MARGE / 2;
	const cxDret = MARGE + AMPLADA_JOC + MARGE / 2;

	// Diamants: rails llargs 0..8 (racons inclosos); rails curts, interiors 1..3.
	const diamantsLlarg = Array.from({ length: DIAMANTS_X + 1 }, (_, i) => i);
	const diamantsCurt = Array.from({ length: DIAMANTS_Y - 1 }, (_, j) => j + 1);
	// Línies de graella interiors sobre el drap (com a la taula original).
	const graellaX = Array.from({ length: DIAMANTS_X - 1 }, (_, i) => i + 1);

	// Posicions en píxels, reactives a les props.
	// Les boles xoquen amb la goma: limitem el CENTRE perquè la vora de la bola
	// toqui la banda sense penetrar-la (un radi de marge a cada costat).
	function adins(v: number, max: number): number {
		return Math.max(RADI_BOLA_DIAMANTS, Math.min(max - RADI_BOLA_DIAMANTS, v));
	}
	const pixBoles = $derived({
		b1: diamantAPixel(adins(boles.b1[0], DIAMANTS_X), adins(boles.b1[1], DIAMANTS_Y)),
		b2: diamantAPixel(adins(boles.b2[0], DIAMANTS_X), adins(boles.b2[1], DIAMANTS_Y)),
		b3: diamantAPixel(adins(boles.b3[0], DIAMANTS_X), adins(boles.b3[1], DIAMANTS_Y))
	});
	const puntsPix = $derived(trajectoria.map((p) => diamantAPixel(p.x, p.y)));
	const tracesPix = $derived(
		traces.map((t) => ({
			color: t.color,
			d: t.punts
				.map((p) => {
					const q = diamantAPixel(p.x, p.y);
					return `${q.px},${q.py}`;
				})
				.join(' ')
		}))
	);
	const liniaPunts = $derived(
		[pixBoles.b1, ...puntsPix].map((p) => `${p.px},${p.py}`).join(' ')
	);

	const colorPunt: Record<TipusPunt, string> = {
		banda: '#dfe6ec',
		bola: '#ff9f1c',
		arribada: '#4dd2ff'
	};

	/** Passa coordenades de pantalla a coordenades internes de l'SVG. */
	function svgDesDeEvent(ev: PointerEvent | MouseEvent): { px: number; py: number } {
		const ctm = svgEl.getScreenCTM();
		if (!ctm) return { px: 0, py: 0 };
		const p = new DOMPoint(ev.clientX, ev.clientY).matrixTransform(ctm.inverse());
		return { px: p.x, py: p.y };
	}

	function emetCanvi() {
		oncanvi?.({
			boles: { b1: [...boles.b1], b2: [...boles.b2], b3: [...boles.b3] },
			trajectoria: trajectoria.map((p) => ({ ...p }))
		});
	}

	function iniciaArrossega(ev: PointerEvent, tipus: 'bola' | 'punt', id: 'b1' | 'b2' | 'b3' | number) {
		if (mode !== 'editor') return;
		ev.stopPropagation();
		ev.preventDefault();
		arrossegant = { tipus, id };
		haMogut = false;
		svgEl.setPointerCapture(ev.pointerId);
	}

	function mou(ev: PointerEvent) {
		if (!arrossegant) return;
		haMogut = true;
		const { px, py } = svgDesDeEvent(ev);
		let { x, y } = pixelADiamant(px, py);
		({ x, y } = limitaADins(x, y));
		if (ev.shiftKey) {
			x = ajustaAGraella(x);
			y = ajustaAGraella(y);
		}
		if (arrossegant.tipus === 'bola') {
			boles[arrossegant.id as 'b1' | 'b2' | 'b3'] = [x, y];
		} else {
			const i = arrossegant.id as number;
			trajectoria[i] = { ...trajectoria[i], x, y };
		}
		emetCanvi();
	}

	function atura(ev: PointerEvent) {
		if (!arrossegant) return;
		try {
			svgEl.releasePointerCapture(ev.pointerId);
		} catch {
			// el punter ja no estava capturat
		}
		arrossegant = null;
	}

	function clicSuperficie(ev: MouseEvent) {
		if (mode !== 'editor') return;
		const objectiu = ev.target as Element;
		if (objectiu.classList?.contains('arrossegable')) return; // clic sobre una nansa
		if (haMogut) {
			haMogut = false;
			return; // era el final d'un arrossegament
		}
		const { px, py } = svgDesDeEvent(ev);
		let { x, y } = pixelADiamant(px, py);
		if (x < 0 || x > DIAMANTS_X || y < 0 || y > DIAMANTS_Y) return;
		if (ev.shiftKey) {
			x = ajustaAGraella(x);
			y = ajustaAGraella(y);
		}
		trajectoria.push({ x, y, tipus: 'banda' });
		emetCanvi();
	}

	// Colors de bola idèntics als de la taula original.
	const boles3 = $derived([
		{ id: 'b1' as const, pos: pixBoles.b1, color: '#f5f5f5' },
		{ id: 'b2' as const, pos: pixBoles.b2, color: '#ffbb00' },
		{ id: 'b3' as const, pos: pixBoles.b3, color: '#e10000' }
	]);
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<svg
	bind:this={svgEl}
	class="billar"
	class:editor={mode === 'editor'}
	class:arrossegant={arrossegant !== null}
	viewBox="0 0 {AMPLADA_VIEWBOX} {ALCADA_VIEWBOX}"
	role="img"
	aria-label="Taula de billar a tres bandes"
	onpointermove={mou}
	onpointerup={atura}
	onpointercancel={atura}
	onclick={clicSuperficie}
>
	<defs>
		<linearGradient id="billar-marc" x1="0" y1="0" x2="0" y2="1">
			<stop offset="0" stop-color="#2c2c2e" />
			<stop offset="0.5" stop-color="#0e0e0f" />
			<stop offset="1" stop-color="#040405" />
		</linearGradient>
		<radialGradient id="billar-drap" cx="50%" cy="42%" r="72%">
			<stop offset="0" stop-color="#3f79a7" />
			<stop offset="0.7" stop-color="#336d9c" />
			<stop offset="1" stop-color="#265a86" />
		</radialGradient>
		<radialGradient id="billar-brill" cx="35%" cy="30%" r="70%">
			<stop offset="0" stop-color="#ffffff" stop-opacity="0.85" />
			<stop offset="0.4" stop-color="#ffffff" stop-opacity="0.12" />
			<stop offset="1" stop-color="#ffffff" stop-opacity="0" />
		</radialGradient>
		<marker
			id="billar-fletxa"
			viewBox="0 0 10 10"
			refX="8"
			refY="5"
			markerWidth="6"
			markerHeight="6"
			orient="auto-start-reverse"
		>
			<path d="M0,0 L10,5 L0,10 z" fill="#eef4fa" />
		</marker>
	</defs>

	<!-- Marc negre -->
	<rect x="0" y="0" width={AMPLADA_VIEWBOX} height={ALCADA_VIEWBOX} rx="10" fill="url(#billar-marc)" />

	<!-- Superfície (drap blau) -->
	<rect x={MARGE} y={MARGE} width={AMPLADA_JOC} height={ALCADA_JOC} rx="2" fill="url(#billar-drap)" />

	<!-- Graella de diamants sobre el drap -->
	<g class="graella">
		{#each graellaX as i (i)}
			<line x1={diamantAPixel(i, 0).px} y1={MARGE + ALCADA_JOC} x2={diamantAPixel(i, 0).px} y2={MARGE} />
		{/each}
		{#each diamantsCurt as j (j)}
			<line x1={MARGE} y1={diamantAPixel(0, j).py} x2={MARGE + AMPLADA_JOC} y2={diamantAPixel(0, j).py} />
		{/each}
	</g>

	<!-- Goma (banda): vora blau clar brillant on reboten les boles, com billiard-bible -->
	<rect
		class="goma"
		x={MARGE}
		y={MARGE}
		width={AMPLADA_JOC}
		height={ALCADA_JOC}
		rx="2"
	/>

	<!-- Diamants dels rails llargs (a dalt i a baix) -->
	{#each diamantsLlarg as i (i)}
		{@const cx = diamantAPixel(i, 0).px}
		<circle class="diamant" cx={cx} cy={cyBaix} r="2.4" />
		<circle class="diamant" cx={cx} cy={cyAlt} r="2.4" />
		{#if mostraNumeros}
			<text class="num" x={cx} y={cyBaix - 10}>{i}</text>
			<text class="num" x={cx} y={cyAlt + 13}>{i}</text>
		{/if}
	{/each}

	<!-- Diamants dels rails curts (esquerra i dreta), interiors -->
	{#each diamantsCurt as j (j)}
		{@const cy = diamantAPixel(0, j).py}
		<circle class="diamant" cx={cxEsq} cy={cy} r="2.4" />
		<circle class="diamant" cx={cxDret} cy={cy} r="2.4" />
		{#if mostraNumeros}
			<text class="num" x={cxEsq + 11} y={cy + 3}>{j}</text>
			<text class="num" x={cxDret - 11} y={cy + 3}>{j}</text>
		{/if}
	{/each}

	<!-- Camins de les boles (tirs analitzats) -->
	{#each tracesPix as t, i (i)}
		{#if t.d}
			<polyline class="traca-halo" points={t.d} />
			<polyline class="traca" points={t.d} style="stroke: {t.color}" />
		{/if}
	{/each}

	<!-- Trajectòria -->
	{#if trajectoria.length >= 1}
		<polyline class="traj-halo" points={liniaPunts} />
		<polyline class="traj-linia" points={liniaPunts} marker-end="url(#billar-fletxa)" />
	{/if}

	<!-- Punts de contacte, numerats -->
	{#each puntsPix as p, i (i)}
		<circle
			class="punt-contacte"
			class:arrossegable={mode === 'editor'}
			cx={p.px}
			cy={p.py}
			r={mode === 'editor' ? 7.5 : 6}
			fill={colorPunt[trajectoria[i].tipus]}
			onpointerdown={(ev) => iniciaArrossega(ev, 'punt', i)}
		/>
		<text class="num-punt" x={p.px} y={p.py + 3}>{i + 1}</text>
	{/each}

	<!-- Boles -->
	{#each boles3 as b (b.id)}
		<circle
			class="bola"
			class:arrossegable={mode === 'editor'}
			cx={b.pos.px}
			cy={b.pos.py}
			r={RADI_BOLA}
			fill={b.color}
			onpointerdown={(ev) => iniciaArrossega(ev, 'bola', b.id)}
		/>
		<!-- Brillantor gloss -->
		<circle
			class="bola-brill"
			cx={b.pos.px}
			cy={b.pos.py}
			r={RADI_BOLA}
			fill="url(#billar-brill)"
			pointer-events="none"
		/>
	{/each}
</svg>

<style>
	.billar {
		display: block;
		width: 100%;
		height: auto;
		user-select: none;
		touch-action: none;
	}

	.diamant {
		fill: #dfe4e9;
		opacity: 0.9;
	}

	.graella line {
		stroke: #ffffff;
		stroke-width: 0.7;
		stroke-dasharray: 2 4;
		opacity: 0.1;
	}

	.goma {
		fill: none;
		stroke: #a9d6f5;
		stroke-width: 2.2;
		opacity: 0.9;
	}

	.num {
		fill: #cdd6df;
		font-size: 11px;
		font-family: system-ui, sans-serif;
		text-anchor: middle;
		dominant-baseline: middle;
	}

	.traj-halo {
		fill: none;
		stroke: #08160d;
		stroke-width: 5;
		stroke-linejoin: round;
		stroke-linecap: round;
		opacity: 0.4;
	}

	.traca-halo {
		fill: none;
		stroke: #0c2033;
		stroke-width: 3;
		stroke-linejoin: round;
		stroke-linecap: round;
		opacity: 0.3;
	}

	.traca {
		fill: none;
		stroke-width: 1.5;
		stroke-linejoin: round;
		stroke-linecap: round;
	}

	.traj-linia {
		fill: none;
		stroke: #eef4fa;
		stroke-width: 2;
		stroke-linejoin: round;
		stroke-linecap: round;
	}

	.punt-contacte {
		stroke: #10202b;
		stroke-width: 1.4;
	}

	.num-punt {
		fill: #10202b;
		font-size: 8px;
		font-weight: 700;
		font-family: system-ui, sans-serif;
		text-anchor: middle;
		dominant-baseline: middle;
		pointer-events: none;
	}

	.bola {
		stroke: rgba(0, 0, 0, 0.55);
		stroke-width: 1;
	}

	/* En editor, les nanses conviden a arrossegar */
	.editor .arrossegable {
		cursor: grab;
	}
	.billar.arrossegant .arrossegable {
		cursor: grabbing;
	}
	.editor {
		cursor: crosshair;
	}
</style>
