<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import Billar from '$lib/biblia/billar/Billar.svelte';
	import Reproductor from '$lib/biblia/billar/Reproductor.svelte';
	import VideoSincronitzat from '$lib/biblia/billar/VideoSincronitzat.svelte';
	import CaraBola from '$lib/biblia/billar/CaraBola.svelte';
	import QuantitatBola from '$lib/biblia/billar/QuantitatBola.svelte';
	import EfecteQuantitat from '$lib/biblia/billar/EfecteQuantitat.svelte';
	import { familiaCat } from '$lib/biblia/api/vocabulari';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	// Vídeo company a la revelació: la mateixa botonera reprodueix animació i vídeo
	// alhora, al ritme del clip.
	let vid = $state<{
		reprodueix: () => void;
		pausa: () => void;
		reinicia: () => void;
		vesA: (f: number) => void;
	} | null>(null);
	let reproduintVideo = $state(false);

	const MODES = [
		{ id: 'multiple', nom: '4 opcions' },
		{ id: 'efecte', nom: "Endevina l'efecte" },
		{ id: 'ambdos', nom: 'Efecte + quantitat' }
	];

	let index = $state(0);
	let encerts = $state(0);
	let total = $state(0);
	let revelat = $state(false);
	let efecteGuess = $state<{ x: number; y: number } | null>(null);
	let gruixGuess = $state(4);
	let seleccio = $state<number | null>(null);

	const shot = $derived(data.tirades.length ? data.tirades[index % data.tirades.length] : null);
	const correctEfecte = $derived.by(() => {
		const p = (shot?.puntContacte ?? '').split('|').map(Number);
		return { x: Number.isFinite(p[0]) ? p[0] : 0, y: Number.isFinite(p[1]) ? p[1] : 0 };
	});
	const correctGruix = $derived(shot?.gruix ?? 0);
	const maxFrame = $derived(
		shot
			? Math.max(
					0,
					...shot.tracaBlanca.map((f) => f.frame),
					...shot.tracaGroga.map((f) => f.frame),
					...shot.tracaVermella.map((f) => f.frame)
				)
			: 0
	);

	// Vídeo mestre: en revelar i havent-hi vídeo, l'animació segueix el temps real
	// del vídeo (frameExtern); si no, es queda al fotograma 0.
	let frameExtern = $state<number | null>(null);
	$effect(() => {
		frameExtern = revelat && shot?.video ? 0 : null;
	});

	// Camí de la bola TIRADORA, que sempre és la BLANCA (수구 = bola 1). Cal
	// ensenyar-lo a l'enunciat: si no, no se sap quin dels tirs possibles es demana
	// i les opcions d'efecte/quantitat serien ambigües.
	const tracesTiradora = $derived.by(() => {
		if (!shot || shot.tracaBlanca.length < 2)
			return [] as { color: string; punts: { x: number; y: number }[] }[];
		return [{ color: '#eaf1f8', punts: shot.tracaBlanca.map((f) => ({ x: f.x, y: f.y })) }];
	});

	function rng(seed: number) {
		let s = seed >>> 0;
		return () => {
			s = (s + 0x6d2b79f5) >>> 0;
			let t = Math.imul(s ^ (s >>> 15), 1 | s);
			t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
			return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
		};
	}

	const opcions = $derived.by(() => {
		if (!shot) return { llista: [] as { efecte: { x: number; y: number }; gruix: number }[], correctIdx: 0 };
		const r = rng(shot.id);
		const correct = { efecte: { ...correctEfecte }, gruix: correctGruix };
		const llista = [correct];
		let intents = 0;
		while (llista.length < 4 && intents < 60) {
			intents++;
			const x = Math.round(r() * 12) % 12;
			const y = 1 + Math.round(r() * 2);
			let g = Math.round(r() * 16) - 8;
			if (g === 0) g = 4;
			if (Math.abs(g - correctGruix) < 2 && Math.abs(x - correctEfecte.x) < 2) continue;
			llista.push({ efecte: { x, y }, gruix: g });
		}
		for (let i = llista.length - 1; i > 0; i--) {
			const j = Math.floor(r() * (i + 1));
			[llista[i], llista[j]] = [llista[j], llista[i]];
		}
		return { llista, correctIdx: llista.indexOf(correct) };
	});

	function pos(p: { x: number; y: number }) {
		const a = (p.x / 12) * 2 * Math.PI;
		const radi = (p.y / 3) * 26;
		return { x: 45 + radi * Math.sin(a), y: 45 - radi * Math.cos(a) };
	}
	const efecteOk = $derived.by(() => {
		if (!efecteGuess) return false;
		const a = pos(efecteGuess);
		const b = pos(correctEfecte);
		return Math.hypot(a.x - b.x, a.y - b.y) < 11;
	});
	const gruixOk = $derived(
		Math.abs(gruixGuess - correctGruix) <= 2 &&
			(Math.sign(gruixGuess) === Math.sign(correctGruix) || correctGruix === 0)
	);

	function prepara() {
		revelat = false;
		efecteGuess = null;
		gruixGuess = 4;
		seleccio = null;
		reproduintVideo = false;
	}
	async function seguent() {
		index++;
		prepara();
		// En acabar el lot, en carrega de fresques (posicions noves a l'atzar).
		if (index >= data.tirades.length) {
			index = 0;
			await invalidateAll();
		}
	}
	function anterior() {
		if (index > 0) {
			index--;
			prepara();
		}
	}
	function comprovaMultiple(i: number) {
		if (revelat) return;
		seleccio = i;
		revelat = true;
		total++;
		if (i === opcions.correctIdx) encerts++;
	}
	function comprova() {
		if (revelat) return;
		revelat = true;
		total++;
		const encertat = data.mode === 'efecte' ? efecteOk : efecteOk && gruixOk;
		if (encertat) encerts++;
	}

	const enllacVideo = $derived(
		shot?.video ? `https://youtu.be/${shot.video.id}?t=${shot.video.inici ?? 0}` : null
	);
</script>

<div class="contenidor">
	<div class="cap">
		<h1>Test del punt de contacte</h1>
		<div class="controls-test">
			<button class="nav" onclick={anterior} disabled={index === 0}>← Anterior</button>
			<div class="marcador">Encerts: <strong>{encerts}</strong> / {total}</div>
			<button class="nav seguent" onclick={seguent}>Següent →</button>
		</div>
	</div>

	<div class="modes">
		{#each MODES as m (m.id)}
			<button class:actiu={data.mode === m.id} onclick={() => goto(`/biblia/quiz?mode=${m.id}`)}>
				{m.nom}
			</button>
		{/each}
	</div>

	{#if !shot}
		<p class="buit">No s'han pogut carregar tirades. <a href="/biblia/quiz?mode={data.mode}">Reintenta</a></p>
	{:else}
		<div class="joc">
			<div class="taula-quiz targeta">
				{#if revelat}
					<Reproductor
						bolesInicials={shot.boles}
						tracaBlanca={shot.tracaBlanca}
						tracaGroga={shot.tracaGroga}
						tracaVermella={shot.tracaVermella}
						{frameExtern}
						teVideo={!!shot.video}
						reproduintExtern={reproduintVideo}
						onReprodueix={() => vid?.reprodueix()}
						onPausa={() => vid?.pausa()}
						onReinicia={() => vid?.reinicia()}
						onVesA={(f) => vid?.vesA(f)}
					/>
					{#if shot.video}
						{#key shot.id}
							<VideoSincronitzat
								bind:this={vid}
								bind:reproduint={reproduintVideo}
								videoId={shot.video.id}
								inici={shot.video.inici ?? 0}
								fi={shot.video.fi}
								{maxFrame}
								onframe={(f) => (frameExtern = f)}
							/>
						{/key}
					{/if}
				{:else}
					<Billar boles={shot.boles} traces={tracesTiradora} mode="visor" />
				{/if}
				<div class="peu-taula">{familiaCat(shot.familia)} · #{shot.id}</div>
			</div>

			<div class="panell targeta">
				{#if data.mode === 'multiple'}
					<p class="instruccio">Quina és l'opció correcta (efecte + quantitat de bola)?</p>
					<div class="opcions">
						{#each opcions.llista as op, i (i)}
							<button
								class="opcio"
								class:correcta={revelat && i === opcions.correctIdx}
								class:erronia={revelat && seleccio === i && i !== opcions.correctIdx}
								disabled={revelat}
								onclick={() => comprovaMultiple(i)}
							>
								<EfecteQuantitat punt={op.efecte} gruix={op.gruix} />
							</button>
						{/each}
					</div>
				{:else if data.mode === 'efecte'}
					<p class="instruccio">Amb aquesta quantitat de bola, marca on picaries (efecte):</p>
					<QuantitatBola gruix={correctGruix} titol="Quantitat de bola (donada)" />
					<div class="cara-gran">
						<CaraBola
							punt={efecteGuess}
							correcte={revelat ? correctEfecte : null}
							interactiu={!revelat}
							onpica={(p) => (efecteGuess = p)}
						/>
					</div>
					{#if !revelat}
						<button class="comprova" disabled={!efecteGuess} onclick={comprova}>Comprova</button>
					{/if}
				{:else}
					<p class="instruccio">Marca l'efecte i tria la quantitat de bola:</p>
					<div class="cara-gran">
						<CaraBola
							punt={efecteGuess}
							correcte={revelat ? correctEfecte : null}
							interactiu={!revelat}
							onpica={(p) => (efecteGuess = p)}
						/>
					</div>
					<QuantitatBola gruix={gruixGuess} titol="La teva quantitat" />
					{#if !revelat}
						<input type="range" min="-8" max="8" step="1" bind:value={gruixGuess} />
						<button class="comprova" disabled={!efecteGuess} onclick={comprova}>Comprova</button>
					{/if}
				{/if}

				{#if revelat}
					<div class="resultat">
						{#if data.mode === 'multiple'}
							<p class="verdicte" class:be={seleccio === opcions.correctIdx}>
								{seleccio === opcions.correctIdx ? '✔ Correcte!' : '✗ La bona era la verda'}
							</p>
						{:else}
							<p class="verdicte" class:be={data.mode === 'efecte' ? efecteOk : efecteOk && gruixOk}>
								Efecte {efecteOk ? '✔' : '✗'}{data.mode === 'ambdos'
									? ` · Quantitat ${gruixOk ? '✔' : '✗'}`
									: ''}
							</p>
							{#if data.mode === 'ambdos'}
								<div class="comparativa">
									<QuantitatBola gruix={correctGruix} titol="Quantitat correcta" />
								</div>
							{/if}
						{/if}
						{#if enllacVideo}
							<a class="video" href={enllacVideo} target="_blank" rel="noopener"
								>▶ Veure la tirada al vídeo ↗</a
							>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.cap {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		flex-wrap: wrap;
		gap: 0.5rem;
	}
	.cap h1 {
		margin: 0;
		font-size: 1.5rem;
	}
	.marcador {
		color: var(--text-suau);
	}
	.controls-test {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		flex-wrap: wrap;
	}
	.nav {
		font-size: 0.85rem;
	}
	.nav:disabled {
		opacity: 0.4;
		cursor: default;
	}
	.marcador strong {
		color: var(--accent);
		font-size: 1.2rem;
	}
	.modes {
		display: flex;
		gap: 0.4rem;
		flex-wrap: wrap;
		margin: 0.8rem 0 1.2rem;
	}
	.joc {
		display: grid;
		grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
		gap: 1.25rem;
		align-items: start;
	}
	.taula-quiz {
		padding: 0.8rem;
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}
	.peu-taula {
		margin-top: 0.4rem;
		font-size: 0.85rem;
		color: var(--text-suau);
	}
	.panell {
		padding: 1rem 1.1rem;
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
		align-items: center;
	}
	.instruccio {
		margin: 0;
		align-self: stretch;
		font-weight: 600;
	}
	.opcions {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.7rem;
		width: 100%;
	}
	.opcio {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.3rem;
		padding: 0.6rem;
		background: var(--fons-3);
		border: 2px solid var(--vora);
		border-radius: 10px;
		cursor: pointer;
	}
	.opcio:hover:not(:disabled) {
		border-color: var(--accent);
	}
	.opcio:disabled {
		cursor: default;
	}
	.opcio.correcta {
		border-color: #2fbf5b;
		background: #10301c;
	}
	.opcio.erronia {
		border-color: var(--perill);
		background: #331416;
	}
	.cara-gran {
		width: 100%;
		max-width: 220px;
	}
	.comprova,
	.seguent {
		background: var(--accent-fosc);
		border-color: var(--accent-fosc);
		color: #fff;
		font-weight: 600;
	}
	input[type='range'] {
		width: 100%;
		accent-color: var(--accent);
	}
	.resultat {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.7rem;
		width: 100%;
		border-top: 1px solid var(--vora);
		padding-top: 0.8rem;
	}
	.verdicte {
		margin: 0;
		font-weight: 700;
		color: var(--perill);
	}
	.verdicte.be {
		color: #2fbf5b;
	}
	.comparativa {
		width: 100%;
		max-width: 200px;
	}
	.video {
		font-size: 0.9rem;
	}
	.buit {
		color: var(--text-suau);
		padding: 2rem 0;
	}
	@media (max-width: 780px) {
		.joc {
			grid-template-columns: 1fr;
		}
	}
</style>
