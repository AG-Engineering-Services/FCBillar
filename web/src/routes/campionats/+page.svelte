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

	const filtered = $derived(
		opens
			.filter((o) => tipusOf(o) === 'campionat')
			.filter((o) => (q.trim() ? norm(o.nom).includes(norm(q.trim())) : true))
	);
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
{:else if filtered.length === 0}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Cap campionat.</p>
{:else}
	<ul class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
		{#each filtered as o (o.open_id)}
			<li class="border-b border-slate-100 dark:border-slate-800 last:border-0">
				<a href="/opens/{o.open_id}" class="flex items-center gap-3 px-3 py-2.5 active:bg-slate-50 dark:active:bg-slate-800/50">
					<div class="min-w-0 flex-1 truncate text-sm font-medium leading-tight">{clean(o.nom)}</div>
					<span class="shrink-0 text-slate-300 dark:text-slate-600">›</span>
				</a>
			</li>
		{/each}
	</ul>
	<p class="px-1 py-3 text-center text-[11px] text-slate-400 dark:text-slate-500">{filtered.length} campionats</p>
{/if}
