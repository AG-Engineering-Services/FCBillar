<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type Open } from '$lib/supabase';

	let opens = $state<Open[]>([]);
	let q = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);

	function norm(s: string): string {
		return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
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

	const filtered = $derived(
		q.trim() ? opens.filter((o) => norm(o.nom).includes(norm(q.trim()))) : opens
	);
</script>

<input
	bind:value={q}
	inputmode="search"
	placeholder="Cerca open…"
	class="mb-3 w-full rounded-lg border-slate-300 bg-white py-2.5 px-3 text-sm shadow-sm"
/>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if filtered.length === 0}
	<p class="py-6 text-center text-sm text-slate-400">Cap open.</p>
{:else}
	<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
		{#each filtered as o (o.open_id)}
			<li class="border-b border-slate-100 last:border-0">
				<a href="/opens/{o.open_id}" class="flex items-center gap-3 px-3 py-2.5 active:bg-slate-50">
					<div class="min-w-0 flex-1 truncate text-sm font-medium leading-tight">{o.nom}</div>
					<span class="shrink-0 text-slate-300">›</span>
				</a>
			</li>
		{/each}
	</ul>
	<p class="px-1 py-3 text-center text-[11px] text-slate-400">{filtered.length} opens</p>
{/if}
