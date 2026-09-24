<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { db } from '$lib/db';
	import { IDIOMES, mmss, segmentA, type Segment, type VideoTraduccio } from '$lib/traductor';

	// Reproductor de YouTube (IFrame API), només la part que fem servir.
	interface YTPlayer {
		getCurrentTime(): number;
		getPlayerState(): number;
		playVideo(): void;
		pauseVideo(): void;
		seekTo(s: number, allowSeekAhead: boolean): void;
		mute(): void;
		unMute(): void;
		setVolume(v: number): void;
		destroy(): void;
	}
	type YTNamespace = { Player: new (el: HTMLElement, opts: object) => YTPlayer };
	const REPRODUINT = 1;

	let v = $state<VideoTraduccio | null>(null);
	let noTrobat = $state(false);
	// 'ca' = veu en off catalana (l'original silenciat o molt baix); 'orig' = so original i subtítols.
	let mode = $state<'ca' | 'orig'>('ca');
	let volumFons = $state(0);
	let ambOriginal = $state(false);
	let temps = $state(0);
	let avisAudio = $state(false);

	let contenidor = $state<HTMLDivElement>();
	let audio = $state<HTMLAudioElement>();
	let player: YTPlayer | null = null;

	const segments = $derived<Segment[]>(v?.segments ?? []);
	const actual = $derived(segmentA(segments, temps));
	const esYoutube = $derived(v?.plataforma === 'youtube');
	const nomIdioma = $derived(IDIOMES.find((i) => i.codi === v?.idioma)?.nom ?? '');

	function carregaApiYoutube(): Promise<YTNamespace> {
		const w = window as unknown as { YT?: YTNamespace; onYouTubeIframeAPIReady?: () => void };
		if (w.YT?.Player) return Promise.resolve(w.YT);
		return new Promise((resol) => {
			w.onYouTubeIframeAPIReady = () => resol(w.YT!);
			const s = document.createElement('script');
			s.src = 'https://www.youtube.com/iframe_api';
			document.head.appendChild(s);
		});
	}

	function aplicaVolum() {
		if (!player) return;
		if (mode === 'ca' && volumFons === 0) player.mute();
		else {
			player.unMute();
			player.setVolume(mode === 'ca' ? volumFons : 100);
		}
	}

	// La veu catalana segueix el rellotge del vídeo: si es desvia més d'un terç de
	// segon (un salt, un tall de xarxa), es recol·loca.
	function sincronitza() {
		if (!player || !audio) return;
		temps = player.getCurrentTime();
		const sona = player.getPlayerState() === REPRODUINT && mode === 'ca';
		if (!sona) {
			if (!audio.paused) audio.pause();
			return;
		}
		if (audio.paused || Math.abs(audio.currentTime - temps) > 0.35) audio.currentTime = temps;
		if (audio.paused)
			audio.play().then(
				() => (avisAudio = false),
				() => (avisAudio = true) // el navegador no deixa sonar sense un clic a la pàgina
			);
	}

	function salta(t: number) {
		if (player) {
			player.seekTo(t, true);
			player.playVideo();
		} else if (audio) {
			audio.currentTime = t;
			audio.play();
		}
		temps = t;
	}

	function reprodueix() {
		player?.playVideo();
		if (audio && mode === 'ca') {
			audio.currentTime = player?.getCurrentTime() ?? audio.currentTime;
			audio.play().then(() => (avisAudio = false));
		}
	}

	$effect(() => {
		// Tornar a aplicar el volum quan canvia el mode o el control.
		void mode;
		void volumFons;
		aplicaVolum();
	});

	onMount(() => {
		let rellotge: ReturnType<typeof setInterval> | undefined;
		let mort = false;
		(async () => {
			const { data } = await db
				.from('video_traduccio')
				.select('*')
				.eq('id', Number($page.params.id))
				.eq('estat', 'fet')
				.maybeSingle();
			if (!data) {
				noTrobat = true;
				return;
			}
			v = data as VideoTraduccio;
			if (v.plataforma !== 'youtube') return;
			const YT = await carregaApiYoutube();
			if (mort || !contenidor) return;
			player = new YT.Player(contenidor, {
				videoId: v.video_id,
				playerVars: { playsinline: 1, rel: 0, cc_load_policy: 0 },
				events: { onReady: aplicaVolum }
			});
			rellotge = setInterval(sincronitza, 250);
		})();
		return () => {
			mort = true;
			clearInterval(rellotge);
			player?.destroy();
		};
	});
</script>

<a
	href="/traductor"
	class="mb-3 inline-block text-sm text-slate-500 hover:underline dark:text-slate-400"
	>← Tots els vídeos traduïts</a
>

{#if noTrobat}
	<p class="py-10 text-center text-slate-500 dark:text-slate-400">
		Aquest vídeo no existeix o encara no està traduït.
	</p>
{:else if v}
	<header class="mb-3">
		<h1 class="text-xl font-bold leading-tight md:text-2xl">{v.titol ?? v.video_id}</h1>
		<p class="text-sm text-slate-500 dark:text-slate-400">
			{v.canal ?? ''}{v.canal ? ' · ' : ''}Traduït del {nomIdioma.toLowerCase()} ·
			<a href={v.url} target="_blank" rel="noopener" class="hover:underline">vídeo original ↗</a>
		</p>
	</header>

	<div class="lg:grid lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:gap-6">
		<div>
			{#if esYoutube}
				<div class="aspect-video w-full overflow-hidden rounded-xl bg-black">
					<div bind:this={contenidor} class="h-full w-full"></div>
				</div>
			{:else}
				<!-- Instagram i Facebook no deixen controlar el reproductor incrustat: no es
				     pot sincronitzar. S'escolta la veu catalana amb el vídeo obert al costat. -->
				<p class="mb-2 rounded-xl border border-slate-200 p-3 text-sm text-slate-600 dark:border-slate-800 dark:text-slate-300">
					{v.plataforma === 'instagram' ? 'Instagram' : 'Facebook'} no deixa posar-hi la veu a
					sobre. Obre el <a href={v.url} target="_blank" rel="noopener" class="text-sky-700 underline dark:text-sky-300">vídeo original</a>
					silenciat i fes sonar la veu catalana alhora.
				</p>
			{/if}

			<audio
				bind:this={audio}
				src={v.audio_url}
				preload="auto"
				controls={!esYoutube}
				ontimeupdate={() => {
					if (!esYoutube && audio) temps = audio.currentTime;
				}}
				class={esYoutube ? 'hidden' : 'w-full'}
			></audio>

			<p
				class="mt-3 min-h-[4.5rem] rounded-xl bg-slate-900 px-4 py-3 text-center text-lg leading-snug text-white md:text-xl dark:bg-slate-800"
				aria-live="polite"
			>
				{actual?.ca ?? ''}
			</p>

			{#if esYoutube}
				<div class="mt-3 flex flex-wrap items-center gap-2 text-sm">
					<button
						class="rounded-sm px-3 py-1 {mode === 'ca'
							? 'bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-900'
							: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
						onclick={() => (mode = 'ca')}>Veu en català</button
					>
					<button
						class="rounded-sm px-3 py-1 {mode === 'orig'
							? 'bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-900'
							: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
						onclick={() => (mode = 'orig')}>So original</button
					>
					{#if mode === 'ca'}
						<label class="ml-auto flex items-center gap-2 text-slate-500 dark:text-slate-400">
							So original de fons
							<input type="range" min="0" max="40" step="5" bind:value={volumFons} class="w-24" />
						</label>
					{/if}
				</div>
				{#if avisAudio}
					<p class="mt-2 text-sm text-amber-700 dark:text-amber-400">
						El navegador ha bloquejat la veu catalana.
						<button class="underline" onclick={reprodueix}>Prem aquí per sentir-la</button>.
					</p>
				{/if}
			{/if}
		</div>

		<section class="mt-6 lg:mt-0">
			<div class="mb-2 flex items-center justify-between">
				<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
					Transcripció
				</h2>
				<label class="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
					<input type="checkbox" bind:checked={ambOriginal} /> Text original
				</label>
			</div>
			<ol class="max-h-[70vh] space-y-1 overflow-y-auto pr-1 text-sm">
				{#each segments as s (s.t0)}
					<li>
						<button
							class="w-full rounded-sm px-2 py-1 text-left {s === actual
								? 'bg-sky-50 dark:bg-sky-950'
								: 'hover:bg-slate-50 dark:hover:bg-slate-800/60'}"
							onclick={() => salta(s.t0)}
						>
							<span class="mr-2 font-mono text-xs text-slate-400">{mmss(s.t0)}</span>
							<span>{s.ca || '—'}</span>
							{#if ambOriginal}
								<span class="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{s.orig}</span>
							{/if}
						</button>
					</li>
				{/each}
			</ol>
		</section>
	</div>
{/if}
