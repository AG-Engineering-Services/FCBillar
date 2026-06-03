<script lang="ts">
	import { api, importInscrits } from '$lib/opens/api';
	import type { ProjectionSummary, LiveIndexEntry } from '$lib/opens/types';

	let projections = $state<ProjectionSummary[]>([]);
	let live = $state<LiveIndexEntry[]>([]);
	let loadingProj = $state(true);
	let loadingLive = $state(true);
	let projError = $state<string | null>(null);
	let liveError = $state<string | null>(null);

	// Inscrits PDF upload (#8)
	let showUpload = $state(false);
	let upFile = $state<FileList | null>(null);
	let upName = $state('');
	let upSeason = $state('2025-2026');
	let uploading = $state(false);
	let upMsg = $state<string | null>(null);
	let upErr = $state<string | null>(null);

	function refreshProjections() {
		api.listProjections()
			.then((p) => (projections = p))
			.catch((e) => (projError = e.message));
	}

	async function doUpload() {
		const f = upFile?.[0];
		if (!f) return;
		uploading = true;
		upMsg = null;
		upErr = null;
		try {
			const r = await importInscrits(f, { name: upName, season: upSeason });
			upMsg = `Importat «${r.name}»: ${r.num_inscriptions} inscrits, ${r.n_linked} enllaçats.`;
			refreshProjections();
		} catch (e) {
			upErr = (e as Error).message;
		} finally {
			uploading = false;
		}
	}

	$effect(() => {
		api.listProjections()
			.then((p) => (projections = p))
			.catch((e) => (projError = e.message))
			.finally(() => (loadingProj = false));
		api.listLiveCompetitions()
			.then((l) => (live = l))
			.catch((e) => (liveError = e.message))
			.finally(() => (loadingLive = false));
	});
</script>

<div class="mb-6 flex items-end justify-between">
	<div>
		<h1 class="text-2xl font-semibold">Opens Tres Bandes</h1>
		<p class="text-sm text-slate-500">
			Seguiment d'opens: quadre projectat a partir dels inscrits i resultats en directe.
		</p>
	</div>
	<nav class="flex flex-wrap gap-2 text-sm">
		<button class="btn-secondary" onclick={() => (showUpload = !showUpload)}>+ Importar inscrits</button>
		<a href="/opens/ranking" class="btn-secondary">Rànquing d'opens</a>
		<a href="/opens/diff" class="btn-secondary">Diff oficial</a>
		<a href="/opens/historic" class="btn-secondary">Opens històrics</a>
		<a href="/opens/live" class="btn-secondary">Tots els directes</a>
	</nav>
</div>

{#if showUpload}
	<div class="card mb-6">
		<h2 class="mb-2 text-base font-semibold">Importar llistat d'inscrits (PDF)</h2>
		<p class="mb-3 text-sm text-slate-500">
			Puja el PDF «LLISTAT D'INSCRITS PER CLUBS» de la federació. Es calcularà el quadre
			projectat (sembrat + fases) i s'enllaçaran els jugadors a la seva fitxa.
		</p>
		<div class="flex flex-wrap items-end gap-3">
			<label class="text-sm">
				<span class="mb-1 block text-slate-600">PDF</span>
				<input type="file" accept="application/pdf,.pdf" bind:files={upFile} class="text-sm" />
			</label>
			<label class="text-sm">
				<span class="mb-1 block text-slate-600">Nom (opcional)</span>
				<input class="rounded-md border border-slate-300 px-3 py-1.5 text-sm" placeholder="del PDF" bind:value={upName} />
			</label>
			<label class="text-sm">
				<span class="mb-1 block text-slate-600">Temporada</span>
				<input class="w-28 rounded-md border border-slate-300 px-3 py-1.5 text-sm" bind:value={upSeason} />
			</label>
			<button class="btn-primary" onclick={doUpload} disabled={uploading || !upFile?.length}>
				{uploading ? 'Important…' : 'Importar i projectar'}
			</button>
		</div>
		{#if upMsg}<p class="mt-2 text-sm text-emerald-700">{upMsg}</p>{/if}
		{#if upErr}<p class="mt-2 text-sm text-red-700">{upErr}</p>{/if}
	</div>
{/if}

<!-- Quadre projectat (pre-publicació) -->
<section class="mb-8">
	<h2 class="mb-3 text-lg font-semibold">Quadre projectat (inscrits)</h2>
	{#if loadingProj}
		<p class="text-slate-500">Carregant…</p>
	{:else if projError}
		<div class="card border-red-200 bg-red-50 text-red-800">{projError}</div>
	{:else if projections.length === 0}
		<div class="card">
			<p class="text-sm text-slate-600">
				Cap quadre projectat encara. Importa el llistat d'inscrits (PDF) amb:
			</p>
			<pre class="mt-2 rounded bg-slate-50 p-3 text-xs"><code>uv run fcbillar open-import-inscrits "&lt;ruta&gt;.pdf" --season 2025-2026</code></pre>
		</div>
	{:else}
		<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each projections as p}
				<a href="/opens/projection/{p.id}" class="card transition-shadow hover:shadow-md">
					<div class="flex items-start justify-between gap-2">
						<h3 class="font-semibold">{p.name}</h3>
						<span class="badge-info shrink-0">Projecció</span>
					</div>
					<p class="mt-1 text-sm text-slate-500">{p.season ?? ''}</p>
					<p class="mt-2 text-sm text-slate-700">{p.num_inscriptions} inscrits</p>
					{#if p.fcb_division_id}
						<p class="mt-1 text-xs text-emerald-700">Publicat a la federació →</p>
					{/if}
				</a>
			{/each}
		</div>
	{/if}
</section>

<!-- En directe -->
<section>
	<h2 class="mb-3 text-lg font-semibold">En directe</h2>
	{#if loadingLive}
		<p class="text-slate-500">Carregant…</p>
	{:else if liveError}
		<div class="card border-amber-200 bg-amber-50 text-amber-800">
			No s'han pogut carregar els opens en directe: {liveError}
		</div>
	{:else if live.length === 0}
		<div class="card">
			<p class="text-sm text-slate-600">
				Ara mateix no hi ha cap Open en joc a la federació.
			</p>
		</div>
	{:else}
		<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each live as e}
				<a href="/opens/live/{e.division_id}" class="card transition-shadow hover:shadow-md">
					<div class="flex items-start justify-between gap-2">
						<h3 class="font-semibold">{e.name}</h3>
						<span class="badge-ok shrink-0">En directe</span>
					</div>
					<p class="mt-1 font-mono text-xs text-slate-500">#{e.division_id}</p>
				</a>
			{/each}
		</div>
	{/if}
</section>
