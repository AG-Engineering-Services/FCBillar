<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { PlayerKpi } from '$lib/types';
	import Card from '$lib/components/Card.svelte';

	let players: PlayerKpi[] = [];
	let loading = true;
	let q = '';

	onMount(async () => {
		try {
			players = await api<PlayerKpi[]>('/api/players?q=&limit=200');
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	});

	async function cercar() {
		loading = true;
		try {
			players = await api<PlayerKpi[]>(
				`/api/players?q=${encodeURIComponent(q)}&limit=500`
			);
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') cercar();
	}
</script>

<h1 class="text-2xl font-bold mb-4">Jugadors</h1>

<div class="flex items-center gap-2 mb-4">
	<input
		class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
		type="text"
		placeholder="Cerca per nom o ID…"
		bind:value={q}
		on:keydown={onKeydown}
	/>
	<button
		class="px-3 py-1.5 rounded-md bg-slate-900 text-white text-sm hover:bg-slate-700"
		on:click={cercar}
	>
		Cercar
	</button>
</div>

{#if loading}
	<p class="text-slate-500">Carregant…</p>
{:else}
	<p class="text-sm text-slate-500 mb-2">{players.length} jugadors</p>
	<Card>
		<table class="w-full text-sm">
			<thead class="bg-slate-50 text-slate-500 text-left">
				<tr>
					<th class="px-4 py-2 font-medium">ID FCB</th>
					<th class="px-4 py-2 font-medium">Jugador</th>
					<th class="px-4 py-2 font-medium">Club</th>
					<th class="px-4 py-2 font-medium text-right">Partides</th>
					<th class="px-4 py-2 font-medium">Seguit</th>
				</tr>
			</thead>
			<tbody>
				{#each players as p}
					<tr class="border-t border-slate-100 hover:bg-slate-50">
						<td class="px-4 py-2 text-slate-500 text-xs">{p.fcb_id}</td>
						<td class="px-4 py-2">
							<a class="hover:underline" href="/players/{p.fcb_id}">{p.nom}</a>
						</td>
						<td class="px-4 py-2 text-slate-600">{p.club ?? '—'}</td>
						<td class="px-4 py-2 text-right">{p.num_partides}</td>
						<td class="px-4 py-2">{p.seguiment ? '★' : ''}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</Card>
{/if}
