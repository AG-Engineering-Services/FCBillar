<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type LligaGroup, type StandingRow, type PlayerRankRow } from '$lib/supabase';

	let groups = $state<LligaGroup[]>([]);
	let standings = $state<StandingRow[]>([]);
	let pranks = $state<PlayerRankRow[]>([]);
	let selDiv = $state<number | null>(null);
	let mode = $state<'equips' | 'jugadors'>('equips');
	let scope = $state<'grup' | 'categoria'>('grup');
	let q = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);

	function norm(s: string): string {
		return (s ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}
	const matchQ = (s: string | null) => !q.trim() || norm(s ?? '').includes(norm(q.trim()));

	onMount(async () => {
		try {
			const [
				{ data: g, error: eg },
				{ data: s, error: es },
				{ data: pr, error: ep },
				{ data: enc }
			] = await Promise.all([
				supabase.from('lliga_groups').select('*'),
				supabase.from('lliga_standings').select('*').order('posicio'),
				supabase.from('lliga_player_rankings').select('*').order('posicio'),
				supabase.from('lliga_encontres').select('*')
			]);
			if (eg) throw eg;
			if (es) throw es;
			if (ep) throw ep;
			groups = (g ?? []) as LligaGroup[];
			standings = (s ?? []) as StandingRow[];
			pranks = (pr ?? []) as PlayerRankRow[];
			encontres = enc ?? [];
			const { data: hs } = await supabase.from('lliga_history').select('temporada');
			histSeasons = [...new Set((hs ?? []).map((r) => r.temporada as string))].sort().reverse();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const divisions = $derived.by(() => {
		const m = new Map<number, string>();
		for (const g of groups) if (!m.has(g.divisio_id)) m.set(g.divisio_id, g.divisio_nom ?? `Div ${g.divisio_id}`);
		return [...m.entries()].map(([id, nom]) => ({ id, nom })).sort((a, b) => a.id - b.id);
	});

	$effect(() => {
		if (selDiv == null && divisions.length) selDiv = divisions[0].id;
	});

	const divGroups = $derived(
		groups
			.filter((g) => g.divisio_id === selDiv)
			.sort((a, b) => {
				const fa = (a.grup_nom ?? '').toUpperCase().startsWith('FINAL') ? 1 : 0;
				const fb = (b.grup_nom ?? '').toUpperCase().startsWith('FINAL') ? 1 : 0;
				return fa - fb || (a.grup_nom ?? '').localeCompare(b.grup_nom ?? '');
			})
	);

	function teamRows(gid: number): StandingRow[] {
		return standings
			.filter((s) => s.divisio_id === selDiv && s.grup_id === gid && matchQ(s.equip))
			.sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99));
	}
	function playerRows(gid: number): PlayerRankRow[] {
		return pranks
			.filter((s) => s.divisio_id === selDiv && s.grup_id === gid && matchQ(s.jugador))
			.sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99));
	}
	function count(gid: number): number {
		return mode === 'equips' ? teamRows(gid).length : playerRows(gid).length;
	}
	// Rànquing individual de tota la categoria (tots els grups de la divisió, reordenats).
	const divPlayers = $derived(
		pranks
			.filter((p) => p.divisio_id === selDiv && matchQ(p.jugador))
			.sort((a, b) => (b.punts ?? 0) - (a.punts ?? 0) || (b.mitjana ?? 0) - (a.mitjana ?? 0))
	);

	let collapsed = $state(new Set<number>());
	function toggle(id: number) {
		const s = new Set(collapsed);
		s.has(id) ? s.delete(id) : s.add(id);
		collapsed = s;
	}

	// Resultats per jornada
	let encontres = $state<any[]>([]);

	// Temporada actual (billar: setembre-juny) i selector històric.
	const currentSeason = (() => {
		const d = new Date();
		const y = d.getMonth() + 1 >= 8 ? d.getFullYear() : d.getFullYear() - 1;
		return `${y}-${y + 1}`;
	})();
	let season = $state(currentSeason);
	let histSeasons = $state<string[]>([]);
	let history = $state<
		{ lliga: string; divisio: string; posicio: number; equip: string; pm: number; pp: number }[]
	>([]);
	$effect(() => {
		if (season !== currentSeason) loadHistory(season);
	});
	async function loadHistory(s: string) {
		const { data } = await supabase
			.from('lliga_history')
			.select('lliga, divisio, posicio, equip, pm, pp')
			.eq('temporada', s)
			.order('lliga')
			.order('divisio')
			.order('posicio');
		history = (data ?? []) as typeof history;
	}
	const histGroups = $derived(
		[...new Set(history.map((r) => `${r.lliga}||${r.divisio}`))].map((k) => ({
			lliga: k.split('||')[0],
			divisio: k.split('||')[1],
			rows: history.filter((r) => `${r.lliga}||${r.divisio}` === k)
		}))
	);
	let jornadaSel = $state<Record<number, number>>({});
	let partidesCache = $state<Record<number, any[]>>({});
	let expandedEnc = $state(new Set<number>());

	function gJornades(gid: number): number[] {
		return [
			...new Set(
				encontres
					.filter((e) => e.grup_id === gid && e.divisio_id === selDiv && e.jornada != null)
					.map((e) => e.jornada as number)
			)
		].sort((a, b) => a - b);
	}
	function curJornada(gid: number): number | null {
		const js = gJornades(gid);
		if (!js.length) return null;
		return jornadaSel[gid] ?? js[js.length - 1];
	}
	function encOf(gid: number): any[] {
		const j = curJornada(gid);
		return encontres.filter(
			(e) => e.grup_id === gid && e.divisio_id === selDiv && e.jornada === j
		);
	}
	function stepJornada(gid: number, dir: number) {
		const js = gJornades(gid);
		const i = js.indexOf(curJornada(gid) ?? js[js.length - 1]);
		jornadaSel = { ...jornadaSel, [gid]: js[Math.min(js.length - 1, Math.max(0, i + dir))] };
	}
	async function toggleEnc(encId: number) {
		const s = new Set(expandedEnc);
		if (s.has(encId)) {
			s.delete(encId);
			expandedEnc = s;
			return;
		}
		s.add(encId);
		expandedEnc = s;
		if (!partidesCache[encId]) {
			const { data } = await supabase
				.from('lliga_partides')
				.select('*')
				.eq('encontre_id', encId)
				.order('ordre');
			partidesCache = { ...partidesCache, [encId]: data ?? [] };
		}
	}
</script>

{#if error}
	<div class="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-300">{error}</div>
{:else}
	{#if histSeasons.length}
		<select bind:value={season} class="mb-3 w-full rounded-lg border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-2 px-3 text-sm shadow-sm">
			<option value={currentSeason}>Temporada {currentSeason} (actual)</option>
			{#each histSeasons as s}<option value={s}>Temporada {s}</option>{/each}
		</select>
	{/if}
	{#if season !== currentSeason}
		{#if histGroups.length === 0}
			<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Sense classificacions d'aquesta temporada.</p>
		{/if}
		{#each histGroups as grp}
			<section class="mb-4 overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
				<header class="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-3 py-2 text-xs font-semibold text-slate-500 dark:text-slate-400">{grp.lliga} · {grp.divisio}</header>
				<div class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
					<span class="w-5 text-center">#</span><span class="flex-1">Equip</span><span class="w-8 text-right">PM</span><span class="w-8 text-right">PP</span>
				</div>
				<ul>
					{#each grp.rows as r (r.equip)}
						<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
							<span class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500 dark:text-amber-400' : 'text-slate-400 dark:text-slate-500'}">{r.posicio}</span>
							<span class="min-w-0 flex-1 truncate text-sm">{r.equip}</span>
							<span class="w-8 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.pm}</span>
							<span class="w-8 shrink-0 text-right font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500">{r.pp}</span>
						</li>
					{/each}
				</ul>
			</section>
		{/each}
	{:else if loading}
		<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
	{:else if divisions.length === 0}
		<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Sense classificacions.</p>
	{:else}
		<!-- Divisions: xips -->
	<div class="-mx-3 mb-2 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
		{#each divisions as d}
			<button
				onclick={() => (selDiv = d.id)}
				class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium {d.id === selDiv
					? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
					: 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-800'}">{d.nom}</button>
		{/each}
	</div>

	<!-- Toggle Equips / Jugadors -->
	<div class="mb-3 inline-flex rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5 text-sm">
		<button
			onclick={() => (mode = 'equips')}
			class="rounded-md px-3 py-1 font-medium {mode === 'equips' ? 'bg-white dark:bg-slate-700 shadow-sm' : 'text-slate-500 dark:text-slate-400'}"
			>Equips</button>
		<button
			onclick={() => (mode = 'jugadors')}
			class="rounded-md px-3 py-1 font-medium {mode === 'jugadors' ? 'bg-white dark:bg-slate-700 shadow-sm' : 'text-slate-500 dark:text-slate-400'}"
			>Jugadors</button>
	</div>

	<input
		bind:value={q}
		inputmode="search"
		placeholder={mode === 'equips' ? 'Filtra equip…' : 'Filtra jugador…'}
		class="mb-3 w-full rounded-lg border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-2 px-3 text-sm shadow-sm"
	/>

	{#if mode === 'jugadors'}
		<div class="mb-3 ml-2 inline-flex rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5 text-xs">
			<button
				onclick={() => (scope = 'grup')}
				class="rounded-md px-2.5 py-1 font-medium {scope === 'grup' ? 'bg-white dark:bg-slate-700 shadow-sm' : 'text-slate-500 dark:text-slate-400'}"
				>Per grup</button>
			<button
				onclick={() => (scope = 'categoria')}
				class="rounded-md px-2.5 py-1 font-medium {scope === 'categoria' ? 'bg-white dark:bg-slate-700 shadow-sm' : 'text-slate-500 dark:text-slate-400'}"
				>Tota la categoria</button>
		</div>
	{/if}

	{#if mode === 'jugadors' && scope === 'categoria'}
		<section class="mb-4 overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
			<header class="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
				Categoria sencera · {divPlayers.length} jugadors
			</header>
			<div class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
				<span class="w-6 text-center">#</span>
				<span class="flex-1">Jugador</span>
				<span class="w-6 text-center">PJ</span>
				<span class="w-11 text-right">Mitj.</span>
				<span class="w-7 text-right">Pts</span>
			</div>
			<ul>
				{#each divPlayers as r, i (r.player_fcb_id)}
					<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
						<span class="w-6 shrink-0 text-center text-sm font-semibold tabular-nums {i === 0 ? 'text-amber-500 dark:text-amber-400' : 'text-slate-400 dark:text-slate-500'}">{i + 1}</span>
						<div class="min-w-0 flex-1">
							<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
							{#if r.club}<div class="truncate text-[11px] text-slate-400 dark:text-slate-500">{r.club}</div>{/if}
						</div>
						<span class="w-6 shrink-0 text-center text-xs tabular-nums text-slate-500 dark:text-slate-400">{r.partides}</span>
						<span class="w-11 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">{r.mitjana != null ? r.mitjana.toFixed(3) : '—'}</span>
						<span class="w-7 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
					</li>
				{/each}
			</ul>
		</section>
	{:else}
		{#each divGroups as g (g.grup_id)}
		<section class="mb-4 overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
			<button
				onclick={() => toggle(g.grup_id)}
				class="flex w-full items-center gap-2 bg-slate-50 dark:bg-slate-800/50 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
			>
				<span class="flex-1">{g.grup_nom ?? 'Grup'}</span>
				<span class="font-normal normal-case text-slate-400 dark:text-slate-500">{count(g.grup_id)} {mode}</span>
				<span class="text-slate-400 dark:text-slate-500 transition-transform {collapsed.has(g.grup_id) ? '' : 'rotate-90'}">›</span>
			</button>
			{#if !collapsed.has(g.grup_id)}
				{#if mode === 'equips'}
					<div class="flex items-center gap-2 border-y border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
						<span class="w-5 text-center">#</span>
						<span class="flex-1">Equip</span>
						<span class="w-7 text-center">PJ</span>
						<span class="w-9 text-right">Pts</span>
					</div>
					<ul>
						{#each teamRows(g.grup_id) as r (r.equip)}
							<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
								<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500 dark:text-amber-400' : 'text-slate-400 dark:text-slate-500'}">{r.posicio}</span>
								<div class="min-w-0 flex-1">
									<div class="truncate text-sm font-medium leading-tight">{r.equip}</div>
									<div class="text-[11px] tabular-nums text-slate-400 dark:text-slate-500">{r.g}-{r.e}-{r.p}{#if r.penalitzacio}<span class="ml-1 font-medium text-red-500 dark:text-red-400" title="Sanció federativa: −{r.penalitzacio} {r.penalitzacio === 1 ? 'punt' : 'punts'}">· −{r.penalitzacio} sanció</span>{/if}</div>
								</div>
								<span class="w-7 shrink-0 text-center text-sm tabular-nums text-slate-500 dark:text-slate-400">{r.pj}</span>
								<span class="w-9 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
							</li>
						{/each}
					</ul>
				{:else}
					<div class="flex items-center gap-2 border-y border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
						<span class="w-5 text-center">#</span>
						<span class="flex-1">Jugador</span>
						<span class="w-6 text-center">PJ</span> <span class="w-11 text-right">Mitj.</span>
						<span class="w-7 text-right">Pts</span>
					</div>
					<ul>
						{#each playerRows(g.grup_id) as r (r.player_fcb_id)}
							<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
								<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500 dark:text-amber-400' : 'text-slate-400 dark:text-slate-500'}">{r.posicio}</span>
								<div class="min-w-0 flex-1">
									<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
									{#if r.club}<div class="truncate text-[11px] text-slate-400 dark:text-slate-500">{r.club}</div>{/if}
								</div>
								<span class="w-6 shrink-0 text-center text-xs tabular-nums text-slate-500 dark:text-slate-400">{r.partides}</span> <span class="w-11 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">{r.mitjana != null ? r.mitjana.toFixed(3) : '—'}</span>
								<span class="w-7 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
							</li>
						{/each}
					</ul>
				{/if}

				<!-- Resultats per jornada -->
				{#if gJornades(g.grup_id).length}
					<div class="border-t border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/60 p-2">
						<div class="mb-2 flex items-center justify-between">
							<button onclick={() => stepJornada(g.grup_id, -1)} class="rounded-md px-3 py-1 text-base text-slate-500 dark:text-slate-400 active:bg-slate-200 dark:active:bg-slate-700" aria-label="anterior">‹</button>
							<span class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Jornada {curJornada(g.grup_id)}</span>
							<button onclick={() => stepJornada(g.grup_id, 1)} class="rounded-md px-3 py-1 text-base text-slate-500 dark:text-slate-400 active:bg-slate-200 dark:active:bg-slate-700" aria-label="seguent">›</button>
						</div>
						<ul class="space-y-1">
							{#each encOf(g.grup_id) as e (e.encontre_id)}
								<li class="overflow-hidden rounded-lg bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
									<button onclick={() => toggleEnc(e.encontre_id)} class="flex w-full items-center gap-2 px-2 py-1.5 text-xs">
										<span class="flex-1 truncate text-left font-medium">{e.equip_local}</span>
										<span class="shrink-0 rounded bg-slate-100 dark:bg-slate-800 px-1.5 font-mono font-bold tabular-nums">{e.gols_local}–{e.gols_visitant}</span>
										<span class="flex-1 truncate text-right font-medium">{e.equip_visitant}</span>
									</button>
									{#if expandedEnc.has(e.encontre_id)}
										<div class="border-t border-slate-100 dark:border-slate-800 px-2 py-1">
											{#each partidesCache[e.encontre_id] ?? [] as p}
												<div class="flex items-center gap-2 py-0.5 text-[11px]">
													<span class="flex-1 truncate text-left">{p.jugador_local}</span>
													<span class="shrink-0 font-mono tabular-nums">{p.caramboles_local}–{p.caramboles_visitant}</span>
													<span class="flex-1 truncate text-right">{p.jugador_visitant}</span>
													<span class="w-12 shrink-0 text-right text-slate-400 dark:text-slate-500">{p.entrades} ent</span>
												</div>
											{/each}
										</div>
									{/if}
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			{/if}
		</section>
		{/each}
	{/if}
	{/if}
{/if}
