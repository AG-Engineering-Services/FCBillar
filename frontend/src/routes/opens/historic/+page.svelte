<script lang="ts">
	import { api } from '$lib/opens/api';
	import type { OpenSummary } from '$lib/opens/types';

	let opens = $state<OpenSummary[]>([]);
	let error = $state<string | null>(null);
	let loading = $state(true);

	$effect(() => {
		api.listOpens()
			.then((o) => (opens = o))
			.catch((e) => (error = e.message))
			.finally(() => (loading = false));
	});
</script>

<h1 class="mb-6 text-2xl font-semibold">Opens emmagatzemats</h1>

{#if loading}
	<p class="text-slate-500">Carregant…</p>
{:else if error}
	<div class="card border-red-200 bg-red-50 text-red-800">{error}</div>
{:else if opens.length === 0}
	<div class="card">
		<p class="text-sm text-slate-600">
			Cap Open emmagatzemat. Importa'n un amb:
		</p>
		<pre class="mt-2 rounded bg-slate-50 p-3 text-xs"><code>fcb-opens scrape-open 204 439 --season 2025-26</code></pre>
	</div>
{:else}
	<div class="card p-0">
		<table class="table-clean">
			<thead>
				<tr>
					<th>Nom</th>
					<th>Temporada</th>
					<th class="text-right">Div. FCB</th>
					<th class="text-right">Jugadors</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{#each opens as op}
					<tr>
						<td class="font-medium">{op.name}</td>
						<td class="text-slate-600">{op.season || '—'}</td>
						<td class="text-right font-mono text-slate-500">#{op.fcb_division_id}</td>
						<td class="text-right font-mono">{op.player_count}</td>
						<td class="text-right">
							<a href="/opens/{op.id}" class="text-sm hover:underline">Veure →</a>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
