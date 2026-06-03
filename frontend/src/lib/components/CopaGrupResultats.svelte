<script lang="ts">
	import { api } from '$lib/api';
	import SortableTable from './SortableTable.svelte';
	import { createEventDispatcher, onMount } from 'svelte';

	// Identificació del grup de copa
	export let edicioId: number;
	export let jornada: number;
	export let grupId: number;
	export let grupNom: string;

	const dispatch = createEventDispatcher();

	let classificacio: any[] = [];
	let encontres: any[] = [];
	let loaded = false;
	let loading = false;

	const classColumns = [
		{ key: 'posicio', label: '#', numeric: true, muted: true },
		{ key: 'equip', label: 'Equip' },
		{ key: 'punts', label: 'Punts', numeric: true },
		{ key: 'parcials', label: 'Parcials', numeric: true, muted: true },
		{
			key: 'mitjana',
			label: 'Mitjana',
			numeric: true,
			fmt: (v: any) => (v != null ? v.toFixed(4) : '—')
		}
	];

	async function load() {
		if (loaded || loading) return;
		loading = true;
		try {
			const data: any = await api(
				`/api/results/copa/grup?edicio_id=${edicioId}&jornada=${jornada}&grup_id=${grupId}`
			);
			classificacio = data.classificacio ?? [];
			encontres = data.encontres ?? [];
			loaded = true;
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	}

	function resultClass(a: number | null, b: number | null, side: 'L' | 'V'): string {
		if (a == null || b == null || a === b) return 'text-slate-600';
		const wins = side === 'L' ? a > b : b > a;
		return wins ? 'font-semibold text-slate-900' : 'text-slate-400';
	}

	onMount(load);
</script>

<div class="bg-white rounded-lg border border-slate-200 overflow-hidden">
	<div class="px-4 py-3 border-b border-slate-200 font-semibold">{grupNom}</div>

	{#if loading && !loaded}
		<p class="text-slate-500 text-sm p-4">Carregant…</p>
	{:else}
		<!-- Classificació -->
		<SortableTable
			columns={classColumns}
			rows={classificacio}
			initialSortKey="posicio"
			initialSortDir="asc"
			emptyText="Sense classificació."
		/>

		<!-- Encontres -->
		<div class="border-t border-slate-200 p-3">
			<div class="text-xs uppercase tracking-wide text-slate-500 mb-1">Encontres</div>
			{#if encontres.length === 0}
				<p class="text-slate-400 text-sm">Sense encontres.</p>
			{:else}
				<div class="rounded-md border border-slate-100 divide-y divide-slate-100">
					{#each encontres as e}
						<button
							type="button"
							class="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-slate-50 text-left {e.n_partides
								? 'cursor-pointer'
								: 'cursor-default'}"
							on:click={() => e.n_partides && dispatch('encontre', e.encontre_copa_id)}
						>
							<span class="flex-1 text-right {resultClass(e.p_match_local, e.p_match_visitant, 'L')}"
								>{e.equip_local}</span
							>
							<span class="px-2 tabular-nums text-slate-700"
								>{e.p_match_local ?? '-'}–{e.p_match_visitant ?? '-'}</span
							>
							<span class="flex-1 {resultClass(e.p_match_local, e.p_match_visitant, 'V')}"
								>{e.equip_visitant}</span
							>
							{#if e.n_partides}
								<span class="text-slate-300 text-xs">›</span>
							{/if}
						</button>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>
