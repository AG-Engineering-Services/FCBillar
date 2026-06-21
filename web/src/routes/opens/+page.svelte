<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, tipusOf, type Open, type OpenLiveRow } from '$lib/supabase';

	let opens = $state<Open[]>([]);
	let liveOpens = $state<OpenLiveRow[]>([]);
	let ranking = $state<any[]>([]);
	let ronda = $state<number | null>(null);
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
	const genRanking = $derived(ranking.filter((r) => r.genere === 'general'));
	const rondes = $derived([...new Set(genRanking.map((r) => r.ronda as number))].sort((a, b) => a - b));
	$effect(() => {
		if (ronda == null && rondes.length) ronda = rondes[rondes.length - 1];
	});
	const rondaRows = $derived(genRanking.filter((r) => r.ronda === ronda).sort((a, b) => a.posicio - b.posicio));
	const rondaInfo = $derived(genRanking.find((r) => r.ronda === ronda));
	function stepRonda(d: number) {
		const i = rondes.indexOf(ronda as number);
		ronda = rondes[Math.min(rondes.length - 1, Math.max(0, i + d))];
	}

	function norm(s: string): string {
		return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}

	// --- Rànquing d'opens CALCULAT (open en curs) -----------------------------
	// Si un dels 5 opens de la finestra vigent encara s'està jugant, el rànquing
	// publicat el deixa a 0 per a tothom (encara no té classificació definitiva):
	// «corren els opens però no els punts». Aquí, a la ronda vigent, li omplim els
	// punts amb la classificació PROVISIONAL en directe (open_live). Això
	// substitueix de facto l'open més antic de la finestra per l'open en curs i hi
	// afegeix els jugadors que NOMÉS disputen aquest. Els qui no el disputen es
	// queden a 0 en aquell open. Marcat com a «calculat · subjecte a errors».
	const maxRonda = $derived(rondes.length ? rondes[rondes.length - 1] : null);

	// {fcb_id -> {pts, pos, nom, club}} d'un open en directe. `open_points` ja ve
	// calculat al payload per a TOTHOM: eliminats per la posició final, i encara en
	// joc per la posició provisional al quadre (open_live.py:_alive_classification_rows).
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

	const overlay = $derived.by(() => {
		if (ronda == null || ronda !== maxRonda) return null;
		const base = rondaRows;
		if (!base.length || !liveOpens.length) return null;
		// Un slot de la finestra és «en curs» si TOTHOM hi té 0 (sense classificació
		// publicada) i hi ha un open_live amb el mateix nom. Així no trepitgem mai
		// un open ja acabat encara que en quedi una fila live obsoleta.
		type Slot = { open: string; live: ReturnType<typeof provPointsFromLive> } | null;
		const slots: Slot[] = (base[0].detall ?? []).map((d: any, i: number): Slot => {
			const allZero = base.every((r: any) => !(((r.detall?.[i]?.punts) ?? 0) > 0));
			if (!allZero) return null;
			const lo = liveOpens.find((o) => norm(o.name) === norm(d.open ?? ''));
			return lo ? { open: d.open as string, live: provPointsFromLive(lo) } : null;
		});
		if (!slots.some(Boolean)) return null;

		const present = new Set<string>();
		const rows: any[] = base.map((r) => {
			const det = (r.detall ?? []).map((d: any) => ({ ...d }));
			let total = 0, njug = 0, maxs = 0;
			det.forEach((d: any, i: number) => {
				const s = slots[i];
				if (s) {
					const p = s.live.get(r.player_fcb_id);
					if (p) { d.pos = p.pos; d.punts = p.pts; d.prov = true; }
					else { d.pos = null; d.punts = 0; d.prov = false; }
				}
				const pts = d.punts || 0;
				if (pts > 0) njug++;
				total += pts;
				maxs = Math.max(maxs, pts);
			});
			present.add(r.player_fcb_id);
			return { ...r, detall: det, punts: total, opens_jugats: njug, _max: maxs };
		});

		// Jugadors que NOMÉS disputen l'open en curs (no surten a cap dels acabats).
		slots.forEach((s, i) => {
			if (!s) return;
			for (const [fid, p] of s.live) {
				if (present.has(fid)) continue;
				present.add(fid);
				const det = (base[0].detall ?? []).map((d: any, j: number) =>
					j === i
						? { open: d.open, temp: d.temp, data: d.data ?? null, pos: p.pos, punts: p.pts, prov: true }
						: { open: d.open, temp: d.temp, data: d.data ?? null, pos: null, punts: 0 }
				);
				rows.push({
					genere: 'general', ronda, ronda_nom: base[0].ronda_nom, ronda_temp: base[0].ronda_temp,
					posicio: 0, player_fcb_id: fid, jugador: p.nom, club: p.club,
					opens_jugats: 1, punts: p.pts, detall: det, _max: p.pts
				});
			}
		});

		rows.sort(
			(a, b) =>
				b.punts - a.punts ||
				(b._max ?? 0) - (a._max ?? 0) ||
				(a.jugador || '').localeCompare(b.jugador || '')
		);
		rows.forEach((r, i) => (r.posicio = i + 1));
		return { rows, liveName: slots.find(Boolean)?.open ?? '' };
	});

	const displayRows = $derived(overlay ? overlay.rows : rondaRows);
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
		{#if overlay}
				<div class="mb-3 flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-[11px] leading-snug text-amber-800 dark:text-amber-300">
					<span class="mt-0.5 shrink-0">⚠</span>
					<span>
						Rànquing <strong>calculat</strong>, <strong>no oficial</strong>: inclou <strong>{overlay.liveName}</strong> en directe amb els punts de la classificació provisional (els qui encara juguen, segons l'ordre de la darrera fase acabada). Els qui no el disputen hi tenen 0. Pot contenir errors fins que l'open sigui definitiu.
					</span>
				</div>
			{/if}
			<div class="mb-3 flex items-center justify-between gap-2 rounded-lg {overlay ? 'bg-amber-600 dark:bg-amber-700' : 'bg-slate-900 dark:bg-slate-700'} px-2 py-2 text-white">
			<button onclick={() => stepRonda(-1)} class="rounded px-3 py-1 text-lg active:bg-slate-700" aria-label="anterior">‹</button>
			<div class="min-w-0 text-center">
				<div class="flex items-center justify-center gap-1.5 text-xs font-semibold">
						<span class="truncate">Fins a {rondaInfo?.ronda_nom ?? ''}</span>
						{#if overlay}<span class="shrink-0 rounded bg-white/25 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider">calculat</span>{/if}
					</div>
				<div class="text-[10px] {overlay ? 'text-amber-100' : 'text-slate-300 dark:text-slate-600'}">{rondaInfo?.ronda_temp ?? ''} · ronda {ronda}/{rondes.length}</div>
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
				{#each displayRows.filter((r) => !q.trim() || norm(r.jugador ?? '').includes(norm(q.trim()))) as r (r.player_fcb_id)}
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
		<p class="px-1 py-2 text-center text-[10px] text-slate-400 dark:text-slate-500">Rànquing Català d'Opens 3 Bandes · suma dels 5 darrers opens (Art. XVIII).{overlay ? ' La ronda vigent és calculada: inclou un open en curs amb punts provisionals.' : ''}</p>
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
