<script lang="ts">
	import sistemes from '$lib/sistemes/sistemes.json';
	import { supabase } from '$lib/supabase';
	import { onMount } from 'svelte';

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
	}
	const totsSistemes = sistemes as Sistema[];

	const ORDRE = [
		'Bricol (bandes)',
		'Natural (sense efecte)',
		'Rotació',
		'Posició i patrons',
		'Tècnica bàsica',
		'Altres'
	];

	// Filtre per categoria (null = totes)
	let categoriaActiva = $state<string | null>(null);
	// Marks funciona/no-funciona (video_id → true | false | null), compartits via Supabase.
	let marks = $state<Record<string, boolean | null>>({});
	let esAdmin = $state(false);
	let nomesFunciona = $state(false);

	const categories = $derived([...new Set(totsSistemes.map((s) => s.categoria))].sort(
		(a, b) => ORDRE.indexOf(a) - ORDRE.indexOf(b)
	));

	const visibles = $derived(
		totsSistemes
			.filter((s) => (categoriaActiva ? s.categoria === categoriaActiva : true))
			.filter((s) => (nomesFunciona ? marks[s.id] === true : true))
			.sort((a, b) => b.visites - a.visites)
	);
	const grups = $derived(
		categories
			.map((cat) => ({ cat, items: visibles.filter((s) => s.categoria === cat) }))
			.filter((g) => g.items.length)
	);

	onMount(async () => {
		esAdmin = typeof localStorage !== 'undefined' && localStorage.getItem('fcb_admin') === '1';
		try {
			const { data } = await supabase.from('sistema_marca').select('video_id, funciona');
			if (data) marks = Object.fromEntries(data.map((r) => [r.video_id, r.funciona]));
		} catch {
			// la taula pot no existir encara; els marks queden buits
		}
	});

	async function marca(id: string, valor: boolean) {
		const nou = marks[id] === valor ? null : valor; // tornar a clicar treu la marca
		marks = { ...marks, [id]: nou };
		try {
			await supabase
				.from('sistema_marca')
				.upsert({ video_id: id, funciona: nou, updated_at: new Date().toISOString() });
		} catch {
			// sense taula encara: es manté només a la vista
		}
	}

	const fmt = (n: number) =>
		n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : String(n);
	const yt = (id: string) => `https://www.youtube.com/watch?v=${id}`;
</script>

<div class="mb-4">
	<h1 class="text-xl font-bold md:text-2xl">Sistemes Coreans</h1>
	<p class="text-sm text-slate-500 dark:text-slate-400">
		Sistemes i patrons de billar a tres bandes de canals coreans de YouTube, catalogats per tipus i
		ordenats per visites.
	</p>
</div>

<!-- Filtres -->
<div class="mb-4 flex flex-wrap items-center gap-2">
	<button
		class="rounded-full px-3 py-1 text-sm {categoriaActiva === null
			? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
			: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
		onclick={() => (categoriaActiva = null)}>Totes</button
	>
	{#each categories as cat (cat)}
		<button
			class="rounded-full px-3 py-1 text-sm {categoriaActiva === cat
				? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
				: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
			onclick={() => (categoriaActiva = cat)}>{cat}</button
		>
	{/each}
	<label class="ml-auto flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
		<input type="checkbox" bind:checked={nomesFunciona} class="accent-emerald-500" />
		Només els que funcionen
	</label>
</div>

{#each grups as g (g.cat)}
	<section class="mb-6">
		<h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
			{g.cat} <span class="font-normal">· {g.items.length}</span>
		</h2>
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each g.items as s (s.id)}
				<div
					class="flex flex-col overflow-hidden rounded-xl border {marks[s.id] === true
						? 'border-emerald-400 dark:border-emerald-600'
						: marks[s.id] === false
							? 'border-red-300 dark:border-red-800'
							: 'border-slate-200 dark:border-slate-800'} bg-white dark:bg-slate-900"
				>
					<a href={yt(s.id)} target="_blank" rel="noopener" class="relative block">
						<img src={s.miniatura} alt={s.nom} class="aspect-video w-full object-cover" loading="lazy" />
						<span
							class="absolute bottom-1 right-1 rounded bg-black/70 px-1.5 py-0.5 text-xs text-white"
							>▶ {fmt(s.visites)}</span
						>
						{#if marks[s.id] === true}
							<span class="absolute left-1 top-1 rounded bg-emerald-500 px-1.5 py-0.5 text-xs font-semibold text-white">✓ funciona</span>
						{:else if marks[s.id] === false}
							<span class="absolute left-1 top-1 rounded bg-red-500 px-1.5 py-0.5 text-xs font-semibold text-white">✗ no funciona</span>
						{/if}
					</a>
					<div class="flex flex-1 flex-col gap-1 p-3">
						<a href={yt(s.id)} target="_blank" rel="noopener" class="font-semibold leading-tight hover:underline">{s.nom}</a>
						<div class="text-xs text-slate-500 dark:text-slate-400">{s.canal}</div>
						{#if s.resum}
							<p class="mt-1 text-sm text-slate-600 dark:text-slate-300">{s.resum}</p>
						{/if}
						{#if esAdmin}
							<div class="mt-2 flex gap-2 border-t border-slate-100 pt-2 dark:border-slate-800">
								<button
									class="flex-1 rounded-md px-2 py-1 text-xs font-medium {marks[s.id] === true
										? 'bg-emerald-500 text-white'
										: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
									onclick={() => marca(s.id, true)}>✓ Funciona</button
								>
								<button
									class="flex-1 rounded-md px-2 py-1 text-xs font-medium {marks[s.id] === false
										? 'bg-red-500 text-white'
										: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
									onclick={() => marca(s.id, false)}>✗ No funciona</button
								>
							</div>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	</section>
{/each}

{#if !grups.length}
	<p class="py-8 text-center text-slate-500 dark:text-slate-400">Cap sistema amb aquests filtres.</p>
{/if}
