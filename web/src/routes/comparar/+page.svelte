<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type GameRow } from '$lib/supabase';
	import { theme } from '$lib/theme';

	// Graella del gràfic SVG reactiva al tema (clar/fosc).
	const cGrid = $derived($theme === 'dark' ? '#1e293b' : '#eef2f7');

	const COLORS = ['#2563eb', '#dc2626', '#16a34a', '#d97706'];
	type Sel = {
		fcb_id: string;
		nom: string;
		color: string;
		games: GameRow[];
		rank: { num_seq: number; posicio: number | null; mitjana: number | null; mod: number }[];
	};
	const MODNOM: Record<number, string> = {
		1: 'Tres bandes',
		2: 'Lliure',
		3: 'Quadre 47/2',
		4: 'Banda',
		6: 'Quadre 71/2'
	};

	let allPlayers = $state<{ fcb_id: string; nom: string }[]>([]);
	let q = $state('');
	let sel = $state<Sel[]>([]);
	let selMod = $state(1);
	const modalitats = $derived(
		[...new Set(sel.flatMap((s) => s.games.map((g) => g.modalitat_codi).filter((v) => v != null)))].sort(
			(a, b) => (a as number) - (b as number)
		) as number[]
	);
	$effect(() => {
		if (modalitats.length && !modalitats.includes(selMod)) selMod = modalitats[0];
	});

	function norm(s: string) {
		return (s ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}

	onMount(async () => {
		const { data } = await supabase.from('players').select('fcb_id, nom');
		allPlayers = (data ?? []).filter((p) => !p.fcb_id.startsWith('name:'));
	});

	const matches = $derived(
		q.trim().length < 2
			? []
			: allPlayers
					.filter(
						(p) => norm(p.nom).includes(norm(q.trim())) && !sel.some((s) => s.fcb_id === p.fcb_id)
					)
					.slice(0, 6)
	);

	async function add(p: { fcb_id: string; nom: string }) {
		if (sel.length >= 4 || sel.some((s) => s.fcb_id === p.fcb_id)) return;
		q = '';
		const color = COLORS[sel.length];
		const [{ data: g }, { data: re }] = await Promise.all([
			supabase
				.from('games')
				.select('*')
				.or(`player1_fcb_id.eq.${p.fcb_id},player2_fcb_id.eq.${p.fcb_id}`)
				.order('data_partida', { ascending: false })
				.limit(1000),
			supabase
				.from('ranking_entries')
				.select('num_seq, posicio, mitjana_general, modalitat_codi')
				.eq('player_fcb_id', p.fcb_id)
				.order('num_seq', { ascending: true })
		]);
		sel = [
			...sel,
			{
				fcb_id: p.fcb_id,
				nom: p.nom,
				color,
				games: (g ?? []) as GameRow[],
				rank: (re ?? []).map((r) => ({
					num_seq: r.num_seq,
					posicio: r.posicio,
					mitjana: r.mitjana_general,
					mod: r.modalitat_codi
				}))
			}
		];
	}
	function remove(id: string) {
		sel = sel.filter((s) => s.fcb_id !== id).map((s, i) => ({ ...s, color: COLORS[i] }));
	}

	function kpi(s: Sel) {
		let car = 0,
			ent = 0,
			w = 0,
			n = 0,
			sm = 0;
		for (const gm of s.games) {
			if (gm.modalitat_codi !== selMod) continue;
			const me1 = gm.player1_fcb_id === s.fcb_id;
			const myCar = (me1 ? gm.caramboles1 : gm.caramboles2) ?? 0;
			car += myCar;
			ent += gm.entrades ?? 0;
			sm = Math.max(sm, (me1 ? gm.serie_max1 : gm.serie_max2) ?? 0);
			if (gm.guanyador_fcb_id === s.fcb_id) w++;
			n++;
		}
		return { n, mitjana: ent ? car / ent : 0, sm, pct: n ? Math.round((100 * w) / n) : 0 };
	}
	const kpis = $derived(sel.map(kpi));
	const curPos = $derived(
		sel.map((s) => s.rank.filter((r) => r.mod === selMod).at(-1)?.posicio ?? null)
	);
	const curMit = $derived(
		sel.map((s) => s.rank.filter((r) => r.mod === selMod).at(-1)?.mitjana ?? null)
	);

	// Cara a cara directe entre els seleccionats (de les partides del primer que els conté).
	const h2h = $derived.by(() => {
		const res: { a: string; b: string; aw: number; bw: number }[] = [];
		for (let i = 0; i < sel.length; i++)
			for (let j = i + 1; j < sel.length; j++) {
				let aw = 0,
					bw = 0;
				for (const gm of sel[i].games) {
					const ids = [gm.player1_fcb_id, gm.player2_fcb_id];
					if (ids.includes(sel[i].fcb_id) && ids.includes(sel[j].fcb_id)) {
						if (gm.guanyador_fcb_id === sel[i].fcb_id) aw++;
						else if (gm.guanyador_fcb_id === sel[j].fcb_id) bw++;
					}
				}
				if (aw + bw > 0) res.push({ a: sel[i].nom, b: sel[j].nom, aw, bw });
			}
		return res;
	});

	// Gràfic de mitjana al rànquing (3 bandes) superposat.
	const VBW = 300,
		VBH = 90,
		PAD = 10;
	const seqRange = $derived.by(() => {
		const all = sel.flatMap((s) => s.rank.filter((r) => r.mod === selMod).map((r) => r.num_seq));
		return all.length ? [Math.min(...all), Math.max(...all)] : [0, 1];
	});
	const mitRange = $derived.by(() => {
		const all = sel.flatMap((s) =>
			s.rank.filter((r) => r.mod === selMod).map((r) => r.mitjana).filter((v): v is number => v != null)
		);
		return all.length ? [Math.min(...all), Math.max(...all)] : [0, 1];
	});
	function lineFor(s: Sel) {
		const [s0, s1] = seqRange,
			sw = s1 - s0 || 1;
		const [v0, v1] = mitRange,
			vw = v1 - v0 || 1;
		return s.rank
			.filter((r) => r.mod === selMod && r.mitjana != null)
			.map((r) => {
				const x = PAD + ((r.num_seq - s0) / sw) * (VBW - 2 * PAD);
				const y = VBH - PAD - (((r.mitjana as number) - v0) / vw) * (VBH - 2 * PAD);
				return `${x},${y}`;
			})
			.join(' ');
	}
	const hasChart = $derived(
		sel.some((s) => s.rank.filter((r) => r.mod === selMod && r.mitjana != null).length >= 2)
	);

	// Mitjana de partides per modalitat (per a la taula comparativa).
	function modMitjana(s: Sel, mod: number): number | null {
		let car = 0,
			ent = 0,
			n = 0;
		for (const gm of s.games) {
			if (gm.modalitat_codi !== mod) continue;
			const me1 = gm.player1_fcb_id === s.fcb_id;
			car += (me1 ? gm.caramboles1 : gm.caramboles2) ?? 0;
			ent += gm.entrades ?? 0;
			n++;
		}
		return n ? (ent ? car / ent : 0) : null;
	}
	const modMitjanes = $derived(modalitats.map((m) => ({ mod: m, vals: sel.map((s) => modMitjana(s, m)) })));
</script>

<h1 class="mb-3 text-lg font-bold">Comparador de jugadors</h1>

{#if sel.length < 4}
	<div class="relative mb-3">
		<input
			bind:value={q}
			inputmode="search"
			placeholder="Afegeix jugador…"
			class="w-full rounded-lg border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-2.5 px-3 text-sm shadow-sm"
		/>
		{#if matches.length}
			<ul class="absolute z-10 mt-1 w-full overflow-hidden rounded-lg bg-white dark:bg-slate-900 shadow-lg ring-1 ring-slate-200 dark:ring-slate-800">
				{#each matches as p (p.fcb_id)}
					<li>
						<button onclick={() => add(p)} class="block w-full truncate px-3 py-2 text-left text-sm active:bg-slate-50 dark:active:bg-slate-800/50">{p.nom}</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
{/if}

{#if sel.length}
	<div class="mb-3 flex flex-wrap gap-1.5">
		{#each sel as s (s.fcb_id)}
			<span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium text-white" style:background-color={s.color}>
				{s.nom}
				<button onclick={() => remove(s.fcb_id)} aria-label="treure">✕</button>
			</span>
		{/each}
	</div>
{/if}

{#if sel.length < 2}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Afegeix com a mínim 2 jugadors per comparar.</p>
{:else}
	<!-- Mitjana de joc per modalitat (cadascuna per separat) -->
	{#if modMitjanes.length}
		<div class="mb-4 overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
			<div class="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">
				Mitjana de joc per modalitat
			</div>
			{#each modMitjanes as row}
				<div class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
					<span class="w-24 shrink-0 text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">{MODNOM[row.mod] ?? row.mod}</span>
					{#each row.vals as v, i}
						<span class="flex-1 text-center font-mono text-sm font-bold tabular-nums" style:color={sel[i].color}>{v != null ? v.toFixed(3) : '—'}</span>
					{/each}
				</div>
			{/each}
		</div>
	{/if}

	<!-- Selector de modalitat per als KPIs detallats -->
	{#if modalitats.length > 1}
		<div class="mb-2 flex flex-wrap gap-1">
			{#each modalitats as m}
				<button
					onclick={() => (selMod = m)}
					class="rounded-full px-2.5 py-1 text-xs font-medium {selMod === m
						? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
						: 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'}">{MODNOM[m] ?? m}</button>
			{/each}
		</div>
	{/if}

	<!-- KPIs de la modalitat seleccionada -->
	<div class="mb-4 overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
		{#each [['Posició rànquing', curPos.map((p) => (p != null ? '#' + p : '—'))], ['Mitjana rànquing', curMit.map((m) => (m != null ? m.toFixed(3) : '—'))], ['Partides', kpis.map((k) => k.n)], ['Sèrie màx', kpis.map((k) => k.sm)], ['% victòries', kpis.map((k) => k.pct + '%')]] as [label, vals]}
			<div class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
				<span class="w-24 shrink-0 text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</span>
				{#each vals as v, i}
					<span class="flex-1 text-center font-mono text-sm font-bold tabular-nums" style:color={sel[i].color}>{v}</span>
				{/each}
			</div>
		{/each}
	</div>

	<!-- Cara a cara directe -->
	{#if h2h.length}
		<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
			<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Cara a cara directe</div>
			{#each h2h as m}
				<div class="flex items-center justify-between gap-2 py-1 text-sm">
					<span class="min-w-0 flex-1 truncate text-right">{m.a}</span>
					<span class="shrink-0 rounded bg-slate-900 dark:bg-slate-700 px-2 py-0.5 font-mono text-xs font-bold text-white">{m.aw}–{m.bw}</span>
					<span class="min-w-0 flex-1 truncate">{m.b}</span>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Gràfic de mitjana al rànquing superposat -->
	{#if hasChart}
		<div class="rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
			<div class="mb-1 flex items-end justify-between">
				<span class="text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Evolució mitjana rànquing · {MODNOM[selMod] ?? selMod}</span>
				<span class="text-[9px] tabular-nums text-slate-400 dark:text-slate-500">{mitRange[1].toFixed(2)} ↕ {mitRange[0].toFixed(2)}</span>
			</div>
			<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" class="h-28 w-full">
				{#each [0, 0.25, 0.5, 0.75, 1] as f}
					<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke={cGrid} stroke-width="1" vector-effect="non-scaling-stroke" />
				{/each}
				{#each sel as s}
					<polyline points={lineFor(s)} fill="none" stroke={s.color} stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
				{/each}
			</svg>
		</div>
	{/if}
{/if}
