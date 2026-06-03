<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { ClubKpi, VirtualClub, OrderEvolution, Modalitat, PlayerKpi } from '$lib/types';
	import StatCard from '$lib/components/StatCard.svelte';
	import Collapsible from '$lib/components/Collapsible.svelte';
	import SortableTable from '$lib/components/SortableTable.svelte';
	import LineChart from '$lib/components/LineChart.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import BackButton from '$lib/components/BackButton.svelte';
	import { fmtDate, mitjana, fmtMitjana, winnerBadge } from '$lib/format';
	import type { GameRow } from '$lib/types';

	// ── Modal de partides (des d'un KPI) ───────────────────────────────────────
	let modalOpen = false;
	let modalTitle = '';
	let modalGames: GameRow[] = [];
	let modalLoading = false;

	const modalGamesColumns = [
		{ key: 'data', label: 'Data', fmt: (v: any) => fmtDate(v) },
		{ key: 'modalitat', label: 'Modalitat' },
		{ key: 'competicio', label: 'Competició', fmt: (v: any) => v ?? '' },
		{ key: 'local', label: 'Local' },
		{ key: 'cara1', label: 'C₁', numeric: true },
		{ key: '_wl', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'L') },
		{ key: 'visitant', label: 'Visitant' },
		{ key: 'cara2', label: 'C₂', numeric: true },
		{ key: '_wv', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'V') },
		{ key: 'entrades', label: 'E', numeric: true },
		{ key: 'm1', label: 'M₁', numeric: true, value: (r: any) => mitjana(r.cara1, r.entrades), fmt: fmtMitjana },
		{ key: 'm2', label: 'M₂', numeric: true, value: (r: any) => mitjana(r.cara2, r.entrades), fmt: fmtMitjana },
		{ key: 'club_local', label: 'Club local', muted: true, fmt: (v: any) => v ?? '' },
		{ key: 'club_visitant', label: 'Club visitant', muted: true, fmt: (v: any) => v ?? '' }
	];

	async function openGamesModal(title: string, result: 'all' | 'won' | 'lost') {
		const focus = currentFocus();
		if (!focus) return;
		modalTitle = title;
		modalOpen = true;
		modalLoading = true;
		modalGames = [];
		try {
			const qs = `kind=${focus.kind}&key=${encodeURIComponent(focus.key)}&season_only=${seasonOnly}&result=${result}`;
			modalGames = await api<GameRow[]>(`/api/focus/games?${qs}`);
		} catch (e) {
			console.error(e);
		} finally {
			modalLoading = false;
		}
	}

	let realClubs: ClubKpi[] = [];
	let virtualClubs: VirtualClub[] = [];
	let selectedValue = '';
	let seasonOnly = true;

	let summary: { total: number; guanyades: number; perdudes: number; num_jugadors: number } | null =
		null;
	let players: PlayerKpi[] = [];
	let bestWorst: Record<string, any[]> = { best: [], worst: [], best_won: [], worst_lost: [] };
	let orderEv: OrderEvolution | null = null;
	let modalitats: Modalitat[] = [];
	let selectedMod = 1;
	let highlightPlayer = ''; // '' = tots; altrament el nom a destacar

	function currentFocus(): { kind: string; key: string } | null {
		if (!selectedValue) return null;
		try {
			return JSON.parse(selectedValue);
		} catch {
			return null;
		}
	}

	async function loadFocus() {
		const focus = currentFocus();
		if (!focus) return;
		const qs = `kind=${focus.kind}&key=${encodeURIComponent(focus.key)}&season_only=${seasonOnly}`;
		try {
			const r = await api<{ summary: typeof summary; players: PlayerKpi[] }>(
				`/api/focus/resolve?${qs}`
			);
			summary = r.summary;
			players = r.players;
		} catch (e) {
			console.error(e);
		}
		try {
			bestWorst = await api(`/api/focus/best-worst?${qs}`);
		} catch (e) {
			console.error(e);
		}
		await loadEvolution();
	}

	async function loadEvolution() {
		const focus = currentFocus();
		if (!focus) return;
		const qs = `kind=${focus.kind}&key=${encodeURIComponent(focus.key)}&modalitat=${selectedMod}&season_only=${seasonOnly}`;
		try {
			orderEv = await api<OrderEvolution>(`/api/focus/order-evolution?${qs}`);
			if (orderEv && orderEv.rows.length) {
				if (!orderEv.rows.some((r) => r.player === highlightPlayer)) {
					highlightPlayer = orderEv.rows[0].player;
				}
			}
		} catch (e) {
			console.error(e);
			orderEv = null;
		}
	}

	// Sèrie del gràfic (ordre intern, 1 = millor).
	$: orderSeries = orderEv?.rows.map((r) => ({ label: r.player, data: r.ordre_intern })) ?? [];
	$: orderLabels = orderEv?.num_seqs.map((s) => String(s)) ?? [];

	// Taula de MITJANES amb el rànquing més recent a l'esquerra (num_seqs invertit).
	$: recentSeqs = orderEv ? [...orderEv.num_seqs].slice().reverse() : [];
	$: mitjColumns = [
		{ key: 'pos', label: '#', numeric: true, muted: true, fmt: (v: any) => (v == null ? '—' : String(v)) },
		{ key: 'player', label: 'Jugador', link: (r: any) => `/players/${r.fcb_id}` },
		...recentSeqs.map((s) => ({
			key: 's' + s,
			label: String(s),
			numeric: true,
			fmt: (v: any) => (v == null ? '—' : v.toFixed(4)),
			// Atenua en gris clar les cel·les de rànquings on el jugador ja no
			// era del club (només aplica a focus de club real).
			cellClass: (r: any) => (r['o' + s] ? 'text-slate-300 italic' : '')
		}))
	];
	// Ordena per defecte per la mitjana del rànquing més recent (descendent).
	$: mitjSortKey = recentSeqs.length ? 's' + recentSeqs[0] : 'player';
	$: mitjRows =
		orderEv?.rows.map((r) => {
			// Posició = ordre intern al rànquing més recent (últim índex).
			const lastOrdre = r.ordre_intern.length ? r.ordre_intern[r.ordre_intern.length - 1] : null;
			const o: any = { player: r.player, fcb_id: r.fcb_id, pos: lastOrdre };
			orderEv!.num_seqs.forEach((s, i) => {
				o['s' + s] = r.mitjanes[i];
				o['o' + s] = r.out_of_club ? r.out_of_club[i] : false;
			});
			return o;
		}) ?? [];
	// Hi ha jugadors amb rànquings post-club? (per mostrar la llegenda)
	$: hasOutOfClub = (orderEv?.rows ?? []).some((r) => (r.out_of_club ?? []).some((b) => b));

	const memberColumns = [
		{ key: 'fcb_id', label: 'fcb_id', muted: true, link: (r: any) => `/players/${r.fcb_id}` },
		{ key: 'nom', label: 'Jugador', link: (r: any) => `/players/${r.fcb_id}` },
		{ key: 'club', label: 'Club', fmt: (v: any) => v ?? '—' },
		{ key: 'num_partides', label: 'Partides', numeric: true },
		{ key: 'seguiment', label: 'Seguit', fmt: (v: any) => (v ? '★' : '') }
	];

	const bwColumns = [
		{ key: 'data', label: 'Data', fmt: (v: any) => fmtDate(v) },
		{ key: 'modalitat', label: 'Modalitat' },
		{ key: 'jugador_club', label: 'Jugador' },
		{ key: 'car_club', label: 'Car', numeric: true },
		{ key: 'entrades', label: 'E', numeric: true },
		{ key: 'mitj', label: 'Mitj', numeric: true, fmt: (v: any) => (v != null ? v.toFixed(3) : '—') }
	];

	const BW_SECTIONS: [string, string][] = [
		['best', '🏆 Millors mitjanes'],
		['best_won', '✅ Millors victòries'],
		['worst', '📉 Pitjors mitjanes'],
		['worst_lost', '❌ Pitjors derrotes']
	];

	function onFocusChange() {
		loadFocus();
	}
	function onSeasonChange() {
		loadFocus();
	}
	function onModChange() {
		loadEvolution();
	}

	onMount(async () => {
		const [rc, vc, mods] = await Promise.all([
			api<ClubKpi[]>('/api/clubs'),
			api<VirtualClub[]>('/api/virtual-clubs'),
			api<Modalitat[]>('/api/modalitats')
		]);
		realClubs = rc;
		virtualClubs = vc;
		modalitats = mods;

		const params = new URLSearchParams(window.location.search);
		const urlKind = params.get('kind');
		const urlKey = params.get('key');
		if (urlKind && urlKey) {
			selectedValue = JSON.stringify({ kind: urlKind, key: urlKey });
		} else {
			const banyoles = realClubs.find((c) => c.fcb_id === 'C.B.BANYOLES');
			if (banyoles) selectedValue = JSON.stringify({ kind: 'real', key: banyoles.fcb_id });
			else if (realClubs.length)
				selectedValue = JSON.stringify({ kind: 'real', key: realClubs[0].fcb_id });
		}
		selectedMod = modalitats[0]?.codi_fcb ?? 1;
		await loadFocus();
	});
</script>

<BackButton fallback="/clubs" />
<h1 class="text-2xl font-bold mb-4">Focus de club</h1>

<div class="flex flex-wrap gap-3 items-center mb-6">
	<select
		class="border border-slate-300 rounded-md px-3 py-2 text-sm min-w-[260px]"
		bind:value={selectedValue}
		on:change={onFocusChange}
	>
		<optgroup label="Clubs reals">
			{#each realClubs as c}
				<option value={JSON.stringify({ kind: 'real', key: c.fcb_id })}>🏛 {c.nom}</option>
			{/each}
		</optgroup>
		<optgroup label="Clubs virtuals">
			{#each virtualClubs as vc}
				<option value={JSON.stringify({ kind: 'virtual', key: String(vc.id) })}>⭐ {vc.nom}</option>
			{/each}
		</optgroup>
	</select>

	<label class="flex items-center gap-2 text-sm text-slate-600">
		<input type="checkbox" bind:checked={seasonOnly} on:change={onSeasonChange} />
		Només temporada actual
	</label>
</div>

{#if !summary}
	<p class="text-slate-500">Carregant…</p>
{:else}
	<div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
		<StatCard label="Jugadors" value={summary.num_jugadors} />
		<StatCard
			label="Partides"
			value={summary.total}
			onClick={() => openGamesModal('Totes les partides', 'all')}
		/>
		<StatCard
			label="Guanyades"
			value={summary.guanyades}
			onClick={() => openGamesModal('Partides guanyades', 'won')}
		/>
		<StatCard
			label="Perdudes"
			value={summary.perdudes}
			onClick={() => openGamesModal('Partides perdudes', 'lost')}
		/>
		<StatCard
			label="% Victòria"
			value={summary.total ? ((summary.guanyades / summary.total) * 100).toFixed(1) + '%' : '—'}
		/>
	</div>

	<Modal open={modalOpen} title={`${modalTitle} (${modalGames.length})`} on:close={() => (modalOpen = false)}>
		<div class="p-2">
			{#if modalLoading}
				<p class="text-slate-500 p-4">Carregant…</p>
			{:else}
				<SortableTable columns={modalGamesColumns} rows={modalGames} emptyText="Cap partida." />
			{/if}
		</div>
	</Modal>

	<!-- Evolució de la mitjana (CENTERPIECE): taula recent → antic, ordenable -->
	<div class="flex flex-wrap items-center gap-3 mb-3">
		<label class="text-sm text-slate-600">Modalitat:</label>
		<select
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
			bind:value={selectedMod}
			on:change={onModChange}
		>
			{#each modalitats as m}
				<option value={m.codi_fcb}>{m.nom}</option>
			{/each}
		</select>
	</div>

	<div class="mb-4">
		<Collapsible
			title="Evolució de la mitjana al rànquing"
			open={true}
			count={mitjRows.length}
			subtitle="rànquing més recent a l'esquerra"
		>
			<div class="px-4 pt-3 pb-1">
				<p class="text-sm text-slate-500">
					Mitjana general de cada jugador per publicació del rànquing (columna = num_seq; la més
					recent a l'esquerra). Clica una columna per ordenar — l'ordre relatiu entre els jugadors
					del focus determina la composició dels equips de la temporada vinent.
				</p>
				{#if hasOutOfClub}
					<p class="text-xs text-slate-400 mt-1">
						Les mitjanes <span class="text-slate-300 italic">en gris clar</span> són de rànquings
						posteriors a deixar el club (el jugador ja no hi jugava).
					</p>
				{/if}
			</div>
			{#if orderEv && orderEv.rows.length > 0}
				<SortableTable
					columns={mitjColumns}
					rows={mitjRows}
					initialSortKey={mitjSortKey}
					initialSortDir="desc"
				/>
			{:else}
				<p class="text-slate-400 text-sm px-4 py-3">
					Sense dades d'evolució per a aquesta modalitat.
				</p>
			{/if}
		</Collapsible>
	</div>

	<!-- Gràfic d'ordre intern (plegat per defecte) -->
	{#if orderEv && orderEv.rows.length > 0}
		<div class="mb-4">
			<Collapsible title="Gràfic d'ordre intern" open={false}>
				<div class="p-4">
					<div class="flex flex-wrap items-center gap-3 mb-3">
						<label class="text-sm text-slate-600">Destaca:</label>
						<select
							class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
							bind:value={highlightPlayer}
						>
							<option value="">Tots</option>
							{#each orderEv?.rows ?? [] as r}
								<option value={r.player}>{r.player}</option>
							{/each}
						</select>
					</div>
					<LineChart
						labels={orderLabels}
						series={orderSeries}
						invertY={true}
						integerY={true}
						yTitle="Ordre"
						height={420}
						highlight={highlightPlayer || null}
					/>
				</div>
			</Collapsible>
		</div>
	{/if}

	<!-- Membres -->
	<div class="mb-4">
		<Collapsible title="Membres" open={true} count={players.length}>
			<SortableTable
				columns={memberColumns}
				rows={players}
				initialSortKey="num_partides"
				initialSortDir="desc"
			/>
		</Collapsible>
	</div>

	<!-- Millors i pitjors actuacions (apilades: les taules són amples) -->
	<div class="grid grid-cols-1 gap-4">
		{#each BW_SECTIONS as [key, title]}
			<Collapsible {title} open={true} count={(bestWorst[key] ?? []).length}>
				<SortableTable columns={bwColumns} rows={bestWorst[key] ?? []} />
			</Collapsible>
		{/each}
	</div>
{/if}
