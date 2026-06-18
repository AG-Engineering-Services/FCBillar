<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, tipusOf, type Open } from '$lib/supabase';

	let opens = $state<Open[]>([]);
	let q = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);

	function norm(s: string): string {
		return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}
	// Tipus de torneig: prioritza el camp publicat; fallback a la regla compartida
	// (tipusOf de $lib/supabase, mirall de fcbillar.torneig_naming).
	const clean = (nom: string) => nom.replace(/\s*-\s*[ÚU]NICA\s*$/i, '').trim();

	// La modalitat no és una columna: es dedueix del nom (prefix abans del " - " o
	// paraula clau). Ordre canònic de modalitats del billar català.
	const MOD_ORDER = ['Lliure', 'Banda', 'Quadre 47/2', 'Quadre 71/2', 'Tres Bandes', '5 Quilles', 'Artístic', 'Snooker'];
	function modalitat(nom: string): string {
		const u = norm(nom);
		if (u.includes('quadre 47')) return 'Quadre 47/2';
		if (u.includes('quadre 71')) return 'Quadre 71/2';
		if (u.includes('tres bandes')) return 'Tres Bandes';
		if (u.includes('banda')) return 'Banda';
		if (u.includes('lliure')) return 'Lliure';
		if (u.includes('quilles')) return '5 Quilles';
		if (u.includes('artistic')) return 'Artístic';
		if (u.includes('snooker')) return 'Snooker';
		return 'Altres';
	}
	function modRank(nom: string): number {
		const i = MOD_ORDER.indexOf(modalitat(nom));
		return i < 0 ? 99 : i;
	}

	onMount(async () => {
		try {
			const { data, error: e } = await supabase.from('opens').select('*').order('nom');
			if (e) throw e;
			opens = (data ?? []) as Open[];
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	// Campionats agrupats per temporada (més recent primer) i, dins de cada
	// temporada, ordenats per modalitat (i categoria com a desempat).
	const groups = $derived.by(() => {
		const list = opens
			.filter((o) => tipusOf(o) === 'campionat')
			.filter((o) => (q.trim() ? norm(o.nom).includes(norm(q.trim())) : true));
		const sorted = [...list].sort(
			(a, b) =>
				(b.temporada ?? '').localeCompare(a.temporada ?? '') ||
				modRank(a.nom) - modRank(b.nom) ||
				a.nom.localeCompare(b.nom, 'ca')
		);
		const out: { temporada: string; items: Open[] }[] = [];
		for (const o of sorted) {
			const t = o.temporada ?? '—';
			let g = out[out.length - 1];
			if (!g || g.temporada !== t) {
				g = { temporada: t, items: [] };
				out.push(g);
			}
			g.items.push(o);
		}
		return out;
	});
	const total = $derived(groups.reduce((n, g) => n + g.items.length, 0));
</script>

<h1 class="mb-3 text-lg font-bold">Campionats de Catalunya</h1>

<input
	bind:value={q}
	inputmode="search"
	placeholder="Cerca…"
	class="mb-3 w-full rounded-lg border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-2.5 px-3 text-sm shadow-sm"
/>

{#if error}
	<div class="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-300">{error}</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
{:else if total === 0}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Cap campionat.</p>
{:else}
	{#each groups as g (g.temporada)}
		<section class="mb-4">
			<h2 class="mb-1.5 px-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
				Temporada {g.temporada}
			</h2>
			<ul class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
				{#each g.items as o (o.open_id)}
					<li class="border-b border-slate-100 dark:border-slate-800 last:border-0">
						<a href="/opens/{o.open_id}" class="flex items-center gap-3 px-3 py-2.5 active:bg-slate-50 dark:active:bg-slate-800/50">
							<div class="min-w-0 flex-1 truncate text-sm font-medium leading-tight">{clean(o.nom)}</div>
							<span class="shrink-0 text-slate-300 dark:text-slate-600">›</span>
						</a>
					</li>
				{/each}
			</ul>
		</section>
	{/each}
	<p class="px-1 py-3 text-center text-[11px] text-slate-400 dark:text-slate-500">{total} campionats</p>
{/if}
