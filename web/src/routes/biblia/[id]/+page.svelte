<script lang="ts">
	import Reproductor from '$lib/biblia/billar/Reproductor.svelte';
	import VideoSincronitzat from '$lib/biblia/billar/VideoSincronitzat.svelte';
	import DiagramaTecnica from '$lib/biblia/billar/DiagramaTecnica.svelte';
	import { familiaCat, familiaKo, FLAGS } from '$lib/biblia/api/vocabulari';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const d = $derived(data.detall);

	// Fotograma controlat pel vídeo (null = l'anima el rellotge intern del Reproductor).
	let frameExtern = $state<number | null>(null);
	const maxFrame = $derived(
		Math.max(
			0,
			...d.tracaBlanca.map((f) => f.frame),
			...d.tracaGroga.map((f) => f.frame),
			...d.tracaVermella.map((f) => f.frame)
		)
	);

	const videoWatch = $derived(d.video ? `https://youtu.be/${d.video.id}?t=${d.video.inici ?? 0}` : null);

	function mmss(s: number): string {
		const m = Math.floor(s / 60);
		const seg = s % 60;
		return `${m}:${seg.toString().padStart(2, '0')}`;
	}

	function enllacVei(id: number | null): string | null {
		if (id == null) return null;
		return `/biblia/${id}${data.esAnalisi ? '?a=1' : ''}`;
	}
</script>

<div class="contenidor">
	<div class="barra">
		<a href="/biblia" class="tornar">← Totes les tirades</a>
		<div class="veins">
			{#if enllacVei(d.prevId)}
				<a href={enllacVei(d.prevId)}>← Anterior</a>
			{/if}
			{#if enllacVei(d.nextId)}
				<a href={enllacVei(d.nextId)}>Següent →</a>
			{/if}
		</div>
	</div>

	<div class="disposicio">
		<!-- Columna esquerra: taula -->
		<section class="taula">
			{#key d.id}
				<Reproductor
					bolesInicials={d.boles}
					tracaBlanca={d.tracaBlanca}
					tracaGroga={d.tracaGroga}
					tracaVermella={d.tracaVermella}
					{frameExtern}
				/>
			{/key}

			{#if !d.teAnalisi}
				<p class="nota-pro">
					Tir pro: la taula mostra la posició inicial. L'animació del recorregut de les
					boles és només als <a href="/biblia?tipus=analisi">Tirs analitzats</a>.
				</p>
			{/if}

			{#if data.jugador}
				<div class="jugador">
					{#if data.jugador.retratUrl}
						<img class="retrat" src={data.jugador.retratUrl} alt={data.jugador.nom} />
					{/if}
					<div>
						<div class="nom">{data.jugador.nom}</div>
						<div class="ko">{data.jugador.nomKo}</div>
					</div>
					{#if data.jugador.banderaUrl}
						<img class="bandera" src={data.jugador.banderaUrl} alt={data.jugador.nacionalitat} />
					{/if}
				</div>
			{/if}

			{#if data.original}
				<div class="explicacio targeta">
					<h3>Explicació</h3>
					{#await data.explicacioPromesa}
						<p class="consell traduint">Traduint…</p>
					{:then explicacio}
						<p class="consell">{explicacio || data.original}</p>
					{:catch}
						<p class="consell">{data.original}</p>
					{/await}
					<details class="original">
						<summary>Text original (coreà)</summary>
						<p class="consell">{data.original}</p>
					</details>
				</div>
			{/if}
		</section>

		<!-- Columna dreta: vídeo + dades -->
		<section class="info">
			{#if d.video}
				<div class="videobloc">
					{#key d.id}
						<VideoSincronitzat
							videoId={d.video.id}
							inici={d.video.inici ?? 0}
							fi={d.video.fi}
							{maxFrame}
							onframe={(f) => (frameExtern = f)}
						/>
					{/key}
					{#if videoWatch}
						<a class="ytlink" href={videoWatch} target="_blank" rel="noopener">
							▶ Obre a YouTube{d.video?.inici ? ` (min ${mmss(d.video.inici)})` : ''} ↗
						</a>
					{/if}
				</div>
			{/if}

			<div class="dades targeta">
				<h2>Tirada #{d.id}</h2>
				<div class="fila">
					<span class="clau">Família</span>
					<span class="valor">{familiaCat(d.familia)} <small class="ko">{familiaKo(d.familia)}</small></span>
				</div>

				{#if d.esPosicio || d.esDefensa || d.esEvitarKiss || d.esDificil}
					<div class="fila">
						<span class="clau">Tipus</span>
						<span class="etiquetes">
							{#if d.esDificil}<span class="tag">{FLAGS.dificil.ca}</span>{/if}
							{#if d.esPosicio}<span class="tag">{FLAGS.posicio.ca}</span>{/if}
							{#if d.esDefensa}<span class="tag">{FLAGS.defensa.ca}</span>{/if}
							{#if d.esEvitarKiss}<span class="tag">{FLAGS.evitarKiss.ca}</span>{/if}
						</span>
					</div>
				{/if}

				{#if d.teAnalisi}
					<DiagramaTecnica puntContacte={d.puntContacte} gruix={d.gruix} velocitat={d.velocitat} />
				{/if}
			</div>
		</section>
	</div>
</div>

<style>
	.barra {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		margin-bottom: 1rem;
		flex-wrap: wrap;
	}
	.veins {
		display: flex;
		gap: 1rem;
	}
	.disposicio {
		display: grid;
		grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
		gap: 1.5rem;
		align-items: start;
	}
	.taula {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}
	.nota-pro {
		margin: 0;
		font-size: 0.85rem;
		color: var(--text-suau);
	}
	.jugador {
		display: flex;
		align-items: center;
		gap: 0.7rem;
		padding: 0.6rem 0.8rem;
		background: var(--fons-2);
		border: 1px solid var(--vora);
		border-radius: var(--radi);
	}
	.retrat {
		width: 42px;
		height: 42px;
		border-radius: 50%;
		object-fit: cover;
		background: var(--fons-3);
	}
	.nom {
		font-weight: 600;
	}
	.ko {
		color: var(--text-suau);
		font-size: 0.82rem;
	}
	.bandera {
		width: 26px;
		height: auto;
		margin-left: auto;
		border-radius: 3px;
	}
	.info {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.videobloc {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.ytlink {
		align-self: flex-start;
		font-size: 0.85rem;
		color: var(--text-suau);
	}
	.ytlink:hover {
		color: var(--accent);
	}
	.dades {
		padding: 0.9rem 1.1rem;
	}
	.dades h2 {
		margin: 0 0 0.7rem;
		font-size: 1.1rem;
	}
	.fila {
		display: flex;
		align-items: baseline;
		gap: 0.8rem;
		padding: 0.35rem 0;
		border-top: 1px solid var(--vora);
	}
	.clau {
		color: var(--text-suau);
		font-size: 0.82rem;
		min-width: 6.5rem;
	}
	.valor {
		font-weight: 500;
	}
	.etiquetes {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}
	.tag {
		font-size: 0.72rem;
		padding: 0.1rem 0.45rem;
		border-radius: 5px;
		background: var(--fons-3);
		border: 1px solid var(--vora);
		color: var(--text-suau);
	}
	.explicacio {
		padding: 0.9rem 1.1rem;
	}
	.explicacio h3 {
		margin: 0 0 0.5rem;
		font-size: 1rem;
	}
	.consell {
		margin: 0;
		color: var(--text-suau);
		white-space: pre-line;
		font-size: 0.92rem;
	}
	.traduint {
		font-style: italic;
		opacity: 0.7;
	}
	.original {
		margin-top: 0.9rem;
		border-top: 1px solid var(--vora);
		padding-top: 0.6rem;
	}
	.original summary {
		cursor: pointer;
		color: var(--text-suau);
		font-size: 0.82rem;
	}
	.original p {
		margin-top: 0.6rem;
	}
	@media (max-width: 820px) {
		.disposicio {
			grid-template-columns: 1fr;
		}
	}
</style>
