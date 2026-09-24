<script lang="ts">
	import { onMount } from 'svelte';
	import { db } from '$lib/db';
	import { IDIOMES, llegeixEnllac, mmss, type Idioma, type VideoTraduccio } from '$lib/traductor';

	let videos = $state<VideoTraduccio[]>([]);
	let carregat = $state(false);
	let url = $state('');
	let idioma = $state<Idioma>('ko');
	let enviant = $state(false);
	let msg = $state<{ ok: boolean; text: string } | null>(null);

	const fets = $derived(videos.filter((v) => v.estat === 'fet'));
	const cua = $derived(videos.filter((v) => v.estat !== 'fet'));
	const enllac = $derived(url.trim() ? llegeixEnllac(url) : null);

	async function carrega() {
		const { data } = await db
			.from('video_traduccio')
			.select('id,url,plataforma,video_id,idioma,estat,titol,canal,durada,missatge,creat,processat')
			.order('creat', { ascending: false })
			.range(0, 499);
		videos = (data as VideoTraduccio[]) ?? [];
		carregat = true;
	}

	onMount(() => {
		carrega();
		// Mentre hi ha feina a la cua, l'estat canvia sol: el workflow passa cada quart d'hora.
		const t = setInterval(() => {
			if (cua.some((v) => v.estat === 'pendent' || v.estat === 'processant')) carrega();
		}, 60_000);
		return () => clearInterval(t);
	});

	async function envia(e: SubmitEvent) {
		e.preventDefault();
		if (!enllac) {
			msg = { ok: false, text: 'Enganxa un enllaç de YouTube, Instagram o Facebook.' };
			return;
		}
		const ja = videos.find(
			(v) => v.plataforma === enllac.plataforma && v.video_id === enllac.video_id
		);
		if (ja) {
			msg = {
				ok: ja.estat !== 'error',
				text:
					ja.estat === 'fet'
						? 'Aquest vídeo ja està traduït.'
						: ja.estat === 'error'
							? `Aquest vídeo ja es va provar i no es va poder traduir: ${ja.missatge ?? ''}`
							: 'Aquest vídeo ja és a la cua.'
			};
			return;
		}
		enviant = true;
		msg = null;
		const { error } = await db
			.from('video_traduccio')
			.insert({ url: url.trim(), plataforma: enllac.plataforma, video_id: enllac.video_id, idioma });
		enviant = false;
		if (error) {
			msg = {
				ok: false,
				text: error.message.includes('cua') ? error.message : "No s'ha pogut desar la petició."
			};
			return;
		}
		url = '';
		msg = {
			ok: true,
			text: "Afegit a la cua. Es tradueix en uns 15-30 minuts i quedarà aquí per a tothom."
		};
		await carrega();
	}

	const miniatura = (v: VideoTraduccio) =>
		v.plataforma === 'youtube' ? `https://i.ytimg.com/vi/${v.video_id}/mqdefault.jpg` : null;
	const nomIdioma = (c: Idioma) => IDIOMES.find((i) => i.codi === c)?.nom ?? c;
	const ETIQUETA = { pendent: 'A la cua', processant: 'Traduint…', error: 'No traduït', fet: '' };
</script>

<div class="mb-4">
	<h1 class="text-xl font-bold md:text-2xl">Traductor de vídeos</h1>
	<p class="text-sm text-slate-500 dark:text-slate-400">
		Enganxa un vídeo de billar en coreà, vietnamita o turc i en tindràs la transcripció traduïda al
		català i una veu en off catalana sobre el vídeo original. Els vídeos traduïts queden per a tothom.
	</p>
</div>

<form
	onsubmit={envia}
	class="mb-6 flex flex-col gap-2 rounded-xl border border-slate-200 p-3 sm:flex-row sm:items-center dark:border-slate-800"
>
	<input
		type="url"
		bind:value={url}
		placeholder="https://www.youtube.com/watch?v=…"
		class="min-w-0 flex-1 rounded-sm border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
		aria-label="Enllaç del vídeo"
	/>
	<select
		bind:value={idioma}
		class="rounded-sm border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
		aria-label="Idioma del vídeo"
	>
		{#each IDIOMES as i (i.codi)}
			<option value={i.codi}>{i.nom}</option>
		{/each}
	</select>
	<button
		type="submit"
		disabled={enviant || !url.trim()}
		class="rounded-sm bg-sky-600 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-sky-500 dark:text-slate-900"
		>{enviant ? 'Enviant…' : 'Tradueix'}</button
	>
</form>
{#if msg}
	<p
		class="-mt-4 mb-6 text-sm {msg.ok
			? 'text-emerald-700 dark:text-emerald-400'
			: 'text-red-700 dark:text-red-400'}"
	>
		{msg.text}
	</p>
{/if}

{#if cua.length}
	<section class="mb-6">
		<h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
			Cua <span class="font-normal">· {cua.length}</span>
		</h2>
		<ul class="divide-y divide-slate-100 text-sm dark:divide-slate-800">
			{#each cua as v (v.id)}
				<li class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-1.5">
					<span
						class="ag-et {v.estat === 'error'
							? 'text-red-700 dark:text-red-400'
							: 'text-slate-500 dark:text-slate-400'}">{ETIQUETA[v.estat]}</span
					>
					<a href={v.url} target="_blank" rel="noopener" class="min-w-0 flex-1 truncate hover:underline"
						>{v.titol ?? v.url}</a
					>
					<span class="text-xs text-slate-400">{nomIdioma(v.idioma)}</span>
					{#if v.estat === 'error' && v.missatge}
						<span class="w-full text-xs text-slate-500 dark:text-slate-400">{v.missatge}</span>
					{/if}
				</li>
			{/each}
		</ul>
	</section>
{/if}

{#if fets.length}
	<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
		{#each fets as v (v.id)}
			<a
				href="/traductor/{v.id}"
				class="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white hover:border-sky-400 dark:border-slate-800 dark:bg-slate-900"
			>
				{#if miniatura(v)}
					<img src={miniatura(v)} alt="" class="aspect-video w-full object-cover" loading="lazy" />
				{:else}
					<div
						class="grid aspect-video w-full place-items-center bg-slate-100 text-sm capitalize text-slate-500 dark:bg-slate-800"
					>
						{v.plataforma}
					</div>
				{/if}
				<div class="flex flex-1 flex-col gap-1 p-3">
					<span class="font-semibold leading-tight">{v.titol ?? v.video_id}</span>
					<span class="text-xs text-slate-500 dark:text-slate-400">
						{v.canal ?? ''}{v.canal ? ' · ' : ''}{nomIdioma(v.idioma)}{v.durada
							? ` · ${mmss(v.durada)}`
							: ''}
					</span>
				</div>
			</a>
		{/each}
	</div>
{:else if carregat && !cua.length}
	<p class="py-10 text-center text-slate-500 dark:text-slate-400">
		Encara no hi ha cap vídeo traduït. Enganxa'n el primer.
	</p>
{/if}
