<script lang="ts">
	import { page } from '$app/stores';
	import { supabase, type GameRow } from '$lib/supabase';

	const fcbId = $derived($page.params.fcb_id);

	let nom = $state('');
	let club = $state<string | null>(null);
	let games = $state<GameRow[]>([]);
	let modalitats = $state<{ codi: number; nom: string }[]>([]);
	let selMod = $state<number | null>(null);
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
	const kpi = $derived.by(() => {
		let car = 0,
			ent = 0,
			w = 0,
			l = 0,
			t = 0,
			sm = 0,
			n = 0;
		for (const g of modGames) {
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
	});

	// Evolució al rànquing (per la modalitat seleccionada): mitjana i posició.
	let rankHist = $state<{ posicio: number | null; mitjana: number | null }[]>([]);
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
		rankHist = (data ?? []).map((r) => ({ posicio: r.posicio, mitjana: r.mitjana_general }));
	}
	const bestPos = $derived.by(() => {
		const ps = rankHist.map((r) => r.posicio).filter((v): v is number => v != null);
		return ps.length ? Math.min(...ps) : null;
	});
	const lastMitjana = $derived(rankHist.at(-1)?.mitjana ?? null);

	function spark(vals: (number | null)[], invert = false): string {
		const n = vals.length;
		const valid = vals.filter((v): v is number => v != null);
		if (valid.length < 2) return '';
		let min = Math.min(...valid);
		let max = Math.max(...valid);
		if (min === max) {
			min -= 1;
			max += 1;
		}
		return vals
			.map((v, i) => {
				if (v == null) return null;
				const x = n > 1 ? (i / (n - 1)) * 300 : 0;
				let t = (v - min) / (max - min);
				if (invert) t = 1 - t;
				return `${x.toFixed(1)},${(58 - t * 56).toFixed(1)}`;
			})
			.filter(Boolean)
			.join(' ');
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
	<h1 class="text-lg font-bold leading-tight">{nom}</h1>
	{#if club}<p class="mb-3 text-sm text-slate-400">{club}</p>{/if}

	{#if modalitats.length > 1}
		<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
			{#each modalitats as m}
				<button
					onclick={() => (selMod = m.codi)}
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
		<!-- KPIs -->
		<div class="mb-4 grid grid-cols-4 gap-2">
			{#each [['Partides', kpi.n], ['Mitjana', kpi.mitjana.toFixed(3)], ['Sèrie màx', kpi.sm], ['% vict.', kpi.pct + '%']] as [label, val]}
				<div class="rounded-xl bg-white px-2 py-2.5 text-center ring-1 ring-slate-200">
					<div class="font-mono text-base font-bold tabular-nums">{val}</div>
					<div class="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
				</div>
			{/each}
		</div>
		<p class="mb-2 px-1 text-xs text-slate-400">
			{kpi.w} guanyades · {kpi.l} perdudes{kpi.t ? ` · ${kpi.t} empats` : ''}
		</p>

		<!-- Evolució al rànquing -->
		{#if rankHist.length >= 2}
			<div class="mb-4 space-y-2">
				<div class="rounded-xl bg-white p-3 ring-1 ring-slate-200">
					<div class="mb-1 flex items-baseline justify-between">
						<span class="text-xs font-medium text-slate-500">Evolució mitjana</span>
						<span class="font-mono text-xs text-slate-400"
							>{lastMitjana != null ? lastMitjana.toFixed(3) : '—'}</span>
					</div>
					<svg viewBox="0 0 300 60" preserveAspectRatio="none" class="h-14 w-full">
						<polyline
							points={spark(rankHist.map((r) => r.mitjana))}
							fill="none"
							stroke="#0f172a"
							stroke-width="1.5"
							stroke-linejoin="round"
							vector-effect="non-scaling-stroke" />
					</svg>
				</div>
				<div class="rounded-xl bg-white p-3 ring-1 ring-slate-200">
					<div class="mb-1 flex items-baseline justify-between">
						<span class="text-xs font-medium text-slate-500"
							>Evolució posició <span class="text-slate-300">(amunt = millor)</span></span>
						<span class="font-mono text-xs text-slate-400">millor #{bestPos ?? '—'}</span>
					</div>
					<svg viewBox="0 0 300 60" preserveAspectRatio="none" class="h-14 w-full">
						<polyline
							points={spark(
								rankHist.map((r) => r.posicio),
								true
							)}
							fill="none"
							stroke="#0f172a"
							stroke-width="1.5"
							stroke-linejoin="round"
							vector-effect="non-scaling-stroke" />
					</svg>
				</div>
			</div>
		{/if}

		<!-- Partides recents -->
		<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			{#each modGames.slice(0, 60) as g (g.id)}
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
						<div class="text-[11px] text-slate-400">{fmtDate(p.date)} · {p.comp ?? ''}</div>
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
		{#if modGames.length > 60}
			<p class="px-1 py-3 text-center text-[11px] text-slate-400">
				Mostrant 60 de {modGames.length} partides
			</p>
		{/if}
	{/if}
{/if}
