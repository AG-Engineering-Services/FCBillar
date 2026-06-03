<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { Modalitat, PlayerKpi } from '$lib/types';
	import LineChart from '$lib/components/LineChart.svelte';
	import Card from '$lib/components/Card.svelte';

	interface HistoryPoint {
		num_seq: number;
		mitjana: number | null;
		posicio: number | null;
	}
	interface Selected {
		fcb_id: string;
		nom: string;
		history: HistoryPoint[];
	}

	let modalitats: Modalitat[] = [];
	let selectedMod = 1;
	let metric: 'mitjana' | 'posicio' = 'mitjana';

	// Cerca de jugadors
	let query = '';
	let results: PlayerKpi[] = [];
	let searching = false;

	// Jugadors seleccionats per comparar
	let selected: Selected[] = [];

	async function search() {
		const q = query.trim();
		if (!q) {
			results = [];
			return;
		}
		searching = true;
		try {
			results = await api<PlayerKpi[]>(`/api/players?q=${encodeURIComponent(q)}&limit=30`);
		} catch (e) {
			console.error(e);
		} finally {
			searching = false;
		}
	}

	async function addPlayer(p: PlayerKpi) {
		if (selected.some((s) => s.fcb_id === p.fcb_id)) return;
		const history = await loadHistory(p.fcb_id);
		selected = [...selected, { fcb_id: p.fcb_id, nom: p.nom, history }];
		query = '';
		results = [];
	}

	function removePlayer(fcb_id: string) {
		selected = selected.filter((s) => s.fcb_id !== fcb_id);
	}

	async function loadHistory(fcb_id: string): Promise<HistoryPoint[]> {
		try {
			return await api<HistoryPoint[]>(
				`/api/players/${fcb_id}/ranking-history?modalitat=${selectedMod}`
			);
		} catch (e) {
			console.error(e);
			return [];
		}
	}

	// En canviar de modalitat, recarrega l'historial de tots els seleccionats.
	async function onModChange() {
		selected = await Promise.all(
			selected.map(async (s) => ({ ...s, history: await loadHistory(s.fcb_id) }))
		);
	}

	// Eix X unificat: tots els num_seq que apareixen en algun jugador, ordenats.
	$: allSeqs = Array.from(
		new Set(selected.flatMap((s) => s.history.map((h) => h.num_seq)))
	).sort((a, b) => a - b);

	$: labels = allSeqs.map(String);

	$: chartSeries = selected.map((s) => {
		const bySeq = new Map(s.history.map((h) => [h.num_seq, h[metric]]));
		return { label: s.nom, data: allSeqs.map((seq) => bySeq.get(seq) ?? null) };
	});

	onMount(async () => {
		modalitats = await api<Modalitat[]>('/api/modalitats').catch(() => []);
		if (modalitats.length) selectedMod = modalitats[0].codi_fcb;
	});

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Enter') search();
	}
</script>

<h1 class="text-2xl font-bold mb-4">Comparar jugadors</h1>

<!-- Controls -->
<div class="flex flex-wrap gap-3 items-end mb-4">
	<div class="flex flex-col gap-1">
		<label class="text-xs text-slate-500 font-medium" for="cmp-mod">Modalitat</label>
		<select
			id="cmp-mod"
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
			bind:value={selectedMod}
			on:change={onModChange}
		>
			{#each modalitats as m}
				<option value={m.codi_fcb}>{m.nom}</option>
			{/each}
		</select>
	</div>

	<div class="flex flex-col gap-1">
		<span class="text-xs text-slate-500 font-medium">Mètrica</span>
		<div class="flex gap-1">
			<button
				class="px-3 py-1.5 rounded-md text-sm {metric === 'mitjana'
					? 'bg-slate-900 text-white'
					: 'text-slate-600 hover:bg-slate-100 border border-slate-300'}"
				on:click={() => (metric = 'mitjana')}>Mitjana</button
			>
			<button
				class="px-3 py-1.5 rounded-md text-sm {metric === 'posicio'
					? 'bg-slate-900 text-white'
					: 'text-slate-600 hover:bg-slate-100 border border-slate-300'}"
				on:click={() => (metric = 'posicio')}>Posició</button
			>
		</div>
	</div>

	<div class="flex flex-col gap-1 flex-1 min-w-[220px]">
		<label class="text-xs text-slate-500 font-medium" for="cmp-q">Afegir jugador</label>
		<div class="flex gap-2">
			<input
				id="cmp-q"
				type="text"
				bind:value={query}
				on:keydown={handleKey}
				placeholder="Nom o fcb_id…"
				class="border border-slate-300 rounded-md px-3 py-1.5 text-sm flex-1"
			/>
			<button
				class="px-3 py-1.5 rounded-md bg-slate-900 text-white text-sm hover:bg-slate-700"
				on:click={search}>Cerca</button
			>
		</div>
	</div>
</div>

<!-- Resultats de cerca -->
{#if results.length}
	<Card>
		<div class="max-h-56 overflow-y-auto">
			<table class="w-full text-sm">
				<tbody>
					{#each results as p}
						<tr class="border-t border-slate-100 hover:bg-slate-50">
							<td class="px-3 py-2 text-slate-500 text-xs">{p.fcb_id}</td>
							<td class="px-3 py-2">{p.nom}</td>
							<td class="px-3 py-2 text-slate-500">{p.club ?? ''}</td>
							<td class="px-3 py-2 text-right">
								<button
									class="px-2 py-0.5 rounded-md bg-slate-900 text-white text-xs hover:bg-slate-700 disabled:opacity-40"
									disabled={selected.some((s) => s.fcb_id === p.fcb_id)}
									on:click={() => addPlayer(p)}>+ Afegeix</button
								>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</Card>
{:else if searching}
	<p class="text-slate-500 text-sm mb-3">Cercant…</p>
{/if}

<!-- Chips de seleccionats -->
{#if selected.length}
	<div class="flex flex-wrap gap-2 my-4">
		{#each selected as s}
			<span class="inline-flex items-center gap-2 bg-slate-100 rounded-full px-3 py-1 text-sm">
				{s.nom}
				<button
					class="text-slate-400 hover:text-slate-700"
					on:click={() => removePlayer(s.fcb_id)}
					aria-label="Treu">×</button
				>
			</span>
		{/each}
	</div>
{/if}

<!-- Gràfic -->
{#if selected.length === 0}
	<p class="text-slate-500">Afegeix jugadors per comparar la seva evolució al rànquing.</p>
{:else if allSeqs.length === 0}
	<p class="text-slate-500">Cap dada de rànquing per a aquesta modalitat.</p>
{:else}
	<Card>
		<div class="p-4">
			<LineChart
				{labels}
				series={chartSeries}
				yTitle={metric === 'mitjana' ? 'Mitjana' : 'Posició'}
				invertY={metric === 'posicio'}
				integerY={metric === 'posicio'}
				height={460}
			/>
		</div>
	</Card>
{/if}
