<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, tipusOf, type Open, type OpenLiveRow } from '$lib/supabase';

	let opens = $state<Open[]>([]);
	let liveOpens = $state<OpenLiveRow[]>([]);
	let ranking = $state<any[]>([]);
	let ronda = $state<number | 'calc' | null>(null);
	let q = $state('');
	let cat = $state<'opens' | 'ranking'>('opens');
	let season = $state<string | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const seasons = $derived(
		[...new Set(opens.map((o) => (o as any).temporada).filter(Boolean) as string[])].sort().reverse()
	);
	$effect(() => {
		if (season == null && seasons.length) season = seasons[0];
	});

	let expandedPlayer = $state<string | null>(null);

	function norm(s: string): string {
		return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}

	const genRanking = $derived(ranking.filter((r) => r.genere === 'general'));
	const rondes = $derived([...new Set(genRanking.map((r) => r.ronda as number))].sort((a, b) => a - b));

	// --- Rànquing d'opens CALCULAT (open en curs) -----------------------------
	// Quan un open de 3 bandes s'està jugant, la finestra publicada ja l'inclou
	// però sense classificació definitiva, i el pas del PDF oficial la desalinea
	// (el PDF encara llista la finestra anterior amb el mateix nombre d'opens →
	// «corren els opens però no els punts»). Per això NO fem servir la ronda
	// publicada amb l'open en curs: en construïm una de CALCULADA a partir de la
	// darrera ronda NETA (sense l'open en curs), deixant-hi els 4 opens acabats
	// més recents i afegint-hi l'open en curs amb els punts de la classificació
	// provisional EN DIRECTE (open_live). Marcat «calculat · subjecte a errors».
	function is3BLive(name: string): boolean {
		const u = norm(name);
		if (u.includes('femeni')) return false;
		return /tres ?bandes|3 ?bandes|\b3b\b/.test(u);
	}
	const liveCD = $derived(liveOpens.find((o) => is3BLive(o.name)) ?? null);

	// {fcb_id -> {pts, pos, nom, club}} d'un open en directe. `open_points` ja ve
	// calculat al payload per a TOTHOM (eliminats per posició final, encara en joc
	// per la posició provisional; open_live.py:_alive_classification_rows).
	function provPointsFromLive(r: OpenLiveRow) {
		const ids = r.payload_json?.player_ids ?? {};
		const m = new Map<string, { pts: number; pos: number; nom: string; club: string }>();
		for (const c of r.payload_json?.classification ?? []) {
			const fid = ids[c.player_name];
			if (!fid) continue;
			const prev = m.get(fid);
			if (!prev || c.position < prev.pos)
				m.set(fid, { pts: c.open_points, pos: c.position, nom: c.player_name, club: c.club });
		}
		return m;
	}

	// Noms (normalitzats) dels opens de la finestra de cada ronda.
	const rondaOpens = $derived.by(() => {
		const m = new Map<number, string[]>();
		for (const r of genRanking)
			if (!m.has(r.ronda)) m.set(r.ronda, (r.detall ?? []).map((d: any) => norm(d.open ?? '')));
		return m;
	});
	const cdNorm = $derived(liveCD ? norm(liveCD.name) : null);
	// Rondes "netes": les que NO contenen l'open en curs (la que el conté ve
	// desalineada pel PDF oficial i no l'usem).
	const cleanRondes = $derived(
		cdNorm ? rondes.filter((rn) => !(rondaOpens.get(rn) ?? []).includes(cdNorm)) : rondes
	);
	// Posicions de l'slider: rondes netes + (si hi ha open en curs) la calculada.
	const positions = $derived<(number | 'calc')[]>(liveCD ? [...cleanRondes, 'calc'] : rondes);
	$effect(() => {
		if (!positions.length) return;
		if (ronda == null || !positions.includes(ronda as number | 'calc'))
			ronda = positions[positions.length - 1];
	});
	const isCalc = $derived(ronda === 'calc');

	// Files de la ronda CALCULADA.
	const calcRows = $derived.by(() => {
		if (!liveCD || !cleanRondes.length) return [];
		const baseRonda = cleanRondes[cleanRondes.length - 1];
		const baseRows = genRanking
			.filter((r) => r.ronda === baseRonda)
			.sort((a, b) => a.posicio - b.posicio);
		if (!baseRows.length) return [];
		const L = (baseRows[0].detall ?? []).length;
		const keepStart = Math.max(0, L - 4); // els 4 opens acabats més recents
		const template = (baseRows[0].detall ?? []).slice(keepStart);
		const temp = baseRows[0].ronda_temp;
		const cdPts = provPointsFromLive(liveCD);
		const cdSlot = (pos: number | null, punts: number) => ({
			open: liveCD.name, temp, data: null, pos, punts, prov: true
		});
		const present = new Set<string>();
		const rows: any[] = baseRows.map((r) => {
			const kept = (r.detall ?? []).slice(keepStart).map((d: any) => ({ ...d }));
			const cp = cdPts.get(r.player_fcb_id);
			const det = [...kept, cdSlot(cp ? cp.pos : null, cp ? cp.pts : 0)];
			let total = 0, njug = 0, maxs = 0;
			for (const d of det) { const p = d.punts || 0; if (p > 0) njug++; total += p; maxs = Math.max(maxs, p); }
			present.add(r.player_fcb_id);
			return { ...r, ronda: 'calc', detall: det, punts: total, opens_jugats: njug, _max: maxs };
		});
		// Jugadors que NOMÉS disputen l'open en curs.
		for (const [fid, p] of cdPts) {
			if (present.has(fid)) continue;
			const det = [
				...template.map((d: any) => ({ open: d.open, temp: d.temp, data: d.data ?? null, pos: null, punts: 0 })),
				cdSlot(p.pos, p.pts)
			];
			rows.push({
				genere: 'general', ronda: 'calc', ronda_nom: liveCD.name, ronda_temp: temp,
				player_fcb_id: fid, jugador: p.nom, club: p.club,
				opens_jugats: p.pts > 0 ? 1 : 0, punts: p.pts, detall: det, _max: p.pts
			});
		}
		return rows
			.filter((r) => r.punts > 0)
			.sort(
				(a, b) =>
					b.punts - a.punts ||
					(b._max ?? 0) - (a._max ?? 0) ||
					(a.jugador || '').localeCompare(b.jugador || '')
			)
			.map((r, i) => ({ ...r, posicio: i + 1 }));
	});

	const rondaRows = $derived(
		isCalc ? calcRows : genRanking.filter((r) => r.ronda === ronda).sort((a, b) => a.posicio - b.posicio)
	);
	const rondaInfo = $derived(isCalc ? null : genRanking.find((r) => r.ronda === ronda));
	// Ronda PUBLICADA provisional: la federació ja té la classificació final de
	// l'open més recent però encara no n'ha actualitzat el rànquing oficial, així
	// que `publish_open_ranking` n'ha calculat els punts des de la classificació i
	// ha marcat la ronda provisional=true. Estil ambre, com la ronda calculada.
	const rondaProvisional = $derived(!isCalc && !!(rondaInfo as any)?.provisional);
	const amber = $derived(isCalc || rondaProvisional);
	function stepRonda(d: number) {
		const i = positions.indexOf(ronda as number | 'calc');
		if (i < 0) return;
		ronda = positions[Math.min(positions.length - 1, Math.max(0, i + d))];
	}

	// Tipus de torneig: prioritza el camp publicat; fallback a la regla compartida
	// (tipusOf de $lib/supabase, mirall de fcbillar.torneig_naming).
	const clean = (nom: string) => nom.replace(/\s*-\s*[ÚU]NICA\s*$/i, '').trim();

	// Resum d'una línia d'un Open en directe: fase activa (o l'última amb dades)
	// i progrés de partides, per mostrar-ho a la targeta sense obrir el detall.
	function liveSummary(r: OpenLiveRow): string {
		const phases = r.payload_json?.phases ?? [];
		const active = phases.find((p) => p.is_active) ?? [...phases].reverse().find((p) => {
			if (p.kind === 'group') return p.groups.some((g) => g.n_matches_total > 0);
			return p.ko_matches.length > 0;
		});
		if (!active) return 'sorteig publicat';
		if (active.kind === 'group') {
			const played = active.groups.reduce((a, g) => a + g.n_matches_played, 0);
			const total = active.groups.reduce((a, g) => a + g.n_matches_total, 0);
			return `${active.label} · ${played}/${total} partides`;
		}
		const played = active.ko_matches.filter((m) => m.is_played).length;
		return `${active.label} · ${played}/${active.ko_matches.length}`;
	}

	onMount(async () => {
		// Opens en directe (no bloqueja la resta si falla).
		supabase
			.from('open_live')
			.select('*')
			.order('fcb_division_id')
			.then(({ data }) => (liveOpens = (data ?? []) as OpenLiveRow[]));
		try {
			const { data, error: e } = await supabase.from('opens').select('*').order('nom');
			if (e) throw e;
			opens = (data ?? []) as Open[];
			// open_ranking pot superar el límit de 1000 files: paginem.
			const all: any[] = [];
			for (let from = 0; ; from += 1000) {
				const { data: rk } = await supabase
					.from('open_ranking')
					.select('*')
					.order('ronda', { ascending: false })
					.range(from, from + 999);
				if (!rk?.length) break;
				all.push(...rk);
				if (rk.length < 1000) break;
			}
			ranking = all;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const filtered = $derived(
		opens
			.filter((o) => tipusOf(o) === 'open')
			.filter((o) => !season || (o as any).temporada === season)
			.filter((o) => (q.trim() ? norm(o.nom).includes(norm(q.trim())) : true))
	);
</script>

<!-- Opens EN DIRECTE: targetes destacades quan n'hi ha en curs -->
{#if liveOpens.length}
	<section class="mb-4">
		<div class="mb-1.5 flex items-center gap-1.5">
			<span class="relative flex h-2 w-2">
				<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
				<span class="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
			</span>
			<h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">En directe</h2>
		</div>
		<div class="grid gap-2 sm:grid-cols-2">
			{#each liveOpens as r (r.fcb_division_id)}
				<a
					href="/opens/directe/{r.fcb_division_id}"
					class="block rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-emerald-200 dark:ring-emerald-900/50 active:bg-emerald-50 dark:active:bg-emerald-950/40"
				>
					<div class="flex items-start justify-between gap-2">
						<div class="min-w-0 text-sm font-semibold leading-tight">{r.name}</div>
						{#if r.modality}
							<span class="shrink-0 rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{r.modality}</span>
						{/if}
					</div>
					<div class="mt-1 text-[11px] text-slate-400 dark:text-slate-500">{liveSummary(r)}</div>
				</a>
			{/each}
		</div>
	</section>
{/if}

<!-- Toggle Opens / Campionats de Catalunya -->
<div class="mb-3 inline-flex rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5 text-sm">
	<button
		onclick={() => (cat = 'opens')}
		class="rounded-md px-3 py-1 font-medium {cat === 'opens' ? 'bg-white dark:bg-slate-700 shadow-sm' : 'text-slate-500 dark:text-slate-400'}"
		>Opens</button>
	<button
		onclick={() => (cat = 'ranking')}
		class="rounded-md px-3 py-1 font-medium {cat === 'ranking' ? 'bg-white dark:bg-slate-700 shadow-sm' : 'text-slate-500 dark:text-slate-400'}"
		>Rànquing</button>
</div>

{#if cat === 'opens' && seasons.length > 1}
	<select
		bind:value={season}
		class="mb-3 w-full rounded-lg border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-2.5 px-3 text-sm shadow-sm"
	>
		{#each seasons as s}<option value={s}>Temporada {s}</option>{/each}
	</select>
{/if}

<input
	bind:value={q}
	inputmode="search"
	placeholder="Cerca…"
	class="mb-3 w-full rounded-lg border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-2.5 px-3 text-sm shadow-sm"
/>

{#if error}
	<div class="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-300">{error}</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
{:else if cat === 'ranking'}
	{#if rondes.length === 0}
		<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Sense rànquing d'opens.</p>
	{:else}
		{#if isCalc}
				<div class="mb-3 flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-[11px] leading-snug text-amber-800 dark:text-amber-300">
					<span class="mt-0.5 shrink-0">⚠</span>
					<span>
						Rànquing <strong>calculat</strong>, <strong>no oficial</strong>: inclou <strong>{liveCD?.name}</strong> en directe amb els punts de la classificació provisional (els qui encara juguen, segons l'ordre de la darrera fase acabada). Els qui no el disputen hi tenen 0. Pot contenir errors fins que l'open sigui definitiu.
					</span>
				</div>
			{:else if rondaProvisional}
				<div class="mb-3 flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-[11px] leading-snug text-amber-800 dark:text-amber-300">
					<span class="mt-0.5 shrink-0">⚠</span>
					<span>
						Rànquing <strong>provisional</strong>: inclou <strong>{rondaInfo?.ronda_nom}</strong> amb els punts de la seva <strong>classificació final</strong>. La federació encara no n'ha actualitzat el rànquing oficial; subjecte a canvis (penalitzacions per incompareixença, desempats) quan es publiqui.
					</span>
				</div>
			{/if}
			<div class="mb-3 flex items-center justify-between gap-2 rounded-lg {amber ? 'bg-amber-600 dark:bg-amber-700' : 'bg-slate-900 dark:bg-slate-700'} px-2 py-2 text-white">
			<button onclick={() => stepRonda(-1)} class="rounded px-3 py-1 text-lg active:bg-slate-700" aria-label="anterior">‹</button>
			<div class="min-w-0 text-center">
				<div class="flex items-center justify-center gap-1.5 text-xs font-semibold">
						<span class="truncate">Fins a {isCalc ? (liveCD?.name ?? '') : (rondaInfo?.ronda_nom ?? '')}</span>
						{#if isCalc}<span class="shrink-0 rounded bg-white/25 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider">calculat</span>{:else if rondaProvisional}<span class="shrink-0 rounded bg-white/25 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider">provisional</span>{/if}
					</div>
				<div class="text-[10px] {amber ? 'text-amber-100' : 'text-slate-300 dark:text-slate-600'}">{isCalc ? 'en directe · calculat' : `${rondaInfo?.ronda_temp ?? ''} · ronda ${ronda}/${rondes.length}${rondaProvisional ? ' · provisional' : ''}`}</div>
			</div>
			<button onclick={() => stepRonda(1)} class="rounded px-3 py-1 text-lg active:bg-slate-700" aria-label="següent">›</button>
		</div>
		<div class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
			<div class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
				<span class="w-6 text-center">#</span>
				<span class="flex-1">Jugador</span>
				<span class="w-7 text-center">Op.</span>
				<span class="w-10 text-right">Punts</span>
			</div>
			<ul>
				{#each rondaRows.filter((r) => !q.trim() || norm(r.jugador ?? '').includes(norm(q.trim()))) as r (r.player_fcb_id)}
					<li class="border-b border-slate-100 dark:border-slate-800 last:border-0">
						<div class="flex items-center gap-2 px-3 py-2">
							<span class="w-6 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500 dark:text-amber-400' : 'text-slate-400 dark:text-slate-500'}">{r.posicio}</span>
							<div class="min-w-0 flex-1">
								<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
								{#if r.club}<div class="truncate text-[11px] text-slate-400 dark:text-slate-500">{r.club}</div>{/if}
							</div>
							<span class="w-7 shrink-0 text-center text-xs tabular-nums text-slate-500 dark:text-slate-400">{r.opens_jugats}</span>
							<button
								onclick={() => (expandedPlayer = expandedPlayer === r.player_fcb_id ? null : r.player_fcb_id)}
								class="flex w-12 shrink-0 items-center justify-end gap-0.5 font-mono text-sm font-bold tabular-nums"
							>
								{r.punts}
								<span class="text-[9px] text-slate-400 dark:text-slate-500">{expandedPlayer === r.player_fcb_id ? '▴' : '▾'}</span>
							</button>
						</div>
						{#if expandedPlayer === r.player_fcb_id && r.detall?.length}
							<div class="space-y-0.5 bg-slate-50 dark:bg-slate-800/50 px-3 pb-2 pl-11 pt-1">
								{#each r.detall as d}
									<div class="flex items-center justify-between gap-2 text-[11px] {d.pos || d.penal || d.absent ? '' : 'opacity-50'}">
										<span class="min-w-0 truncate {d.penal ? 'font-medium text-red-500 dark:text-red-400' : d.prov ? 'font-medium text-amber-600 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'}">
											{d.open}{d.temp ? ` ${d.temp}` : ''} · {d.penal
												? 'no presentat'
												: d.absent
													? 'absència justif.'
													: d.pos
														? `${d.pos}è${d.prov ? ' (prov.)' : ''}`
														: 'no inscrit'}
										</span>
										<span class="shrink-0 font-mono font-semibold {d.penal ? 'text-red-500 dark:text-red-400' : d.prov ? 'text-amber-600 dark:text-amber-400' : 'text-slate-700 dark:text-slate-200'}">{d.punts}</span>
									</div>
								{/each}
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		</div>
		<p class="px-1 py-2 text-center text-[10px] text-slate-400 dark:text-slate-500">Rànquing Català d'Opens 3 Bandes · suma dels 5 darrers opens (Art. XVIII).{isCalc ? ' Ronda CALCULADA: els 4 darrers opens acabats + l’open en curs amb punts provisionals en directe.' : rondaProvisional ? ' Ronda PROVISIONAL: punts de la classificació final del darrer open, pendent que la federació actualitzi el rànquing oficial.' : ''}</p>
	{/if}
{:else if filtered.length === 0}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Cap open.</p>
{:else}
	<ul class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
		{#each filtered as o (o.open_id)}
			<li class="border-b border-slate-100 dark:border-slate-800 last:border-0">
				<a href="/opens/{o.open_id}" class="flex items-center gap-3 px-3 py-2.5 active:bg-slate-50 dark:active:bg-slate-800/50">
					<div class="min-w-0 flex-1 truncate text-sm font-medium leading-tight">{clean(o.nom)}</div>
					<span class="shrink-0 text-slate-300 dark:text-slate-600">›</span>
				</a>
			</li>
		{/each}
	</ul>
	<p class="px-1 py-3 text-center text-[11px] text-slate-400 dark:text-slate-500">
		{filtered.length} opens
	</p>
{/if}
