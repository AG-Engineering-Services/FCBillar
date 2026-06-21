<script lang="ts">
	import { api, resolvePlayers, followedPlayers } from '$lib/opens/api';
	import { page } from '$app/stores';
	import Bracket from '$lib/components/Bracket.svelte';
	import type {
		LiveOpenResponse,
		LivePhase,
		LiveMatch,
		OpenDocument,
		RankingBandResponse,
		MonthlyRankingSummary
	} from '$lib/opens/types';

	let liveData = $state<LiveOpenResponse | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let refreshing = $state(false);
	let expandedGroup = $state<string | null>(null);
	let selectedPhase = $state<number | null>(null);
	let search = $state('');
	let showDocs = $state(false);
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	// Favorite players: normalized-uppercase names. Persisted to localStorage.
	// The normalized form (display_name uppercased) is what the API returns
	// — no diacritic stripping needed for this simple include check.
	const FAV_KEY = 'fcb_open_live_favorites';
	let favorites = $state<Set<string>>(new Set());
	let onlyFavorites = $state(false);

	// name -> FCBillar fcb_id, so live player names link to their profile.
	let fcbMap = $state<Record<string, string | null>>({});

	// Discipline (modality) of the open, derived from its name. The ranking-band
	// panel buckets players by the FCB *Tres Bandes* monthly ranking, so it only
	// makes sense for Tres Bandes opens — for Quadre / Banda / Lliure it would be
	// misleading. We surface the modality as a badge and gate the panel on it.
	function detectModality(name: string): string {
		const n = name.toUpperCase();
		if (n.includes('TRES BANDES') || n.includes('3 BANDES')) return 'Tres Bandes';
		if (n.includes('QUADRE 47/2')) return 'Quadre 47/2';
		if (n.includes('QUADRE 71/2')) return 'Quadre 71/2';
		if (n.includes('BANDA')) return 'Banda';
		if (n.includes('LLIURE')) return 'Lliure';
		return '';
	}
	let modality = $derived(liveData ? detectModality(liveData.name) : '');
	// Conservative: only show the TB ranking-band panel when we're sure it's
	// Tres Bandes. Unknown/other disciplines hide it.
	let isTresBandes = $derived(modality === 'Tres Bandes');

	function playerHref(name: string): string {
		const id = fcbMap[name];
		return id ? `/players/${encodeURIComponent(id)}` : `/players?q=${encodeURIComponent(name)}`;
	}

	function collectNames(data: LiveOpenResponse): string[] {
		const s = new Set<string>();
		for (const ph of data.phases) {
			for (const g of ph.groups ?? []) {
				for (const st of g.standings ?? []) s.add(st.player_name);
				for (const m of g.matches ?? []) {
					if (m.player_a) s.add(m.player_a);
					if (m.player_b) s.add(m.player_b);
				}
			}
		}
		return [...s];
	}

	// Merge the user's followed players (FCBillar 'seguiment') into the favourites
	// set so the "Només ★" filter can focus the live view on them.
	async function loadFollowed() {
		try {
			const f = await followedPlayers();
			if (f.length) {
				for (const p of f) favorites.add(normalizeFav(p.nom));
				favorites = new Set(favorites);
			}
		} catch {
			// ignore — followed list is best-effort
		}
	}

	function normalizeFav(name: string): string {
		return name.trim().toUpperCase();
	}

	function loadFavorites() {
		if (typeof localStorage === 'undefined') return;
		try {
			const raw = localStorage.getItem(FAV_KEY);
			if (raw) favorites = new Set(JSON.parse(raw) as string[]);
		} catch {
			// ignore
		}
	}

	function saveFavorites() {
		if (typeof localStorage === 'undefined') return;
		localStorage.setItem(FAV_KEY, JSON.stringify([...favorites]));
	}

	function toggleFavorite(name: string) {
		const key = normalizeFav(name);
		if (favorites.has(key)) favorites.delete(key);
		else favorites.add(key);
		favorites = new Set(favorites); // trigger reactivity
		saveFavorites();
	}

	function isFavorite(name: string): boolean {
		return favorites.has(normalizeFav(name));
	}

	async function load(force = false) {
		const id = Number($page.params.divisionId);
		if (!Number.isFinite(id)) {
			error = 'divisionId invàlid';
			loading = false;
			return;
		}
		try {
			refreshing = force;
			// Persist a snapshot on manual refreshes so we keep a timeline.
			const data = await api.getOpenLive(id, { force, persist: force });
			liveData = data;
			error = null;
			resolvePlayers(collectNames(data))
				.then((m) => (fcbMap = { ...fcbMap, ...m }))
				.catch(() => {});
			// Default to the first INCOMPLETE phase (not yet finished) if nothing
			// selected yet — so an open with an already-completed phase opens on the
			// phase that's actually in play. If every phase is done, show the last.
			if (selectedPhase === null) {
				const firstIncomplete = data.phases.findIndex((p) => phaseStatus(p) !== 'done');
				selectedPhase = firstIncomplete >= 0 ? firstIncomplete : Math.max(0, data.phases.length - 1);
			}
			// Refresh snapshot count on each load
			api
				.listSnapshots(id)
				.then((s) => (snapshotCount = s.length))
				.catch(() => {});
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	let snapshotCount = $state(0);
	let documents = $state<OpenDocument[]>([]);

	// Parallel by-ranking-band view (lazy: not fetched until the user
	// opens the panel; once open it refreshes on each poll cycle).
	let showBands = $state(false);
	let bandData = $state<RankingBandResponse | null>(null);
	let bandLoading = $state(false);
	let bandError = $state<string | null>(null);

	// Prize-ranking selector. The prizes of an Open are decided by each
	// player's FCB Tres Bandes position *at the moment of the convocatòria*,
	// which is not always the latest published ranking. The user picks which
	// monthly ranking applies; the choice is persisted per Open and the bands
	// recompute automatically.
	let rankings = $state<MonthlyRankingSummary[]>([]);
	let selectedMonthId = $state<number | null>(null);

	// Catalan calendar label for an FCB ranking month_id. Anchor:
	// month_id 120 = March 2026 (see src/fcb_opens/scraper/ranking.py); the
	// FCB publishes one per month, monotonically increasing.
	const CA_MONTHS = [
		'Gener', 'Febrer', 'Març', 'Abril', 'Maig', 'Juny',
		'Juliol', 'Agost', 'Setembre', 'Octubre', 'Novembre', 'Desembre'
	];
	function monthLabel(monthId: number): string {
		const abs = 2026 * 12 + 2 + (monthId - 120); // 2 = March (0-based)
		const year = Math.floor(abs / 12);
		const month = ((abs % 12) + 12) % 12;
		return `${CA_MONTHS[month]} ${year}`;
	}

	async function ensureRankings() {
		if (rankings.length) return;
		try {
			rankings = await api.listMonthlyRankings();
		} catch {
			// best-effort: without the list the selector falls back to a label
		}
	}

	async function loadBands(monthId?: number | null) {
		const id = Number($page.params.divisionId);
		if (!Number.isFinite(id)) return;
		bandLoading = true;
		bandError = null;
		try {
			bandData = await api.getLiveOpenByRankingBand(
				id,
				monthId != null ? { monthId } : undefined
			);
			// Sync the selector to whatever the backend resolved (saved or latest).
			selectedMonthId = bandData.month_id;
		} catch (e: any) {
			bandError = e.message;
		} finally {
			bandLoading = false;
		}
	}

	// User picked a ranking: persist it for this Open and recompute the bands.
	async function onSelectRanking(monthId: number) {
		const id = Number($page.params.divisionId);
		if (!Number.isFinite(id)) return;
		selectedMonthId = monthId;
		try {
			await api.setPrizeRanking(id, monthId);
		} catch {
			// even if persisting fails, still show the recomputed view
		}
		await loadBands(monthId);
	}

	function toggleBands() {
		showBands = !showBands;
		if (showBands) {
			ensureRankings();
			if (bandData === null && !bandLoading) loadBands();
		}
	}

	$effect(() => {
		const id = Number($page.params.divisionId);
		if (!Number.isFinite(id)) return;
		api
			.getDocsForOpen(id)
			.then((d) => (documents = d))
			.catch(() => (documents = []));
	});

	$effect(() => {
		loadFavorites();
		loadFollowed();
		load(false);
		// Poll every 2 minutes while tab is active
		pollTimer = setInterval(() => {
			if (document.visibilityState === 'visible') {
				load(true);
				if (showBands) loadBands();
			}
		}, 120_000);
		return () => {
			if (pollTimer) clearInterval(pollTimer);
		};
	});

	function toggleGroup(label: string) {
		expandedGroup = expandedGroup === label ? null : label;
	}

	function phaseStatus(p: LivePhase): 'done' | 'active' | 'pending' {
		if (p.kind === 'group') {
			const total = p.groups.reduce((a, g) => a + g.n_matches_total, 0);
			const played = p.groups.reduce((a, g) => a + g.n_matches_played, 0);
			if (total === 0) return 'pending';
			if (played === 0) return 'pending';
			if (played === total) return 'done';
			return 'active';
		} else {
			if (p.ko_matches.length === 0) return 'pending';
			const played = p.ko_matches.filter((m) => m.is_played).length;
			if (played === 0) return 'pending';
			if (played === p.ko_matches.length) return 'done';
			return 'active';
		}
	}

	function matchesForPlayer(needle: string): Array<{
		phase: string;
		where: string;
		match: LiveMatch;
	}> {
		if (!liveData || !needle.trim()) return [];
		const n = needle.trim().toUpperCase();
		const out: Array<{ phase: string; where: string; match: LiveMatch }> = [];
		for (const ph of liveData.phases) {
			for (const g of ph.groups) {
				for (const m of g.matches) {
					if (m.player_a.toUpperCase().includes(n) || m.player_b.toUpperCase().includes(n)) {
						out.push({ phase: ph.label, where: g.label, match: m });
					}
				}
			}
			for (const m of ph.ko_matches) {
				if (m.player_a.toUpperCase().includes(n) || m.player_b.toUpperCase().includes(n)) {
					out.push({ phase: ph.label, where: 'KO', match: m });
				}
			}
		}
		return out;
	}
</script>

{#if loading}
	<p class="text-slate-500">Carregant estat del torneig…</p>
{:else if error}
	<div class="card border-red-200 bg-red-50 text-red-800">{error}</div>
{:else if liveData}
	<div class="mb-4 flex items-start justify-between gap-4">
		<div>
			<div class="flex flex-wrap items-center gap-2">
				<h1 class="text-2xl font-semibold">{liveData.name}</h1>
				{#if modality}
					<span
						class="shrink-0 rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-slate-600"
						title="Modalitat"
					>
						{modality}
					</span>
				{/if}
			</div>
			<p class="mt-1 text-sm text-slate-500">
				FCB #{liveData.division_id} · actualitzat {new Date(liveData.fetched_at).toLocaleTimeString('ca-ES')}
			</p>
		</div>
		<div class="flex items-center gap-3">
			<input
				type="search"
				placeholder="Cerca jugador…"
				class="rounded border border-slate-300 px-3 py-1 text-sm"
				bind:value={search}
			/>
			<label class="flex items-center gap-1 text-sm text-slate-600">
				<input type="checkbox" bind:checked={onlyFavorites} />
				Només ★ i seguits ({favorites.size})
			</label>
			<button
				class="rounded bg-slate-800 px-3 py-1 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
				disabled={refreshing}
				onclick={() => load(true)}
			>
				{refreshing ? 'Refrescant…' : 'Refresca'}
			</button>
		</div>
	</div>

	<!-- Player search results -->
	{#if search.trim()}
		{@const results = matchesForPlayer(search)}
		<div class="card mb-4">
			<h3 class="mb-2 text-sm font-semibold">
				Resultats cerca ({results.length})
			</h3>
			{#if results.length === 0}
				<p class="text-sm text-slate-500">Cap partida amb aquest nom.</p>
			{:else}
				<ul class="space-y-1 text-sm">
					{#each results as r}
						<li>
							<span class="font-medium">{r.phase}</span>
							<span class="text-slate-500"> · {r.where}</span>
							<span class="ml-2">
								{r.match.player_a}
								<span class="mx-1 font-mono">{r.match.punts_a}–{r.match.punts_b}</span>
								{r.match.player_b}
							</span>
							{#if r.match.is_played}
								<span class="ml-2 text-xs text-slate-500">
									({r.match.caramboles_a}–{r.match.caramboles_b} car., {r.match.entrades} ent.)
								</span>
							{:else}
								<span class="ml-2 text-xs text-amber-700">(pendent)</span>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}

	<!-- Documents FCB: convocatòria, horaris, organigrama, grups publicats, etc. -->
	{#if documents.length > 0}
		<div class="card mb-4">
			<button
				class="flex w-full items-center gap-2 text-left"
				onclick={() => (showDocs = !showDocs)}
			>
				<span
					class="rounded bg-sky-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-sky-800"
					title="Documents publicats per la FCB"
				>
					FCB
				</span>
				<h3 class="text-sm font-semibold">
					Documents publicats ({documents.length})
				</h3>
				<span class="ml-auto text-slate-400">{showDocs ? '▾' : '▸'}</span>
			</button>
			{#if showDocs}
				<ul class="mt-3 space-y-1 text-sm">
					{#each documents as doc (doc.doc_id)}
						<li class="flex items-center gap-2">
							<span class="font-mono text-xs text-slate-400">{doc.date}</span>
							<a
								href="/opens-backend/api/opens/docs/{doc.doc_id}/pdf"
								target="_blank"
								rel="noopener"
								class="hover:underline"
							>
								{doc.title}
							</a>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}

	<!-- Parallel classifications by FCB ranking band (Tres Bandes only) -->
	{#if isTresBandes}
	<div class="card mb-4">
		<button
			class="flex w-full items-center gap-2 text-left"
			onclick={toggleBands}
		>
			<span
				class="rounded bg-indigo-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-indigo-800"
				title="Filtrat per posició FCB al moment de la convocatòria"
			>
				FCB
			</span>
			<h3 class="text-sm font-semibold">Classificacions paral·leles per banda de rànquing</h3>
			<span class="ml-auto text-slate-400">{showBands ? '▾' : '▸'}</span>
		</button>
		{#if showBands}
			{#if bandLoading && bandData === null}
				<p class="mt-3 text-sm text-slate-500">Carregant…</p>
			{:else if bandError}
				<p class="mt-3 text-sm text-red-700">{bandError}</p>
			{:else if bandData}
				<div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
					<label for="prize-ranking" class="font-medium">Rànquing aplicable (premis):</label>
					{#if rankings.length}
						<select
							id="prize-ranking"
							class="rounded border border-slate-300 bg-white px-2 py-1 text-xs"
							bind:value={selectedMonthId}
							onchange={() => {
								if (selectedMonthId != null) onSelectRanking(selectedMonthId);
							}}
						>
							{#each rankings as r, i (r.month_id)}
								<option value={r.month_id}>
									{monthLabel(r.month_id)} (#{r.month_id}){i === 0 ? ' · darrer' : ''}
								</option>
							{/each}
						</select>
					{:else}
						<span class="font-mono">{monthLabel(bandData.month_id)} (#{bandData.month_id})</span>
					{/if}
					{#if bandData.month_is_saved}
						<span
							class="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700"
							title="Triat manualment per a aquest open"
						>
							fixat
						</span>
					{:else}
						<span class="text-[11px] italic text-slate-400">(per defecte: darrer publicat)</span>
					{/if}
					{#if bandLoading}<span class="italic">actualitzant…</span>{/if}
				</div>
				<p class="mt-1 text-[11px] text-slate-400">
					Posició al rànquing FCB Tres Bandes en el moment de la convocatòria.
				</p>
				<div class="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
					{#each [{ title: 'Banda 61-180', entries: bandData.band_61_180 }, { title: 'Banda 181 → fi', entries: bandData.band_181_plus }] as band}
						<div>
							<h4 class="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">
								{band.title} ({band.entries.length})
							</h4>
							{#if band.entries.length === 0}
								<p class="text-xs italic text-slate-400">Cap jugador en aquesta banda.</p>
							{:else}
								<div class="overflow-x-auto rounded-md border border-slate-200">
									<table class="min-w-full text-xs">
										<thead class="bg-slate-50 text-slate-600">
											<tr>
												<th class="px-2 py-1 text-right font-medium">FCB</th>
												<th class="px-2 py-1 text-left font-medium">Jugador</th>
												<th class="px-2 py-1 text-left font-medium">Club</th>
												<th class="px-2 py-1 text-left font-medium">Grup</th>
												<th class="px-2 py-1 text-right font-medium">Pts</th>
												<th class="px-2 py-1 text-right font-medium">Mitjana</th>
											</tr>
										</thead>
										<tbody>
											{#each band.entries as e (e.player_name)}
												<tr class="border-t border-slate-100">
													<td class="px-2 py-1 text-right font-mono text-slate-500">
														{e.fcb_position}
													</td>
													<td class="px-2 py-1 font-medium">{e.player_name}</td>
													<td class="px-2 py-1 text-slate-600">{e.club}</td>
													<td class="px-2 py-1 text-slate-500">{e.group_label}</td>
													<td class="px-2 py-1 text-right font-mono">{e.punts}</td>
													<td class="px-2 py-1 text-right font-mono">{e.mitjana.toFixed(3)}</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
							{/if}
						</div>
					{/each}
				</div>
				{#if bandData.unranked.length > 0}
					<details class="mt-3">
						<summary class="cursor-pointer text-xs text-slate-500 hover:text-slate-700">
							Sense rànquing FCB ({bandData.unranked.length})
						</summary>
						<ul class="mt-2 space-y-0.5 text-xs text-slate-600">
							{#each bandData.unranked as e (e.player_name)}
								<li>
									{e.player_name}
									<span class="text-slate-400">— {e.club} · {e.group_label}</span>
								</li>
							{/each}
						</ul>
					</details>
				{/if}
			{/if}
		{/if}
	</div>

	{/if}

	<!-- Phase progress bar -->
	<div class="card mb-4">
		<div class="flex flex-wrap gap-2">
			{#each liveData.phases as p, i}
				{@const status = phaseStatus(p)}
				<button
					class="rounded border px-3 py-1 text-sm font-medium transition-colors"
					class:border-emerald-500={status === 'done'}
					class:bg-emerald-50={status === 'done'}
					class:text-emerald-800={status === 'done'}
					class:border-amber-500={status === 'active'}
					class:bg-amber-50={status === 'active'}
					class:text-amber-800={status === 'active'}
					class:border-slate-300={status === 'pending'}
					class:bg-slate-50={status === 'pending'}
					class:text-slate-500={status === 'pending'}
					class:ring-2={selectedPhase === i}
					class:ring-slate-400={selectedPhase === i}
					onclick={() => (selectedPhase = i)}
				>
					{p.label}
					{#if status === 'done'}✓{:else if status === 'active'}●{:else}○{/if}
				</button>
			{/each}
		</div>
	</div>

	<!-- Selected phase content -->
	{#if selectedPhase !== null}
		{@const phase = liveData.phases[selectedPhase]}
		{#if phase.kind === 'group'}
			{@const visibleGroups = onlyFavorites
				? phase.groups.filter((g) => g.standings.some((s) => isFavorite(s.player_name)))
				: phase.groups}
			{#if onlyFavorites && visibleGroups.length === 0}
				<p class="text-sm text-slate-500 italic">
					Cap jugador favorit en aquesta fase. Afegeix-ne clicant el ★ a qualsevol grup.
				</p>
			{/if}

			<!-- Provisional qualifiers: our own computation, not FCB-official. -->
			{#if phase.provisional_qualifiers.length > 0}
				{@const winners = phase.provisional_qualifiers.filter(
					(q) => q.position_in_group === 1
				)}
				{@const runnersUp = phase.provisional_qualifiers.filter(
					(q) => q.position_in_group >= 2
				)}
				<div class="card mb-4 border-dashed border-slate-300 bg-slate-50/50">
					<div class="mb-2 flex items-center gap-2">
						<span
							class="rounded bg-slate-200 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-slate-700"
							title="Dades derivades del càlcul intern, no publicades per la FCB"
						>
							Calculat
						</span>
						<h3 class="text-sm font-semibold">
							Classificats provisionals ({phase.provisional_qualifiers.length})
						</h3>
						<span class="text-xs text-slate-500">
							· 1r sempre passa · 2n(s) si calen places
						</span>
					</div>
					{#if winners.length > 0}
						<p class="mt-2 text-xs font-semibold text-emerald-700">
							Guanyadors de grup ({winners.length}) · classificació garantida
						</p>
						<div class="grid gap-1 text-sm md:grid-cols-2 lg:grid-cols-4">
							{#each winners as q}
								{@const fav = isFavorite(q.player_name)}
								<div
									class="flex items-center gap-2 rounded border-l-2 border-emerald-400 px-2 py-0.5"
									class:bg-amber-50={fav}
								>
									<span class="font-mono text-xs text-slate-500">
										{q.group_label.replace('Grup ', '')}
									</span>
									<span class="flex-1 truncate">{q.player_name}</span>
									<span class="font-mono text-xs text-slate-500">{q.punts}pt · {q.mitjana.toFixed(3)}</span>
								</div>
							{/each}
						</div>
					{/if}
					{#if runnersUp.length > 0}
						<p class="mt-3 text-xs font-semibold text-amber-700">
							Segons ({runnersUp.length}) · contingents
						</p>
						<div class="grid gap-1 text-sm md:grid-cols-2 lg:grid-cols-4">
							{#each runnersUp as q}
								{@const fav = isFavorite(q.player_name)}
								<div
									class="flex items-center gap-2 rounded border-l-2 border-amber-400 px-2 py-0.5"
									class:bg-amber-50={fav}
								>
									<span class="font-mono text-xs text-slate-500">
										{q.group_label.replace('Grup ', '')}#{q.position_in_group}
									</span>
									<span class="flex-1 truncate">{q.player_name}</span>
									<span class="font-mono text-xs text-slate-500">{q.punts}pt · {q.mitjana.toFixed(3)}</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
			<div class="grid gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
				{#each visibleGroups as g (g.label)}
					{@const isExpanded = expandedGroup === g.label}
					{@const isDone = g.n_matches_total > 0 && g.n_matches_played === g.n_matches_total}
					{@const hasFav = g.standings.some((s) => isFavorite(s.player_name))}
					<button
						class="card text-left p-3 transition-shadow hover:shadow-md {isDone
							? 'border-emerald-200 bg-emerald-50'
							: ''} {hasFav ? 'ring-2 ring-amber-300' : ''}"
						onclick={() => toggleGroup(g.label)}
					>
						<div class="mb-2 flex items-baseline justify-between">
							<span class="font-semibold">{g.label}</span>
							<span
								class="text-xs"
								class:text-emerald-700={isDone}
								class:text-amber-700={!isDone}
							>
								{g.n_matches_played}/{g.n_matches_total}
							</span>
						</div>
						{#if g.standings.length > 0}
							<ol class="space-y-0.5 text-sm">
								{#each g.standings as s, idx}
									{@const fav = isFavorite(s.player_name)}
									{@const q = phase.provisional_qualifiers.find(
										(x) => x.player_name === s.player_name && x.group_label === g.label
									)}
									{@const isWinner = q?.position_in_group === 1}
									{@const isRunnerUp = (q?.position_in_group ?? 0) >= 2}
									<li
										class="flex items-center gap-2 rounded {isRunnerUp && !fav
											? 'bg-amber-50/60'
											: ''}"
										class:bg-amber-50={fav}
										class:bg-emerald-50={isWinner && !fav}
									>
										<span
											class="w-4 text-right font-mono"
											class:text-emerald-600={isWinner}
											class:text-amber-600={isRunnerUp}
											class:text-slate-400={!q}
										>
											{isWinner ? '▸' : isRunnerUp ? '·' : idx + 1}
										</span>
										<a href={playerHref(s.player_name)} class="flex-1 truncate hover:underline">{s.player_name}</a>
										<span
											role="button"
											tabindex="0"
											class="cursor-pointer select-none text-sm leading-none"
											class:text-amber-500={fav}
											class:text-slate-300={!fav}
											title={fav ? 'Treure de favorits' : 'Afegir a favorits'}
											onclick={(e) => {
												e.stopPropagation();
												toggleFavorite(s.player_name);
											}}
											onkeydown={(e) => {
												if (e.key === 'Enter' || e.key === ' ') {
													e.stopPropagation();
													e.preventDefault();
													toggleFavorite(s.player_name);
												}
											}}
										>
											{fav ? '★' : '☆'}
										</span>
										<span class="font-mono text-xs text-slate-500">{s.mitjana.toFixed(3)}</span>
										<span class="w-6 text-right font-mono font-semibold">{s.punts}</span>
									</li>
								{/each}
							</ol>
						{:else}
							<p class="text-xs text-slate-400">Sense classificació</p>
						{/if}
						{#if isExpanded && g.matches.length > 0}
							<div class="mt-3 border-t border-slate-200 pt-2 text-xs">
								{#each g.matches as m}
									<div class="py-1">
										<div class="flex justify-between">
											<span class="truncate">{m.player_a}</span>
											<span class="font-mono">{m.punts_a}–{m.punts_b}</span>
											<span class="truncate text-right">{m.player_b}</span>
										</div>
										{#if m.is_played}
											<div class="text-slate-400">
												{m.caramboles_a}–{m.caramboles_b} car. · {m.entrades} ent.
											</div>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
					</button>
				{/each}
			</div>
		{:else}
			<!-- KO phase: render the entire bracket spanning all KO rounds.
			     The Bracket component handles its own provisional-vs-official
			     marking for the first round. -->
			{@const koPhases = liveData.phases.filter((p) => p.kind === 'ko')}
			{@const anyOfficial = koPhases.some((p) => p.ko_matches.length > 0)}
			{@const anyProvisional = koPhases.some((p) => p.provisional_matches.length > 0)}
			<div class="card p-3">
				<div class="mb-2 flex items-center gap-2">
					{#if anyOfficial}
						<span
							class="rounded bg-sky-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-sky-800"
							title="Dades publicades per la FCB"
						>
							FCB
						</span>
					{/if}
					{#if anyProvisional}
						<span
							class="rounded bg-slate-200 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-slate-700"
							title="Emparellament calculat internament"
						>
							Calculat
						</span>
					{/if}
					<h3 class="text-sm font-semibold">Bracket</h3>
				</div>
				<Bracket koPhases={koPhases} highlightName={search} {favorites} />
			</div>
		{/if}
	{/if}

	<p class="mt-6 text-xs text-slate-400">
		Les dades es refresquen automàticament cada 2 minuts mentre la pàgina estigui activa.
		{#if snapshotCount > 0}
			· {snapshotCount} snapshot{snapshotCount === 1 ? '' : 's'} desat{snapshotCount === 1 ? '' : 's'}
		{/if}
		· <a href="/opens/live" class="hover:underline">← Tots els Opens</a>
	</p>
{/if}
