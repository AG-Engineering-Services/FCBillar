<script lang="ts">
	import { page } from '$app/stores';
	import { supabase, type GameRow } from '$lib/supabase';
	import { follows, toggleFollow } from '$lib/follows';

	const fcbId = $derived($page.params.fcb_id);

	let nom = $state('');
	let club = $state<string | null>(null);
	let games = $state<GameRow[]>([]);
	let modalitats = $state<{ codi: number; nom: string }[]>([]);
	let selMod = $state<number | null>(null);
	let shown = $state(60);
	let serieFilter = $state(false);
	let clubHist = $state<{ temporada: string; club: string | null }[]>([]);
	let openRank = $state<{ ronda: number; posicio: number; punts: number }[]>([]);
	const openCur = $derived.by(() => {
		if (!openRank.length) return null;
		const maxR = Math.max(...openRank.map((o) => o.ronda));
		return openRank.find((o) => o.ronda === maxR) ?? null;
	});
	const openBest = $derived(openRank.length ? Math.min(...openRank.map((o) => o.posicio)) : null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		const id = fcbId;
		if (id) loadAll(id);
	});

	async function loadAll(id: string) {
		loading = true;
		error = null;
		try {
			const { data: p } = await supabase
				.from('players')
				.select('nom, club_fcb_id')
				.eq('fcb_id', id)
				.maybeSingle();
			nom = p?.nom ?? id;
			if (p?.club_fcb_id) {
				const { data: c } = await supabase
					.from('clubs')
					.select('nom')
					.eq('fcb_id', p.club_fcb_id)
					.maybeSingle();
				club = c?.nom ?? null;
			} else {
				club = null;
			}

			const { data: g, error: e } = await supabase
				.from('games')
				.select('*')
				.or(`player1_fcb_id.eq.${id},player2_fcb_id.eq.${id}`)
				.order('data_partida', { ascending: false })
				.limit(1000);
			if (e) throw e;
			games = (g ?? []) as GameRow[];

			const { data: pc } = await supabase
				.from('player_clubs')
				.select('temporada, club')
				.eq('player_fcb_id', id)
				.order('temporada', { ascending: false });
			clubHist = pc ?? [];

			const { data: or } = await supabase
				.from('open_ranking')
				.select('ronda, posicio, punts')
				.eq('player_fcb_id', id)
				.eq('genere', 'general');
			openRank = or ?? [];

			const present = [...new Set(games.map((x) => x.modalitat_codi).filter((v) => v != null))];
			const { data: md } = await supabase
				.from('modalitats')
				.select('codi_fcb, nom')
				.in('codi_fcb', present.length ? present : [1]);
			const cnt = (c: number) => games.filter((x) => x.modalitat_codi === c).length;
			modalitats = (md ?? [])
				.map((m) => ({ codi: m.codi_fcb, nom: m.nom }))
				.sort((a, b) => cnt(b.codi) - cnt(a.codi));
			selMod = modalitats[0]?.codi ?? null;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	function persp(g: GameRow) {
		const me1 = g.player1_fcb_id === fcbId;
		const myCar = (me1 ? g.caramboles1 : g.caramboles2) ?? 0;
		const oppCar = (me1 ? g.caramboles2 : g.caramboles1) ?? 0;
		return {
			date: g.data_partida,
			comp: g.competicio,
			opp: (me1 ? g.player2_nom : g.player1_nom) ?? '—',
			oppId: me1 ? g.player2_fcb_id : g.player1_fcb_id,
			myCar,
			oppCar,
			mySerie: (me1 ? g.serie_max1 : g.serie_max2) ?? 0,
			ent: g.entrades ?? 0,
			won: g.guanyador_fcb_id === fcbId,
			tie: g.guanyador_fcb_id == null && g.caramboles1 === g.caramboles2
		};
	}

	const modGames = $derived(games.filter((g) => selMod == null || g.modalitat_codi === selMod));
	function computeKpi(gs: GameRow[]) {
		let car = 0, ent = 0, w = 0, l = 0, t = 0, sm = 0, n = 0;
		for (const g of gs) {
			const p = persp(g);
			n++;
			car += p.myCar;
			ent += p.ent;
			sm = Math.max(sm, p.mySerie);
			if (p.tie) t++;
			else if (p.won) w++;
			else l++;
		}
		return { n, mitjana: ent ? car / ent : 0, sm, w, l, t, pct: n ? Math.round((100 * w) / n) : 0 };
	}
	const kpi = $derived(computeKpi(modGames));
	// Temporada actual: comença l'1 d'agost.
	const seasonStart = (() => {
		const d = new Date();
		return `${d.getMonth() + 1 >= 8 ? d.getFullYear() : d.getFullYear() - 1}-08-01`;
	})();
	const seasonKpi = $derived(computeKpi(modGames.filter((g) => (g.data_partida ?? '') >= seasonStart)));
	const displayGames = $derived(
		serieFilter && kpi.sm > 0
			? modGames.filter((g) => persp(g).mySerie === kpi.sm)
			: modGames.slice(0, shown)
	);
	// Cara a cara (només històric): rival amb més victòries / derrotes / partides (si >1).
	const h2h = $derived.by(() => {
		const map = new Map<string, { nom: string; id: string | null; won: number; lost: number; total: number }>();
		for (const g of modGames) {
			const p = persp(g);
			const key = p.oppId ?? p.opp;
			if (!map.has(key)) map.set(key, { nom: p.opp, id: p.oppId, won: 0, lost: 0, total: 0 });
			const e = map.get(key)!;
			e.total++;
			if (!p.tie) {
				if (p.won) e.won++;
				else e.lost++;
			}
		}
		const arr = [...map.values()];
		const top = (sel: (e: (typeof arr)[number]) => number) =>
			arr.filter((e) => sel(e) >= 2).sort((a, b) => sel(b) - sel(a))[0] ?? null;
		return { won: top((e) => e.won), lost: top((e) => e.lost), played: top((e) => e.total) };
	});

	// Evolució al rànquing (per la modalitat seleccionada): mitjana i posició.
	let rankHist = $state<{ num_seq: number; posicio: number | null; mitjana: number | null }[]>([]);
	$effect(() => {
		const id = fcbId;
		const mod = selMod;
		if (id && mod != null) loadRankHist(id, mod);
		else rankHist = [];
	});
	async function loadRankHist(id: string, mod: number) {
		const { data } = await supabase
			.from('ranking_entries')
			.select('num_seq, posicio, mitjana_general')
			.eq('player_fcb_id', id)
			.eq('modalitat_codi', mod)
			.order('num_seq', { ascending: true });
		rankHist = (data ?? []).map((r) => ({
			num_seq: r.num_seq,
			posicio: r.posicio,
			mitjana: r.mitjana_general
		}));
		selIdx = null;
	}
	// Marques de l'eix X (divisions) amb el número de rànquing de referència.
	const xTicks = $derived.by(() => {
		const n = rankHist.length;
		if (n < 2) return [] as { x: number; label: string }[];
		const k = Math.min(4, n);
		const ticks: { x: number; label: string }[] = [];
		for (let i = 0; i < k; i++) {
			const idx = Math.round((i * (n - 1)) / (k - 1));
			ticks.push({ x: PAD + (idx / (n - 1)) * (VBW - 2 * PAD), label: dateShort(rankHist[idx].num_seq) });
		}
		return ticks;
	});
	const bestPos = $derived.by(() => {
		const ps = rankHist.map((r) => r.posicio).filter((v): v is number => v != null);
		return ps.length ? Math.min(...ps) : null;
	});
	const lastMitjana = $derived(rankHist.at(-1)?.mitjana ?? null);
	const currentPos = $derived(rankHist.at(-1)?.posicio ?? null);

	const VBW = 300;
	const VBH = 84;
	const PAD = 10;
	function chartData(vals: (number | null)[], invert = false) {
		const valid = vals.filter((v): v is number => v != null);
		if (valid.length < 2) return null;
		const lo = Math.min(...valid);
		const hi = Math.max(...valid);
		let min = lo;
		let max = hi;
		if (min === max) {
			min -= 0.5;
			max += 0.5;
		}
		const n = vals.length;
		const pts: { x: number; y: number; v: number }[] = [];
		vals.forEach((v, i) => {
			if (v == null) return;
			const x = n > 1 ? PAD + (i / (n - 1)) * (VBW - 2 * PAD) : VBW / 2;
			let t = (v - min) / (max - min);
			if (invert) t = 1 - t;
			pts.push({ x, y: VBH - PAD - t * (VBH - 2 * PAD), v });
		});
		const line = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
		const base = (VBH - PAD).toFixed(1);
		const area = `${pts[0].x.toFixed(1)},${base} ${line} ${pts.at(-1)!.x.toFixed(1)},${base}`;
		return { line, area, lo, hi, last: pts.at(-1)!, n: valid.length, pts };
	}
	const mitjanaChart = $derived(chartData(rankHist.map((r) => r.mitjana)));
	const posChart = $derived(chartData(rankHist.map((r) => r.posicio), true));

	// Selecció de punt (clic): mostra els valors del punt més proper als dos gràfics.
	let selIdx = $state<number | null>(null);
	function pickPoint(ev: MouseEvent) {
		const el = ev.currentTarget as Element;
		const rect = el.getBoundingClientRect();
		const n = rankHist.length;
		if (n < 2) return;
		const frac = (ev.clientX - rect.left) / rect.width;
		selIdx = Math.max(0, Math.min(n - 1, Math.round(frac * (n - 1))));
	}

	// Data de publicació d'un rànquing (122 = juny 2026, mensual saltant agost).
	const MESOS_NOM = [
		'Gener', 'Febrer', 'Març', 'Abril', 'Maig', 'Juny',
		'Juliol', 'Agost', 'Setembre', 'Octubre', 'Novembre', 'Desembre'
	];
	function ymFromSeq(seq: number): [number, number] {
		let y = 2026,
			m = 6;
		for (let i = 0; i < 122 - seq; i++) {
			m--;
			if (m === 0) {
				y--;
				m = 12;
			}
			if (m === 8) m = 7;
		}
		return [y, m];
	}
	function dateFromSeq(seq: number): string {
		const [y, m] = ymFromSeq(seq);
		return `${MESOS_NOM[m - 1]} '${String(y).slice(2)}`;
	}
	function dateShort(seq: number): string {
		const [y, m] = ymFromSeq(seq);
		return `${String(m).padStart(2, '0')}/${String(y).slice(2)}`;
	}

	function fmtDate(d: string | null): string {
		if (!d) return '';
		const [y, m, day] = d.split('-');
		return `${day}/${m}/${y.slice(2)}`;
	}
	function back() {
		if (typeof history !== 'undefined' && history.length > 1) history.back();
		else location.href = '/';
	}
</script>

<button onclick={back} class="mb-2 inline-flex items-center gap-1 text-sm text-slate-500">
	<span aria-hidden="true">←</span> Rànquings
</button>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
{:else}
	<div class="mb-3 flex items-start justify-between gap-3">
		<div class="min-w-0">
			<h1 class="text-lg font-bold leading-tight">{nom}</h1>
			{#if club}<p class="text-sm text-slate-400">{club}</p>{/if}
		</div>
		<button
			onclick={() => toggleFollow(fcbId)}
			class="shrink-0 rounded-full px-3 py-1.5 text-sm font-medium {$follows.includes(fcbId)
				? 'bg-amber-100 text-amber-700 ring-1 ring-amber-300'
				: 'bg-slate-900 text-white'}"
		>
			{$follows.includes(fcbId) ? '★ Seguint' : '☆ Seguir'}
		</button>
	</div>

	{#if modalitats.length > 1}
		<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
			{#each modalitats as m}
				<button
					onclick={() => {
						selMod = m.codi;
						shown = 60;
					}}
					class="shrink-0 rounded-full px-3 py-1 text-sm font-medium {m.codi === selMod
						? 'bg-slate-900 text-white'
						: 'bg-white text-slate-600 ring-1 ring-slate-200'}"
				>{m.nom}</button>
			{/each}
		</div>
	{/if}

	{#if loading}
		<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
	{:else}
		<div class="lg:grid lg:grid-cols-2 lg:gap-6 lg:items-start">
			<div class="min-w-0">
			<!-- KPIs -->
			<div class="mb-1 px-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-400">Històric</div>
			<div class="mb-3 grid grid-cols-4 gap-2">
				{#each [['Partides', kpi.n, ''], ['Mitjana', kpi.mitjana.toFixed(3), ''], ['Sèrie màx', kpi.sm, 'sm'], ['% vict.', kpi.pct + '%', '']] as [label, val, key]}
					<button onclick={() => { if (key === 'sm') serieFilter = !serieFilter; }} class="rounded-xl bg-white px-2 py-2.5 text-center ring-1 {key === 'sm' && serieFilter ? 'ring-2 ring-blue-500' : 'ring-slate-200'}">
						<div class="font-mono text-base font-bold tabular-nums">{val}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
					</button>
				{/each}
			</div>
			<p class="mb-3 px-1 text-[11px] text-slate-400">{kpi.w} G · {kpi.l} P{kpi.t ? ` · ${kpi.t} E` : ''}</p>
			<div class="mb-1 px-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-400">Temporada actual</div>
			<div class="mb-2 grid grid-cols-4 gap-2">
				{#each [['Partides', seasonKpi.n], ['Mitjana', seasonKpi.mitjana.toFixed(3)], ['Sèrie màx', seasonKpi.sm], ['% vict.', seasonKpi.pct + '%']] as [label, val]}
					<div class="rounded-xl bg-white px-2 py-2.5 text-center ring-1 ring-slate-200">
						<div class="font-mono text-base font-bold tabular-nums">{val}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
					</div>
				{/each}
			</div>
			<p class="mb-2 px-1 text-[11px] text-slate-400">
				Temporada des de l'1 d'agost.
			</p>
			{#if serieFilter}
				<p class="mb-2 px-1 text-[11px] text-blue-600">Partides amb la sèrie màxima ({kpi.sm}). Torna a tocar «Sèrie màx» per desfer.</p>
			{/if}

		{#if openRank.length}
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Rànquing d'Opens 3 Bandes</div>
				<div class="grid grid-cols-3 gap-2">
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">#{openCur?.posicio ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">posició actual</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-emerald-600">#{openBest ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">millor posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">{openCur?.punts ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">punts</div>
					</div>
				</div>
			</div>
		{/if}

		{#if h2h.won || h2h.lost || h2h.played}
			<div class="mb-4 space-y-1.5 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="text-[10px] font-bold uppercase tracking-wide text-slate-400">Cara a cara (històric)</div>
				{#if h2h.played}
					<div class="flex items-center gap-2 text-sm">
						<span class="shrink-0 text-slate-500">Més jugat amb</span>
						<a href="/jugador/{h2h.played.id}" class="min-w-0 flex-1 truncate text-right font-medium active:underline">{h2h.played.nom}</a>
						<span class="shrink-0 font-mono font-bold tabular-nums">{h2h.played.total}</span>
					</div>
				{/if}
				{#if h2h.won}
					<div class="flex items-center gap-2 text-sm">
						<span class="shrink-0 text-slate-500">Més guanyat a</span>
						<a href="/jugador/{h2h.won.id}" class="min-w-0 flex-1 truncate text-right font-medium active:underline">{h2h.won.nom}</a>
						<span class="shrink-0 font-mono font-bold tabular-nums text-emerald-600">{h2h.won.won} G</span>
					</div>
				{/if}
				{#if h2h.lost}
					<div class="flex items-center gap-2 text-sm">
						<span class="shrink-0 text-slate-500">Més perdut amb</span>
						<a href="/jugador/{h2h.lost.id}" class="min-w-0 flex-1 truncate text-right font-medium active:underline">{h2h.lost.nom}</a>
						<span class="shrink-0 font-mono font-bold tabular-nums text-red-500">{h2h.lost.lost} P</span>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Evolució al rànquing -->
		{#if mitjanaChart}
			{#if selIdx != null && rankHist[selIdx]}
				<div class="mb-2 flex items-center justify-center gap-3 rounded-lg bg-slate-900 px-3 py-1.5 text-xs text-white">
					<span class="font-semibold">{dateFromSeq(rankHist[selIdx].num_seq)}</span>
					<span>mitjana <span class="font-mono font-bold">{rankHist[selIdx].mitjana?.toFixed(3) ?? '—'}</span></span>
					<span>posició <span class="font-mono font-bold">#{rankHist[selIdx].posicio ?? '—'}</span></span>
				</div>
			{:else}
				<p class="mb-2 text-center text-[11px] text-slate-400">Toca un gràfic per veure els valors d'un rànquing</p>
			{/if}
			<div class="mb-4 space-y-3">
				<!-- Mitjana -->
				<div class="rounded-xl bg-white p-3 ring-1 ring-slate-200">
					<div class="mb-2 flex items-end justify-between">
						<span class="text-xs font-semibold uppercase tracking-wide text-slate-400"
							>Mitjana al rànquing</span>
						<div class="flex gap-4 text-right">
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums">
									{lastMitjana != null ? lastMitjana.toFixed(3) : '—'}
								</div>
								<div class="text-[10px] text-slate-400">actual</div>
							</div>
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums text-emerald-600">
									{mitjanaChart.hi.toFixed(3)}
								</div>
								<div class="text-[10px] text-slate-400">millor</div>
							</div>
						</div>
					</div>
					<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickPoint} role="presentation" class="h-24 w-full cursor-pointer">
							{#each [0, 0.25, 0.5, 0.75, 1] as f}
								<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke="#eef2f7" stroke-width="1" vector-effect="non-scaling-stroke" />
							{/each}
						{#each xTicks as t}
							<line x1={t.x} y1="2" x2={t.x} y2={VBH - 2} stroke="#e2e8f0" stroke-width="1" vector-effect="non-scaling-stroke" />
						{/each}
						<polyline points={mitjanaChart.area} fill="#0f172a" opacity="0.06" />
						<polyline
							points={mitjanaChart.line}
							fill="none"
							stroke="#0f172a"
							stroke-width="1.5"
							stroke-linejoin="round"
							vector-effect="non-scaling-stroke" />
						<circle cx={mitjanaChart.last.x} cy={mitjanaChart.last.y} r="3" fill="#0f172a" />
							{#if selIdx != null && mitjanaChart.pts[selIdx]}
								<line x1={mitjanaChart.pts[selIdx].x} y1="2" x2={mitjanaChart.pts[selIdx].x} y2={VBH - 2} stroke="#0f172a" stroke-width="1" vector-effect="non-scaling-stroke" />
								<circle cx={mitjanaChart.pts[selIdx].x} cy={mitjanaChart.pts[selIdx].y} r="4" fill="#0f172a" stroke="#fff" stroke-width="1.5" />
							{/if}
					</svg>
					<div class="flex justify-between px-0.5 text-[9px] tabular-nums text-slate-300">
						{#each xTicks as t}<span>{t.label}</span>{/each}
					</div>
				</div>
				<!-- Posició -->
				<div class="rounded-xl bg-white p-3 ring-1 ring-slate-200">
					<div class="mb-2 flex items-end justify-between">
						<span class="text-xs font-semibold uppercase tracking-wide text-slate-400"
							>Posició al rànquing</span>
						<div class="flex gap-4 text-right">
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums">
									#{currentPos ?? '—'}
								</div>
								<div class="text-[10px] text-slate-400">actual</div>
							</div>
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums text-amber-500">
									#{bestPos ?? '—'}
								</div>
								<div class="text-[10px] text-slate-400">millor</div>
							</div>
						</div>
					</div>
					{#if posChart}
						<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickPoint} role="presentation" class="h-24 w-full cursor-pointer">
							{#each [0, 0.25, 0.5, 0.75, 1] as f}
								<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke="#eef2f7" stroke-width="1" vector-effect="non-scaling-stroke" />
							{/each}
							{#each xTicks as t}
								<line x1={t.x} y1="2" x2={t.x} y2={VBH - 2} stroke="#fde68a" stroke-width="1" vector-effect="non-scaling-stroke" />
							{/each}
							<polyline points={posChart.area} fill="#f59e0b" opacity="0.08" />
							<polyline
								points={posChart.line}
								fill="none"
								stroke="#f59e0b"
								stroke-width="1.5"
								stroke-linejoin="round"
								vector-effect="non-scaling-stroke" />
							<circle cx={posChart.last.x} cy={posChart.last.y} r="3" fill="#f59e0b" />
								{#if selIdx != null && posChart.pts[selIdx]}
									<line x1={posChart.pts[selIdx].x} y1="2" x2={posChart.pts[selIdx].x} y2={VBH - 2} stroke="#b45309" stroke-width="1" vector-effect="non-scaling-stroke" />
									<circle cx={posChart.pts[selIdx].x} cy={posChart.pts[selIdx].y} r="4" fill="#f59e0b" stroke="#fff" stroke-width="1.5" />
								{/if}
						</svg>
						<div class="flex justify-between px-0.5 text-[9px] tabular-nums text-slate-300">
							{#each xTicks as t}<span>{t.label}</span>{/each}
						</div>
						<p class="mt-1 text-right text-[10px] text-slate-300">{posChart.n} rànquings · amunt = millor</p>
					{/if}
				</div>
			</div>
		{/if}

		{#if clubHist.length}
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Clubs per temporada</div>
				<div class="flex flex-wrap gap-1.5">
					{#each clubHist as ch}
						<div class="rounded-lg bg-slate-50 px-2 py-1 text-[11px] ring-1 ring-slate-200">
							<span class="font-semibold text-slate-700">{ch.temporada}</span>
							<span class="text-slate-500">· {ch.club ?? '—'}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

			</div>
			<div class="min-w-0">
			<!-- Partides recents -->
		<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			{#each displayGames as g (g.id)}
				{@const p = persp(g)}
				<li class="flex items-center gap-3 border-b border-slate-100 px-3 py-2 last:border-0">
					<span
						class="w-6 shrink-0 rounded text-center text-xs font-bold {p.tie
							? 'text-slate-400'
							: p.won
								? 'text-emerald-600'
								: 'text-red-500'}">{p.tie ? 'E' : p.won ? 'G' : 'P'}</span>
					<div class="min-w-0 flex-1">
						{#if p.oppId}
							<a
								href="/jugador/{p.oppId}"
								class="block truncate text-sm font-medium leading-tight underline-offset-2 active:underline"
								>{p.opp}</a>
						{:else}
							<div class="truncate text-sm leading-tight">{p.opp}</div>
						{/if}
						<div class="text-[11px] text-slate-400">
							{fmtDate(p.date)} · {p.comp ?? ''}{p.mySerie ? ` · S.M. ${p.mySerie}` : ''}
						</div>
					</div>
					<div class="shrink-0 text-right">
						<div class="font-mono text-sm tabular-nums">{p.myCar}–{p.oppCar}</div>
						<div class="text-[11px] tabular-nums text-slate-400">
							{p.ent ? `${(p.myCar / p.ent).toFixed(3)} · ${p.ent} ent.` : '—'}
						</div>
					</div>
				</li>
			{/each}
		</ul>
		{#if !serieFilter && modGames.length > shown}
			<button
				onclick={() => (shown += 60)}
				class="mt-2 w-full rounded-lg bg-white py-2 text-sm font-medium text-slate-600 ring-1 ring-slate-200 active:bg-slate-50"
			>
				Carregar més ({shown} de {modGames.length})
			</button>
		{:else if modGames.length > 60}
			<p class="px-1 py-3 text-center text-[11px] text-slate-400">{modGames.length} partides</p>
		{/if}
			</div>
		</div>
	{/if}
{/if}
