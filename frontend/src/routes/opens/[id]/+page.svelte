<script lang="ts">
	import { api, resolvePlayers } from '$lib/opens/api';
	import { page } from '$app/stores';
	import BackButton from '$lib/components/BackButton.svelte';
	import type { OpenDetail } from '$lib/opens/types';

	let detail = $state<OpenDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let fcbMap = $state<Record<string, string | null>>({});

	$effect(() => {
		const id = Number($page.params.id);
		if (!Number.isFinite(id)) {
			error = 'id invàlid';
			loading = false;
			return;
		}
		api.getOpen(id)
			.then(async (d) => {
				detail = d;
				fcbMap = await resolvePlayers(d.classification.map((r) => r.player_name));
			})
			.catch((e) => (error = e.message))
			.finally(() => (loading = false));
	});

	// Link to the existing FCBillar player profile, or a name-prefilled search.
	function playerHref(name: string): string {
		const id = fcbMap[name];
		return id ? `/players/${encodeURIComponent(id)}` : `/players?q=${encodeURIComponent(name)}`;
	}
</script>

{#if loading}
	<p class="text-slate-500">Carregant…</p>
{:else if error}
	<div class="card border-red-200 bg-red-50 text-red-800">{error}</div>
{:else if detail}
	<div class="mb-6 flex items-baseline justify-between">
		<div>
			<h1 class="text-2xl font-semibold">{detail.name}</h1>
			<p class="mt-1 text-sm text-slate-500">
				{detail.season || 'temporada desconeguda'} · FCB #{detail.fcb_division_id}
				{#if detail.fcb_classification_id}
					· classif. #{detail.fcb_classification_id}
				{/if}
			</p>
		</div>
		<BackButton fallback="/opens" />
	</div>

	<div class="card p-0">
		<table class="table-clean">
			<thead>
				<tr>
					<th class="w-14">#</th>
					<th>Jugador</th>
					<th>Club</th>
					<th class="text-right">PJ</th>
					<th class="text-right">MG</th>
					<th class="text-right">SM</th>
					<th class="text-right">Punts Open</th>
				</tr>
			</thead>
			<tbody>
				{#each detail.classification as row (row.player_id + '-' + row.position)}
					<tr>
						<td class="font-mono text-slate-500">{row.position}</td>
						<td>
							<a href={playerHref(row.player_name)} class="hover:underline">
								{row.player_name}
							</a>
						</td>
						<td class="text-slate-600">{row.club ?? ''}</td>
						<td class="text-right font-mono">{row.matches_played}</td>
						<td class="text-right font-mono">{row.general_average.toFixed(3)}</td>
						<td class="text-right font-mono text-slate-500">{row.best_series}</td>
						<td class="text-right font-mono font-semibold">{row.open_points}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
