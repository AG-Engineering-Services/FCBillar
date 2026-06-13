<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { supabase, type OpenLiveRow, type OpenLivePhase, type OpenLiveMatch } from '$lib/supabase';

	let row = $state<OpenLiveRow | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let selectedPhase = $state<number | null>(null);
	let showClass = $state(false);
	let timer: ReturnType<typeof setInterval> | null = null;

	const divisionId = $derived(Number($page.params.id));
	const payload = $derived(row?.payload_json ?? null);
	const phases = $derived(payload?.phases ?? []);

	async function load() {
		const { data, error: e } = await supabase
			.from('open_live')
			.select('*')
			.eq('fcb_division_id', divisionId)
			.maybeSingle();
		if (e) {
			error = e.message;
		} else if (!data) {
			error = 'Aquest Open ja no està en curs.';
			row = null;
		} else {
			row = data as OpenLiveRow;
			error = null;
			if (selectedPhase === null) {
				const active = (row.payload_json.phases ?? []).findIndex((p) => p.is_active);
				selectedPhase = active >= 0 ? active : 0;
			}
		}
		loading = false;
	}

	onMount(() => {
		load();
		// Auto-refresc cada 90 s mentre la pestanya estigui visible.
		timer = setInterval(() => {
			if (document.visibilityState === 'visible') load();
		}, 90_000);
	});
	onDestroy(() => {
		if (timer) clearInterval(timer);
	});

	function agoText(iso: string): string {
		const ms = Date.now() - new Date(iso).getTime();
		const min = Math.floor(ms / 60000);
		if (min < 1) return 'ara mateix';
		if (min < 60) return `fa ${min} min`;
		const h = Math.floor(min / 60);
		return `fa ${h} h`;
	}

	function phaseStatus(p: OpenLivePhase): 'done' | 'active' | 'pending' {
		if (p.kind === 'group') {
			const total = p.groups.reduce((a, g) => a + g.n_matches_total, 0);
			const played = p.groups.reduce((a, g) => a + g.n_matches_played, 0);
			if (total === 0 || played === 0) return 'pending';
			return played === total ? 'done' : 'active';
		}
		if (p.ko_matches.length === 0) return 'pending';
		const played = p.ko_matches.filter((m) => m.is_played).length;
		if (played === 0) return 'pending';
		return played === p.ko_matches.length ? 'done' : 'active';
	}

	// Posició d'un jugador dins el seu grup segons els classificats provisionals
	// (1 = guanyador de grup). Retorna 0 si no hi és.
	function provPos(phase: OpenLivePhase, group: string, name: string): number {
		const q = phase.provisional_qualifiers.find(
			(x) => x.player_name === name && x.group_label === group
		);
		return q?.position_in_group ?? 0;
	}

	function koPairs(phase: OpenLivePhase): OpenLiveMatch[] {
		return phase.ko_matches.length ? phase.ko_matches : phase.provisional_matches;
	}
</script>

<a href="/opens" class="mb-3 inline-block text-sm text-slate-400 active:underline">‹ Opens</a>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if error}
	<div class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{error}</div>
{:else if row && payload}
	<div class="mb-3">
		<div class="flex flex-wrap items-center gap-2">
			<h1 class="text-lg font-bold leading-tight">{payload.name}</h1>
			{#if row.modality}
				<span class="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-600">{row.modality}</span>
			{/if}
			<span class="shrink-0 rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">En directe</span>
		</div>
		<p class="mt-0.5 text-[11px] text-slate-400">Actualitzat {agoText(row.captured_at)} · es refresca sol</p>
	</div>

	<!-- Selector de fases -->
	<div class="mb-3 flex flex-wrap gap-1.5">
		{#each phases as p, i}
			{@const st = phaseStatus(p)}
			<button
				onclick={() => (selectedPhase = i)}
				class="rounded-lg border px-2.5 py-1 text-xs font-medium {selectedPhase === i ? 'ring-2 ring-slate-400' : ''} {st === 'done'
					? 'border-emerald-300 bg-emerald-50 text-emerald-700'
					: st === 'active'
						? 'border-amber-300 bg-amber-50 text-amber-700'
						: 'border-slate-200 bg-slate-50 text-slate-400'}"
			>
				{p.label}
				{st === 'done' ? '✓' : st === 'active' ? '●' : '○'}
			</button>
		{/each}
	</div>

	{#if selectedPhase !== null && phases[selectedPhase]}
		{@const phase = phases[selectedPhase]}
		{#if phase.kind === 'group'}
			<div class="grid gap-2.5 sm:grid-cols-2">
				{#each phase.groups as g (g.label)}
					{@const done = g.n_matches_total > 0 && g.n_matches_played === g.n_matches_total}
					<div class="overflow-hidden rounded-xl bg-white ring-1 {done ? 'ring-emerald-200' : 'ring-slate-200'}">
						<div class="flex items-center justify-between gap-2 px-3 py-1.5 {done ? 'bg-emerald-50' : 'bg-slate-50'}">
							<span class="text-sm font-semibold">{g.label}</span>
							<span class="text-[11px] {done ? 'text-emerald-700' : 'text-amber-700'}">{g.n_matches_played}/{g.n_matches_total}</span>
						</div>
						{#if g.venue}<div class="px-3 pt-1 text-[10px] text-slate-400">{g.venue}</div>{/if}
						{#if g.standings.length}
							<ol class="px-2 py-1">
								{#each g.standings as s, idx}
									{@const pos = provPos(phase, g.label, s.player_name)}
									<li class="flex items-center gap-2 rounded px-1 py-1 {pos === 1 ? 'bg-emerald-50' : pos >= 2 ? 'bg-amber-50/60' : ''}">
										<span class="w-4 text-center text-xs font-mono {pos === 1 ? 'text-emerald-600' : pos >= 2 ? 'text-amber-600' : 'text-slate-400'}">{pos === 1 ? '▸' : idx + 1}</span>
										<span class="min-w-0 flex-1 truncate text-sm">{s.player_name}</span>
										<span class="shrink-0 font-mono text-[11px] text-slate-400">{s.mitjana.toFixed(3)}</span>
										<span class="w-5 shrink-0 text-right font-mono text-sm font-semibold">{s.punts}</span>
									</li>
								{/each}
							</ol>
						{:else}
							<p class="px-3 py-2 text-xs text-slate-400">Sense classificació encara.</p>
						{/if}
					</div>
				{/each}
			</div>
		{:else}
			<!-- Fase KO: emparellaments (oficials o calculats) -->
			{@const pairs = koPairs(phase)}
			{#if pairs.length === 0}
				<p class="py-4 text-center text-sm text-slate-400">Encara no hi ha emparellaments d'aquesta ronda.</p>
			{:else}
				<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
					{#each pairs as m, i}
						{@const aWins = m.is_played && m.punts_a > m.punts_b}
						{@const bWins = m.is_played && m.punts_b > m.punts_a}
						<li class="border-b border-slate-100 px-3 py-2 last:border-0">
							<div class="flex items-center justify-between gap-2 text-sm">
								<span class="min-w-0 flex-1 truncate {aWins ? 'font-semibold' : ''}">{m.player_a || '—'}</span>
								<span class="shrink-0 font-mono text-xs {m.is_played ? '' : 'text-slate-400'}">{m.punts_a}–{m.punts_b}</span>
								<span class="min-w-0 flex-1 truncate text-right {bWins ? 'font-semibold' : ''}">{m.player_b || '—'}</span>
							</div>
							{#if m.is_played}
								<div class="mt-0.5 text-center text-[10px] text-slate-400">{m.caramboles_a}–{m.caramboles_b} car. · {m.entrades} ent.</div>
							{:else}
								<div class="mt-0.5 text-center text-[10px] text-amber-600">{phase.ko_matches.length ? 'pendent' : 'calculat'}</div>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		{/if}
	{/if}

	<!-- Classificació provisional de l'Open (eliminats + projecció) -->
	{#if payload.classification.length}
		<button
			onclick={() => (showClass = !showClass)}
			class="mt-4 flex w-full items-center justify-between rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white"
		>
			<span>Classificació {payload.classification_is_provisional ? 'provisional' : 'final'} ({payload.classification.length})</span>
			<span class="text-xs text-slate-300">{showClass ? '▴' : '▾'}</span>
		</button>
		{#if showClass}
			<div class="mt-2 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
				<ul>
					{#each payload.classification as c}
						<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-1.5 last:border-0">
							<span class="w-6 text-center text-sm font-semibold tabular-nums {c.position === 1 ? 'text-amber-500' : 'text-slate-400'}">{c.position}</span>
							<div class="min-w-0 flex-1">
								<div class="truncate text-sm leading-tight {c.is_provisional_position ? 'italic' : ''}">{c.player_name}</div>
								{#if c.club}<div class="truncate text-[10px] text-slate-400">{c.club} · {c.round_label}</div>{/if}
							</div>
							<span class="shrink-0 font-mono text-sm font-bold tabular-nums">{c.open_points}</span>
						</li>
					{/each}
				</ul>
			</div>
			<p class="px-1 py-2 text-center text-[10px] text-slate-400">
				Punts segons posició (Art. XVII). Classificació calculada en directe; pot canviar fins que la FCB la publiqui.
			</p>
		{/if}
	{/if}
{/if}
