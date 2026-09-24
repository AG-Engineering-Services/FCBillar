<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { db } from '$lib/db';
	import {
		IDIOMES,
		aVtt,
		ambReintentsCache,
		eliminaVideo,
		mmss,
		segmentA,
		urlServida,
		type Segment,
		type VideoTraduccio
	} from '$lib/traductor';

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
	const CARREGANT = 3;

	let v = $state<VideoTraduccio | null>(null);
	let noTrobat = $state(false);
	// 'ca' = veu en off catalana (l'original silenciat o molt baix); 'orig' = so original i subtítols.
	let mode = $state<'ca' | 'orig'>('ca');
	let volumFons = $state(0);
	let ambOriginal = $state(false);
	let temps = $state(0);
	let avisAudio = $state(false);
	let errorAudio = $state('');
	let sonant = $state(false);
	let esAdmin = $state(false);

	async function elimina() {
		if (v && (await eliminaVideo((f, a) => db.rpc(f, a), v))) goto('/traductor');
	}

	let contenidor = $state<HTMLDivElement>();
	let audio = $state<HTMLAudioElement>();
	// Instagram i Facebook no es poden controlar incrustats: es reprodueix la còpia
	// que en desa el workflow (migració 0025), amb els subtítols com a pista WebVTT.
	let videoEl = $state<HTMLVideoElement>();
	let vttUrl = $state<string | null>(null);
	let player: YTPlayer | null = null;

	const segments = $derived<Segment[]>(v?.segments ?? []);
	const actual = $derived(segmentA(segments, temps));
	const esYoutube = $derived(v?.plataforma === 'youtube');
	const teVideo = $derived(!esYoutube && !!v?.video_url);
	const controlable = $derived(esYoutube || teVideo);
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
		const silenci = mode === 'ca' && volumFons === 0;
		if (player) {
			if (silenci) player.mute();
			else {
				player.unMute();
				player.setVolume(mode === 'ca' ? volumFons : 100);
			}
		} else if (videoEl) {
			videoEl.muted = silenci;
			videoEl.volume = mode === 'ca' ? volumFons / 100 : 1;
		}
	}

	// El rellotge és el del vídeo, sigui el de YouTube o el propi.
	function tempsVideo(): number {
		return player ? player.getCurrentTime() : (videoEl?.currentTime ?? 0);
	}
	function videoSona(): boolean {
		if (player) {
			const e = player.getPlayerState();
			return e === REPRODUINT || e === CARREGANT; // carregant: no parem la veu
		}
		return !!videoEl && !videoEl.paused && !videoEl.ended;
	}

	function fesSonar() {
		if (!audio) return;
		audio.play().then(
			() => {
				avisAudio = false;
				errorAudio = '';
			},
			(e: DOMException) => {
				// NotAllowedError: el navegador vol un clic a la pàgina (un clic dins del
				// reproductor de YouTube no compta a tots: Safari no). Qualsevol altre és
				// un error de debò, i es diu tal qual en lloc de «bloquejat».
				if (e.name === 'NotAllowedError') avisAudio = true;
				else errorAudio = `${e.name}: ${e.message}`;
			}
		);
	}

	// La veu catalana segueix el rellotge del vídeo. Salta només si es desvia més
	// d'un segon; per sota, s'accelera o s'alenteix una mica fins que l'atrapa.
	function sincronitza() {
		if (!audio || (!player && !videoEl)) return;
		temps = tempsVideo();
		sonant = videoSona();
		if (!sonant || mode !== 'ca') {
			if (!audio.paused) audio.pause();
			audio.playbackRate = 1;
			return;
		}
		if (audio.paused) {
			if (Math.abs(audio.currentTime - temps) > 1) audio.currentTime = temps;
			fesSonar();
			return;
		}
		if (audio.seeking || audio.readyState < 3) return;
		const deriva = audio.currentTime - temps;
		if (Math.abs(deriva) > 1) {
			audio.currentTime = temps;
			audio.playbackRate = 1;
		} else audio.playbackRate = Math.abs(deriva) > 0.15 ? (deriva > 0 ? 0.95 : 1.05) : 1;
	}

	function salta(t: number) {
		if (player) {
			player.seekTo(t, true);
			player.playVideo();
		} else if (videoEl) {
			videoEl.currentTime = t;
			videoEl.play();
		} else if (audio) {
			audio.currentTime = t;
			audio.play();
		}
		if (audio && controlable) audio.currentTime = t;
		temps = t;
	}

	// El botó propi: vídeo i veu amb el mateix clic, que és a la pàgina i no dins
	// del reproductor, i per tant el navegador el compta per deixar sonar la veu.
	function reprodueix() {
		if (videoSona()) {
			player?.pauseVideo();
			videoEl?.pause();
			audio?.pause();
			sonant = false;
			return;
		}
		if (player) player.playVideo();
		else videoEl?.play();
		if (audio && mode === 'ca') {
			audio.currentTime = tempsVideo();
			fesSonar();
		}
		sonant = true;
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
		try {
			esAdmin = localStorage.getItem('fcb_admin') === '1';
		} catch {
			esAdmin = false;
		}
		(async () => {
			const { data } = await ambReintentsCache(() =>
				db
					.from('video_traduccio')
					.select('*')
					.eq('id', Number($page.params.id))
					.eq('estat', 'fet')
					.maybeSingle()
			);
			if (!data) {
				noTrobat = true;
				return;
			}
			v = data as VideoTraduccio;
			if (v.plataforma !== 'youtube') {
				if (v.video_url) {
					vttUrl = URL.createObjectURL(
						new Blob([aVtt(v.segments ?? [])], { type: 'text/vtt' })
					);
					rellotge = setInterval(sincronitza, 250);
				}
				return;
			}
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
			if (vttUrl) URL.revokeObjectURL(vttUrl);
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
			{#if esAdmin}
				·
				<button class="text-red-700 hover:underline dark:text-red-400" onclick={elimina}
					>Elimina</button
				>
			{/if}
		</p>
	</header>

	<div class="lg:grid lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:gap-6">
		<div>
			{#if esYoutube}
				<div class="aspect-video w-full overflow-hidden rounded-xl bg-black">
					<div bind:this={contenidor} class="h-full w-full"></div>
				</div>
			{:else if teVideo}
				<!-- svelte-ignore a11y_media_has_caption (els subtítols van a la pista WebVTT) -->
				<video
					bind:this={videoEl}
					src={urlServida(v.video_url, v.processat)}
					controls
					playsinline
					preload="metadata"
					class="max-h-[70vh] w-full rounded-xl bg-black"
					onplay={() => {
						aplicaVolum();
						sincronitza();
					}}
					onpause={sincronitza}
					onseeked={sincronitza}
				>
					{#if vttUrl}
						<track kind="subtitles" srclang="ca" label="Català" src={vttUrl} default />
					{/if}
				</video>
			{:else}
				<!-- Traduccions d'Instagram o Facebook d'abans de la 0025, sense còpia: no es
				     pot sincronitzar. S'escolta la veu catalana amb el vídeo obert al costat. -->
				<p class="mb-2 rounded-xl border border-slate-200 p-3 text-sm text-slate-600 dark:border-slate-800 dark:text-slate-300">
					{v.plataforma === 'instagram' ? 'Instagram' : 'Facebook'} no deixa posar-hi la veu a
					sobre. Obre el <a href={v.url} target="_blank" rel="noopener" class="text-sky-700 underline dark:text-sky-300">vídeo original</a>
					silenciat i fes sonar la veu catalana alhora.
				</p>
			{/if}

			<audio
				bind:this={audio}
				src={urlServida(v.audio_url, v.processat)}
				preload="auto"
				controls={!controlable}
				ontimeupdate={() => {
					if (!controlable && audio) temps = audio.currentTime;
				}}
				class={controlable ? 'hidden' : 'w-full'}
			></audio>

			<p
				class="mt-3 min-h-[4.5rem] rounded-xl bg-slate-900 px-4 py-3 text-center text-lg leading-snug text-white md:text-xl dark:bg-slate-800"
				aria-live="polite"
			>
				{actual?.ca ?? ''}
			</p>

			{#if controlable}
				<div class="mt-3 flex flex-wrap items-center gap-2 text-sm">
					<button
						class="rounded-sm bg-slate-900 px-4 py-1 font-medium text-white dark:bg-slate-100 dark:text-slate-900"
						onclick={reprodueix}>{sonant ? '⏸ Pausa' : '▶ Reprodueix'}</button
					>
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
				{#if errorAudio}
					<p class="mt-2 text-sm text-red-700 dark:text-red-400">
						No s'ha pogut reproduir la veu catalana ({errorAudio}).
					</p>
				{:else if avisAudio}
					<p class="mt-2 text-sm text-amber-700 dark:text-amber-400">
						El navegador no deixa sonar la veu si el vídeo s'engega des de dins del reproductor.
						Fes-lo anar amb el botó <strong>▶ Reprodueix</strong> d'aquí sobre.
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
