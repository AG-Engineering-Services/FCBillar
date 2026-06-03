<script lang="ts">
	import { api } from '$lib/opens/api';
	import type { OpensRankingResponse, OpensRankingRow } from '$lib/opens/types';

	let data = $state<OpensRankingResponse | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let search = $state('');

	async function load() {
		loading = true;
		error = null;
		try {
			data = await api.opensRanking(5);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		load();
	});

	const filtered = $derived.by<OpensRankingRow[]>(() => {
		if (!data) return [];
		const q = search.trim().toUpperCase();
		if (!q) return data.entries;
		return data.entries.filter(
			(e) =>
				e.display_name.toUpperCase().includes(q) ||
				(e.club ?? '').toUpperCase().includes(q)
		);
	});

	const opensColumns = $derived.by(() => {
		const entry = data?.entries[0];
		return entry?.breakdown ?? [];
	});
</script>

<h1 class="mb-2 text-2xl font-semibold">Rànquing Opens (calculat)</h1>
<p class="mb-6 text-sm text-slate-500">
	Suma de punts dels últims 5 Opens, segons l'Article XVIII del reglament FCB.
</p>

<div class="mb-4 flex flex-wrap items-center gap-4">
	<input
		type="text"
		bind:value={search}
		placeholder="Filtra per nom o club…"
		class="min-w-0 flex-1 rounded-md border-slate-300 text-sm"
	/>
</div>

{#if loading}
	<p class="text-slate-500">Carregant…</p>
{:else if error}
	<div class="card border-red-200 bg-red-50 text-red-800">{error}</div>
{:else if data && data.entries.length === 0}
	<div class="card">
		<p class="text-sm text-slate-600">
			No hi ha Opens suficients per calcular un rànquing. Importa'n amb:
		</p>
		<pre class="mt-2 rounded bg-slate-50 p-3 text-xs"><code>fcb-opens scrape-open 204 439 --season 2025-26</code></pre>
	</div>
{:else if data}
	<p class="mb-3 text-xs text-slate-500">
		Opens a la finestra: {data.opens_in_window} · Jugadors puntuats: {data.entries.length}
	</p>
	<div class="card p-0">
		<table class="table-clean">
			<thead>
				<tr>
					<th class="w-14">#</th>
					<th>Jugador</th>
					<th>Club</th>
					{#each opensColumns as open (open.open_id)}
						<th class="text-right" title={`${open.name} (${open.season})`}>
							{open.name}
						</th>
					{/each}
					<th class="text-right">Total</th>
				</tr>
			</thead>
			<tbody>
				{#each filtered as row (row.player_id)}
					<tr>
						<td class="font-mono text-slate-500">{row.rank}</td>
						<td>
							<a href="/players/{row.player_id}" class="hover:underline">
								{row.display_name}
							</a>
						</td>
						<td class="text-slate-600">{row.club ?? ''}</td>
						{#each row.breakdown as open (open.open_id)}
							<td class="text-right font-mono text-slate-500">
								{open.points ?? '-'}
							</td>
						{/each}
						<td class="text-right font-mono font-semibold">{row.total_points}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
