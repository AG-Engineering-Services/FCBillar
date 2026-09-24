<script lang="ts">
	import { onMount } from 'svelte';
	import { db } from '$lib/db';
	import {
		IDIOMES,
		ambReintentsCache,
		eliminaVideo,
		estimaCua,
		hora,
		llegeixEnllac,
		mmss,
		quantFalta,
		type Idioma,
		type VideoTraduccio
	} from '$lib/traductor';

	let videos = $state<VideoTraduccio[]>([]);
	let carregat = $state(false);
	let url = $state('');
	let idioma = $state<Idioma>('ko');
	let enviant = $state(false);
	let msg = $state<{ ok: boolean; text: string } | null>(null);

	const fets = $derived(videos.filter((v) => v.estat === 'fet'));
	const cua = $derived(videos.filter((v) => v.estat !== 'fet'));
	const enllac = $derived(url.trim() ? llegeixEnllac(url) : null);

	// Quan estarà llest cada vídeo de la cua; es refà sol a mesura que passa el temps.
	let ara = $state(new Date());
	const estimacions = $derived(estimaCua(videos, ara));
	function previsio(v: VideoTraduccio): string {
		const e = estimacions.get(v.id);
		if (!e) return '';
		return `llest cap a les ${hora(e.acaba)} (${quantFalta(e.acaba, ara)})`;
	}

	// En enganxar un enllaç es mira de seguida si el vídeo ja hi és, a la base de
	// dades i no a la llista carregada: la llista es talla a 500 i pot ser vella.
	let existent = $state<VideoTraduccio | null>(null);
	let comprovant = $state(false);
	$effect(() => {
		const e = enllac;
		existent = null;
		if (!e) return;
		let vigent = true;
		comprovant = true;
		ambReintentsCache(() =>
			db
				.from('video_traduccio')
				.select('id,url,plataforma,video_id,idioma,estat,titol,canal,durada,missatge,creat,processat,iniciat')
				.eq('plataforma', e.plataforma)
				.eq('video_id', e.video_id)
				.maybeSingle()
		).then(({ data }) => {
			if (!vigent) return; // l'usuari ja ha canviat l'enllaç
			existent = (data as VideoTraduccio | null) ?? null;
			comprovant = false;
		});
		return () => {
			vigent = false;
		};
	});

	async function carrega() {
		const { data } = await ambReintentsCache(() =>
			db
				.from('video_traduccio')
				.select('id,url,plataforma,video_id,idioma,estat,titol,canal,durada,missatge,creat,processat,iniciat')
				.order('creat', { ascending: false })
				.range(0, 499)
		);
		videos = (data as VideoTraduccio[]) ?? [];
		carregat = true;
	}

	// Admin: la mateixa marca que als sistemes. Només ensenya els botons; qui decideix
	// és la clau que demana eliminaVideo.
	let esAdmin = $state(false);
	async function elimina(v: VideoTraduccio) {
		if (await eliminaVideo((f, a) => db.rpc(f, a), v)) await carrega();
	}

	onMount(() => {
		try {
			esAdmin = localStorage.getItem('fcb_admin') === '1';
		} catch {
			esAdmin = false;
		}
		carrega();
		// Mentre hi ha feina a la cua, l'estat canvia sol: el workflow passa cada quart d'hora.
		const rellotge = setInterval(() => (ara = new Date()), 15_000);
		const t = setInterval(() => {
			if (cua.some((v) => v.estat === 'pendent' || v.estat === 'processant')) carrega();
		}, 20_000);
		return () => {
			clearInterval(rellotge);
			clearInterval(t);
		};
	});

	async function envia(e: SubmitEvent) {
		e.preventDefault();
		if (!enllac) {
			msg = { ok: false, text: 'Enganxa un enllaç de YouTube, Instagram o Facebook.' };
			return;
		}
		if (existent || comprovant) return; // l'avís de sota el formulari ja ho diu
		enviant = true;
		msg = null;
		const fila = { url: url.trim(), plataforma: enllac.plataforma, video_id: enllac.video_id, idioma };
		const { error } = await ambReintentsCache(() => db.from('video_traduccio').insert(fila));
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
			text: 'Afegit a la cua. Quedarà aquí per a tothom.'
		};
		await carrega();
		ara = new Date();
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
		disabled={enviant || !url.trim() || comprovant || !!existent}
		class="rounded-sm bg-sky-600 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-sky-500 dark:text-slate-900"
		>{enviant ? 'Enviant…' : 'Tradueix'}</button
	>
</form>
{#if url.trim() && !enllac}
	<p class="-mt-4 mb-6 text-sm text-slate-500 dark:text-slate-400">
		Aquest enllaç no és de YouTube, Instagram ni Facebook.
	</p>
{:else if existent?.estat === 'fet'}
	<a
		href="/traductor/{existent.id}"
		class="-mt-4 mb-6 flex items-center gap-3 rounded-xl border border-emerald-300 bg-emerald-50 p-3 text-sm hover:border-emerald-500 dark:border-emerald-800 dark:bg-emerald-950"
	>
		<span class="text-emerald-800 dark:text-emerald-300">
			<strong>Ja està traduït:</strong>
			{existent.titol ?? existent.video_id}
		</span>
		<span class="ml-auto shrink-0 font-medium text-emerald-800 dark:text-emerald-300">Mira'l →</span>
	</a>
{:else if existent?.estat === 'pendent' || existent?.estat === 'processant'}
	<p class="-mt-4 mb-6 text-sm text-slate-600 dark:text-slate-300">
		{existent.estat === 'processant' ? "S'està traduint ara mateix" : 'Ja és a la cua'}{previsio(
			existent
		)
			? `: ${previsio(existent)}.`
			: '.'}
	</p>
{:else if existent?.estat === 'error'}
	<p class="-mt-4 mb-6 text-sm text-red-700 dark:text-red-400">
		Aquest vídeo ja es va provar i no es va poder traduir{existent.missatge
			? `: ${existent.missatge}`
			: '.'}
	</p>
{:else if msg}
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
					{#if previsio(v)}
						<span class="w-full text-xs text-slate-500 dark:text-slate-400">
							{v.durada ? `${mmss(v.durada)} de vídeo · ` : ''}{previsio(v)}
						</span>
					{/if}
					{#if esAdmin}
						<button
							class="text-xs text-red-700 hover:underline dark:text-red-400"
							onclick={() => elimina(v)}>Elimina</button
						>
					{/if}
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
			<div
				class="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white hover:border-sky-400 dark:border-slate-800 dark:bg-slate-900"
			>
				<a href="/traductor/{v.id}" class="flex flex-1 flex-col">
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
				{#if esAdmin}
					<button
						class="border-t border-slate-100 px-3 py-1.5 text-left text-xs text-red-700 hover:bg-red-50 dark:border-slate-800 dark:text-red-400 dark:hover:bg-red-950"
						onclick={() => elimina(v)}>Elimina</button
					>
				{/if}
			</div>
		{/each}
	</div>
{:else if carregat && !cua.length}
	<p class="py-10 text-center text-slate-500 dark:text-slate-400">
		Encara no hi ha cap vídeo traduït. Enganxa'n el primer.
	</p>
{/if}
