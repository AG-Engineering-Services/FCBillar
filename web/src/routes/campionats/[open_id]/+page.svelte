<script lang="ts">
	// Un campionat de Catalunya, llegit com es llegeix un campionat.
	//
	// I per això té la seva pàgina i no la dels opens. Un campionat NO és un open:
	// es reparteix per divisions (Honor, 1a…6a) i es juga per rondes —pre-prèvia,
	// prèvia, vuitens, i després el quadre—, on cada ronda és una colla de grups
	// de tres o quatre que juguen per separat i dels quals passen uns quants.
	//
	// El que fa falta veure-hi, i que a la pàgina d'un open no hi cabia:
	//
	//  - cada GRUP amb la seva classificació i, al costat, les partides que
	//    l'expliquen;
	//  - i el RÀNQUING de la ronda, que és l'ordre entre grups. La federació
	//    publica la classificació de cada grup i cap ordre entre ells, i sense
	//    aquell ordre no es pot dir qui passa quan se n'emporten «els millors
	//    segons».
	//
	// Comparteix les taules amb els opens perquè la forma de les dades és la
	// mateixa —un torneig amb fases, grups i partides— i separar-les seria copiar
	// l'esquema per canviar-li el nom. El que no comparteix és el catàleg (a
	// /opens no hi surt), el rànquing del circuit (no hi puntua) ni aquesta vista.
	import { page } from '$app/stores';
	import {
		db,
		type Open,
		type OpenFase,
		type OpenFaseRanquing,
		type OpenPartida,
		type OpenRondaProjectada
	} from '$lib/db';

	const openId = $derived(Number($page.params.open_id));
	let open = $state<Open | null>(null);
	let fases = $state<OpenFase[]>([]);
	let ranquing = $state<OpenFaseRanquing[]>([]);
	let partides = $state<OpenPartida[]>([]);
	let faseSel = $state<number | null>(null);
	let projectada = $state<OpenRondaProjectada[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		const id = openId;
		if (!Number.isNaN(id)) load(id);
	});

	async function load(id: number) {
		loading = true;
		error = null;
		try {
			// Els .range() són explícits: PostgREST talla a mil files en silenci i
			// un campionat de vuit divisions les passa de sobres.
			const [{ data: o }, { data: fs, error: ef }, { data: rq }, { data: pt }, { data: pj }] =
				await Promise.all([
					db.from('opens').select('*').eq('open_id', id).maybeSingle(),
					db.from('open_fases').select('*').eq('open_id', id).order('ordre'),
					db
						.from('open_fase_ranquing')
						.select('*')
						.eq('open_id', id)
						.order('fase_id')
						.order('posicio')
						.range(0, 4999),
					db
						.from('open_partides')
						.select('*')
						.eq('open_id', id)
						.order('fase_id')
						.order('ordre')
						.range(0, 9999),
					db
						.from('open_ronda_projectada')
						.select('*')
						.eq('open_id', id)
						.order('posicio')
						.range(0, 4999)
				]);
			if (ef) throw ef;
			open = (o ?? null) as Open | null;
			fases = (fs ?? []) as OpenFase[];
			ranquing = (rq ?? []) as OpenFaseRanquing[];
			partides = (pt ?? []) as OpenPartida[];
			projectada = (pj ?? []) as OpenRondaProjectada[];
			// S'obre la darrera ronda que s'ha jugat, que és la que algú ve a mirar.
			const jugades = fases.filter(
				(f) =>
					ranquing.some((r) => r.fase_id === f.fase_id) ||
					partides.some((p) => p.fase_id === f.fase_id)
			);
			faseSel = jugades.at(-1)?.fase_id ?? fases[0]?.fase_id ?? null;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	const nom = $derived((open?.nom ?? '').replace(/\s*-\s*[ÚU]NICA\s*$/i, '').trim());
	const fase = $derived(fases.find((f) => f.fase_id === faseSel) ?? null);
	const rankFase = $derived(ranquing.filter((r) => r.fase_id === faseSel));
	const partFase = $derived(partides.filter((p) => p.fase_id === faseSel));

	/** Els grups de la ronda oberta, cadascun amb la seva classificació i les seves partides. */
	const grups = $derived.by(() => {
		const noms = [
			...new Set([
				...rankFase.map((r) => r.grup_nom).filter((g): g is string => Boolean(g)),
				...partFase.map((p) => p.grup_nom).filter((g): g is string => Boolean(g))
			])
		].sort((a, b) => a.localeCompare(b, 'ca', { numeric: true }));
		return noms.map((g) => ({
			nom: g,
			classificacio: rankFase
				.filter((r) => r.grup_nom === g)
				.sort((a, b) => (a.posicio_grup ?? 99) - (b.posicio_grup ?? 99)),
			partides: partFase.filter((p) => p.grup_nom === g)
		}));
	});

	/** La ronda projectada, agrupada pel grup que li hem posat. */
	const grupsProjectats = $derived.by(() => {
		const per = new Map<string, OpenRondaProjectada[]>();
		for (const r of projectada) {
			const llista = per.get(r.grup_projectat) ?? [];
			llista.push(r);
			per.set(r.grup_projectat, llista);
		}
		return [...per.entries()]
			.sort((a, b) => a[0].localeCompare(b[0], 'ca', { numeric: true }))
			.map(([nom, files]) => ({ nom, files: files.sort((x, y) => x.bombo - y.bombo) }));
	});
	const rondaProjectada = $derived(projectada[0]?.ronda ?? '');
	/** «18 places en 6 grups de 3»: el que la regla del PDF dona per a aquesta ronda. */
	const placesText = $derived(
		projectada.length
			? `${projectada.length} places en ${grupsProjectats.length} grups de ${projectada[0].mida_grup}`
			: ''
	);

	/** Les partides de la ronda que no són de cap grup: les eliminatòries. */
	const eliminatories = $derived(partFase.filter((p) => !p.grup_nom));

	/** On es trenca la llista del rànquing entre una posició de grup i la següent. */
	function trenca(i: number): boolean {
		return i > 0 && rankFase[i - 1].posicio_grup !== rankFase[i].posicio_grup;
	}
	function mitj(v: number | null): string {
		return v != null ? v.toFixed(4) : '—';
	}
	const jugada = (p: OpenPartida) =>
		(p.caramboles_local ?? 0) > 0 || (p.caramboles_visitant ?? 0) > 0;
</script>

<a href="/campionats" class="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
	<span aria-hidden="true">←</span> Campionats
</a>

{#if error}
	<div class="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-300">{error}</div>
{:else}
	<h1 class="mb-0.5 text-base font-bold leading-tight">{nom || '…'}</h1>
	{#if open?.temporada}
		<p class="mb-3 text-[11px] text-slate-500 dark:text-slate-400">Temporada {open.temporada}</p>
	{/if}

	{#if loading}
		<p class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">Carregant…</p>
	{:else if !fases.length}
		<p class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">
			Encara no s'ha publicat cap ronda d'aquest campionat.
		</p>
	{:else}
		<div class="mb-3 flex flex-wrap gap-1">
			{#each fases as f (f.fase_id)}
				<button
					onclick={() => (faseSel = f.fase_id)}
					class="rounded-full px-2.5 py-1 text-[11px] font-medium {faseSel === f.fase_id
						? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
						: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}"
				>
					{f.nom}
				</button>
			{/each}
		</div>

		{#if !grups.length && !eliminatories.length}
			<p class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">
				{fase?.nom}: encara no s'hi ha jugat res.
			</p>
		{/if}

		<!-- Els grups de la ronda: classificació i partides, un al costat de l'altre. -->
		{#each grups as g (g.nom)}
			<section class="mb-3 overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
				<h2 class="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/60 px-3 py-1.5 text-xs font-semibold">
					{g.nom}
				</h2>
				{#if g.classificacio.length}
					<ul>
						{#each g.classificacio as r (r.jugador)}
							<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5">
								<span class="w-4 shrink-0 text-center text-xs font-semibold tabular-nums text-slate-500 dark:text-slate-400">{r.posicio_grup ?? '—'}</span>
								<div class="min-w-0 flex-1">
									{#if r.player_fcb_id}
										<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm leading-tight underline decoration-slate-300 dark:decoration-slate-600">{r.jugador}</a>
									{:else}
										<span class="block truncate text-sm leading-tight">{r.jugador}</span>
									{/if}
									{#if r.club}<span class="block truncate text-[10px] text-slate-500 dark:text-slate-400">{r.club}</span>{/if}
								</div>
								<span class="w-7 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts ?? 0}</span>
								<span class="w-14 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400">{mitj(r.mitjana)}</span>
								<span class="w-8 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400">{r.serie_major ?? '—'}</span>
							</li>
						{/each}
					</ul>
				{/if}
				{#if g.partides.length}
					<div class="px-3 py-1.5">
						{#each g.partides as p (p.ordre)}
							<div class="flex items-center gap-2 py-0.5 text-[11px]">
								<span class="flex-1 truncate text-right">{p.jugador_local}</span>
								{#if jugada(p)}
									<span class="shrink-0 rounded bg-slate-100 dark:bg-slate-800 px-1.5 font-mono font-bold tabular-nums">{p.caramboles_local}–{p.caramboles_visitant}</span>
								{:else}
									<span class="shrink-0 rounded bg-slate-100 dark:bg-slate-800 px-1.5 text-[10px] text-slate-500 dark:text-slate-400">per jugar</span>
								{/if}
								<span class="flex-1 truncate">{p.jugador_visitant}</span>
								<span class="w-12 shrink-0 text-right text-slate-500 dark:text-slate-400">{p.entrades ?? '—'} ent</span>
							</div>
						{/each}
					</div>
				{/if}
			</section>
		{/each}

		{#if eliminatories.length}
			<section class="mb-3 overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
				<h2 class="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/60 px-3 py-1.5 text-xs font-semibold">
					{fase?.nom}
				</h2>
				<div class="px-3 py-1.5">
					{#each eliminatories as p (p.ordre)}
						<div class="flex items-center gap-2 py-0.5 text-[11px]">
							<span class="flex-1 truncate text-right">{p.jugador_local}</span>
							<span class="shrink-0 rounded bg-slate-100 dark:bg-slate-800 px-1.5 font-mono font-bold tabular-nums">{p.caramboles_local}–{p.caramboles_visitant}</span>
							<span class="flex-1 truncate">{p.jugador_visitant}</span>
							<span class="w-12 shrink-0 text-right text-slate-500 dark:text-slate-400">{p.entrades ?? '—'} ent</span>
						</div>
					{/each}
				</div>
			</section>
		{/if}

		<!-- La ronda que ve, projectada mentre la federació no la sortegi. -->
		{#if grupsProjectats.length}
			<section class="mb-4">
				<h2 class="mb-1 text-sm font-semibold">
					{rondaProjectada}: com podria quedar
				</h2>
				<div
					class="mb-2 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/30 px-3 py-2 text-[11px] leading-snug text-amber-900 dark:text-amber-200"
				>
					<strong>Això és una projecció</strong>, no el sorteig. Qui passa i en quin
					<strong>bombo</strong> va són exactes: surten de la regla del PDF de la
					federació («{placesText}») i de la classificació publicada. El <strong
						>grup</strong
					> no: el seu sorteig és geogràfic —la seu de cada grup hi posa jugadors de
					casa i no separa clubs— i les seus no es publiquen fins que surt. Quan la
					federació el publiqui, això desapareixerà i hi haurà els grups de debò.
				</div>
				<div class="grid gap-2 sm:grid-cols-2">
					{#each grupsProjectats as g (g.nom)}
						<div
							class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800"
						>
							<h3
								class="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/60 px-3 py-1 text-[11px] font-semibold"
							>
								{g.nom} <span class="font-normal text-slate-500 dark:text-slate-400">· projectat</span>
							</h3>
							<ul>
								{#each g.files as r (r.jugador)}
									<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 last:border-0">
										<span class="w-11 shrink-0 rounded bg-slate-100 dark:bg-slate-800 px-1 text-center text-[10px] text-slate-600 dark:text-slate-300">B{r.bombo}</span>
										<div class="min-w-0 flex-1">
											{#if r.player_fcb_id}
												<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm leading-tight underline decoration-slate-300 dark:decoration-slate-600">{r.jugador}</a>
											{:else}
												<span class="block truncate text-sm leading-tight">{r.jugador}</span>
											{/if}
											{#if r.club}<span class="block truncate text-[10px] text-slate-500 dark:text-slate-400">{r.club}</span>{/if}
										</div>
										<span class="w-7 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400">#{r.posicio}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/each}
				</div>
			</section>
		{/if}

		<!-- El rànquing de la ronda: l'ordre ENTRE grups, que la federació no publica. -->
		{#if rankFase.length}
			<section class="mb-4">
				<h2 class="mb-1 text-sm font-semibold">Rànquing de la ronda</h2>
				<p class="mb-2 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
					Els grups es juguen per separat i la federació no publica cap ordre entre
					ells. Aquí van com ella els ordena, amb quatre criteris: posició dins del
					grup, punts de la ronda, mitjana i sèrie major. És el que fa falta quan
					se n'emporten «els millors segons».
				</p>
				<div class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
					<ul>
						{#each rankFase as r, i (r.jugador)}
							{#if trenca(i)}
								<li class="border-y border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 px-3 py-1 text-[10px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
									{r.posicio_grup}a posició de grup
								</li>
							{/if}
							<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 last:border-0">
								<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums text-slate-500 dark:text-slate-400">{r.posicio}</span>
								<div class="min-w-0 flex-1">
									{#if r.player_fcb_id}
										<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm leading-tight underline decoration-slate-300 dark:decoration-slate-600">{r.jugador}</a>
									{:else}
										<span class="block truncate text-sm leading-tight">{r.jugador}</span>
									{/if}
									<!-- El club de l'INDIVIDUAL, que no és sempre el de la lliga. No
									     entra a l'ordre: la federació ordena per posició al grup,
									     punts i mitjana. -->
									{#if r.club}<span class="block truncate text-[10px] text-slate-500 dark:text-slate-400">{r.club}</span>{/if}
								</div>
								<span class="w-14 shrink-0 text-center text-[11px] text-slate-500 dark:text-slate-400">{r.grup_nom ?? '—'}</span>
								<span class="w-7 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts ?? 0}</span>
								<span class="w-14 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400">{mitj(r.mitjana)}</span>
								<span class="w-8 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400">{r.serie_major ?? '—'}</span>
							</li>
						{/each}
					</ul>
				</div>
				<p class="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
					{rankFase.length} jugadors en {grups.length} grups. Qui no ha jugat cap partida
					hi surt sense mitjana.
				</p>
			</section>
		{/if}
	{/if}
{/if}
