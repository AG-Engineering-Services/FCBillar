<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { Counts, RankingEntry } from '$lib/types';
	import StatCard from '$lib/components/StatCard.svelte';
	import Collapsible from '$lib/components/Collapsible.svelte';
	import SortableTable from '$lib/components/SortableTable.svelte';

	const columns = [
		{ key: 'posicio', label: '#', numeric: true, muted: true },
		{ key: 'nom', label: 'Jugador', link: (r: RankingEntry) => `/players/${r.fcb_id}` },
		{
			key: 'mitjana',
			label: 'Mitjana',
			numeric: true,
			fmt: (v: any) => (v != null ? v.toFixed(4) : '—')
		}
	];

	let stats: Counts | null = null;
	let top: RankingEntry[] = [];
	let loading = true;

	// Agrupa el top per modalitat.
	$: byMod = top.reduce<Record<string, RankingEntry[]>>((acc, e) => {
		(acc[e.modalitat] ??= []).push(e);
		return acc;
	}, {});

	onMount(async () => {
		try {
			stats = await api<Counts>('/api/stats');
			top = await api<RankingEntry[]>('/api/rankings/top?top_n=10');
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	});
</script>

<h1 class="text-2xl font-bold mb-4">Dashboard</h1>

{#if loading}
	<p class="text-slate-500">Carregant…</p>
{:else}
	<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
		<StatCard label="Clubs" value={stats?.clubs} />
		<StatCard label="Jugadors" value={stats?.players} />
		<StatCard label="Rànquings" value={stats?.rankings} />
		<StatCard label="Partides" value={stats?.games} />
		<StatCard label="Encontres lliga" value={stats?.encontres_lliga} />
		<StatCard label="Temporades" value={stats?.temporades} />
	</div>

	<h2 class="text-lg font-semibold mb-3">Top 10 per modalitat (rànquing actual)</h2>
	<div class="grid gap-4 lg:grid-cols-2">
		{#each Object.entries(byMod) as [mod, entries]}
			<Collapsible title={mod} open={true} count={entries.length}>
				<SortableTable {columns} rows={entries} />
			</Collapsible>
		{/each}
	</div>
{/if}
