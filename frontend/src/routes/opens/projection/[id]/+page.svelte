<script lang="ts">
	import { page } from '$app/stores';
	import { api } from '$lib/opens/api';
	import type { ProjectionDetail, ProjectionSlot } from '$lib/opens/types';

	let proj = $state<ProjectionDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let tab = $state<'groups' | 'final' | 'seeds'>('groups');
	let search = $state('');

	const id = $derived(Number($page.params.id));

	$effect(() => {
		loading = true;
		api.getProjection(id)
			.then((p) => (proj = p))
			.catch((e) => (error = e.message))
			.finally(() => (loading = false));
	});

	function norm(s: string): string {
		return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
	}
	const q = $derived(norm(search.trim()));
	function hit(slot: ProjectionSlot): boolean {
		return q.length > 0 && slot.kind === 'player' && norm(slot.player_name ?? '').includes(q);
	}
	const structureLabel = $derived(
		proj ? Object.entries(proj.structure).map(([k, v]) => `${v} ${k}`).join(' · ') : ''
	);
</script>

<a href="/opens" class="text-sm text-slate-500 hover:underline">← Opens</a>

{#if loading}
	<p class="mt-4 text-slate-500">Carregant…</p>
{:else if error}
	<div class="card mt-4 border-red-200 bg-red-50 text-red-800">{error}</div>
{:else if proj}
	<header class="mb-4 mt-2">
		<div class="flex flex-wrap items-center gap-2">
			<h1 class="text-2xl font-semibold">{proj.name}</h1>
			<span class="badge-info">Projecció provisional</span>
			{#if proj.fcb_division_id}
				<a href="/opens/live/{proj.fcb_division_id}" class="badge-ok hover:underline">Veure en directe →</a>
			{/if}
		</div>
		<p class="mt-1 text-sm text-slate-500">
			{proj.season ?? ''} · {proj.num_inscriptions} inscrits · estructura: {structureLabel} + Fase Final
		</p>
	</header>

	<div class="card mb-4 border-blue-200 bg-blue-50 text-sm text-blue-900">
		Aquest és el quadre <strong>projectat</strong> calculat a partir del llistat d'inscrits
		(sembrat segons el Rànquing Català d'Opens i les fases del reglament). És provisional:
		quan la federació publiqui els grups reals, es podrà comparar amb el seguiment en directe.
	</div>

	<div class="mb-4 flex flex-wrap items-center gap-2">
		<div class="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm">
			<button
				class="rounded-md px-3 py-1.5 {tab === 'groups' ? 'bg-white shadow-sm' : 'text-slate-600'}"
				onclick={() => (tab = 'groups')}>Grups per fase</button>
			<button
				class="rounded-md px-3 py-1.5 {tab === 'final' ? 'bg-white shadow-sm' : 'text-slate-600'}"
				onclick={() => (tab = 'final')}>Fase Final</button>
			<button
				class="rounded-md px-3 py-1.5 {tab === 'seeds' ? 'bg-white shadow-sm' : 'text-slate-600'}"
				onclick={() => (tab = 'seeds')}>Caps de sèrie</button>
		</div>
		<input
			class="ml-auto w-56 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
			placeholder="Cerca un jugador…"
			bind:value={search} />
	</div>

	{#if tab === 'groups'}
		{#each proj.phases as phase}
			<section class="mb-6">
				<h2 class="mb-2 text-lg font-semibold">
					{phase.title}
					<span class="text-sm font-normal text-slate-500">· {phase.n_groups} grups de 3</span>
				</h2>
				<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
					{#each phase.groups as g}
						<div class="card p-3">
							<div class="mb-2 text-sm font-semibold text-slate-700">Grup {g.label}</div>
							<ul class="space-y-1">
								{#each g.players as slot}
									<li
										class="flex items-center justify-between gap-2 rounded px-1.5 py-1 text-sm
										{hit(slot) ? 'bg-yellow-100 ring-1 ring-yellow-400' : ''}">
										{#if slot.kind === 'player'}
											<span class="truncate">
												<span class="font-medium">{slot.player_name}</span>
												{#if slot.club}<span class="text-xs text-slate-400"> · {slot.club}</span>{/if}
											</span>
											<span class="shrink-0 font-mono text-xs text-slate-500">
												{slot.ranking_position ? `#${slot.ranking_position}` : '—'}
											</span>
										{:else}
											<span class="italic text-slate-400">{slot.label}</span>
										{/if}
									</li>
								{/each}
							</ul>
						</div>
					{/each}
				</div>
			</section>
		{/each}
	{:else if tab === 'final'}
		<section>
			<h2 class="mb-2 text-lg font-semibold">{proj.fase_final.title}</h2>
			<p class="mb-3 text-sm text-slate-500">
				Setzens de final: els {proj.fase_final.n_direct_seeds} millors caps de sèrie entren
				directament i s'enfronten als guanyadors dels grups de Prèvies.
			</p>
			<div class="grid gap-2 sm:grid-cols-2">
				{#each proj.fase_final.setzens as m}
					<div class="card flex items-center gap-3 p-3 text-sm">
						<span class="w-6 shrink-0 text-center font-mono text-xs text-slate-400">{m.match}</span>
						<div class="min-w-0 flex-1">
							<div class="truncate {hit(m.a) ? 'rounded bg-yellow-100 px-1' : ''}">
								<span class="font-medium">{m.a.player_name}</span>
								<span class="font-mono text-xs text-slate-400"> ({m.a.seed_order})</span>
							</div>
							<div class="my-0.5 text-xs text-slate-400">vs</div>
							<div class="truncate italic text-slate-500">{m.b.label}</div>
						</div>
					</div>
				{/each}
			</div>
		</section>
	{:else}
		<section class="card p-0">
			<table class="table-clean">
				<thead>
					<tr>
						<th class="text-right">Seed</th>
						<th>Jugador</th>
						<th>Club</th>
						<th class="text-right">Pos. rànq.</th>
						<th class="text-right">Mitjana</th>
						<th>Entra a</th>
					</tr>
				</thead>
				<tbody>
					{#each proj.seeds as s}
						<tr class={q && norm(s.player_name).includes(q) ? 'bg-yellow-100' : ''}>
							<td class="text-right font-mono text-slate-500">{s.seed_order}</td>
							<td class="font-medium">{s.player_name}</td>
							<td class="text-slate-600">{s.club ?? '—'}</td>
							<td class="text-right font-mono">
								{#if s.ranking_position}{s.ranking_position}{:else}
									<span class="badge-prov">{s.ranquing_estat || 's/c'}</span>
								{/if}
							</td>
							<td class="text-right font-mono">{s.mitjana.toFixed(3)}</td>
							<td class="text-slate-600">{s.entry_phase}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</section>
	{/if}
{/if}
