<script lang="ts">
	import Billar from './Billar.svelte';
	import { onDestroy } from 'svelte';
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
		/** Fotogrames per segon del rellotge intern (derivat del clip: maxFrame/durada). */
		fps?: number;
		/** Hi ha un vídeo que s'ha de reproduir alhora amb la mateixa botonera. */
		teVideo?: boolean;
		/** Estat de reproducció del vídeo (per engegar l'animació quan arrenca el vídeo). */
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
		fps = 30,
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
	// Amb vídeo, no s'auto-reprodueix: espera que premis play (que engega tots dos).
	// svelte-ignore state_referenced_locally
	let reproduint = $state(!teVideo);
	let velocitat = $state(1);

	const frameActiu = $derived(frame);

	// Retard de sincronització: en prémer play s'engega el vídeo i l'animació
	// s'endarrereix uns segons perquè el vídeo mostri la preparació (apuntada)
	// abans del cop; així el moviment de les boles no va avançat respecte al vídeo.
	const RETARD_SYNC_MS = 3000;
	let esperantVideo = $state(false);
	let timerArrenca: ReturnType<typeof setTimeout> | null = null;
	function neteja() {
		if (timerArrenca) {
			clearTimeout(timerArrenca);
			timerArrenca = null;
		}
	}
	function programaArrenca() {
		neteja();
		esperantVideo = true;
		timerArrenca = setTimeout(() => {
			esperantVideo = false;
			reproduint = true;
		}, RETARD_SYNC_MS);
	}
	onDestroy(neteja);

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

	// Bucle d'animació amb requestAnimationFrame (rellotge intern, al fps del clip).
	$effect(() => {
		if (!teAnimacio || !reproduint) return;
		let raf = 0;
		let anterior = performance.now();
		const passa = (ara: number) => {
			const dt = (ara - anterior) / 1000;
			anterior = ara;
			frame += dt * fps * velocitat;
			if (frame >= maxFrame) {
				if (teVideo) {
					frame = maxFrame;
					reproduint = false; // amb vídeo, s'atura al final (no fa bucle)
					return;
				}
				frame = 0; // sense vídeo, bucle
			}
			raf = requestAnimationFrame(passa);
		};
		raf = requestAnimationFrame(passa);
		return () => cancelAnimationFrame(raf);
	});

	function alterna() {
		if (!teVideo) {
			reproduint = !reproduint;
			return;
		}
		if (reproduint || esperantVideo) {
			reproduint = false;
			esperantVideo = false;
			neteja();
			onPausa?.();
		} else {
			// Engega el vídeo ja, i l'animació amb el retard de sincronització.
			onReprodueix?.();
			programaArrenca();
		}
	}
	function reinicia() {
		frame = 0;
		if (teVideo) {
			reproduint = false;
			onReinicia?.();
			programaArrenca();
		} else {
			reproduint = true;
		}
	}
	function scrub(v: number) {
		reproduint = false;
		esperantVideo = false;
		neteja();
		frame = v;
		if (teVideo) {
			onPausa?.();
			onVesA?.(v);
		}
	}

	const enMarxa = $derived(reproduint || esperantVideo);
</script>

<div class="reproductor">
	<Billar {boles} {traces} mode="visor" {mostraNumeros} />

	{#if teAnimacio}
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
