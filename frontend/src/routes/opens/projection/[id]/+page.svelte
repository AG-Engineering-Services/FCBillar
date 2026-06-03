<script lang="ts">
	import { page } from '$app/stores';
	import { api } from '$lib/opens/api';
	import BackButton from '$lib/components/BackButton.svelte';
	import type { ProjectionDetail, ProjectionSlot, ProjectionSeed } from '$lib/opens/types';

	// Link a player to their existing FCBillar profile when resolved, otherwise
	// to a name-prefilled player search as a graceful fallback.
	function playerHref(p: { fcb_id?: string | null; player_name?: string }): string {
		if (p.fcb_id) return `/players/${encodeURIComponent(p.fcb_id)}`;
		return `/players?q=${encodeURIComponent(p.player_name ?? '')}`;
	}

	let proj = $state<ProjectionDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let tab = $state<'groups' | 'final' | 'seeds' | 'clubs'>('groups');
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

	// Per-club grouping (#5): seeds bucketed by club, each sorted by seed order.
	const byClub = $derived.by(() => {
		const m = new Map<string, ProjectionSeed[]>();
		for (const s of proj?.seeds ?? []) {
			const key = s.club ?? '—';
			if (!m.has(key)) m.set(key, []);
			m.get(key)!.push(s);
		}
		return [...m.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
	});

	// Compare with the real draw (#1) — only meaningful once linked & published.
	let divInput = $state('');
	let linking = $state(false);
	let comparison = $state<any>(null);
	let comparing = $state(false);

	async function linkDivision() {
		const n = Number(divInput);
		if (!n || !proj) return;
		linking = true;
		try {
			await api.linkProjection(proj.id, n);
			proj = await api.getProjection(id);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			linking = false;
		}
	}
	async function runCompare() {
		if (!proj) return;
		comparing = true;
		try {
			comparison = await api.compareProjection(proj.id);
		} catch (e) {
			comparison = { published: false, reason: (e as Error).message };
		} finally {
			comparing = false;
		}
	}
</script>

<BackButton fallback="/opens" />

{#if loading}
	<p class="mt-4 text-slate-500">Carregant…</p>
{:else if error}
	<div class="card mt-4 border-red-200 bg-red-50 text-red-800">{error}</div>
{:else if proj}
	<header class="mb-4 mt-2 flex flex-wrap items-start justify-between gap-2"><div>
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
	</div><button type="button" class="btn-secondary no-print" onclick={() => window.print()}>🖨 Imprimeix</button></header>

	<div class="card mb-4 border-blue-200 bg-blue-50 text-sm text-blue-900">
		Aquest és el quadre <strong>projectat</strong> calculat a partir del llistat d'inscrits
		(sembrat segons el Rànquing Català d'Opens i les fases del reglament). És provisional:
		quan la federació publiqui els grups reals, es podrà comparar amb el seguiment en directe.
	</div>

	{#if proj.warnings && proj.warnings.length}
			<div class="mb-4 space-y-1">
				{#each proj.warnings as w}
					<div class="rounded-md px-3 py-1.5 text-sm {w.level === 'error' ? 'bg-red-50 text-red-800' : w.level === 'warning' ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-slate-600'}">
						{w.level === 'error' ? '⛔' : w.level === 'warning' ? '⚠️' : 'ℹ️'} {w.message}
					</div>
				{/each}
			</div>
		{/if}

		<div class="mb-4 flex flex-wrap items-center gap-2 no-print">
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
				<button
					class="rounded-md px-3 py-1.5 {tab === 'clubs' ? 'bg-white shadow-sm' : 'text-slate-600'}"
					onclick={() => (tab = 'clubs')}>Per club</button>
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
												<a href={playerHref(slot)} class="font-medium hover:underline">{slot.player_name}</a>
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
								<a href={playerHref(m.a)} class="font-medium hover:underline">{m.a.player_name}</a>
								<span class="font-mono text-xs text-slate-400"> ({m.a.seed_order})</span>
							</div>
							<div class="my-0.5 text-xs text-slate-400">vs</div>
							<div class="truncate italic text-slate-500">{m.b.label}</div>
						</div>
					</div>
				{/each}
			</div>
		</section>
	{:else if tab === 'clubs'}
		<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each byClub as [club, members]}
				<div class="card p-3">
					<div class="mb-2 flex items-center justify-between">
						<span class="text-sm font-semibold text-slate-700">{club}</span>
						<span class="text-xs text-slate-400">{members.length}</span>
					</div>
					<ul class="space-y-1">
						{#each members as s}
							<li class="flex items-center justify-between gap-2 text-sm {q && norm(s.player_name).includes(q) ? 'rounded bg-yellow-100 px-1' : ''}">
								<a href={playerHref(s)} class="truncate hover:underline">{s.player_name}</a>
								<span class="shrink-0 font-mono text-xs text-slate-400">{s.ranking_position ? '#' + s.ranking_position : s.ranquing_estat}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/each}
		</div>
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
						<th class="text-right">Punts opens</th>
						<th>Entra a</th>
					</tr>
				</thead>
				<tbody>
					{#each proj.seeds as s}
						<tr class={q && norm(s.player_name).includes(q) ? 'bg-yellow-100' : ''}>
							<td class="text-right font-mono text-slate-500">{s.seed_order}</td>
							<td class="font-medium">
								<a href={playerHref(s)} class="hover:underline">{s.player_name}</a>
							</td>
							<td class="text-slate-600">{s.club ?? '—'}</td>
							<td class="text-right font-mono">
								{#if s.ranking_position}{s.ranking_position}{:else}
									<span class="badge-prov">{s.ranquing_estat || 's/c'}</span>
								{/if}
							</td>
							<td class="text-right font-mono">{s.mitjana.toFixed(3)}</td>
								<td class="text-right font-mono text-slate-600">{s.opens_points ?? '—'}</td>
							<td class="text-slate-600">{s.entry_phase}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</section>
	{/if}

	<section class="mt-8 no-print">
		<h2 class="mb-2 text-lg font-semibold">Comparació amb el sorteig real</h2>
		{#if proj.fcb_division_id}
			<p class="mb-2 text-sm text-slate-500">
				Vinculat a la divisió #{proj.fcb_division_id}.
				<a href="/opens/live/{proj.fcb_division_id}" class="text-blue-700 hover:underline">Veure en directe →</a>
			</p>
			<button class="btn-secondary" onclick={runCompare} disabled={comparing}>
				{comparing ? 'Comparant…' : 'Comparar amb el sorteig publicat'}
			</button>
			{#if comparison}
				{#if comparison.published}
					<p class="mt-3 text-sm text-slate-600">{comparison.n_matched} jugadors localitzats al sorteig real.</p>
					<div class="card mt-2 p-0">
						<table class="table-clean">
							<thead><tr><th>Jugador</th><th>Projectat</th><th>Real</th></tr></thead>
							<tbody>
								{#each comparison.moves as mv}
									<tr><td>{mv.player}</td><td class="text-slate-500">{mv.projected}</td><td>{mv.real}</td></tr>
								{/each}
							</tbody>
						</table>
					</div>
				{:else}
					<p class="mt-3 text-sm text-amber-700">Encara no hi ha grups publicats per comparar.</p>
				{/if}
			{/if}
		{:else}
			<p class="mb-2 text-sm text-slate-500">
				Quan la federació publiqui els grups, vincula aquesta projecció a la divisió FCB per comparar el sorteig real amb el projectat.
			</p>
			<div class="flex items-center gap-2">
				<input
					class="w-40 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
					placeholder="ID divisió FCB"
					bind:value={divInput} />
				<button class="btn-secondary" onclick={linkDivision} disabled={linking}>
					{linking ? 'Vinculant…' : 'Vincular'}
				</button>
			</div>
		{/if}
	</section>
{/if}
