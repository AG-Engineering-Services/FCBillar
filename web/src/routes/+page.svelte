<script lang="ts">
	import { onMount } from 'svelte';
	import {
		supabase,
		type Modalitat,
		type Snapshot,
		type RankingRow,
		type ProvisionalRow
	} from '$lib/supabase';
	import { clubMatches, playerMatches } from '$lib/search';

	type SearchScope = 'tot' | 'jugador' | 'club';
	const SCOPES: { val: SearchScope; label: string }[] = [
		{ val: 'tot', label: 'Tot' },
		{ val: 'jugador', label: 'Jugador' },
		{ val: 'club', label: 'Club' }
	];

	// Fila mostrada: a la vista provisional, `posicio`/`mitjana_general` ja porten
	// el valor calculat i `ref*` el valor oficial vigent (per a les marques ▲▼).
	type Row = RankingRow & {
		refMitjana?: number | null;
		refPosicio?: number | null;
		partidesNoves?: number;
	};

	let modalitats = $state<Modalitat[]>([]);
	let snapshots = $state<Snapshot[]>([]);
	let rows = $state<Row[]>([]);
	// Projecció provisional de tota la modalitat (una fila per jugador). La taula
	// només conté el snapshot vigent, així que la carreguem sencera per modalitat.
	let prov = $state<Map<string, ProvisionalRow>>(new Map());
	let selMod = $state<number | null>(null);
	// Posició de l'slider: el num_seq d'un rànquing oficial, o 'prov' per a la
	// projecció provisional (la posició més nova, a la dreta de l'oficial vigent).
	let selSeq = $state<number | 'prov' | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let search = $state('');
	let scope = $state<SearchScope>('tot');

	const MESOS = [
		'gener', 'febrer', 'març', 'abril', 'maig', 'juny',
		'juliol', 'agost', 'setembre', 'octubre', 'novembre', 'desembre'
	];
	function snapLabel(s: Snapshot): string {
		if (s.mes_pub && s.any_pub) {
			const m = MESOS[s.mes_pub - 1] ?? String(s.mes_pub);
			return `${m.charAt(0).toUpperCase()}${m.slice(1)} ${s.any_pub}`;
		}
		return `Rànquing #${s.num_seq}`;
	}

	// La projecció provisional s'ofereix a l'slider només si el proper rànquing
	// diferirà del vigent (algú ha jugat partides noves o canvia de posició).
	const hasProv = $derived(
		[...prov.values()].some(
			(p) =>
				(p.partides_post ?? 0) > 0 ||
				(p.posicio_provisional != null &&
					p.posicio_oficial != null &&
					p.posicio_provisional !== p.posicio_oficial)
		)
	);
	// Posicions de l'slider, de més nova (esquerra→dreta = més nova a la dreta).
	const positions = $derived(
		hasProv
			? (['prov', ...snapshots.map((s) => s.num_seq)] as (number | 'prov')[])
			: snapshots.map((s) => s.num_seq)
	);
	const posIndex = $derived(positions.findIndex((p) => p === selSeq));
	const hasNewer = $derived(posIndex > 0);
	const hasOlder = $derived(posIndex >= 0 && posIndex < positions.length - 1);
	const isProvView = $derived(selSeq === 'prov');
	const officialIndex = $derived(snapshots.findIndex((s) => s.num_seq === selSeq));
	const isLatestOfficial = $derived(officialIndex === 0);
	const currentLabel = $derived(snapshots[officialIndex] ? snapLabel(snapshots[officialIndex]) : '');
	const latestOfficialLabel = $derived(snapshots[0] ? snapLabel(snapshots[0]) : '');
	// Marques ▲▼ de projecció sobre l'oficial vigent (mateixa idea que la vista
	// provisional, però mostrades en línia al darrer rànquing oficial).
	const provActive = $derived(!isProvView && prov.size > 0 && selSeq === snapshots[0]?.num_seq);

	const filtered = $derived.by(() => {
		const t = search.trim();
		if (!t) return rows;
		return rows.filter((r) => {
			const mp = scope !== 'club' && playerMatches(r.jugador, t);
			const mc = scope !== 'jugador' && clubMatches(r.club, t);
			return mp || mc;
		});
	});

	onMount(async () => {
		try {
			const { data, error: e } = await supabase
				.from('modalitats')
				.select('codi_fcb, nom')
				.order('codi_fcb');
			if (e) throw e;
			modalitats = data ?? [];
			selMod = modalitats.find((m) => m.codi_fcb === 1)?.codi_fcb ?? modalitats[0]?.codi_fcb ?? null;
			await loadSnapshots();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	async function loadSnapshots() {
		if (selMod == null) return;
		const [snapsRes, provRes] = await Promise.all([
			supabase
				.from('rankings')
				.select('num_seq, any_pub, mes_pub')
				.eq('modalitat_codi', selMod)
				.order('num_seq', { ascending: false }),
			supabase
				.from('ranking_provisional')
				.select(
					'player_fcb_id, posicio_oficial, mitjana_oficial, posicio_provisional, mitjana_provisional, partides_post'
				)
				.eq('modalitat_codi', selMod)
		]);
		if (snapsRes.error) {
			error = snapsRes.error.message;
			return;
		}
		snapshots = snapsRes.data ?? [];
		const m = new Map<string, ProvisionalRow>();
		for (const p of (provRes.data ?? []) as ProvisionalRow[]) m.set(p.player_fcb_id, p);
		prov = m;
		// Per defecte, el darrer rànquing oficial (amb les marques de projecció en
		// línia). La vista provisional sencera és una posició a la dreta.
		selSeq = snapshots[0]?.num_seq ?? null;
		await loadRows();
	}

	async function loadRows() {
		if (selMod == null || selSeq == null) {
			rows = [];
			return;
		}
		loading = true;

		// Vista PROVISIONAL: noms i valors oficials del rànquing vigent, amb la
		// posició/mitjana provisional sobreposada i reordenats per la provisional.
		if (selSeq === 'prov') {
			const latest = snapshots[0]?.num_seq ?? -1;
			const { data, error: e } = await supabase
				.from('ranking_full')
				.select('posicio, player_fcb_id, jugador, club, mitjana_general, partides')
				.eq('modalitat_codi', selMod)
				.eq('num_seq', latest);
			loading = false;
			if (e) {
				error = e.message;
				return;
			}
			rows = ((data ?? []) as RankingRow[])
				.map((r) => {
					const pv = prov.get(r.player_fcb_id);
					return {
						...r,
						posicio: pv?.posicio_provisional ?? r.posicio,
						mitjana_general: pv?.mitjana_provisional ?? r.mitjana_general,
						refPosicio: r.posicio,
						refMitjana: r.mitjana_general,
						partidesNoves: pv?.partides_post ?? 0
					} as Row;
				})
				.sort((a, b) => (a.posicio ?? Infinity) - (b.posicio ?? Infinity));
			return;
		}

		// Vista d'un rànquing OFICIAL.
		const { data, error: e } = await supabase
			.from('ranking_full')
			.select('posicio, player_fcb_id, jugador, club, mitjana_general, partides')
			.eq('modalitat_codi', selMod)
			.eq('num_seq', selSeq)
			.order('posicio', { ascending: true });
		loading = false;
		if (e) {
			error = e.message;
			return;
		}
		rows = (data ?? []) as Row[];
	}

	async function pickMod(codi: number) {
		if (codi === selMod) return;
		selMod = codi;
		search = '';
		scope = 'tot';
		await loadSnapshots();
	}

	async function step(delta: number) {
		const next = positions[posIndex + delta];
		if (next === undefined) return;
		selSeq = next;
		await loadRows();
	}
</script>

{#if error}
	<div class="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-300">
		{error}
	</div>
{/if}

<!-- Modalitats: xips amb scroll horitzontal -->
<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
	{#each modalitats as m}
		<button
			onclick={() => pickMod(m.codi_fcb)}
			class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors {m.codi_fcb ===
			selMod
				? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
				: 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-800'}"
		>
			{m.nom}
		</button>
	{/each}
</div>

<!-- Slider de rànquings: ‹ més antic · més recent / provisional › -->
{#if snapshots.length}
	<div class="mb-3 flex items-center gap-2">
		<button
			type="button"
			onclick={() => step(1)}
			disabled={!hasOlder}
			aria-label="Rànquing més antic"
			class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-800 active:bg-slate-50 dark:active:bg-slate-800 disabled:opacity-30"
		>‹</button>
		<div
			class="min-w-0 flex-1 rounded-xl px-3 py-1.5 text-center ring-1 {isProvView
				? 'bg-amber-50 dark:bg-amber-950/40 ring-amber-300 dark:ring-amber-800'
				: 'bg-white dark:bg-slate-900 ring-slate-200 dark:ring-slate-800'}"
		>
			{#if isProvView}
				<p class="truncate text-sm font-semibold text-amber-800 dark:text-amber-300">Provisional calculat</p>
				<p class="text-[10px] uppercase tracking-wide text-amber-600 dark:text-amber-400">estimació · pot tenir errors</p>
			{:else}
				<p class="truncate text-sm font-semibold">{currentLabel}</p>
				<p class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
					{isLatestOfficial ? 'Oficial vigent' : `${snapshots.length - officialIndex} de ${snapshots.length} · oficial`}
				</p>
			{/if}
		</div>
		<button
			type="button"
			onclick={() => step(-1)}
			disabled={!hasNewer}
			aria-label="Rànquing més recent"
			title={hasNewer && positions[posIndex - 1] === 'prov' ? 'Projecció provisional' : 'Rànquing més recent'}
			class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-800 active:bg-slate-50 dark:active:bg-slate-800 disabled:opacity-30"
		>›</button>
	</div>

	<input
		bind:value={search}
		inputmode="search"
		placeholder="Cerca jugador o club…"
		class="mb-3 w-full rounded-lg border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-2 px-3 text-sm shadow-sm"
	/>
{/if}

<!-- Àmbit de la cerca: evita que cognoms com «Manresa» o «Olesa» es barregin amb clubs -->
{#if search.trim()}
	<div class="-mt-1 mb-3 flex items-center gap-1.5 px-0.5 text-xs">
		<span class="text-slate-400 dark:text-slate-500">Cerca a:</span>
		{#each SCOPES as s (s.val)}
			<button
				type="button"
				onclick={() => (scope = s.val)}
				class="rounded-full px-2.5 py-1 font-medium transition-colors {scope === s.val
					? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
					: 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-800'}"
			>
				{s.label}
			</button>
		{/each}
	</div>
{/if}

{#if isProvView}
	<div class="mb-2 flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-[11px] leading-snug text-amber-800 dark:text-amber-300">
		<span class="mt-0.5 shrink-0">⚠</span>
		<span>
			Rànquing <strong>provisional</strong>, <strong>no oficial</strong>: el darrer oficial ({latestOfficialLabel})
			recalculat amb les partides de competicions en curs. Són càlculs automàtics i poden contenir errors.
		</span>
	</div>
{:else if provActive}
	<p class="mb-2 px-1 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
		A la dreta, <span class="font-semibold">projecció del proper rànquing</span> (mitjana i posició
		amb les partides de competicions en curs): <span class="font-semibold text-emerald-600 dark:text-emerald-400">verd</span>
		puja, <span class="font-semibold text-red-500 dark:text-red-400">vermell</span> baixa. Llisca a la dreta («Provisional calculat») per veure el rànquing sencer recalculat.
	</p>
{/if}

{#if loading}
	<p class="px-1 py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
{:else if filtered.length === 0}
	<p class="px-1 py-6 text-center text-sm text-slate-400 dark:text-slate-500">Sense resultats.</p>
{:else}
	<ul class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800 lg:columns-2 lg:gap-x-6">
		{#each filtered as r (r.player_fcb_id + '-' + r.posicio)}
			{@const pv = provActive ? prov.get(r.player_fcb_id) : undefined}
			<li class="break-inside-avoid border-b border-slate-100 dark:border-slate-800 last:border-0">
				<a
					href="/jugador/{r.player_fcb_id}"
					class="flex items-center gap-3 px-3 py-2.5 active:bg-slate-50 dark:active:bg-slate-800/50"
				>
					<span
						class="w-7 shrink-0 text-center text-sm font-semibold tabular-nums {isProvView
							? 'text-amber-600 dark:text-amber-400'
							: 'text-slate-400 dark:text-slate-500'}"
					>{r.posicio ?? '—'}</span>
					<div class="min-w-0 flex-1">
						<div class="truncate text-sm font-medium leading-tight">{r.jugador}</div>
						{#if r.club}<div class="truncate text-xs text-slate-400 dark:text-slate-500">{r.club}</div>{/if}
						{#if isProvView && (r.partidesNoves ?? 0) > 0}
							<div class="text-[10px] font-medium text-amber-600 dark:text-amber-400">
								+{r.partidesNoves} {r.partidesNoves === 1 ? 'partida nova' : 'partides noves'}
							</div>
						{/if}
					</div>
					<span class="shrink-0 font-mono text-sm font-semibold tabular-nums">
						{r.mitjana_general != null ? r.mitjana_general.toFixed(3) : '—'}
					</span>
					{#if isProvView}
						{@const dp = (r.refPosicio ?? 0) - (r.posicio ?? 0)}
						{@const dm = (r.mitjana_general ?? 0) - (r.refMitjana ?? 0)}
						{@const mUp = dm > 0.0005}
						{@const mDown = dm < -0.0005}
						<span class="w-16 shrink-0 text-right leading-tight">
							<span
								class="block font-mono text-xs font-semibold tabular-nums {mUp
									? 'text-emerald-600 dark:text-emerald-400'
									: mDown
										? 'text-red-500 dark:text-red-400'
										: 'text-slate-400 dark:text-slate-500'}"
								>{mUp ? `+${dm.toFixed(3)}` : mDown ? dm.toFixed(3) : '='}</span>
							<span
								class="block text-[10px] font-bold tabular-nums {dp > 0
									? 'text-emerald-600 dark:text-emerald-400'
									: dp < 0
										? 'text-red-500 dark:text-red-400'
										: 'text-slate-400 dark:text-slate-500'}"
								>{dp > 0 ? `▲${dp}` : dp < 0 ? `▼${-dp}` : '–'}</span>
						</span>
					{:else if pv && pv.partides_post > 0}
						{@const dp = (pv.posicio_oficial ?? 0) - (pv.posicio_provisional ?? 0)}
						{@const dm = (pv.mitjana_provisional ?? 0) - (pv.mitjana_oficial ?? 0)}
						{@const mUp = dm > 0.0005}
						{@const mDown = dm < -0.0005}
						<span class="w-16 shrink-0 text-right leading-tight">
							<span
								class="block font-mono text-xs font-semibold tabular-nums {mUp
									? 'text-emerald-600 dark:text-emerald-400'
									: mDown
										? 'text-red-500 dark:text-red-400'
										: 'text-slate-500 dark:text-slate-400'}"
								>{mUp ? `+${dm.toFixed(3)}` : mDown ? dm.toFixed(3) : '='}</span>
							<span
								class="block text-[10px] font-bold tabular-nums {dp > 0
									? 'text-emerald-600 dark:text-emerald-400'
									: dp < 0
										? 'text-red-500 dark:text-red-400'
										: 'text-slate-400 dark:text-slate-500'}"
								>{dp > 0 ? `▲${dp}` : dp < 0 ? `▼${-dp}` : '–'}</span>
						</span>
					{:else if provActive}
						<span class="w-16 shrink-0"></span>
					{/if}
					<span class="shrink-0 text-slate-300 dark:text-slate-600">›</span>
				</a>
			</li>
		{/each}
	</ul>
	<p class="px-1 py-3 text-center text-[11px] text-slate-400 dark:text-slate-500">{filtered.length} jugadors</p>
{/if}
