<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { GameRow, TorneigRow } from '$lib/types';
	import Collapsible from '$lib/components/Collapsible.svelte';
	import SortableTable from '$lib/components/SortableTable.svelte';
	import GrupResultats from '$lib/components/GrupResultats.svelte';
	import EncontreModal from '$lib/components/EncontreModal.svelte';
	import CopaGrupResultats from '$lib/components/CopaGrupResultats.svelte';
	import CopaEncontreModal from '$lib/components/CopaEncontreModal.svelte';
	import { fmtDate, mitjana, fmtMitjana, winnerBadge } from '$lib/format';

	// Modal de detall d'encontre (compartit per lliga i copa)
	let encontreModalOpen = false;
	let encontreModalId: number | null = null;
	function openEncontre(id: number) {
		encontreModalId = id;
		encontreModalOpen = true;
	}

	// Modal de detall d'encontre de copa
	let copaEncontreOpen = false;
	let copaEncontreId: number | null = null;
	function openCopaEncontre(id: number) {
		copaEncontreId = id;
		copaEncontreOpen = true;
	}

	type Standing = {
		posicio: number;
		equip: string;
		pj: number;
		g: number;
		e: number;
		p: number;
		punts: number;
		parcials_favor: number;
		parcials_contra: number;
	};
	type Group = { grup_id: number; nom: string; standings: Standing[] };
	type Category = { divisio_id: number; nom: string; groups: Group[] };
	type Competition = { lliga_id: number; nom: string; categories: Category[] };

	let tab: 'lliga' | 'copa' | 'individuals' = 'lliga';

	// ── Lliga ──────────────────────────────────────────────────────────────
	let lligaSeasonOnly = true;
	let tree: Competition[] = [];
	let lligaLoading = false;
	let selectedComp: number | null = null;
	let activeCats = new Set<number>();

	const standingColumns = [
		{ key: 'posicio', label: '#', numeric: true, muted: true },
		{ key: 'equip', label: 'Equip' },
		{ key: 'pj', label: 'PJ', numeric: true },
		{ key: 'g', label: 'G', numeric: true },
		{ key: 'e', label: 'E', numeric: true },
		{ key: 'p', label: 'P', numeric: true },
		{ key: 'punts', label: 'Punts', numeric: true },
		{ key: 'parcials_favor', label: 'PF', numeric: true, muted: true },
		{ key: 'parcials_contra', label: 'PC', numeric: true, muted: true }
	];

	async function loadTree() {
		lligaLoading = true;
		try {
			tree = await api<Competition[]>(`/api/results/lliga/tree?season_only=${lligaSeasonOnly}`);
			if (tree.length && (selectedComp === null || !tree.some((c) => c.lliga_id === selectedComp))) {
				selectedComp = tree[0].lliga_id;
			}
			resetCats();
			lligaRankMod = defaultModForComp();
		} catch (e) {
			console.error(e);
			tree = [];
		} finally {
			lligaLoading = false;
		}
	}

	function currentComp(): Competition | undefined {
		return tree.find((c) => c.lliga_id === selectedComp);
	}
	function resetCats() {
		const comp = currentComp();
		activeCats = new Set(comp ? comp.categories.map((c) => c.divisio_id) : []);
	}
	function toggleCat(divisioId: number) {
		const next = new Set(activeCats);
		if (next.has(divisioId)) next.delete(divisioId);
		else next.add(divisioId);
		activeCats = next;
	}
	function allCats() {
		resetCats();
	}
	function noCats() {
		activeCats = new Set();
	}
	function onCompChange() {
		resetCats();
		lligaRankMod = defaultModForComp();
		if (lligaRankOpen) loadLligaRanking();
	}

	// Reactiu: depèn de tree+selectedComp. NO usar currentComp() directament a la
	// plantilla — Svelte no en rastreja les dependències i el deixa fixat al valor
	// inicial (undefined), fent que mai es mostri la lliga.
	$: comp = tree.find((c) => c.lliga_id === selectedComp);
	$: visibleCategories = (comp?.categories ?? []).filter((c) => activeCats.has(c.divisio_id));

	// ── Copa ───────────────────────────────────────────────────────────────
	// Per defecte mostrem totes les temporades: les dades de copa solen ser de
	// temporades anteriors i amb season-only quedaria buit.
	let copaSeasonOnly = false;
	let copa: GameRow[] = [];
	let copaLoading = false;
	let copaLoaded = false;

	const copaColumns = [
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
		{ key: 'm2', label: 'M₂', numeric: true, value: (r: any) => mitjana(r.cara2, r.entrades), fmt: fmtMitjana },
		{ key: 'club_local', label: 'Club local', muted: true, fmt: (v: any) => v ?? '' },
		{ key: 'club_visitant', label: 'Club visitant', muted: true, fmt: (v: any) => v ?? '' }
	];

	async function loadCopa() {
		copaLoading = true;
		try {
			copa = await api<GameRow[]>(`/api/results/copa?season_only=${copaSeasonOnly}&limit=300`);
			copaLoaded = true;
		} catch (e) {
			console.error(e);
		} finally {
			copaLoading = false;
		}
	}

	// Estructura de copa: edicions → jornades → grups
	type CopaEdicio = { edicio_id: number; nom: string; n_jornades: number; temporada: string };
	type CopaGrup = { grup_id: number; grup_nom: string };
	type CopaJornada = { jornada: number; ordre: number; nom: string; grups: CopaGrup[] };

	let copaEdicions: CopaEdicio[] = [];
	let copaEdicioId: number | null = null;
	let copaJornades: CopaJornada[] = [];
	let copaStructLoaded = false;

	async function loadCopaEdicions() {
		if (copaStructLoaded) return;
		copaStructLoaded = true;
		try {
			copaEdicions = await api<CopaEdicio[]>('/api/results/copa/edicions');
			if (copaEdicions.length) {
				copaEdicioId = copaEdicions[0].edicio_id;
				await loadCopaJornades();
			}
		} catch (e) {
			console.error(e);
		}
	}

	async function loadCopaJornades() {
		if (copaEdicioId === null) {
			copaJornades = [];
			return;
		}
		try {
			copaJornades = await api<CopaJornada[]>(
				`/api/results/copa/jornades?edicio_id=${copaEdicioId}`
			);
		} catch (e) {
			console.error(e);
			copaJornades = [];
		}
	}

	// ── Rànquing de jugadors (lliga / copa) ──────────────────────────────────
	// Ordenat per defecte per posició = punts aconseguits i, a igualtat, mitjana
	// (l'API ja ho retorna ordenat). Totes les columnes són reordenables.
	const playerRankColumns = [
		{ key: 'posicio', label: '#', numeric: true, muted: true },
		{
			key: 'nom',
			label: 'Jugador',
			link: (r: any) => (r.fcb_id ? `/players/${r.fcb_id}` : null)
		},
		{ key: 'pj', label: 'PJ', numeric: true },
		{ key: 'g', label: 'G', numeric: true },
		{ key: 'punts', label: 'Punts', numeric: true },
		{ key: 'caramboles', label: 'C', numeric: true, muted: true },
		{ key: 'entrades', label: 'E', numeric: true, muted: true },
		{
			key: 'mitjana',
			label: 'Mitjana',
			numeric: true,
			fmt: (v: any) => (v != null ? v.toFixed(4) : '—')
		}
	];

	// Modalitats segons el tipus de lliga. La modalitat ja discrimina el tipus de
	// lliga: el 3 bandes només es juga a la lliga Tres Bandes; Lliure/Banda/Quadre
	// només a la lliga de 4 Modalitats.
	const TRES_BANDES_MOD = { codi_fcb: 1, nom: 'Tres bandes' };
	const QUATRE_MODS = [
		{ codi_fcb: 2, nom: 'Lliure' },
		{ codi_fcb: 4, nom: 'Banda' },
		{ codi_fcb: 3, nom: 'Quadre 47/2' },
		{ codi_fcb: 6, nom: 'Quadre 71/2' }
	];
	$: isQuatreMod = !!comp && /modalitats/i.test(comp.nom);
	$: rankMods = isQuatreMod ? QUATRE_MODS : [TRES_BANDES_MOD];

	let lligaTemporades: { id: number; nom: string }[] = [];
	let lligaRankMod = 1; // preseleccionada segons el tipus de lliga
	let lligaRankTemp: number | null = null; // per defecte la més recent
	let lligaRanking: any[] = [];
	let lligaRankOpen = false;
	let lligaRankLoaded = false;

	// Modalitat per defecte d'una competició: 4 Modalitats → Lliure (2); si no, 3b (1).
	function defaultModForComp(): number {
		const c = currentComp();
		return c && /modalitats/i.test(c.nom) ? 2 : 1;
	}

	async function loadLligaRanking() {
		if (!lligaTemporades.length) {
			lligaTemporades = await api('/api/results/lliga/temporades');
			if (lligaRankTemp === null && lligaTemporades.length)
				lligaRankTemp = lligaTemporades[0].id;
		}
		const p = new URLSearchParams();
		p.set('modalitat', String(lligaRankMod));
		if (lligaRankTemp != null) p.set('temporada_id', String(lligaRankTemp));
		lligaRanking = await api(`/api/results/lliga/player-ranking?${p}`);
	}
	function setRankMod(codi: number) {
		lligaRankMod = codi;
		loadLligaRanking();
	}
	$: if (lligaRankOpen && !lligaRankLoaded) {
		lligaRankLoaded = true;
		loadLligaRanking();
	}

	// Copa: rànquing de l'edició seleccionada (es recarrega en canviar d'edició)
	let copaRanking: any[] = [];
	let copaRankOpen = false;
	let copaRankEdicio: number | null = null;

	async function loadCopaRanking() {
		if (copaEdicioId == null) {
			copaRanking = [];
			return;
		}
		copaRanking = await api(`/api/results/copa/player-ranking?edicio_id=${copaEdicioId}`);
		copaRankEdicio = copaEdicioId;
	}
	$: if (copaRankOpen && copaEdicioId != null && copaRankEdicio !== copaEdicioId) loadCopaRanking();

	// ── Individuals ──────────────────────────────────────────────────────────
	let seasons: string[] = [];
	let indivSeason: string | undefined = undefined;
	let torneigs: TorneigRow[] = [];
	let indivTorneig: number | null = null;
	let classification: any[] = [];
	let indivLoaded = false;

	const indivColumns = [
		{ key: 'posicio', label: 'Pos', numeric: true, muted: true },
		{ key: 'nom', label: 'Jugador', link: (r: any) => (r.fcb_id ? `/players/${r.fcb_id}` : null) },
		{ key: 'club_text', label: 'Club', fmt: (v: any) => v ?? '' },
		{ key: 'partides_jugades', label: 'PJ', numeric: true },
		{ key: 'punts', label: 'Punts', numeric: true },
		{ key: 'caramboles', label: 'C', numeric: true },
		{ key: 'entrades', label: 'E', numeric: true },
		{ key: 'mitjana_general', label: 'MG', numeric: true, fmt: (v: any) => (v != null ? v.toFixed(4) : '—') },
		{ key: 'mitjana_particular', label: 'MP', numeric: true, fmt: (v: any) => (v != null ? v.toFixed(4) : '—') },
		{ key: 'serie_max', label: 'Sèrie', numeric: true }
	];

	async function loadSeasons() {
		seasons = await api<string[]>('/api/results/individuals/seasons');
		await loadTorneigs();
	}
	async function loadTorneigs() {
		const q = indivSeason ? `?temporada=${encodeURIComponent(indivSeason)}` : '';
		torneigs = await api<TorneigRow[]>(`/api/results/individuals${q}`);
		const first = torneigs.find((t) => t.num_participants > 0) ?? torneigs[0];
		indivTorneig = first ? first.id : null;
		await loadClassification();
	}
	// Fases (composició de grups). El portal no publica classificacions amb punts
	// per fase, només l'assignació jugador→grup.
	type IndivFase = {
		fase_id: number;
		nom: string;
		tipus: string;
		ordre: number;
		grups: { grup_nom: string; jugadors: string[] }[];
	};
	let indivPhases: IndivFase[] = [];

	async function loadClassification() {
		if (indivTorneig === null) {
			classification = [];
			indivPhases = [];
			return;
		}
		classification = await api<any[]>(`/api/results/individuals/${indivTorneig}`);
		try {
			indivPhases = await api<IndivFase[]>(`/api/results/individuals/${indivTorneig}/phases`);
		} catch (e) {
			console.error(e);
			indivPhases = [];
		}
	}

	function setTab(t: typeof tab) {
		tab = t;
		if (t === 'copa') {
			if (!copaLoaded) loadCopa();
			loadCopaEdicions();
		}
		if (t === 'individuals' && !indivLoaded) {
			indivLoaded = true;
			loadSeasons();
		}
	}

	onMount(loadTree);
</script>

<h1 class="text-2xl font-bold mb-4">Resultats</h1>

<div class="flex gap-1 mb-4">
	<button
		class="px-3 py-1.5 rounded-md text-sm {tab === 'lliga' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}"
		on:click={() => setTab('lliga')}>Lliga</button
	>
	<button
		class="px-3 py-1.5 rounded-md text-sm {tab === 'copa' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}"
		on:click={() => setTab('copa')}>Copa</button
	>
	<button
		class="px-3 py-1.5 rounded-md text-sm {tab === 'individuals' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}"
		on:click={() => setTab('individuals')}>Individuals</button
	>
</div>

{#if tab === 'lliga'}
	<div class="flex flex-wrap gap-3 items-center mb-4">
		<label class="flex items-center gap-2 text-sm text-slate-600">
			<input type="checkbox" bind:checked={lligaSeasonOnly} on:change={loadTree} />
			Només temporada actual
		</label>
		{#if tree.length > 1}
			<select
				class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
				bind:value={selectedComp}
				on:change={onCompChange}
			>
				{#each tree as comp}
					<option value={comp.lliga_id}>{comp.nom}</option>
				{/each}
			</select>
		{:else if tree.length === 1}
			<span class="text-sm font-medium">{tree[0].nom}</span>
		{/if}
	</div>

	<!-- Rànquing de jugadors de lliga -->
	<div class="mb-6">
		<Collapsible title="Rànquing de jugadors" subtitle="punts i mitjana" bind:open={lligaRankOpen}>
			<div class="p-3">
				<div class="flex flex-wrap gap-2 items-center mb-3">
					{#if rankMods.length > 1}
						<span class="text-xs uppercase tracking-wide text-slate-500 mr-1">Modalitat:</span>
						{#each rankMods as m}
							<button
								class="px-2.5 py-1 rounded-full text-xs border transition-colors {lligaRankMod ===
								m.codi_fcb
									? 'bg-slate-900 text-white border-slate-900'
									: 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100'}"
								on:click={() => setRankMod(m.codi_fcb)}
							>
								{m.nom}
							</button>
						{/each}
					{:else}
						<span class="text-xs uppercase tracking-wide text-slate-500"
							>Modalitat: <span class="font-medium text-slate-700">{rankMods[0].nom}</span></span
						>
					{/if}
					<span class="mx-1 text-slate-300">·</span>
					<select
						class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
						bind:value={lligaRankTemp}
						on:change={loadLligaRanking}
					>
						<option value={null}>Totes les temporades</option>
						{#each lligaTemporades as t}
							<option value={t.id}>{t.nom}</option>
						{/each}
					</select>
				</div>
				<SortableTable
					columns={playerRankColumns}
					rows={lligaRanking}
					initialSortKey="posicio"
					initialSortDir="asc"
					emptyText="Sense dades."
				/>
			</div>
		</Collapsible>
	</div>

	{#if lligaLoading}
		<p class="text-slate-500">Carregant…</p>
	{:else if !comp}
		<p class="text-slate-500">Sense dades de lliga.</p>
	{:else}
		<div class="flex flex-wrap items-center gap-2 mb-5">
			<span class="text-xs uppercase tracking-wide text-slate-500 mr-1">Categories:</span>
			{#each comp?.categories ?? [] as cat}
				<button
					class="px-2.5 py-1 rounded-full text-xs border transition-colors {activeCats.has(cat.divisio_id)
						? 'bg-slate-900 text-white border-slate-900'
						: 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100'}"
					on:click={() => toggleCat(cat.divisio_id)}
				>
					{cat.nom}
				</button>
			{/each}
			<span class="mx-1 text-slate-300">·</span>
			<button class="text-xs text-slate-500 hover:underline" on:click={allCats}>Totes</button>
			<button class="text-xs text-slate-500 hover:underline" on:click={noCats}>Cap</button>
		</div>

		{#if visibleCategories.length === 0}
			<p class="text-slate-500">Cap categoria seleccionada.</p>
		{/if}

		<div class="space-y-6">
			{#each visibleCategories as cat (cat.divisio_id)}
				<section>
					<h2 class="text-lg font-semibold mb-3">{cat.nom}</h2>
					<div class="grid gap-4 lg:grid-cols-2">
						{#each cat.groups as grup (grup.grup_id)}
							<GrupResultats
								lligaId={selectedComp ?? 0}
								divisioId={cat.divisio_id}
								grupId={grup.grup_id}
								nom={grup.nom}
								standings={grup.standings}
								{standingColumns}
								on:encontre={(e) => openEncontre(e.detail)}
							/>
						{/each}
					</div>
				</section>
			{/each}
		</div>
	{/if}
{:else if tab === 'copa'}
	{#if copaEdicions.length > 1}
		<div class="flex flex-wrap gap-3 items-center mb-4">
			<select
				class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
				bind:value={copaEdicioId}
				on:change={loadCopaJornades}
			>
				{#each copaEdicions as ed}
					<option value={ed.edicio_id}>{ed.nom}</option>
				{/each}
			</select>
		</div>
	{:else if copaEdicions.length === 1}
		<div class="flex flex-wrap gap-3 items-center mb-4">
			<span class="text-sm font-medium">{copaEdicions[0].nom}</span>
		</div>
	{/if}

	<!-- Rànquing de jugadors de copa (edició seleccionada) -->
	<div class="mb-6">
		<Collapsible title="Rànquing de jugadors" subtitle="Tres bandes · punts i mitjana" bind:open={copaRankOpen}>
			<div class="p-3">
				<SortableTable
					columns={playerRankColumns}
					rows={copaRanking}
					initialSortKey="posicio"
					initialSortDir="asc"
					emptyText="Sense dades."
				/>
			</div>
		</Collapsible>
	</div>

	{#if copaJornades.length === 0}
		<p class="text-slate-500 mb-6">Sense dades estructurades de copa.</p>
	{:else}
		<div class="space-y-6 mb-6">
			{#each copaJornades as j (j.jornada)}
				<Collapsible title={j.nom} count={j.grups.length} open={false}>
					<div class="p-3 grid gap-4 lg:grid-cols-2">
						{#each j.grups as grup (grup.grup_id)}
							<CopaGrupResultats
								edicioId={copaEdicioId ?? 0}
								jornada={j.jornada}
								grupId={grup.grup_id}
								grupNom={grup.grup_nom}
								on:encontre={(e) => openCopaEncontre(e.detail)}
							/>
						{/each}
					</div>
				</Collapsible>
			{/each}
		</div>
	{/if}

	<div class="flex flex-wrap gap-3 items-center mb-4">
		<label class="flex items-center gap-2 text-sm text-slate-600">
			<input type="checkbox" bind:checked={copaSeasonOnly} on:change={loadCopa} />
			Només temporada actual
		</label>
	</div>
	{#if copaLoading}
		<p class="text-slate-500">Carregant…</p>
	{:else}
		<Collapsible title="Totes les partides de copa" open={false} count={copa.length}>
			<SortableTable columns={copaColumns} rows={copa} emptyText="Cap partida disponible" />
		</Collapsible>
	{/if}
{:else}
	<div class="flex flex-wrap gap-3 items-center mb-4">
		<select
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
			bind:value={indivSeason}
			on:change={loadTorneigs}
		>
			<option value={undefined}>Totes les temporades</option>
			{#each seasons as s}
				<option value={s}>{s}</option>
			{/each}
		</select>
		<select
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
			bind:value={indivTorneig}
			on:change={loadClassification}
		>
			{#each torneigs as t}
				<option value={t.id}>{t.nom} ({t.num_participants})</option>
			{/each}
		</select>
	</div>
	<Collapsible title="Classificació final" open={true} count={classification.length}>
		<SortableTable
			columns={indivColumns}
			rows={classification}
			initialSortKey="posicio"
			initialSortDir="asc"
			emptyText="Cap resultat disponible"
		/>
	</Collapsible>

	{#if indivPhases.length}
		<div class="mt-4 space-y-4">
			{#each indivPhases as fase (fase.fase_id)}
				<Collapsible title={fase.nom} subtitle="composició de grups" count={fase.grups.length} open={false}>
					<div class="p-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
						{#each fase.grups as grup (grup.grup_nom)}
							<div class="rounded-md border border-slate-200">
								<div class="px-3 py-1.5 border-b border-slate-100 text-xs uppercase tracking-wide text-slate-500">
									{grup.grup_nom}
									<span class="text-slate-400">· {grup.jugadors.length}</span>
								</div>
								<ol class="px-3 py-2 text-sm list-decimal list-inside space-y-0.5">
									{#each grup.jugadors as jug}
										<li class="whitespace-nowrap">{jug}</li>
									{/each}
								</ol>
							</div>
						{/each}
					</div>
				</Collapsible>
			{/each}
		</div>
	{/if}
{/if}

<EncontreModal
	open={encontreModalOpen}
	encontreId={encontreModalId}
	on:close={() => (encontreModalOpen = false)}
/>

<CopaEncontreModal
	open={copaEncontreOpen}
	encontreId={copaEncontreId}
	on:close={() => (copaEncontreOpen = false)}
/>
