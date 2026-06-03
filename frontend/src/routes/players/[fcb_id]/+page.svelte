<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import type { GameRow, PlayerSummary, Modalitat } from '$lib/types';
	import StatCard from '$lib/components/StatCard.svelte';
	import LineChart from '$lib/components/LineChart.svelte';
	import Card from '$lib/components/Card.svelte';
	import SortableTable from '$lib/components/SortableTable.svelte';
	import Collapsible from '$lib/components/Collapsible.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import BackButton from '$lib/components/BackButton.svelte';
	import { fmtDate, mitjana, fmtMitjana, winnerBadge } from '$lib/format';

	// ── Modal de partides (obert des d'un KPI) ─────────────────────────────────
	let modalOpen = false;
	let modalTitle = '';
	let modalGames: GameRow[] = [];

	// Resultat de la partida des del punt de vista del jugador d'aquesta fitxa.
	function playerResult(g: GameRow): 'W' | 'L' | 'T' | null {
		if (g.cara1 == null || g.cara2 == null) return null;
		if (g.cara1 === g.cara2) return 'T';
		const meLocal = g.local === summary?.nom;
		const myCar = meLocal ? g.cara1 : g.cara2;
		const otherCar = meLocal ? g.cara2 : g.cara1;
		return myCar > otherCar ? 'W' : 'L';
	}

	function openGamesModal(title: string, filter: (g: GameRow) => boolean) {
		modalTitle = title;
		modalGames = games.filter(filter);
		modalOpen = true;
	}

	// Sèrie del jugador d'aquesta fitxa en una partida (segons quin costat és).
	function playerSerie(g: GameRow): number | null {
		const meLocal = g.local === summary?.nom;
		return meLocal ? (g.serie1 ?? null) : (g.serie2 ?? null);
	}

	// ── Types ────────────────────────────────────────────────────────────────
	interface BestWorst {
		best: GameRow[];
		worst: GameRow[];
		best_won: GameRow[];
		worst_lost: GameRow[];
	}
	interface ProfileResponse {
		summary: PlayerSummary;
		best_worst: BestWorst;
	}
	interface HistoryPoint {
		num_seq: number;
		mitjana: number | null;
		posicio: number | null;
	}

	// ── State ────────────────────────────────────────────────────────────────
	$: fcbId = $page.params.fcb_id;

	let summary: PlayerSummary | null = null;
	let bestWorst: BestWorst | null = null;
	let games: GameRow[] = [];
	let modalitats: Modalitat[] = [];
	let selectedMod: number | null = null;
	let history: HistoryPoint[] = [];

	let loading = true;
	let notFound = false;
	let loadingHistory = false;

	// Derived KPIs
	$: winPct =
		summary && summary.total > 0
			? ((summary.guanyades / summary.total) * 100).toFixed(1)
			: '—';

	// Chart data derived from history
	$: chartLabels = history.map((h) => String(h.num_seq));
	$: chartSeries = [{ label: 'Mitjana', data: history.map((h) => h.mitjana) }];

	// Re-load when the route param changes (navigation between profiles)
	$: fcbId, loadAll();

	// ── Shared table columns ───────────────────────────────────────────────────
	const bestWorstColumns = [
		{ key: 'data', label: 'Data', fmt: (v: any) => fmtDate(v) },
		{ key: 'modalitat', label: 'Modalitat' },
		{ key: 'local', label: 'Local' },
		{ key: 'cara1', label: 'C₁', numeric: true },
		{ key: '_wl', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'L') },
		{ key: 'visitant', label: 'Visitant' },
		{ key: 'cara2', label: 'C₂', numeric: true },
		{ key: '_wv', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'V') },
		{ key: 'entrades', label: 'E', numeric: true },
		{ key: 'm1', label: 'M₁', numeric: true, value: (r: any) => mitjana(r.cara1, r.entrades), fmt: fmtMitjana },
		{ key: 'm2', label: 'M₂', numeric: true, value: (r: any) => mitjana(r.cara2, r.entrades), fmt: fmtMitjana }
	];

	const gamesColumns = [
		{
			key: '_computa',
			label: '★',
			sortable: false,
			badge: (r: any) => (r.computa ? { label: 'Compta', tone: 'win' } : null)
		},
		{ key: 'data', label: 'Data', fmt: (v: any) => fmtDate(v) },
		{ key: 'modalitat', label: 'Modalitat' },
		{ key: 'competicio', label: 'Competició', fmt: (v: unknown) => (v ?? '') as string },
		{ key: 'local', label: 'Local' },
		{ key: 'cara1', label: 'C₁', numeric: true },
		{ key: '_wl', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'L') },
		{ key: 'visitant', label: 'Visitant' },
		{ key: 'cara2', label: 'C₂', numeric: true },
		{ key: '_wv', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'V') },
		{ key: 'entrades', label: 'E', numeric: true },
		{ key: 'm1', label: 'M₁', numeric: true, value: (r: any) => mitjana(r.cara1, r.entrades), fmt: fmtMitjana },
		{ key: 'm2', label: 'M₂', numeric: true, value: (r: any) => mitjana(r.cara2, r.entrades), fmt: fmtMitjana },
		{ key: 'serie1', label: 'S₁', numeric: true, muted: true, fmt: (v: any) => (v ?? '—') },
		{ key: 'serie2', label: 'S₂', numeric: true, muted: true, fmt: (v: any) => (v ?? '—') },
		{ key: 'club_local', label: 'Club local', muted: true, fmt: (v: unknown) => (v ?? '') as string },
		{
			key: 'club_visitant',
			label: 'Club visitant',
			muted: true,
			fmt: (v: unknown) => (v ?? '') as string
		}
	];

	// Modalitat del filtre global de la fitxa. null = Totes (afecta KPIs i llistes).
	// La del gràfic d'evolució és a banda (chartMod), perquè el gràfic necessita
	// sempre una modalitat concreta.
	let chartMod: number | null = null;

	// Sufix de query segons el filtre de modalitat global.
	$: modQS = selectedMod != null ? `&modalitat=${selectedMod}` : '';

	async function loadAll() {
		if (!fcbId) return;
		loading = true;
		notFound = false;
		summary = null;
		bestWorst = null;
		games = [];
		history = [];

		try {
			const mods = await api<Modalitat[]>('/api/modalitats').catch(() => [] as Modalitat[]);
			modalitats = mods;
			chartMod = mods.length ? mods[0].codi_fcb : null;
			await loadFiltered();
			await loadHistory();
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	}

	// Carrega summary + best/worst + games segons la modalitat global seleccionada.
	async function loadFiltered() {
		if (!fcbId) return;
		const [profRaw, gamesRaw] = await Promise.all([
			api<ProfileResponse>(`/api/players/${fcbId}?x=1${modQS}`).catch((e: Error) => {
				if (e.message.includes('404')) {
					notFound = true;
					return null;
				}
				throw e;
			}),
			api<GameRow[]>(`/api/players/${fcbId}/games?limit=200${modQS}`).catch(
				() => [] as GameRow[]
			)
		]);
		if (profRaw) {
			summary = profRaw.summary;
			bestWorst = profRaw.best_worst;
		}
		games = gamesRaw;
	}

	async function loadHistory() {
		if (!fcbId || chartMod == null) return;
		loadingHistory = true;
		try {
			history = await api<HistoryPoint[]>(
				`/api/players/${fcbId}/ranking-history?modalitat=${chartMod}`
			);
		} catch (e) {
			console.error(e);
			history = [];
		} finally {
			loadingHistory = false;
		}
	}

	onMount(() => {
		// loadAll is triggered reactively via $: fcbId, loadAll()
		// but we also call it explicitly in case the reactive block
		// fires before the component is fully mounted.
	});
</script>

{#if loading}
	<p class="text-slate-500">Carregant…</p>
{:else if notFound}
	<p class="text-slate-500">Jugador no trobat.</p>
{:else if summary}
	<BackButton fallback="/players" />
	<!-- ── Header ─────────────────────────────────────────────────────────── -->
	<h1 class="text-2xl font-bold mb-4">
		{summary.nom}
		<span class="inline-block px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600 align-middle ml-2"
			>{summary.fcb_id}</span
		>
	</h1>

	<!-- ── Filtre global de modalitat (afecta KPIs i llistes) ─────────────── -->
	<div class="flex items-center gap-3 mb-4">
		<label class="text-sm text-slate-600 font-medium" for="sel-global-mod">Modalitat</label>
		<select
			id="sel-global-mod"
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
			bind:value={selectedMod}
			on:change={loadFiltered}
		>
			<option value={null}>Totes</option>
			{#each modalitats as m}
				<option value={m.codi_fcb}>{m.nom}</option>
			{/each}
		</select>
	</div>

	<!-- ── KPI StatCards ──────────────────────────────────────────────────── -->
	<div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
		<StatCard
			label="Partides"
			value={summary.total}
			onClick={() => openGamesModal('Totes les partides', () => true)}
		/>
		<StatCard
			label="Guanyades"
			value={summary.guanyades}
			onClick={() => openGamesModal('Partides guanyades', (g) => playerResult(g) === 'W')}
		/>
		<StatCard
			label="Perdudes"
			value={summary.perdudes}
			onClick={() => openGamesModal('Partides perdudes', (g) => playerResult(g) === 'L')}
		/>
		<StatCard label="% Victòria" value={winPct} />
		<StatCard
			label="Sèrie màx"
			value={summary.serie_max ?? '—'}
			onClick={summary.serie_max != null
				? () =>
						openGamesModal(
							`Partides amb la sèrie màxima (${summary?.serie_max})`,
							(g) => playerSerie(g) === summary?.serie_max
						)
				: null}
		/>
	</div>

	<!-- ── Evolució al rànquing ───────────────────────────────────────────── -->
	<div class="mb-6">
		<Collapsible title="Evolució al rànquing" open={true}>
			<div class="flex items-center gap-3 mb-3">
				<label class="text-sm text-slate-600 font-medium" for="sel-hist-mod">Modalitat</label>
				<select
					id="sel-hist-mod"
					class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
					bind:value={chartMod}
					on:change={loadHistory}
				>
					{#each modalitats as m}
						<option value={m.codi_fcb}>{m.nom}</option>
					{/each}
				</select>
			</div>

			{#if loadingHistory}
				<p class="text-slate-500">Carregant…</p>
			{:else if history.length === 0}
				<p class="text-slate-500">Sense dades de rànquing per a aquesta modalitat.</p>
			{:else}
				<Card>
					<div class="p-4">
						<LineChart
							labels={chartLabels}
							series={chartSeries}
							yTitle="Mitjana"
							height={280}
						/>
					</div>
				</Card>
			{/if}
		</Collapsible>
	</div>

	<!-- ── Millors i pitjors partides ─────────────────────────────────────── -->
	<h2 class="text-lg font-semibold mb-3">Millors i pitjors partides</h2>
	<div class="grid grid-cols-1 gap-4 mb-6">
		<Collapsible
			title="🏆 Millors mitjanes"
			open={true}
			count={bestWorst?.best?.length ?? 0}
		>
			<SortableTable columns={bestWorstColumns} rows={bestWorst?.best ?? []} emptyText="Sense dades." />
		</Collapsible>

		<Collapsible
			title="✅ Millors victòries"
			open={true}
			count={bestWorst?.best_won?.length ?? 0}
		>
			<SortableTable columns={bestWorstColumns} rows={bestWorst?.best_won ?? []} emptyText="Sense dades." />
		</Collapsible>

		<Collapsible
			title="📉 Pitjors mitjanes"
			open={true}
			count={bestWorst?.worst?.length ?? 0}
		>
			<SortableTable columns={bestWorstColumns} rows={bestWorst?.worst ?? []} emptyText="Sense dades." />
		</Collapsible>

		<Collapsible
			title="❌ Pitjors derrotes"
			open={true}
			count={bestWorst?.worst_lost?.length ?? 0}
		>
			<SortableTable columns={bestWorstColumns} rows={bestWorst?.worst_lost ?? []} emptyText="Sense dades." />
		</Collapsible>
	</div>

	<!-- ── Últimes partides ───────────────────────────────────────────────── -->
	<Collapsible title="Últimes partides" open={true} count={games.length}>
		<SortableTable columns={gamesColumns} rows={games} emptyText="Sense partides registrades." />
	</Collapsible>

	<!-- ── Modal de partides (des d'un KPI) ───────────────────────────────── -->
	<Modal open={modalOpen} title={`${modalTitle} (${modalGames.length})`} on:close={() => (modalOpen = false)}>
		<div class="p-2">
			<SortableTable columns={gamesColumns} rows={modalGames} emptyText="Cap partida." />
		</div>
	</Modal>
{/if}
