<script lang="ts">
	import Billar from './Billar.svelte';
	import { posicioAlFrame, type Fotograma } from './mapatge';
	import { RADI_BOLA_DIAMANTS } from './geometria';
	import type { Boles } from './tipus';

	// Colors distingibles per a cada camí (relacionats amb cada bola).
	const COLOR_BLANCA = '#eaf1f8';
	const COLOR_GROGA = '#ffcf3a';
	const COLOR_VERMELLA = '#ff6b5e';

	interface Props {
		/** Posició inicial (per als tirs pro sense animació). */
		bolesInicials: Boles;
		tracaBlanca?: Fotograma[];
		tracaGroga?: Fotograma[];
		tracaVermella?: Fotograma[];
		mostraNumeros?: boolean;
		/** Si es dona, el fotograma el controla l'exterior (p. ex. el vídeo). */
		frameExtern?: number | null;
		/** Hi ha un vídeo mestre: els controls comanden el vídeo, no el rellotge intern. */
		teVideo?: boolean;
		/** Estat de reproducció del vídeo mestre (per pintar el botó). */
		reproduintExtern?: boolean;
		onReprodueix?: () => void;
		onPausa?: () => void;
		onReinicia?: () => void;
		onVesA?: (frame: number) => void;
	}

	let {
		bolesInicials,
		tracaBlanca = [],
		tracaGroga = [],
		tracaVermella = [],
		mostraNumeros = false,
		frameExtern = null,
		teVideo = false,
		reproduintExtern = false,
		onReprodueix,
		onPausa,
		onReinicia,
		onVesA
	}: Props = $props();

	const maxFrame = $derived(
		Math.max(
			0,
			...tracaBlanca.map((f) => f.frame),
			...tracaGroga.map((f) => f.frame),
			...tracaVermella.map((f) => f.frame)
		)
	);

	// Només és una animació si hi ha una seqüència de fotogrames (no un sol punt).
	const teAnimacio = $derived(maxFrame > 0);

	let frame = $state(0);
	let reproduint = $state(true);
	let velocitat = $state(1);

	const FPS = 30;

	// Fotograma efectiu: el del vídeo si es controla des de fora, si no l'intern.
	const frameActiu = $derived(frameExtern ?? frame);

	function puntBola(traca: Fotograma[], fallback: [number, number]): [number, number] {
		const p = posicioAlFrame(traca, frameActiu);
		return p ? [p.x, p.y] : fallback;
	}

	/** Rastre recorregut per una bola des de l'inici fins al fotograma actual. */
	function rastre(traca: Fotograma[]): { x: number; y: number }[] {
		if (traca.length < 2) return [];
		const punts: { x: number; y: number }[] = [];
		for (const f of traca) {
			if (f.frame < frameActiu) punts.push({ x: f.x, y: f.y });
			else break;
		}
		const pos = posicioAlFrame(traca, frameActiu);
		if (pos) punts.push(pos);
		return punts;
	}

	/**
	 * Evita que dues boles se superposin: si estan més a prop que un diàmetre,
	 * les separa fins que només es toquin (sense moure-les gairebé mai fora
	 * del punt de contacte real).
	 */
	function separa(p: Boles): Boles {
		const b: [number, number][] = [[...p.b1], [...p.b2], [...p.b3]];
		const minDist = 2 * RADI_BOLA_DIAMANTS;
		for (let iter = 0; iter < 4; iter++) {
			for (let i = 0; i < 3; i++) {
				for (let j = i + 1; j < 3; j++) {
					let dx = b[j][0] - b[i][0];
					let dy = b[j][1] - b[i][1];
					let d = Math.hypot(dx, dy);
					if (d === 0) {
						dx = 0.001;
						dy = 0;
						d = 0.001;
					}
					if (d < minDist) {
						const empenta = (minDist - d) / 2;
						const ux = dx / d;
						const uy = dy / d;
						b[i][0] -= ux * empenta;
						b[i][1] -= uy * empenta;
						b[j][0] += ux * empenta;
						b[j][1] += uy * empenta;
					}
				}
			}
		}
		return { b1: b[0], b2: b[1], b3: b[2] };
	}

	const boles = $derived<Boles>(
		separa({
			b1: puntBola(tracaBlanca, bolesInicials.b1),
			b2: puntBola(tracaGroga, bolesInicials.b2),
			b3: puntBola(tracaVermella, bolesInicials.b3)
		})
	);

	// Rastre de cada bola: la línia creix seguint el moviment fins al fotograma
	// actual (un color distingible per bola).
	const traces = $derived(
		[
			{ color: COLOR_BLANCA, punts: rastre(tracaBlanca) },
			{ color: COLOR_GROGA, punts: rastre(tracaGroga) },
			{ color: COLOR_VERMELLA, punts: rastre(tracaVermella) }
		].filter((t) => t.punts.length > 1)
	);

	// Bucle d'animació amb requestAnimationFrame (només si NO el controla el vídeo).
	$effect(() => {
		if (frameExtern != null) return;
		if (teVideo) return; // amb vídeo mestre, el rellotge intern no corre mai
		if (!teAnimacio || !reproduint) return;
		let raf = 0;
		let anterior = performance.now();
		const passa = (ara: number) => {
			const dt = (ara - anterior) / 1000;
			anterior = ara;
			frame += dt * FPS * velocitat;
			if (frame >= maxFrame) frame = 0; // bucle
			raf = requestAnimationFrame(passa);
		};
		raf = requestAnimationFrame(passa);
		return () => cancelAnimationFrame(raf);
	});

	function alterna() {
		if (teVideo) {
			// El vídeo mana: engega'l o atura'l, i l'animació el seguirà.
			if (reproduintExtern) onPausa?.();
			else onReprodueix?.();
		} else {
			reproduint = !reproduint;
		}
	}
	function reinicia() {
		frame = 0;
		if (teVideo) onReinicia?.();
	}
	function scrub(v: number) {
		if (teVideo) {
			onVesA?.(v);
		} else {
			reproduint = false;
			frame = v;
		}
	}

	// Botó reflecteix l'estat del vídeo quan aquest mana; si no, el rellotge intern.
	const enMarxa = $derived(teVideo ? reproduintExtern : reproduint);
</script>

<div class="reproductor">
	<Billar {boles} {traces} mode="visor" {mostraNumeros} />

	{#if teAnimacio && (teVideo || frameExtern == null)}
		<div class="controls">
			<button class="rodo" onclick={alterna} aria-label={enMarxa ? 'Pausa' : 'Reprodueix'}>
				{enMarxa ? '❚❚' : '▶'}
			</button>
			<button class="rodo" onclick={reinicia} aria-label="Reinicia">↺</button>
			<input
				type="range"
				min="0"
				max={maxFrame}
				step="1"
				value={Math.round(frameActiu)}
				oninput={(e) => scrub(+e.currentTarget.value)}
			/>
			{#if !teVideo}
				<select bind:value={velocitat} aria-label="Velocitat">
					<option value={0.5}>0,5×</option>
					<option value={1}>1×</option>
					<option value={2}>2×</option>
				</select>
			{/if}
		</div>
		{#if teVideo}
			<p class="sync-nota">▶ reprodueix vídeo i animació alhora, sincronitzats</p>
		{/if}
	{/if}
</div>

<style>
	.reproductor {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}
	.controls {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.rodo {
		width: 2.2rem;
		height: 2.2rem;
		padding: 0;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.9rem;
	}
	input[type='range'] {
		flex: 1;
		accent-color: var(--accent);
		padding: 0;
		background: transparent;
		border: none;
	}
	select {
		padding: 0.3rem 0.4rem;
	}
	.sync-nota {
		margin: 0;
		font-size: 0.78rem;
		color: var(--text-suau);
	}
</style>
