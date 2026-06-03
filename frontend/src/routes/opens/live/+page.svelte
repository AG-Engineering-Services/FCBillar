<script lang="ts">
	import { api } from '$lib/opens/api';
	import type { LiveIndexEntry } from '$lib/opens/types';

	let entries = $state<LiveIndexEntry[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		api
			.listLiveCompetitions()
			.then((es) => (entries = es))
			.catch((e) => (error = e.message))
			.finally(() => (loading = false));
	});
</script>

<div class="mb-4">
	<h1 class="text-2xl font-semibold">Opens en curs</h1>
	<p class="mt-1 text-sm text-slate-500">
		Només Opens que la FCB encara no ha tancat (sense classificació final
		publicada). Clic per veure'n l'estat en directe.
	</p>
</div>

{#if loading}
	<p class="text-slate-500">Carregant llista…</p>
{:else if error}
	<div class="card border-red-200 bg-red-50 text-red-800">{error}</div>
{:else if entries.length === 0}
	<div class="card bg-slate-50 text-sm text-slate-600">
		Ara mateix no hi ha cap Open en curs segons la web de la FCB.
	</div>
{:else}
	<div class="grid gap-2 md:grid-cols-2">
		{#each entries as e (e.division_id)}
			<a
				href="/opens/live/{e.division_id}"
				class="card flex items-center justify-between p-3 transition-shadow hover:shadow-md"
			>
				<div>
					<span class="font-semibold">{e.name}</span>
				</div>
				<span class="font-mono text-xs text-slate-400">#{e.division_id}</span>
			</a>
		{/each}
	</div>
{/if}
