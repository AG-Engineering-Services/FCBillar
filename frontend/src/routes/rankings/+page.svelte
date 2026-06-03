<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { Modalitat, RankingEntry } from '$lib/types';
	import SortableTable from '$lib/components/SortableTable.svelte';
	import Collapsible from '$lib/components/Collapsible.svelte';

	let modalitats: Modalitat[] = [];
	let selectedCodi: number | null = null;
	let snapshots: number[] = [];
	let selectedSeq: number | null = null;
	let ranking: RankingEntry[] = [];
	let loading = true;
	let loadingRanking = false;

	const columns = [
		{ key: 'posicio', label: '#', numeric: true },
		{ key: 'nom', label: 'Jugador', link: (r: RankingEntry) => '/players/' + r.fcb_id },
		{
			key: 'mitjana',
			label: 'MJ',
			numeric: true,
			fmt: (v: number | null) => (v != null ? v.toFixed(4) : '')
		},
		{
			key: 'mitjana_contraris',
			label: 'MR',
			numeric: true,
			fmt: (v: number | null) => (v != null ? v.toFixed(4) : '')
		},
		{ key: 'caramboles', label: 'C', numeric: true },
		{ key: 'entrades', label: 'E', numeric: true },
		{
			key: 'punts',
			label: 'P/PT',
			fmt: (_v: unknown, row: RankingEntry) =>
				row.punts != null && row.punts_totals != null
					? row.punts + '/' + row.punts_totals
					: '—'
		},
		{ key: 'definitiva', label: 'Def', fmt: (v: unknown) => (v ? 'Sí' : 'No') }
	];

	onMount(async () => {
		try {
			modalitats = await api<Modalitat[]>('/api/modalitats');
			if (modalitats.length > 0) {
				selectedCodi = modalitats[0].codi_fcb;
				await loadSnapshots();
			}
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	});

	async function loadSnapshots() {
		if (selectedCodi == null) return;
		try {
			snapshots = await api<number[]>(`/api/rankings/${selectedCodi}/snapshots`);
			selectedSeq = snapshots.length > 0 ? snapshots[0] : null;
			await loadRanking();
		} catch (e) {
			console.error(e);
			snapshots = [];
			selectedSeq = null;
			ranking = [];
		}
	}

	async function loadRanking() {
		if (selectedCodi == null || selectedSeq == null) return;
		loadingRanking = true;
		try {
			ranking = await api<RankingEntry[]>(
				`/api/rankings/${selectedCodi}?num_seq=${selectedSeq}`
			);
		} catch (e) {
			console.error(e);
			ranking = [];
		} finally {
			loadingRanking = false;
		}
	}

	async function onModalitatChange() {
		ranking = [];
		snapshots = [];
		selectedSeq = null;
		await loadSnapshots();
	}

	async function onSnapshotChange() {
		await loadRanking();
	}
</script>

<h1 class="text-2xl font-bold mb-4">Rànquings</h1>

{#if loading}
	<p class="text-slate-500">Carregant…</p>
{:else}
	<div class="flex flex-wrap items-center gap-3 mb-4">
		<label class="text-sm text-slate-600 font-medium" for="sel-modalitat">Modalitat</label>
		<select
			id="sel-modalitat"
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
			bind:value={selectedCodi}
			on:change={onModalitatChange}
		>
			{#each modalitats as m}
				<option value={m.codi_fcb}>{m.nom}</option>
			{/each}
		</select>

		{#if snapshots.length > 0}
			<label class="text-sm text-slate-600 font-medium" for="sel-snapshot">Instantània</label>
			<select
				id="sel-snapshot"
				class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
				bind:value={selectedSeq}
				on:change={onSnapshotChange}
			>
				{#each snapshots as seq}
					<option value={seq}>#{seq}</option>
				{/each}
			</select>
		{/if}
	</div>

	{#if loadingRanking}
		<p class="text-slate-500">Carregant…</p>
	{:else if ranking.length === 0}
		<p class="text-slate-500">Sense dades per a aquesta selecció.</p>
	{:else}
		<Collapsible title="Rànquing" open={true} count={ranking.length}>
			<SortableTable
				{columns}
				rows={ranking}
				initialSortKey="posicio"
				initialSortDir="asc"
				emptyText="Sense dades per a aquesta selecció."
			/>
		</Collapsible>
	{/if}
{/if}
