<script module lang="ts">
	import type { OpenLiveRow } from '$lib/supabase';
	// Cache per divisió: en tornar enrere des d'una fitxa de jugador, la pàgina
	// es repinta a l'instant (contingut complet) i la restauració d'scroll de
	// SvelteKit recupera el punt on era l'usuari sense esperar la xarxa.
	const rowCache = new Map<number, OpenLiveRow>();
	const phaseCache = new Map<number, number>();
</script>

<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { supabase, type OpenLivePhase, type OpenLiveMatch } from '$lib/supabase';

	const id0 = Number($page.params.id);
	let row = $state<OpenLiveRow | null>(rowCache.get(id0) ?? null);
	let loading = $state(rowCache.get(id0) == null);
	let error = $state<string | null>(null);
	let selectedPhase = $state<number | null>(phaseCache.get(id0) ?? null);
	let timer: ReturnType<typeof setInterval> | null = null;

	const divisionId = $derived(Number($page.params.id));
	const payload = $derived(row?.payload_json ?? null);
	const phases = $derived(payload?.phases ?? []);

	// Recorda la fase seleccionada per divisió (per restaurar-la en tornar enrere).
	$effect(() => {
		if (selectedPhase !== null) phaseCache.set(divisionId, selectedPhase);
	});

	function playerHref(name: string): string | null {
		const id = payload?.player_ids?.[name];
		return id ? `/jugador/${id}` : null;
	}

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
			rowCache.delete(divisionId);
		} else {
			row = data as OpenLiveRow;
			rowCache.set(divisionId, row);
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

<!-- Nom de jugador: enllaç a la fitxa si el podem resoldre, si no text pla. -->
{#snippet player(name: string, cls: string)}
	{@const href = playerHref(name)}
	{#if href}
		<a {href} class="{cls} hover:underline active:underline">{name}</a>
	{:else}
		<span class={cls}>{name}</span>
	{/if}
{/snippet}

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
			{@const quals = phase.provisional_qualifiers
				.filter((q) => q.position_in_group === 1)
				.slice()
				.sort((a, b) => b.punts - a.punts || b.mitjana - a.mitjana)}
			{@const phaseComplete = phase.groups.every((g) => g.n_matches_total > 0 && g.n_matches_played === g.n_matches_total)}
			{#if quals.length}
				<div class="mb-3 rounded-xl bg-emerald-50 p-3 ring-1 ring-emerald-200">
					<div class="mb-1.5 flex items-center gap-2">
						<span class="text-xs font-semibold uppercase tracking-wide text-emerald-700">
							Classificats per a la següent ronda · 1rs de grup ({quals.length})
						</span>
						{#if !phaseComplete}
							<span class="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-700">Provisional</span>
						{/if}
					</div>
					<!-- Capçalera de columnes (només PC/tablet) -->
					<div class="hidden items-center gap-2 border-b border-emerald-200/70 px-1 pb-1 text-[9px] font-semibold uppercase tracking-wider text-emerald-700/70 md:flex">
						<span class="w-4 text-right">#</span>
						<span class="w-6">Gr</span>
						<span class="flex-1">Jugador</span>
						<span class="w-8 text-right">PJ</span>
						<span class="w-8 text-right">Pts</span>
						<span class="w-12 text-right">C</span>
						<span class="w-12 text-right">E</span>
						<span class="w-14 text-right">Mitjana</span>
					</div>
					<ol class="space-y-0.5">
						{#each quals as q, i}
							{@const grp = phase.groups.find((gg) => gg.label === q.group_label)}
							{@const sure = !!grp && grp.n_matches_total > 0 && grp.n_matches_played === grp.n_matches_total}
							<li class="flex items-center gap-2 text-sm">
								<span class="w-4 shrink-0 text-right font-mono text-[11px] text-slate-400">{i + 1}</span>
								<span class="w-6 shrink-0 rounded bg-white/70 text-center font-mono text-[10px] text-slate-500">{q.group_label.replace('Grup ', '')}</span>
								<span class="flex min-w-0 flex-1 items-center gap-1">
									{@render player(q.player_name, 'truncate ' + (sure ? 'font-medium' : ''))}
									{#if sure}<span class="shrink-0 text-emerald-600" title="Classificació assegurada (grup acabat)">✓</span>{/if}
								</span>
								<!-- Estadístiques completes: només PC/tablet -->
								<span class="hidden w-8 shrink-0 text-right font-mono text-[11px] text-slate-500 md:inline">{q.pj ?? 0}</span>
								<span class="hidden w-8 shrink-0 text-right font-mono text-[11px] font-semibold text-slate-700 md:inline">{q.punts}</span>
								<span class="hidden w-12 shrink-0 text-right font-mono text-[11px] text-slate-500 md:inline">{q.caramboles ?? 0}</span>
								<span class="hidden w-12 shrink-0 text-right font-mono text-[11px] text-slate-500 md:inline">{q.entrades ?? 0}</span>
								<span class="w-14 shrink-0 text-right font-mono text-[11px] text-slate-500">{q.mitjana.toFixed(3)}</span>
							</li>
						{/each}
					</ol>
					<p class="mt-1.5 text-[10px] text-slate-400">Només grups amb partides jugades. Ordre: punts → mitjana. ✓ = classificació assegurada (grup acabat).</p>
				</div>
			{/if}
			<div class="grid gap-2.5 sm:grid-cols-2">
				{#each phase.groups as g (g.label)}
					{@const done = g.n_matches_total > 0 && g.n_matches_played === g.n_matches_total}
					{@const played = g.matches.filter((m) => m.is_played)}
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
										{@render player(s.player_name, 'min-w-0 flex-1 truncate text-sm')}
										<span class="shrink-0 font-mono text-[11px] text-slate-400">{s.mitjana.toFixed(3)}</span>
										<span class="w-5 shrink-0 text-right font-mono text-sm font-semibold">{s.punts}</span>
									</li>
								{/each}
							</ol>
						{:else}
							<p class="px-3 py-2 text-xs text-slate-400">Sense classificació encara.</p>
						{/if}
						{#if played.length}
							<div class="border-t border-slate-100 px-3 py-2">
								<div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
									Partides disputades
								</div>
								<ul class="space-y-1.5">
									{#each played as m}
										{@const aWin = m.caramboles_a > m.caramboles_b}
										{@const bWin = m.caramboles_b > m.caramboles_a}
										<li>
											<div class="flex items-center justify-between gap-2 text-xs">
												{@render player(m.player_a, 'min-w-0 flex-1 truncate font-bold ' + (aWin ? 'text-emerald-600' : bWin ? 'text-red-600' : 'text-slate-900'))}
												<span class="shrink-0 font-mono font-bold text-slate-700">{m.caramboles_a}–{m.caramboles_b}</span>
												{@render player(m.player_b, 'min-w-0 flex-1 truncate text-right font-bold ' + (bWin ? 'text-emerald-600' : aWin ? 'text-red-600' : 'text-slate-900'))}
											</div>
											{#if m.entrades}<div class="text-center text-[10px] text-slate-400">{m.entrades} ent.</div>{/if}
										</li>
									{/each}
								</ul>
							</div>
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
								{#if m.player_a}{@render player(m.player_a, 'min-w-0 flex-1 truncate ' + (aWins ? 'font-semibold' : ''))}{:else}<span class="min-w-0 flex-1 truncate text-slate-400">—</span>{/if}
								<span class="shrink-0 font-mono text-xs {m.is_played ? '' : 'text-slate-400'}">{m.punts_a}–{m.punts_b}</span>
								{#if m.player_b}{@render player(m.player_b, 'min-w-0 flex-1 truncate text-right ' + (bWins ? 'font-semibold' : ''))}{:else}<span class="min-w-0 flex-1 truncate text-right text-slate-400">—</span>{/if}
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
{/if}
