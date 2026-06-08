<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';
	import { follows, toggleFollow, clubFollows, toggleClubFollow } from '$lib/follows';

	interface Pt {
		seq: number;
		mitjana: number | null;
		posicio: number | null;
	}
	interface Serie {
		fcb_id: string;
		nom: string;
		club: string | null;
		color: string;
		pts: Pt[];
		posicio: number | null;
		mitjana: number | null;
	}
	const COLORS = ['#0f172a', '#e0322a', '#2563eb', '#16a34a', '#f59e0b', '#7c3aed', '#db2777', '#0891b2'];

	let allPlayers = $state<{ fcb_id: string; nom: string; club_fcb_id: string | null }[]>([]);
	let clubsMap = $state<Map<string, string>>(new Map());
	let allClubs = $state<{ fcb_id: string; nom: string }[]>([]);
	let rankMap = $state<Map<string, { posicio: number; mitjana: number }>>(new Map());
	let series = $state<Serie[]>([]);
	let loading = $state(true);
	let clubQ = $state('');
	let collapsedClubs = $state(new Set<string>());
	function toggleClubCollapse(id: string) {
		const s = new Set(collapsedClubs);
		s.has(id) ? s.delete(id) : s.add(id);
		collapsedClubs = s;
	}

	onMount(async () => {
		const [{ data: pl }, { data: cl }, { data: maxR }] = await Promise.all([
			supabase.from('players').select('fcb_id, nom, club_fcb_id'),
			supabase.from('clubs').select('fcb_id, nom').order('nom'),
			supabase.from('rankings').select('num_seq').eq('modalitat_codi', 1).order('num_seq', { ascending: false }).limit(1)
		]);
		allPlayers = pl ?? [];
		allClubs = cl ?? [];
		clubsMap = new Map((cl ?? []).map((c) => [c.fcb_id, c.nom]));
		const latest = maxR?.[0]?.num_seq;
		if (latest != null) {
			const { data: re } = await supabase
				.from('ranking_entries')
				.select('player_fcb_id, posicio, mitjana_general')
				.eq('modalitat_codi', 1)
				.eq('num_seq', latest);
			rankMap = new Map((re ?? []).map((r) => [r.player_fcb_id, { posicio: r.posicio, mitjana: r.mitjana_general }]));
		}
		loading = false;
	});

	$effect(() => {
		loadSeries($follows);
	});
	async function loadSeries(ids: string[]) {
		if (!ids.length) {
			series = [];
			return;
		}
		const [{ data: pl }, { data: cl }, { data: re }] = await Promise.all([
			supabase.from('players').select('fcb_id, nom, club_fcb_id').in('fcb_id', ids),
			supabase.from('clubs').select('fcb_id, nom'),
			supabase
				.from('ranking_entries')
				.select('player_fcb_id, num_seq, posicio, mitjana_general')
				.eq('modalitat_codi', 1)
				.in('player_fcb_id', ids)
				.order('num_seq')
		]);
		const pmap = new Map((pl ?? []).map((p) => [p.fcb_id, p]));
		const cmap = new Map((cl ?? []).map((c) => [c.fcb_id, c.nom]));
		const byPlayer = new Map<string, Pt[]>();
		for (const r of re ?? []) {
			if (!byPlayer.has(r.player_fcb_id)) byPlayer.set(r.player_fcb_id, []);
			byPlayer.get(r.player_fcb_id)!.push({ seq: r.num_seq, mitjana: r.mitjana_general, posicio: r.posicio });
		}
		series = ids
			.map((id, i) => {
				const p = pmap.get(id);
				const pts = byPlayer.get(id) ?? [];
				return {
					fcb_id: id,
					nom: p?.nom ?? id,
					club: p?.club_fcb_id ? (cmap.get(p.club_fcb_id) ?? null) : null,
					color: COLORS[i % COLORS.length],
					pts,
					posicio: pts.at(-1)?.posicio ?? null,
					mitjana: pts.at(-1)?.mitjana ?? null
				};
			})
			.sort((a, b) => (a.posicio ?? 9999) - (b.posicio ?? 9999));
	}

	function clubPlayers(clubId: string) {
		return allPlayers
			.filter((p) => p.club_fcb_id === clubId && rankMap.has(p.fcb_id))
			.map((p) => ({ ...p, rank: rankMap.get(p.fcb_id) }))
			.sort((a, b) => (b.rank?.mitjana ?? -1) - (a.rank?.mitjana ?? -1));
	}
	function norm(s: string) {
		return (s ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}
	const clubMatches = $derived(
		clubQ.trim()
			? allClubs.filter((c) => norm(c.nom).includes(norm(clubQ.trim())) && !$clubFollows.includes(c.fcb_id)).slice(0, 8)
			: []
	);

	// Gràfics multi-jugador
	const VBW = 320, VBH = 90, PAD = 8;
	const seqRange = $derived.by(() => {
		const all = series.flatMap((s) => s.pts.map((p) => p.seq));
		return all.length ? [Math.min(...all), Math.max(...all)] : [0, 1];
	});
	function rng(getter: (p: Pt) => number | null): [number, number] {
		const vs = series.flatMap((s) => s.pts.map(getter)).filter((v): v is number => v != null);
		if (!vs.length) return [0, 1];
		let lo = Math.min(...vs), hi = Math.max(...vs);
		if (lo === hi) { lo -= 0.5; hi += 0.5; }
		return [lo, hi];
	}
	function lineFor(s: Serie, getter: (p: Pt) => number | null, invert: boolean): string {
		const [smin, smax] = seqRange;
		const [vmin, vmax] = rng(getter);
		const sw = smax - smin || 1;
		return s.pts.map((p) => {
			const v = getter(p);
			if (v == null) return null;
			const x = PAD + ((p.seq - smin) / sw) * (VBW - 2 * PAD);
			let t = (v - vmin) / (vmax - vmin);
			if (invert) t = 1 - t;
			return `${x.toFixed(1)},${(VBH - PAD - t * (VBH - 2 * PAD)).toFixed(1)}`;
		}).filter(Boolean).join(' ');
	}
	const hasHist = $derived(series.some((s) => s.pts.length >= 2));

	// Dates (122 = juny 2026, mensual saltant agost)
	const MESOS_NOM = ['Gener', 'Febrer', 'Març', 'Abril', 'Maig', 'Juny', 'Juliol', 'Agost', 'Setembre', 'Octubre', 'Novembre', 'Desembre'];
	function ymFromSeq(seq: number): [number, number] {
		let y = 2026, m = 6;
		for (let i = 0; i < 122 - seq; i++) { m--; if (m === 0) { y--; m = 12; } if (m === 8) m = 7; }
		return [y, m];
	}
	const dateFromSeq = (seq: number) => { const [y, m] = ymFromSeq(seq); return `${MESOS_NOM[m - 1]} '${String(y).slice(2)}`; };
	const dateShort = (seq: number) => { const [y, m] = ymFromSeq(seq); return `${String(m).padStart(2, '0')}/${String(y).slice(2)}`; };

	const allSeq = $derived([...new Set(series.flatMap((s) => s.pts.map((p) => p.seq)))].sort((a, b) => a - b));
	const xTicksSeg = $derived.by(() => {
		if (allSeq.length < 2) return [] as number[];
		const [smin, smax] = seqRange;
		return [smin, Math.round((smin + smax) / 2), smax];
	});
	let selSeq = $state<number | null>(null);
	function pickSeq(ev: MouseEvent) {
		const el = ev.currentTarget as Element;
		const rect = el.getBoundingClientRect();
		const [smin, smax] = seqRange;
		if (smax <= smin || !allSeq.length) return;
		const target = smin + ((ev.clientX - rect.left) / rect.width) * (smax - smin);
		selSeq = allSeq.reduce((best, s) => (Math.abs(s - target) < Math.abs(best - target) ? s : best), allSeq[0]);
	}
	function xForSeq(seq: number): number {
		const [smin, smax] = seqRange;
		return PAD + ((seq - smin) / (smax - smin || 1)) * (VBW - 2 * PAD);
	}
	function valAt(s: Serie, seq: number, getter: (p: Pt) => number | null): number | null {
		const pt = s.pts.find((p) => p.seq === seq);
		return pt ? getter(pt) : null;
	}
</script>

<h1 class="mb-3 text-base font-bold">★ Seguiment</h1>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else}
	<!-- CLUBS seguits -->
	<h2 class="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Clubs</h2>
	<input
		bind:value={clubQ}
		placeholder="Afegeix un club…"
		class="mb-2 w-full rounded-lg border-slate-300 bg-white py-2 px-3 text-sm shadow-sm"
	/>
	{#if clubMatches.length}
		<ul class="mb-3 overflow-hidden rounded-lg bg-white ring-1 ring-slate-200">
			{#each clubMatches as c (c.fcb_id)}
				<button
					onclick={() => {
						toggleClubFollow(c.fcb_id);
						clubQ = '';
					}}
					class="flex w-full items-center justify-between border-b border-slate-100 px-3 py-2 text-left text-sm last:border-0 active:bg-slate-50"
				>
					<span class="truncate">{c.nom}</span><span class="text-amber-500">+ seguir</span>
				</button>
			{/each}
		</ul>
	{/if}
	{#each $clubFollows as clubId (clubId)}
		<section class="mb-3 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			<header class="flex items-center gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2">
				<button onclick={() => toggleClubCollapse(clubId)} class="flex min-w-0 flex-1 items-center gap-2 text-left">
					<span class="text-slate-400 transition-transform {collapsedClubs.has(clubId) ? '' : 'rotate-90'}">›</span>
					<span class="truncate text-sm font-bold">{clubsMap.get(clubId) ?? clubId}</span>
					<span class="shrink-0 text-[11px] font-normal text-slate-400">{clubPlayers(clubId).length}</span>
				</button>
				<button onclick={() => toggleClubFollow(clubId)} class="shrink-0 text-xs text-amber-600">★ treure</button>
			</header>
			{#if !collapsedClubs.has(clubId)}
				<ul>
					{#each clubPlayers(clubId) as p, i (p.fcb_id)}
						<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
							<span class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums text-slate-400">{i + 1}</span>
							<a href="/jugador/{p.fcb_id}" class="min-w-0 flex-1 truncate text-sm font-medium active:underline">{p.nom}</a>
							{#if p.rank}
								<span class="shrink-0 font-mono text-xs tabular-nums text-slate-500">#{p.rank.posicio} · {p.rank.mitjana?.toFixed(3)}</span>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/each}
	{#if $clubFollows.length === 0}
		<p class="mb-4 text-[11px] text-slate-400">Cap club seguit. Cerca'n un a dalt.</p>
	{/if}

	<!-- JUGADORS seguits -->
	<h2 class="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">Jugadors</h2>
	{#if series.length === 0}
		<div class="rounded-xl bg-white p-5 text-center text-sm text-slate-400 ring-1 ring-slate-200">
			Cap jugador seguit. Entra a una fitxa i toca <b>☆ Seguir</b>.
		</div>
	{:else}
		{#if hasHist}
			<div class="mb-3 space-y-3">
				{#if selSeq != null}
					<div class="rounded-lg bg-slate-900 px-3 py-2 text-xs text-white">
						<div class="mb-1 font-semibold">{dateFromSeq(selSeq)}</div>
						<div class="flex flex-wrap gap-x-3 gap-y-1">
							{#each series as s}
								{@const m = valAt(s, selSeq, (p) => p.mitjana)}
								{@const po = valAt(s, selSeq, (p) => p.posicio)}
								{#if m != null || po != null}
									<span class="flex items-center gap-1">
										<span class="h-2 w-2 rounded-full" style:background-color={s.color}></span>
										{s.nom.split(',')[0]}: <span class="font-mono font-bold">{m != null ? m.toFixed(3) : '—'}</span> · #{po ?? '—'}
									</span>
								{/if}
							{/each}
						</div>
					</div>
				{/if}
				{#each [['Evolució mitjana', false, (p: Pt) => p.mitjana] as const, ['Evolució posició (amunt=millor)', true, (p: Pt) => p.posicio] as const] as [title, inv, getter]}
					{@const vr = rng(getter)}
					{@const yTop = inv ? vr[0] : vr[1]}
					{@const yBot = inv ? vr[1] : vr[0]}
					<div class="rounded-xl bg-white p-3 ring-1 ring-slate-200">
						<div class="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</div>
						<div class="flex gap-1">
							<div class="flex w-9 flex-col justify-between py-0.5 text-right text-[9px] tabular-nums text-slate-400">
								<span>{inv ? '#' + Math.round(yTop) : yTop.toFixed(2)}</span>
								<span>{inv ? '#' + Math.round(yBot) : yBot.toFixed(2)}</span>
							</div>
							<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickSeq} role="presentation" class="h-24 flex-1 cursor-pointer">
								{#each [0, 0.25, 0.5, 0.75, 1] as f}
									<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke="#eef2f7" stroke-width="1" vector-effect="non-scaling-stroke" />
								{/each}
								{#each series as s}
									<polyline points={lineFor(s, getter, inv)} fill="none" stroke={s.color} stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
								{/each}
								{#if selSeq != null}
									<line x1={xForSeq(selSeq)} y1="2" x2={xForSeq(selSeq)} y2={VBH - 2} stroke="#475569" stroke-width="1" vector-effect="non-scaling-stroke" />
									{#each series as s}
										{@const v = valAt(s, selSeq, getter)}
										{#if v != null}
											{@const t = inv ? 1 - (v - vr[0]) / (vr[1] - vr[0]) : (v - vr[0]) / (vr[1] - vr[0])}
											<circle cx={xForSeq(selSeq)} cy={VBH - PAD - t * (VBH - 2 * PAD)} r="3.5" fill={s.color} stroke="#fff" stroke-width="1" />
										{/if}
									{/each}
								{/if}
							</svg>
						</div>
						<div class="flex justify-between pl-10 text-[9px] tabular-nums text-slate-400">
							{#each xTicksSeg as seq}<span>{dateShort(seq)}</span>{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}
		<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 lg:columns-2 lg:gap-x-6">
			{#each series as s (s.fcb_id)}
				<li class="flex break-inside-avoid items-center gap-2 border-b border-slate-100 px-3 py-2.5 last:border-0">
					<span class="h-3 w-3 shrink-0 rounded-full" style:background-color={s.color}></span>
					<a href="/jugador/{s.fcb_id}" class="min-w-0 flex-1">
						<div class="truncate text-sm font-medium leading-tight">{s.nom}</div>
						{#if s.club}<div class="truncate text-xs text-slate-400">{s.club}</div>{/if}
					</a>
					{#if s.posicio != null}
						<div class="shrink-0 text-right">
							<div class="font-mono text-sm font-bold tabular-nums">#{s.posicio}</div>
							<div class="text-[10px] text-slate-400">{s.mitjana?.toFixed(3) ?? ''}</div>
						</div>
					{/if}
					<button onclick={() => toggleFollow(s.fcb_id)} class="shrink-0 rounded-full px-2 py-1 text-xs text-amber-600" aria-label="treure">★</button>
				</li>
			{/each}
		</ul>
	{/if}
{/if}
