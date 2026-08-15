<script lang="ts">
	import sistemes from '$lib/sistemes/sistemes.json';
	import { db } from '$lib/db';
	import { onMount } from 'svelte';
	import Explora from '$lib/sistemes/Explora.svelte';

	// mode 'pendents' = encara no validats (per curar) · 'validats' = marcats com que funcionen
	let { mode }: { mode: 'pendents' | 'validats' } = $props();

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
		explicacio?: { nivell: string } | null;
	}
	const totsSistemes = sistemes as Sistema[];

	const ORDRE = [
		'Endavant',
		'Endarrere',
		'De costat',
		'Tocar la bola fina',
		'Gran rotació',
		'Bricol',
		'Doble banda',
		'Travessa',
		'Sense efecte',
		'Sistemes de càlcul',
		'Tècnica bàsica',
		'Altres'
	];

	let categoriaActiva = $state<string | null>(null);
	// Marks funciona/no-funciona (video_id → true | false | null), compartits via Supabase.
	let marks = $state<Record<string, boolean | null>>({});
	let esAdmin = $state(false);
	let carregat = $state(false);

	// Predicat de pertinença a aquesta pestanya segons el mark.
	function pertany(id: string): boolean {
		return mode === 'validats' ? marks[id] === true : marks[id] !== true;
	}

	const totsAmbFiltre = $derived(
		totsSistemes
			.filter((s) => pertany(s.id))
			.filter((s) => (categoriaActiva ? s.categoria === categoriaActiva : true))
			.sort((a, b) => b.visites - a.visites)
	);
	// Categories que tenen algun element EN AQUESTA pestanya (per als xips de filtre).
	const categories = $derived(
		[...new Set(totsSistemes.filter((s) => pertany(s.id)).map((s) => s.categoria))].sort(
			(a, b) => ORDRE.indexOf(a) - ORDRE.indexOf(b)
		)
	);
	const grups = $derived(
		categories
			.map((cat) => ({ cat, items: totsAmbFiltre.filter((s) => s.categoria === cat) }))
			.filter((g) => g.items.length)
	);
	const total = $derived(totsSistemes.filter((s) => pertany(s.id)).length);

	onMount(async () => {
		esAdmin = typeof localStorage !== 'undefined' && localStorage.getItem('fcb_admin') === '1';
		try {
			const { data } = await db.from('sistema_marca').select('video_id, funciona');
			if (data) marks = Object.fromEntries(data.map((r) => [r.video_id, r.funciona]));
		} catch {
			// la taula pot no existir encara; els marks queden buits
		}
		carregat = true;
	});

	async function marca(id: string, valor: boolean) {
		const nou = marks[id] === valor ? null : valor; // tornar a clicar treu la marca
		marks = { ...marks, [id]: nou };
		try {
			await db
				.from('sistema_marca')
				.upsert({ video_id: id, funciona: nou, updated_at: new Date().toISOString() });
		} catch {
			// sense taula encara: es manté només a la vista
		}
	}

	const fmt = (n: number) =>
		n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : String(n);
	const detall = (id: string) => `/sistemes-coreans/${id}`;
</script>

<div class="mb-4">
	<h1 class="text-xl font-bold md:text-2xl">
		{mode === 'validats' ? 'Sistemes Validats' : 'Sistemes Coreans'}
	</h1>
	<p class="text-sm text-slate-500 dark:text-slate-400">
		{#if mode === 'validats'}
			Sistemes coreans que has provat i validat com que funcionen a la taula.
		{:else}
			Sistemes i patrons de billar a tres bandes de canals coreans de YouTube, pendents de validar.
			Obre'n un per llegir-ne l'explicació en català.
		{/if}
	</p>
</div>

{#if mode === 'pendents' && esAdmin}
	<Explora />
{/if}

<!-- Filtres per categoria -->
{#if categories.length > 1}
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
	</div>
{/if}

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
					<a href={detall(s.id)} class="relative block">
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
						<a href={detall(s.id)} class="font-semibold leading-tight hover:underline">{s.nom}</a>
						<div class="text-xs text-slate-500 dark:text-slate-400">{s.canal}</div>
						{#if s.resum}
							<p class="mt-1 text-sm text-slate-600 dark:text-slate-300">{s.resum}</p>
						{/if}
						<a
							href={detall(s.id)}
							class="mt-1 inline-block text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
							>{s.explicacio ? '📖 Llegir explicació →' : 'Veure detall →'}</a
						>
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

{#if !total}
	<div class="py-10 text-center text-slate-500 dark:text-slate-400">
		{#if mode === 'validats'}
			<p>Encara no has validat cap sistema.</p>
			<p class="mt-1 text-sm">
				Ves a <a href="/sistemes-coreans" class="text-indigo-600 hover:underline dark:text-indigo-400"
					>Sistemes Coreans</a
				> i marca'n algun com a «✓ Funciona».
			</p>
		{:else}
			<p>Cap sistema pendent amb aquests filtres.</p>
		{/if}
	</div>
{/if}
