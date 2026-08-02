<script lang="ts">
	import sistemes from '$lib/sistemes/sistemes.json';
	import { page } from '$app/stores';
	import { supabase } from '$lib/supabase';
	import { onMount } from 'svelte';

	interface Explicacio {
		queEs: string;
		passos: string[];
		quan: string;
		consells: string[];
		nivell: string;
	}
	interface Sistema {
		id: string;
		nom: string;
		categoria: string;
		resum: string;
		canal: string;
		visites: number;
		likes: number;
		data: string;
		miniatura: string;
		explicacio?: Explicacio;
		transcripcio?: string;
		font?: string;
	}
	const tots = sistemes as Sistema[];
	const s = $derived(tots.find((x) => x.id === $page.params.id));

	let esAdmin = $state(false);
	let mark = $state<boolean | null>(null);

	onMount(async () => {
		esAdmin = typeof localStorage !== 'undefined' && localStorage.getItem('fcb_admin') === '1';
		if (!s) return;
		try {
			const { data } = await supabase
				.from('sistema_marca')
				.select('funciona')
				.eq('video_id', s.id)
				.maybeSingle();
			mark = data ? (data.funciona as boolean | null) : null;
		} catch {
			mark = null;
		}
	});

	async function marca(valor: boolean) {
		if (!s) return;
		const nou = mark === valor ? null : valor;
		mark = nou;
		try {
			await supabase
				.from('sistema_marca')
				.upsert({ video_id: s.id, funciona: nou, updated_at: new Date().toISOString() });
		} catch {
			// sense taula encara: es manté només a la vista
		}
	}

	const fmt = (n: number) =>
		n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : String(n);
	const FONT: Record<string, string> = {
		subtítols: 'Explicació generada a partir dels subtítols del vídeo, traduïts i resumits.',
		descripció: 'Explicació generada a partir de la descripció del vídeo.',
		coneixement: 'El vídeo no tenia text; explicació basada en el sistema pel seu nom.'
	};
</script>

<a
	href="/sistemes-coreans"
	class="mb-3 inline-block text-sm text-slate-500 hover:underline dark:text-slate-400"
	>← Tots els sistemes</a
>

{#if !s}
	<p class="py-10 text-center text-slate-500 dark:text-slate-400">Sistema no trobat.</p>
{:else}
	<header class="mb-4">
		<div class="mb-1 flex flex-wrap items-center gap-2">
			<span
				class="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
				>{s.categoria}</span
			>
			{#if s.explicacio}
				<span
					class="rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
					>Nivell {s.explicacio.nivell}</span
				>
			{/if}
			{#if mark === true}
				<span class="rounded-full bg-emerald-500 px-2.5 py-0.5 text-xs font-semibold text-white">✓ funciona</span>
			{:else if mark === false}
				<span class="rounded-full bg-red-500 px-2.5 py-0.5 text-xs font-semibold text-white">✗ no funciona</span>
			{/if}
		</div>
		<h1 class="text-xl font-bold md:text-2xl">{s.nom}</h1>
		<div class="text-sm text-slate-500 dark:text-slate-400">
			{s.canal} · ▶ {fmt(s.visites)} visites
		</div>
	</header>

	<div class="grid grid-cols-1 gap-5 lg:grid-cols-[1.1fr_1fr]">
		<!-- Vídeo -->
		<div>
			<div class="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
				<iframe
					class="aspect-video w-full"
					src={`https://www.youtube.com/embed/${s.id}`}
					title={s.nom}
					frameborder="0"
					allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
					allowfullscreen
				></iframe>
			</div>
			<a
				href={`https://www.youtube.com/watch?v=${s.id}`}
				target="_blank"
				rel="noopener"
				class="mt-2 inline-block text-sm text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
				>▶ Obre a YouTube ↗</a
			>

			{#if esAdmin}
				<div class="mt-4 flex gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
					<button
						class="flex-1 rounded-md px-3 py-2 text-sm font-medium {mark === true
							? 'bg-emerald-500 text-white'
							: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
						onclick={() => marca(true)}>✓ Funciona</button
					>
					<button
						class="flex-1 rounded-md px-3 py-2 text-sm font-medium {mark === false
							? 'bg-red-500 text-white'
							: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
						onclick={() => marca(false)}>✗ No funciona</button
					>
				</div>
			{/if}
		</div>

		<!-- Explicació -->
		<div>
			{#if s.explicacio}
				<section class="space-y-4">
					<div>
						<h2 class="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
							Què és
						</h2>
						<p class="text-slate-700 dark:text-slate-200">{s.explicacio.queEs}</p>
					</div>

					{#if s.explicacio.passos.length}
						<div>
							<h2 class="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
								Com s'aplica
							</h2>
							<ol class="list-decimal space-y-1 pl-5 text-slate-700 dark:text-slate-200">
								{#each s.explicacio.passos as p}
									<li>{p}</li>
								{/each}
							</ol>
						</div>
					{/if}

					{#if s.explicacio.quan}
						<div>
							<h2 class="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
								Quan fer-lo servir
							</h2>
							<p class="text-slate-700 dark:text-slate-200">{s.explicacio.quan}</p>
						</div>
					{/if}

					{#if s.explicacio.consells.length}
						<div>
							<h2 class="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
								Consells
							</h2>
							<ul class="space-y-1 text-slate-700 dark:text-slate-200">
								{#each s.explicacio.consells as c}
									<li class="flex gap-2"><span class="text-amber-500">•</span>{c}</li>
								{/each}
							</ul>
						</div>
					{/if}

					{#if s.font}
						<p class="text-xs italic text-slate-400 dark:text-slate-500">
							{FONT[s.font] ?? ''} Repassa el vídeo per als detalls.
						</p>
					{/if}
				</section>
			{:else}
				<p class="text-slate-600 dark:text-slate-300">{s.resum}</p>
				<p class="mt-3 text-sm italic text-slate-400 dark:text-slate-500">
					Encara no hi ha explicació de text detallada per a aquest sistema.
				</p>
			{/if}

			{#if s.transcripcio}
				<details class="mt-5 border-t border-slate-100 pt-3 dark:border-slate-800">
					<summary class="cursor-pointer text-sm text-slate-500 dark:text-slate-400">
						Transcripció original (coreà)
					</summary>
					<p class="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-500 dark:text-slate-400">
						{s.transcripcio}
					</p>
				</details>
			{/if}
		</div>
	</div>
{/if}
