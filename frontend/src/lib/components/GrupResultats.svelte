<script lang="ts">
	import { api } from '$lib/api';
	import Collapsible from './Collapsible.svelte';
	import SortableTable from './SortableTable.svelte';
	import { fmtDate } from '$lib/format';
	import { createEventDispatcher } from 'svelte';

	// Identificació del grup
	export let lligaId: number;
	export let divisioId: number;
	export let grupId: number;
	export let nom: string;
	export let standings: any[] = [];
	export let standingColumns: any[];

	const dispatch = createEventDispatcher();

	let jornades: any[] = [];
	let loaded = false;
	let loading = false;
	let jornadesOpen = false;
	let jornadaIndex = 0;

	// Carrega automàticament en obrir el desplegable.
	$: if (jornadesOpen && !loaded && !loading) loadJornades();

	async function loadJornades() {
		if (loaded || loading) return;
		loading = true;
		try {
			jornades = await api(
				`/api/results/lliga/jornades?lliga_id=${lligaId}&divisio_id=${divisioId}&grup_id=${grupId}`
			);
			loaded = true;
			jornadaIndex = lastPlayedIndex(jornades);
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	}

	// Darrera jornada amb algun resultat introduït; si no n'hi ha cap, l'última.
	function lastPlayedIndex(js: any[]): number {
		for (let i = js.length - 1; i >= 0; i--) {
			if (js[i].encontres?.some((e: any) => e.p_match_local != null || e.p_match_visitant != null))
				return i;
		}
		return Math.max(0, js.length - 1);
	}

	function prev() {
		jornadaIndex = Math.max(0, jornadaIndex - 1);
	}
	function next() {
		jornadaIndex = Math.min(jornades.length - 1, jornadaIndex + 1);
	}

	function resultClass(a: number | null, b: number | null, side: 'L' | 'V'): string {
		if (a == null || b == null || a === b) return 'text-slate-600';
		const wins = side === 'L' ? a > b : b > a;
		return wins ? 'font-semibold text-slate-900' : 'text-slate-400';
	}

	$: jornada = jornades[jornadaIndex];
</script>

<div class="bg-white rounded-lg border border-slate-200 overflow-hidden">
	<div class="px-4 py-3 border-b border-slate-200 font-semibold">{nom}</div>

	<!-- Classificació -->
	<SortableTable columns={standingColumns} rows={standings} initialSortKey="posicio" initialSortDir="asc" />

	<!-- Jornades (desplegable, càrrega automàtica en obrir; slider per navegar) -->
	<div class="border-t border-slate-200">
		<Collapsible title="Jornades i encontres" bind:open={jornadesOpen}>
			<div class="p-3">
				{#if loading}
					<p class="text-slate-400 text-sm">Carregant…</p>
				{:else if jornades.length === 0}
					<p class="text-slate-400 text-sm">Sense jornades.</p>
				{:else}
					<!-- Navegador de jornades -->
					<div class="flex items-center gap-3 mb-3">
						<button
							type="button"
							class="px-2 py-0.5 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-transparent"
							on:click={prev}
							disabled={jornadaIndex === 0}
							aria-label="Jornada anterior">‹</button
						>
						<input
							type="range"
							min="0"
							max={jornades.length - 1}
							bind:value={jornadaIndex}
							class="flex-1 accent-slate-700"
						/>
						<button
							type="button"
							class="px-2 py-0.5 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-transparent"
							on:click={next}
							disabled={jornadaIndex === jornades.length - 1}
							aria-label="Jornada següent">›</button
						>
					</div>

					{#if jornada}
						<div class="text-xs uppercase tracking-wide text-slate-500 mb-2">
							Jornada {jornadaIndex + 1} / {jornades.length} · {fmtDate(jornada.data)}
						</div>
						<div class="rounded-md border border-slate-100 divide-y divide-slate-100">
							{#each jornada.encontres as e}
								<button
									type="button"
									class="w-full flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-slate-50 text-left {e.n_partides
										? 'cursor-pointer'
										: 'cursor-default'}"
									on:click={() => e.n_partides && dispatch('encontre', e.encontre_id)}
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
				{/if}
			</div>
		</Collapsible>
	</div>
</div>
