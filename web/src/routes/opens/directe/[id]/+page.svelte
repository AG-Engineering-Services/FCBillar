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
	import { supabase, type OpenLivePhase, type OpenLiveGroup, type OpenLiveMatch, type OpenLiveScore, type OpenLiveClassRow } from '$lib/supabase';

	const id0 = Number($page.params.id);
	let row = $state<OpenLiveRow | null>(rowCache.get(id0) ?? null);
	let loading = $state(rowCache.get(id0) == null);
	let error = $state<string | null>(null);
	let selectedPhase = $state<number | null>(phaseCache.get(id0) ?? null);
	let scores = $state<OpenLiveScore[]>([]);
	let timer: ReturnType<typeof setInterval> | null = null;
	let scoresTimer: ReturnType<typeof setInterval> | null = null;

	const divisionId = $derived(Number($page.params.id));
	const payload = $derived(row?.payload_json ?? null);
	const phases = $derived(payload?.phases ?? []);

	// Classificació provisional (jugadors ELIMINATS, per tram segons la fase on cauen),
	// agrupada per ronda i ordenada pel millor lloc. Es va omplint a mesura que cauen.
	const classByRound = $derived.by(() => {
		const m = new Map<string, OpenLiveClassRow[]>();
		for (const r of payload?.classification ?? []) {
			if (!m.has(r.round_label)) m.set(r.round_label, []);
			m.get(r.round_label)!.push(r);
		}
		return [...m.entries()]
			.map(([round, rows]) => ({ round, rows: rows.slice().sort((a, b) => a.position - b.position) }))
			.sort((a, b) => a.rows[0].position - b.rows[0].position);
	});

	// Millor sèrie major del torneig (màxim de totes les partides jugades).
	const bestSerie = $derived.by(() => {
		let best = 0;
		const who: string[] = [];
		const consider = (name: string | null | undefined, sm: number) => {
			if (!name || !sm) return;
			if (sm > best) { best = sm; who.length = 0; who.push(name); }
			else if (sm === best && !who.includes(name)) who.push(name);
		};
		for (const ph of phases) {
			for (const g of ph.groups) for (const mm of g.matches) {
				if (!mm.is_played) continue;
				consider(mm.player_a, mm.serie_major_a);
				consider(mm.player_b, mm.serie_major_b);
			}
			for (const mm of ph.ko_matches) {
				if (!mm.is_played) continue;
				consider(mm.player_a, mm.serie_major_a);
				consider(mm.player_b, mm.serie_major_b);
			}
		}
		return best > 0 ? { sm: best, players: who } : null;
	});

	// Marcadors en viu (OCR) per grup. Normalitzem l'etiqueta (de vegades "T",
	// de vegades "Grup T") perquè casi amb el grup de la classificació.
	const normGroup = (s: string | null) => (s ?? '').replace(/grup\s*/i, '').toUpperCase().trim();
	// Només marcadors FRESCS: si fa més de 8 min que no es refresquen, la partida
	// pot haver acabat o estar en pausa → no mostrem un valor potser obsolet.
	const FRESH_MS = 12 * 60 * 1000;
	function liveForGroup(label: string): OpenLiveScore[] {
		const k = normGroup(label);
		const cutoff = Date.now() - FRESH_MS;
		return scores.filter(
			(s) => normGroup(s.group_label) === k && new Date(s.captured_at).getTime() > cutoff
		);
	}

	// Recorda la fase seleccionada per divisió (per restaurar-la en tornar enrere).
	$effect(() => {
		if (selectedPhase !== null) phaseCache.set(divisionId, selectedPhase);
	});

	function playerHref(name: string): string | null {
		const id = payload?.player_ids?.[name];
		return id ? `/jugador/${id}` : null;
	}

	// Marcadors en viu (OCR): taula minúscula, és el que canvia més sovint → es
	// refresca tot sol cada 30 s (independent del payload pesat de la federació).
	function loadScores() {
		supabase
			.from('open_live_scores')
			.select('*')
			.eq('fcb_division_id', divisionId)
			.then(({ data }) => (scores = (data ?? []) as OpenLiveScore[]));
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
				// Obre a la primera fase INCOMPLETA (encara en joc), no a una de ja
				// tancada. Si totes estan acabades, mostra l'última.
				const ph = row.payload_json.phases ?? [];
				const firstIncomplete = ph.findIndex((p) => phaseStatus(p) !== 'done');
				selectedPhase = firstIncomplete >= 0 ? firstIncomplete : Math.max(0, ph.length - 1);
			}
		}
		// Marcadors en viu (OCR) — no bloqueja; es refresca a cada poll.
		loadScores();
		loading = false;
	}

	onMount(() => {
		load();
		// Payload de la federació (pesat, canvia lent): cada 90 s.
		timer = setInterval(() => {
			if (document.visibilityState === 'visible') load();
		}, 90_000);
		// Marcadors en viu (lleuger, canvia sovint): cada 30 s.
		scoresTimer = setInterval(() => {
			if (document.visibilityState === 'visible') loadScores();
		}, 30_000);
	});
	onDestroy(() => {
		if (timer) clearInterval(timer);
		if (scoresTimer) clearInterval(scoresTimer);
	});

	function agoText(iso: string): string {
		const ms = Date.now() - new Date(iso).getTime();
		const min = Math.floor(ms / 60000);
		if (min < 1) return 'ara mateix';
		if (min < 60) return `fa ${min} min`;
		const h = Math.floor(min / 60);
		return `fa ${h} h`;
	}

	const canonName = (s: string | null | undefined) =>
		(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/[^A-Z0-9]/g, '');

	// Un grup està TANCAT (places decidides) quan totes les partides estan jugades,
	// O BÉ —grup de 3 amb un jugador que NO es presenta— quan les partides jugades
	// són totes del MATEIX parell: els 2 presents juguen dos cops i el grup queda
	// tancat amb 2 partides, encara que la federació mantingui n_matches_total=3.
	function groupClosed(g: OpenLiveGroup): boolean {
		if (g.n_matches_total > 0 && g.n_matches_played === g.n_matches_total) return true;
		const played = (g.matches ?? []).filter((m) => m.is_played && m.player_a && m.player_b);
		if (played.length >= 2) {
			const pairs = new Set(played.map((m) => [canonName(m.player_a), canonName(m.player_b)].sort().join('|')));
			if (pairs.size === 1) return true; // totes les jugades són el mateix parell → no-show
		}
		return false;
	}

	function phaseStatus(p: OpenLivePhase): 'done' | 'active' | 'pending' {
		if (p.kind === 'group') {
			const total = p.groups.reduce((a, g) => a + g.n_matches_total, 0);
			const played = p.groups.reduce((a, g) => a + g.n_matches_played, 0);
			if (total === 0 || played === 0) return 'pending';
			return p.groups.every(groupClosed) ? 'done' : 'active';
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

	// Cognoms (vista de partides en directe): el nom ve "COGNOM1 [COGNOM2], NOM" →
	// mostrem tot el tros abans de la coma (els DOS cognoms, compostos inclosos com
	// "DE LA HOZ") i deixem fora el nom de pila.
	function surnamesOnly(name: string | null | undefined): string {
		if (!name || name === '—') return name ?? '—';
		return (name.includes(',') ? name.split(',')[0] : name).trim() || name;
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

<!-- Igual que player() però mostra els dos COGNOMS, sense el nom (partides en directe). -->
{#snippet playerShort(name: string, cls: string)}
	{@const href = playerHref(name)}
	{#if href}
		<a {href} class="{cls} hover:underline active:underline">{surnamesOnly(name)}</a>
	{:else}
		<span class={cls}>{surnamesOnly(name)}</span>
	{/if}
{/snippet}

<a href="/opens" class="mb-3 inline-block text-sm text-slate-400 dark:text-slate-500 active:underline">‹ Opens</a>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
{:else if error}
	<div class="rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-sm text-amber-800 dark:text-amber-300">{error}</div>
{:else if row && payload}
	<div class="mb-3">
		<div class="flex flex-wrap items-center gap-2">
			<h1 class="text-lg font-bold leading-tight">{payload.name}</h1>
			{#if row.modality}
				<span class="shrink-0 rounded bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300">{row.modality}</span>
			{/if}
			<span class="shrink-0 rounded bg-emerald-100 dark:bg-emerald-900/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">En directe</span>
		</div>
		<p class="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">Actualitzat {agoText(row.captured_at)} · es refresca sol</p>
	</div>

	{#if bestSerie}
		<div class="mb-3 flex items-center gap-2 rounded-xl bg-violet-50 dark:bg-violet-950/40 px-3 py-2 ring-1 ring-violet-200 dark:ring-violet-900/50">
			<span class="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300">Millor sèrie</span>
			<span class="min-w-0 flex-1 truncate text-sm">
				{#each bestSerie.players as p, i}{#if i > 0}, {/if}{@render player(p, 'font-bold')}{/each}
			</span>
			<span class="shrink-0 font-mono text-lg font-bold text-violet-700 dark:text-violet-300">{bestSerie.sm}</span>
		</div>
	{/if}

	<!-- Selector de fases -->
	<div class="mb-3 flex flex-wrap gap-1.5">
		{#each phases as p, i}
			{@const st = phaseStatus(p)}
			<button
				onclick={() => (selectedPhase = i)}
				class="rounded-lg border px-2.5 py-1 text-xs font-medium {selectedPhase === i ? 'ring-2 ring-slate-400 dark:ring-slate-600' : ''} {st === 'done'
					? 'border-emerald-300 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300'
					: st === 'active'
						? 'border-amber-300 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300'
						: 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-slate-400 dark:text-slate-500'}"
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
				.slice()
				.sort((a, b) => a.position_in_group - b.position_in_group || b.punts - a.punts || b.mitjana - a.mitjana)}
			{@const nSeconds = quals.filter((q) => q.position_in_group > 1).length}
			{@const phaseComplete = phase.groups.every(groupClosed)}
			{#if quals.length}
				<div class="mb-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 p-3 ring-1 ring-emerald-200 dark:ring-emerald-900/50">
					<div class="mb-1.5 flex items-center gap-2">
						<span class="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
							Classificats per a la següent ronda ({quals.length}){#if nSeconds} · 1rs + {nSeconds} {nSeconds === 1 ? 'millor 2n' : 'millors 2ns'}{/if}
						</span>
						{#if !phaseComplete}
							<span class="shrink-0 rounded bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">Provisional</span>
						{/if}
					</div>
					<!-- Capçalera de columnes (només PC/tablet) -->
					<div class="hidden items-center gap-2 border-b border-emerald-200/70 dark:border-emerald-900/50 px-1 pb-1 text-[9px] font-semibold uppercase tracking-wider text-emerald-700/70 dark:text-emerald-300 md:flex">
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
							{@const sure = q.position_in_group > 1 || (!!grp && groupClosed(grp))}
							<li class="flex items-center gap-2 text-sm {q.position_in_group > 1 ? '-mx-1 rounded bg-amber-50/70 dark:bg-amber-950/40 px-1' : ''}">
								<span class="w-4 shrink-0 text-right font-mono text-[11px] text-slate-400 dark:text-slate-500">{i + 1}</span>
								<span class="w-6 shrink-0 rounded bg-white/70 dark:bg-slate-900/70 text-center font-mono text-[10px] text-slate-500 dark:text-slate-400">{q.group_label.replace('Grup ', '')}</span>
								<span class="flex min-w-0 flex-1 items-center gap-1">
									{@render player(q.player_name, 'truncate ' + (sure ? 'font-bold' : ''))}
									{#if q.position_in_group > 1}<span class="shrink-0 rounded bg-amber-100 dark:bg-amber-900/40 px-1 text-[9px] font-semibold uppercase text-amber-700 dark:text-amber-300" title="Millor 2n: classificat per omplir la següent ronda">2n</span>{/if}{#if sure}<span class="shrink-0 text-emerald-600 dark:text-emerald-400" title={q.position_in_group > 1 ? 'Classificat (millor 2n, col·locat per la federació)' : 'Classificació assegurada (grup acabat)'}>✓</span>{/if}
								</span>
								<!-- Estadístiques completes: només PC/tablet -->
								<span class="hidden w-8 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400 md:inline">{q.pj ?? 0}</span>
								<span class="hidden w-8 shrink-0 text-right font-mono text-[11px] font-semibold text-slate-700 dark:text-slate-200 md:inline">{q.punts}</span>
								<span class="hidden w-12 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400 md:inline">{q.caramboles ?? 0}</span>
								<span class="hidden w-12 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400 md:inline">{q.entrades ?? 0}</span>
								<span class="w-14 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400">{q.mitjana.toFixed(3)}</span>
							</li>
						{/each}
					</ol>
					<p class="mt-1.5 text-[10px] text-slate-400 dark:text-slate-500">Tots els 1rs de grup + els millors 2ns que calguin per omplir la següent ronda. ✓ = plaça assegurada.</p>
				</div>
			{/if}
			{@const liveNow = scores.filter((s) => Date.now() - new Date(s.captured_at).getTime() < FRESH_MS).map((sc) => ({ sc, grp: sc.group_label || '—' }))}
			{#if liveNow.length}
				<div class="mb-3 rounded-xl bg-red-50 p-3 ring-1 ring-red-200 dark:bg-red-950/40 dark:ring-red-900/50">
					<div class="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-red-700 dark:text-red-400">
						<span class="relative inline-flex h-1.5 w-1.5"><span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75"></span><span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500"></span></span>
						En joc ara ({liveNow.length})
					</div>
					<ul class="space-y-1">
						{#each liveNow as { sc, grp } (sc.video_id)}
							{@const aW = (sc.car_a ?? 0) > (sc.car_b ?? 0)}
							{@const bW = (sc.car_b ?? 0) > (sc.car_a ?? 0)}
							{@const warm = sc.car_a == null && sc.car_b == null}
							<li class="flex items-center gap-2 text-xs">
								<span class="w-6 shrink-0 rounded bg-white/70 text-center font-mono text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">{grp.replace('Grup ', '')}</span>
								{@render playerShort(sc.player_a ?? '—', 'min-w-0 flex-1 truncate font-bold ' + (aW ? 'text-emerald-600 dark:text-emerald-400' : bW ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
								{#if warm}<span class="shrink-0 rounded bg-amber-100 px-1.5 text-[9px] font-semibold uppercase text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">escalfament</span>{:else}<span class="shrink-0 font-mono font-bold text-slate-700 dark:text-slate-200">{sc.car_a}–{sc.car_b}</span>{/if}
								{@render playerShort(sc.player_b ?? '—', 'min-w-0 flex-1 truncate text-right font-bold ' + (bW ? 'text-emerald-600 dark:text-emerald-400' : aW ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
								{#if sc.entrades}<span class="shrink-0 font-mono text-[10px] text-slate-400 dark:text-slate-500">{sc.entrades}e</span>{/if}
								<a href="https://www.youtube.com/watch?v={sc.video_id}" target="_blank" rel="noopener" title="Veure a YouTube" class="shrink-0 text-red-600 hover:opacity-80 dark:text-red-400"><svg viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor" aria-hidden="true"><path d="M23.5 6.2a3 3 0 0 0-2.11-2.12C21.5 3.55 12 3.55 12 3.55s-9.5 0-11.39.53A3 3 0 0 0 .5 6.2 31.4 31.4 0 0 0 0 12a31.4 31.4 0 0 0 .5 5.8 3 3 0 0 0 2.11 2.12C4.5 20.45 12 20.45 12 20.45s9.5 0 11.39-.53A3 3 0 0 0 23.5 17.8 31.4 31.4 0 0 0 24 12a31.4 31.4 0 0 0-.5-5.8zM9.55 15.57V8.43L15.82 12z"/></svg></a>
							</li>
						{/each}
					</ul>
					<p class="mt-1.5 text-[10px] leading-tight text-red-700/70 dark:text-red-400/70">Lectura automàtica del marcador (OCR): pot portar un cert retard i tenir errors puntuals respecte al resultat real.</p>
				</div>
			{/if}
			<div class="grid gap-2.5 sm:grid-cols-2">
				{#each phase.groups as g (g.label)}
					{@const done = groupClosed(g)}
					{@const played = g.matches.filter((m) => m.is_played)}
					<div class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 {liveForGroup(g.label).length ? 'ring-red-200 dark:ring-red-900/50' : done ? 'ring-emerald-200 dark:ring-emerald-900/50' : 'ring-slate-200 dark:ring-slate-800'}">
						<div class="flex items-center justify-between gap-2 px-3 py-1.5 {done ? 'bg-emerald-50 dark:bg-emerald-950/40' : 'bg-slate-50 dark:bg-slate-800/50'}">
							<span class="text-sm font-semibold">{g.label}</span>
							<span class="text-[11px] {done ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'}">{g.n_matches_played}/{done ? g.n_matches_played : g.n_matches_total}</span>
						</div>
						{#if g.venue}<div class="px-3 pt-1 text-[10px] text-slate-400 dark:text-slate-500">{g.venue}</div>{/if}
						{#if g.standings.length}
							<ol class="px-2 py-1">
								{#each g.standings as s, idx}
									{@const pos = provPos(phase, g.label, s.player_name)}
									<li class="flex items-center gap-2 rounded px-1 py-1 {pos === 1 ? 'bg-emerald-50 dark:bg-emerald-950/40' : pos >= 2 ? 'bg-amber-50/60 dark:bg-amber-950/40' : ''}">
										<span class="w-4 text-center text-xs font-mono {pos === 1 ? 'text-emerald-600 dark:text-emerald-400' : pos >= 2 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-400 dark:text-slate-500'}">{pos === 1 ? '▸' : idx + 1}</span>
										{@render player(s.player_name, 'min-w-0 flex-1 truncate text-sm')}
										<span class="shrink-0 font-mono text-[11px] text-slate-400 dark:text-slate-500">{s.mitjana.toFixed(3)}</span>
										<span class="w-5 shrink-0 text-right font-mono text-sm font-semibold">{s.punts}</span>
									</li>
								{/each}
							</ol>
						{:else}
							<p class="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">Sense classificació encara.</p>
						{/if}
						{#if liveForGroup(g.label).length}
								<div class="border-t border-red-100 dark:border-red-900/50 px-3 py-2">
									<div class="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-red-600 dark:text-red-400">
										<span class="relative inline-flex h-1.5 w-1.5">
											<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75"></span>
											<span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500"></span>
										</span>
										En joc ara
									</div>
									<ul class="space-y-1.5">
										{#each liveForGroup(g.label) as sc (sc.video_id)}
											{@const aW = (sc.car_a ?? 0) > (sc.car_b ?? 0)}
											{@const bW = (sc.car_b ?? 0) > (sc.car_a ?? 0)}
											<li>
												<div class="flex items-center justify-between gap-2 text-xs">
													{@render playerShort(sc.player_a ?? '—', 'min-w-0 flex-1 truncate font-bold ' + (aW ? 'text-emerald-600 dark:text-emerald-400' : bW ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
													<span class="shrink-0 font-mono font-bold text-slate-700 dark:text-slate-200">{sc.car_a}–{sc.car_b}</span>
													{@render playerShort(sc.player_b ?? '—', 'min-w-0 flex-1 truncate text-right font-bold ' + (bW ? 'text-emerald-600 dark:text-emerald-400' : aW ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
												</div>
												<div class="mt-0.5 flex items-center justify-center gap-2 text-[10px] text-slate-400 dark:text-slate-500">
													{#if sc.entrades}<span>{sc.entrades} ent.</span>{/if}
													<a href="https://www.youtube.com/watch?v={sc.video_id}" target="_blank" rel="noopener" title="Veure a YouTube" class="inline-flex items-center gap-0.5 font-semibold text-red-600 hover:underline active:underline dark:text-red-400">
														<svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="currentColor" aria-hidden="true"><path d="M23.5 6.2a3 3 0 0 0-2.11-2.12C21.5 3.55 12 3.55 12 3.55s-9.5 0-11.39.53A3 3 0 0 0 .5 6.2 31.4 31.4 0 0 0 0 12a31.4 31.4 0 0 0 .5 5.8 3 3 0 0 0 2.11 2.12C4.5 20.45 12 20.45 12 20.45s9.5 0 11.39-.53A3 3 0 0 0 23.5 17.8 31.4 31.4 0 0 0 24 12a31.4 31.4 0 0 0-.5-5.8zM9.55 15.57V8.43L15.82 12z"/></svg>
														vídeo
													</a>
												</div>
											</li>
										{/each}
									</ul>
								</div>
							{/if}
							{#if played.length}
							<div class="border-t border-slate-100 dark:border-slate-800 px-3 py-2">
								<div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
									Partides disputades
								</div>
								<ul class="space-y-1.5">
									{#each played as m}
										{@const aWin = m.caramboles_a > m.caramboles_b}
										{@const bWin = m.caramboles_b > m.caramboles_a}
										<li>
											<div class="flex items-center justify-between gap-2 text-xs">
												{@render player(m.player_a, 'min-w-0 flex-1 truncate font-bold ' + (aWin ? 'text-emerald-600 dark:text-emerald-400' : bWin ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
												<span class="shrink-0 font-mono font-bold text-slate-700 dark:text-slate-200">{m.caramboles_a}–{m.caramboles_b}</span>
												{@render player(m.player_b, 'min-w-0 flex-1 truncate text-right font-bold ' + (bWin ? 'text-emerald-600 dark:text-emerald-400' : aWin ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
											</div>
											{#if m.entrades}<div class="text-center text-[10px] text-slate-400 dark:text-slate-500">{m.entrades} ent.</div>{/if}
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
				<p class="py-4 text-center text-sm text-slate-400 dark:text-slate-500">Encara no hi ha emparellaments d'aquesta ronda.</p>
			{:else}
				<ul class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
					{#each pairs as m, i}
						{@const aWins = m.is_played && m.punts_a > m.punts_b}
						{@const bWins = m.is_played && m.punts_b > m.punts_a}
						<li class="border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
							<div class="flex items-center justify-between gap-2 text-sm">
								{#if m.player_a}{@render player(m.player_a, 'min-w-0 flex-1 truncate ' + (aWins ? 'font-semibold' : ''))}{:else}<span class="min-w-0 flex-1 truncate text-slate-400 dark:text-slate-500">—</span>{/if}
								<span class="shrink-0 font-mono text-xs {m.is_played ? '' : 'text-slate-400 dark:text-slate-500'}">{m.punts_a}–{m.punts_b}</span>
								{#if m.player_b}{@render player(m.player_b, 'min-w-0 flex-1 truncate text-right ' + (bWins ? 'font-semibold' : ''))}{:else}<span class="min-w-0 flex-1 truncate text-right text-slate-400 dark:text-slate-500">—</span>{/if}
							</div>
							{#if m.is_played}
								<div class="mt-0.5 text-center text-[10px] text-slate-400 dark:text-slate-500">{m.caramboles_a}–{m.caramboles_b} car. · {m.entrades} ent.</div>
							{:else}
								<div class="mt-0.5 text-center text-[10px] text-amber-600 dark:text-amber-400">{phase.ko_matches.length ? 'pendent' : 'calculat'}</div>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		{/if}
	{/if}

	{#if classByRound.length}
		<div class="mt-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
			<div class="mb-2">
				<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-200">Classificació provisional</h2>
				<p class="mt-0.5 text-[10px] leading-tight text-slate-400 dark:text-slate-500">Jugadors ja eliminats, ordenats per la ronda on cauen. S'actualitza a mesura que es tanquen grups i partides.</p>
			</div>
			<div class="space-y-3">
				{#each classByRound as tier (tier.round)}
					{@const lo = tier.rows[0].position}
					{@const hi = tier.rows[tier.rows.length - 1].position}
					<div>
						<div class="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
							<span>{tier.round}</span>
							<span class="font-mono font-normal text-slate-400 dark:text-slate-500">llocs {lo === hi ? lo : `${lo}–${hi}`}</span>
						</div>
						<ol class="space-y-0.5">
							{#each tier.rows as r (r.player_name)}
								<li class="flex items-center gap-2 text-sm">
									<span class="w-8 shrink-0 text-right font-mono text-[11px] text-slate-400 dark:text-slate-500">{r.position}{#if r.is_provisional_position}<span class="text-amber-500" title="Posició provisional">*</span>{/if}</span>
									{@render player(r.player_name, 'min-w-0 flex-1 truncate')}
									<span class="hidden w-14 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400 sm:inline">{r.mitjana.toFixed(3)}</span>
									<span class="w-10 shrink-0 text-right font-mono text-[11px] font-semibold text-slate-700 dark:text-slate-200" title="Punts de rànquing segons el lloc (reglament dels opens)">{r.open_points}</span>
								</li>
							{/each}
						</ol>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[10px] leading-tight text-slate-400 dark:text-slate-500"><span class="text-amber-500">*</span> posició provisional. Punts = puntuació de rànquing segons el lloc final (reglament dels opens).</p>
		</div>
	{/if}
{/if}
