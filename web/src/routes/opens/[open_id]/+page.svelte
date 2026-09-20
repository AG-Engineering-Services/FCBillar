<script lang="ts">
	import { page } from '$app/stores';
	import {
		db,
		type Open,
		type OpenClassification,
		type OpenFase,
		type OpenFaseRanquing
	} from '$lib/db';

	const openId = $derived(Number($page.params.open_id));
	let open = $state<Open | null>(null);
	let rows = $state<OpenClassification[]>([]);
	let partides = $state<any[]>([]);
	let fases = $state<OpenFase[]>([]);
	let ranquing = $state<OpenFaseRanquing[]>([]);
	let faseOberta = $state<number | null>(null);
	let expanded = $state<string | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let q = $state('');
	const filteredRows = $derived(
		q.trim() ? rows.filter((r) => norm(r.jugador).includes(norm(q.trim()))) : rows
	);

	$effect(() => {
		const id = openId;
		if (!Number.isNaN(id)) load(id);
	});

	async function load(id: number) {
		loading = true;
		error = null;
		expanded = null;
		try {
			const [{ data: o }, { data: cl, error: e }, op, { data: fs }, { data: rq }] =
				await Promise.all([
					db.from('opens').select('*').eq('open_id', id).maybeSingle(),
					db.from('open_classifications').select('*').eq('open_id', id).order('posicio'),
					loadAllGames(id),
					db.from('open_fases').select('*').eq('open_id', id).order('ordre'),
					// El .range() és explícit perquè PostgREST talla a mil files en
					// silenci: una pre-prèvia de 2a divisió en porta 42, però un
					// campionat amb vuit divisions en pot portar moltes més.
					db
						.from('open_fase_ranquing')
						.select('*')
						.eq('open_id', id)
						.order('fase_id')
						.order('posicio')
						.range(0, 4999)
				]);
			if (e) throw e;
			open = (o ?? null) as Open | null;
			rows = (cl ?? []) as OpenClassification[];
			partides = op;
			fases = (fs ?? []) as OpenFase[];
			ranquing = (rq ?? []) as OpenFaseRanquing[];
			// S'obre l'última ronda amb rànquing, que és la que algú vol veure:
			// la que s'acaba de jugar i decideix qui passa.
			const ambRanquing = fases.filter((f) => ranquing.some((r) => r.fase_id === f.fase_id));
			faseOberta = ambRanquing.at(-1)?.fase_id ?? null;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	async function loadAllGames(id: number) {
		const pageSize = 1000;
		const result: any[] = [];
		for (let from = 0; ; from += pageSize) {
			const { data, error: gamesError } = await db
				.from('open_partides')
				.select('*')
				.eq('open_id', id)
				.order('fase_id')
				.order('ordre')
				.range(from, from + pageSize - 1);
			if (gamesError) throw gamesError;
			result.push(...(data ?? []));
			if (!data || data.length < pageSize) return result;
		}
	}

	function norm(s: string | null): string {
		return (s ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();
	}
	function gamesOf(nom: string) {
		const n = norm(nom);
		return partides
			.filter((p) => norm(p.jugador_local) === n || norm(p.jugador_visitant) === n)
			.map((p) => {
				const loc = norm(p.jugador_local) === n;
				return {
					opp: loc ? p.jugador_visitant : p.jugador_local,
					my: loc ? p.caramboles_local : p.caramboles_visitant,
					oppc: loc ? p.caramboles_visitant : p.caramboles_local,
					ent: p.entrades
				};
			});
	}
	function toggle(nom: string) {
		expanded = expanded === nom ? null : nom;
	}

	/** Les fases que tenen rànquing, de la primera a l'última. */
	const fasesAmbRanquing = $derived(
		fases.filter((f) => ranquing.some((r) => r.fase_id === f.fase_id))
	);
	const ranquingDeLaFase = $derived(ranquing.filter((r) => r.fase_id === faseOberta));
	/** Quants grups té la fase oberta: serveix per dir quants primers, quants segons… */
	const grupsDeLaFase = $derived(
		new Set(ranquingDeLaFase.map((r) => r.grup_nom).filter(Boolean)).size
	);

	/**
	 * On es trenca la llista entre una posició de grup i la següent.
	 *
	 * És l'única cosa que fa llegible aquest rànquing: sense la ratlla, «tots els
	 * primers i després tots els segons» sembla una llista qualsevol de 33 noms.
	 * Amb ella es veu d'un cop on acaben els primers, que és el que la federació
	 * fa servir per repartir les places.
	 */
	function primerDelSeuLloc(r: OpenFaseRanquing, i: number): boolean {
		return i === 0 || ranquingDeLaFase[i - 1].posicio_grup !== r.posicio_grup;
	}
</script>

<a href="/opens" class="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
	<span aria-hidden="true">←</span> Opens
</a>

{#if error}
	<div class="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-300">{error}</div>
{:else}
	<h1 class="mb-1 text-base font-bold leading-tight">
		{open ? open.nom.replace(/\s*-\s*[ÚU]NICA\s*$/i, '').trim() : '…'}
	</h1>
	{#if partides.length}
		<p class="mb-3 text-[11px] text-slate-500 dark:text-slate-400">Toca un jugador per veure el desglòs de partides.</p>
	{/if}

	{#if !loading && fasesAmbRanquing.length}
		<section class="mb-4">
			<h2 class="mb-1 text-sm font-semibold">Rondes</h2>
			<p class="mb-2 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
				Els grups d'una ronda es juguen per separat i la federació no publica cap
				ordre entre ells. Aquí van ordenats com ella els ordena: primer la posició
				dins del grup, després els punts de la ronda, i a igualtat de tots dos la
				mitjana. Serveix per veure qui passa quan se n'emporten «els millors
				segons».
			</p>
			<div class="mb-2 flex flex-wrap gap-1">
				{#each fasesAmbRanquing as f (f.fase_id)}
					<button
						onclick={() => (faseOberta = f.fase_id)}
						class="rounded-full px-2.5 py-1 text-[11px] font-medium {faseOberta === f.fase_id
							? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
							: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
					>
						{f.nom}
					</button>
				{/each}
			</div>
			{#if ranquingDeLaFase.length}
				<div
					class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800"
				>
					<div
						class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400"
					>
						<span class="w-5 text-center">#</span>
						<span class="flex-1">Jugador</span>
						<span class="w-14 text-center">Grup</span>
						<span class="w-8 text-right">Pts</span>
						<span class="w-12 text-right">Mitj.</span>
					</div>
					<ul>
						{#each ranquingDeLaFase as r, i (r.jugador)}
							{#if primerDelSeuLloc(r, i) && i > 0}
								<li
									class="border-y border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 px-3 py-1 text-[10px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400"
								>
									{r.posicio_grup}a posició de grup
								</li>
							{/if}
							<li
								class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0"
							>
								<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums text-slate-500 dark:text-slate-400">{r.posicio}</span>
								<div class="min-w-0 flex-1">
									{#if r.player_fcb_id}
										<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm font-medium leading-tight underline decoration-slate-300 dark:decoration-slate-600">{r.jugador}</a>
									{:else}
										<span class="block truncate text-sm font-medium leading-tight">{r.jugador}</span>
									{/if}
									{#if r.club}<span class="block truncate text-[10px] text-slate-500 dark:text-slate-400">{r.club}</span>{/if}
								</div>
								<span class="w-14 shrink-0 text-center text-[11px] text-slate-500 dark:text-slate-400">{r.grup_nom ?? '—'}</span>
								<span class="w-8 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts ?? 0}</span>
								<span class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">{r.mitjana != null ? r.mitjana.toFixed(3) : '—'}</span>
							</li>
						{/each}
					</ul>
				</div>
				<p class="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
					{ranquingDeLaFase.length} jugadors en {grupsDeLaFase} grups. Qui no ha jugat cap
					partida hi surt sense mitjana.
				</p>
			{/if}
		</section>
	{/if}

	{#if loading}
		<p class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">Carregant…</p>
	{:else if rows.length === 0}
		<p class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">Sense classificació disponible.</p>
	{:else}
		{#if rows.length > 10}
			<input
				bind:value={q}
				inputmode="search"
				placeholder="Cerca jugador…"
				class="mb-3 w-full rounded-lg border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-2 px-3 text-sm shadow-sm"
			/>
		{/if}
		<div class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
			<div class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
				<span class="w-5 text-center">#</span>
				<span class="flex-1">Jugador</span>
				<span class="w-7 text-center">PJ</span>
				<span class="w-12 text-right">Mitj.</span>
				<span class="w-8 text-right">Pts</span>
			</div>
			<ul>
				{#each filteredRows as r (r.player_fcb_id)}
					<li class="border-b border-slate-100 dark:border-slate-800 last:border-0">
						<button onclick={() => toggle(r.jugador ?? '')} class="flex w-full items-center gap-2 px-3 py-2 text-left active:bg-slate-50 dark:active:bg-slate-800/50">
							<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}">{r.posicio}</span>
							<div class="min-w-0 flex-1">
								<div class="truncate text-sm font-medium leading-tight">{r.jugador}</div>
								{#if r.club}<div class="truncate text-[11px] text-slate-500 dark:text-slate-400">{r.club}</div>{/if}
							</div>
							<span class="w-7 shrink-0 text-center text-sm tabular-nums text-slate-500 dark:text-slate-400">{r.partides}</span>
							<span class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">{r.mitjana_general != null ? r.mitjana_general.toFixed(3) : '—'}</span>
							<span class="w-8 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
						</button>
						{#if expanded === r.jugador}
							<div class="border-t border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/60 px-3 py-2">
								{#each gamesOf(r.jugador ?? '') as g}
									<div class="flex items-center gap-2 py-0.5 text-[11px]">
										<span class="flex-1 truncate">vs {g.opp}</span>
										<span class="font-mono tabular-nums {g.my > g.oppc ? 'font-bold text-emerald-600 dark:text-emerald-400' : 'text-slate-500 dark:text-slate-400'}">{g.my}–{g.oppc}</span>
										<span class="w-12 text-right text-slate-500 dark:text-slate-400">{g.ent} ent</span>
									</div>
								{:else}
									<p class="py-1 text-[11px] text-slate-500 dark:text-slate-400">No hi ha partides desglossades disponibles per aquest jugador.</p>
								{/each}
								{#if r.player_fcb_id}
									<a href="/jugador/{r.player_fcb_id}" class="mt-1 inline-block text-[11px] text-slate-500 dark:text-slate-400 underline">Fitxa completa →</a>
								{/if}
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		</div>
	{/if}
{/if}
