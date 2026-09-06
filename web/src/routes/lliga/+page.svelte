<script lang="ts">
	import { onMount } from 'svelte';
	import {
		db,
		type LligaGroup,
		type StandingRow,
		type PlayerRankRow,
		type LligaInscrit,
		type EncontreCalendari
	} from '$lib/db';
	import { titulars } from '$lib/titulars';
	import { clubDeLEquip } from '$lib/clubEquip';

	let groups = $state<LligaGroup[]>([]);
	let standings = $state<StandingRow[]>([]);
	let pranks = $state<PlayerRankRow[]>([]);
	let inscrits = $state<LligaInscrit[]>([]);
	let calendari = $state<EncontreCalendari[]>([]);
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
				{ data: enc },
				{ data: ins },
				{ data: cal }
			] = await Promise.all([
				db.from('lliga_groups').select('*'),
				db.from('lliga_standings').select('*').order('posicio'),
				db.from('lliga_player_rankings').select('*').order('posicio'),
				db.from('lliga_encontres').select('*'),
				// Els inscrits del club: qui la federació diu que juga la lliga amb
				// cada club, que és més que qui ja hi ha jugat. El .range() és
				// explícit perquè PostgREST talla a mil files en silenci.
				db.from('lliga_inscrits').select('*').order('posicio').range(0, 4999),
				// El calendari de la temporada que comença. La federació no publica
				// els encontres fins que es juguen, o sigui que fins llavors això és
				// tot el que se'n sap: qui hi ha a cada grup, contra qui i quin dia.
				db.from('lliga_calendari').select('*').order('jornada').range(0, 4999)
			]);
			if (eg) throw eg;
			if (es) throw es;
			if (ep) throw ep;
			groups = (g ?? []) as LligaGroup[];
			standings = (s ?? []) as StandingRow[];
			pranks = (pr ?? []) as PlayerRankRow[];
			encontres = enc ?? [];
			inscrits = (ins ?? []) as LligaInscrit[];
			calendari = (cal ?? []) as EncontreCalendari[];
			// `lliga_standings_hist` i no `lliga_history`: la segona és una taula
			// morta que no escriu ningú i es va quedar al 2024-2025, o sigui que el
			// selector no s'actualitzava mai. La que s'omple a cada publicació és
			// aquesta, i a més porta el nom real del grup —«Final», «Promoció»—,
			// que l'altra no distingia.
			const { data: hs, error: eh } = await db
				.from('lliga_standings_hist')
				.select('temporada');
			// L'error s'ensenya: si es menja, el selector desapareix i ningú no
			// sap que hi hauria d'haver històric.
			if (eh) throw eh;
			histSeasons = [...new Set((hs ?? []).map((r) => r.temporada as string))]
				.filter((t) => t !== currentSeason)
				.sort()
				.reverse();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	// `lliga_groups` és el diccionari dels grup_id de TOTES les temporades: hi ha
	// de quedar-hi, perquè `lliga_encontres` es guarda els encontres de totes i
	// sense el nom del grup es quedarien orfes. La que sí que és només de la
	// temporada en curs és `lliga_standings`, i per això la temporada que
	// s'ensenya surt d'aquí i no del rellotge.
	// La més alta de les que hi ha: la federació estrena id cada temporada i sempre
	// creix. `lliga_standings` en porta més d'una -l'aplicació del club penja el
	// seguiment de les passades- i aquí només s'ensenya la d'ara.
	const lligaActual = $derived(
		standings.length ? Math.max(...standings.map((s) => s.lliga_id)) : null
	);
	// Els grups que NOMÉS coneixem pel calendari.
	//
	// La federació no dona d'alta els encontres al web fins que es juguen, o
	// sigui que al setembre la classificació només porta els grups que ja ha
	// penjat -enguany, Honor Grup A i prou. El PDF del calendari, en canvi, diu
	// qui hi ha a cada grup, contra qui i quin dia, i això es pot ensenyar amb la
	// mateixa forma: tots els equips a zero i les jornades senceres.
	//
	// Se n'exclou el que ja té competició publicada: quan la federació el penja,
	// mana ella. Els identificadors són NEGATIUS perquè no en tenen cap de real i
	// així no poden xocar amb els de debò.
	interface GrupProvisional {
		divisio: string;
		grup: string;
		divisioId: number;
		grupId: number;
		equips: string[];
		encontres: EncontreCalendari[];
	}

	/** «1a DIVISIÓ» → «1A», «GRUP B» → «B»: com es diuen les dues fonts. */
	/** On va cada divisió. L'Honor és la de dalt i es diu 'Honor', o sigui que
	 *  ordenades com a text quedaria darrere de la 4a. */
	function ordreDivisio(divisio: string): number {
		const d = (divisio ?? '').trim().toUpperCase();
		if (d.startsWith('HONOR')) return 0;
		const n = parseInt(d, 10);
		return Number.isNaN(n) ? 99 : n;
	}

	function clauGrup(divisio: string, grup: string): string {
		const d = (divisio ?? '').toUpperCase().replace(/\s*DIVISI[ÓO].*$/, '').trim();
		const g = (grup ?? '').toUpperCase().replace(/^GRUP\s+/, '').trim();
		return `${d}|${g}`;
	}

	const grupsProvisionals = $derived.by(() => {
		const publicats = new Set(
			groups
				.filter((g) => g.lliga_id === lligaActual)
				.map((g) => clauGrup(g.divisio_nom ?? '', g.grup_nom ?? ''))
		);
		const per = new Map<string, EncontreCalendari[]>();
		for (const e of calendari) {
			if (publicats.has(clauGrup(e.divisio, e.grup))) continue;
			const clau = `${e.divisio}|${e.grup}`;
			const llista = per.get(clau);
			if (llista) llista.push(e);
			else per.set(clau, [e]);
		}
		return [...per.entries()]
			.sort(([a], [b]) => {
				const [da, ga] = a.split('|');
				const [db, gb] = b.split('|');
				return (
					ordreDivisio(da) - ordreDivisio(db) || da.localeCompare(db) || ga.localeCompare(gb)
				);
			})
			.map(([clau, encontres], i) => {
				const [divisio, grup] = clau.split('|');
				return {
					divisio,
					grup,
					divisioId: -(i + 1),
					grupId: -(i + 1),
					equips: [...new Set(encontres.flatMap((e) => [e.local, e.visitant]))].sort(),
					encontres
				} as GrupProvisional;
			});
	});

	const divisions = $derived.by(() => {
		const m = new Map<number, string>();
		for (const g of groups.filter((g) => g.lliga_id === lligaActual)) if (!m.has(g.divisio_id)) m.set(g.divisio_id, g.divisio_nom ?? `Div ${g.divisio_id}`);
		const publicades = [...m.entries()].map(([id, nom]) => ({ id, nom })).sort((a, b) => a.id - b.id);
		// Les del calendari, darrere: primer el que ja es juga.
		const delCalendari = new Map<number, string>();
		for (const g of grupsProvisionals) {
			if (![...delCalendari.values()].includes(g.divisio))
				delCalendari.set(g.divisioId, g.divisio);
		}
		return [...publicades, ...[...delCalendari].map(([id, nom]) => ({ id, nom }))];
	});

	$effect(() => {
		if (selDiv == null && divisions.length) selDiv = divisions[0].id;
	});

	/** El club del cens que hi ha darrere d'un nom d'equip, si se sap. */
	const clubsDelCens = $derived([...new Set(inscrits.map((i) => i.club))]);
	const fcbIdPerClub = $derived(
		new Map(inscrits.filter((i) => i.club_fcb_id).map((i) => [i.club, i.club_fcb_id!]))
	);

	const divGroups = $derived(
		selDiv != null && selDiv < 0
			? grupsProvisionals
					.filter((g) => g.divisioId === selDiv || g.divisio === divisions.find((d) => d.id === selDiv)?.nom)
					.map((g) => ({
						lliga_id: lligaActual ?? 0,
						divisio_id: selDiv,
						grup_id: g.grupId,
						divisio_nom: g.divisio,
						grup_nom: `Grup ${g.grup}`
					}))
			: groups
			.filter((g) => g.lliga_id === lligaActual && g.divisio_id === selDiv)
			.sort((a, b) => {
				const fa = (a.grup_nom ?? '').toUpperCase().startsWith('FINAL') ? 1 : 0;
				const fb = (b.grup_nom ?? '').toUpperCase().startsWith('FINAL') ? 1 : 0;
				return fa - fb || (a.grup_nom ?? '').localeCompare(b.grup_nom ?? '');
			})
	);

	function teamRows(gid: number): StandingRow[] {
		// Els grups que només tenim del calendari: tots els equips a zero, per
		// ordre alfabètic. Encara no s'ha jugat res, i posar-los una posició seria
		// inventar-se una classificació.
		if (gid < 0) {
			const g = grupsProvisionals.find((x) => x.grupId === gid);
			return (g?.equips ?? []).filter(matchQ).map((equip, i) => {
				const club = clubDeLEquip(equip, clubsDelCens);
				return {
					lliga_id: lligaActual ?? 0,
					divisio_id: selDiv ?? 0,
					grup_id: gid,
					posicio: i + 1,
					equip,
					club_fcb_id: club ? (fcbIdPerClub.get(club) ?? null) : null,
					pj: 0,
					g: 0,
					e: 0,
					p: 0,
					punts: 0,
					pf: 0,
					pc: 0
				} satisfies StandingRow;
			});
		}
		return standings
			.filter((s) => s.divisio_id === selDiv && s.grup_id === gid && matchQ(s.equip))
			.sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99));
	}
	function playerRows(gid: number): PlayerRankRow[] {
		// Al rànquing individual només hi entra qui ha jugat: d'un grup que encara
		// no ha començat no n'hi ha cap.
		if (gid < 0) return [];
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

	// Qui juga a un equip: la classificació diu com va el conjunt i això diu de qui
	// està fet.
	//
	// Surt de la llista d'INSCRITS de la federació i no del rànquing individual.
	// El rànquing només porta qui ja ha jugat, o sigui que a l'inici de temporada
	// el modal sortia buit; i la llista d'inscrits, a més, ve amb l'ordre que la
	// federació fixa per a tot l'any, que és el que decideix a quins equips del
	// club pot jugar cadascú.
	let equipObert = $state<StandingRow | null>(null);
	const jugadorsDeLEquip = $derived(
		equipObert
			? inscrits
					// Per `club_fcb_id` als dos costats. Comparar el nom del club contra
					// l'identificador semblava funcionar perquè a gairebé tots coincideixen,
					// però a un no; i les taules arrosseguen noms d'abans d'unificar els
					// clubs, o sigui que hi havia equips que obrien el modal buit.
					.filter(
						(p) =>
							p.club_fcb_id != null &&
							p.club_fcb_id === equipObert!.club_fcb_id &&
							p.lliga_id === equipObert!.lliga_id
					)
					.sort((a, b) => a.posicio - b.posicio)
			: []
	);
	/** Els quatre que és més probable que formin AQUEST equip, per la regla de la federació. */
	const titularsDeLEquip = $derived(
		equipObert ? titulars(equipObert.equip, jugadorsDeLEquip) : new Set<string>()
	);
	function obreEquip(r: StandingRow) {
		equipObert = r;
	}

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
		{
			lliga: string;
			divisio: string;
			/** «A», «B», «Final», «Promoció»… Cada fase té la seva classificació. */
			grup: string;
			posicio: number;
			equip: string;
			pm: number;
			pp: number;
		}[]
	>([]);
	$effect(() => {
		if (season !== currentSeason) loadHistory(season);
	});
	async function loadHistory(s: string) {
		const { data } = await db
			.from('lliga_standings_hist')
			.select('lliga, divisio, grup, posicio, equip, pm, pp')
			.eq('temporada', s)
			.order('lliga')
			.order('divisio')
			.order('grup')
			.order('posicio');
		history = (data ?? []) as typeof history;
	}
	// El grup forma part de la clau: una divisió té grup A, grup B, la promoció i
	// la final, i cadascuna té la seva classificació. Ajuntar-les en una de sola
	// barrejaria quatre taules diferents amb posicions repetides.
	const histGroups = $derived(
		[...new Set(history.map((r) => `${r.lliga}||${r.divisio}||${r.grup}`))].map((k) => ({
			lliga: k.split('||')[0],
			divisio: k.split('||')[1],
			grup: k.split('||')[2],
			rows: history.filter((r) => `${r.lliga}||${r.divisio}||${r.grup}` === k)
		}))
	);
	let jornadaSel = $state<Record<number, number>>({});
	let partidesCache = $state<Record<number, any[]>>({});
	let expandedEnc = $state(new Set<number>());

	function gJornades(gid: number): number[] {
		if (gid < 0) {
			const g = grupsProvisionals.find((x) => x.grupId === gid);
			return [...new Set((g?.encontres ?? []).map((e) => e.jornada))].sort((a, b) => a - b);
		}
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
		// D'un grup que encara no ha començat, la primera: l'última no s'ha jugat
		// més que les altres i ensenyar-la seria començar per l'final.
		if (gid < 0) return jornadaSel[gid] ?? js[0];
		return jornadaSel[gid] ?? js[js.length - 1];
	}
	function encOf(gid: number): any[] {
		const j = curJornada(gid);
		if (gid < 0) {
			const g = grupsProvisionals.find((x) => x.grupId === gid);
			// Identificador NEGATIU: aquests encontres no en tenen cap de real
			// -la federació no en dona fins que es juguen- i així no poden xocar
			// amb els de debò. Buscar-ne les partides no en troba cap, que és el
			// que toca.
			return (g?.encontres ?? [])
				.filter((e) => e.jornada === j)
				.map((e, i) => ({
					encontre_id: gid * 1000 - i,
					jornada: e.jornada,
					data: e.data,
					equip_local: e.local,
					equip_visitant: e.visitant,
					gols_local: null,
					gols_visitant: null
				}));
		}
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
			const { data } = await db
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
			<p class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">Sense classificacions d'aquesta temporada.</p>
		{/if}
		{#each histGroups as grp}
			<section class="mb-4 overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
				<header class="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-3 py-2 text-xs font-semibold text-slate-500 dark:text-slate-400">{grp.lliga} · {grp.divisio} · {grp.grup}</header>
				<div class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
					<span class="w-5 text-center">#</span><span class="flex-1">Equip</span><span class="w-8 text-right">PM</span><span class="w-8 text-right">PP</span>
				</div>
				<ul>
					{#each grp.rows as r (r.equip + r.grup)}
						<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
							<span class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums {r.posicio === 1 ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}">{r.posicio}</span>
							<span class="min-w-0 flex-1 truncate text-sm">{r.equip}</span>
							<span class="w-8 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.pm}</span>
							<span class="w-8 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">{r.pp}</span>
						</li>
					{/each}
				</ul>
			</section>
		{/each}
	{:else if loading}
		<p class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">Carregant…</p>
	{:else if divisions.length === 0}
		<p class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">Sense classificacions.</p>
	{:else}
		<!-- Divisions: xips -->
	<div class="-mx-3 mb-2 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
		{#each divisions as d}
			<button
				onclick={() => (selDiv = d.id)}
				class="shrink-0 rounded-sm px-3.5 py-1.5 text-sm font-medium {d.id === selDiv
					? 'bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-900'
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
			<div class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
				<span class="w-6 text-center">#</span>
				<span class="flex-1">Jugador</span>
				<span class="w-6 text-center">PJ</span>
				<span class="w-11 text-right">Mitj.</span>
				<span class="w-7 text-right">Pts</span>
			</div>
			<ul>
				{#each divPlayers as r, i (r.player_fcb_id)}
					<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
						<span class="w-6 shrink-0 text-center text-sm font-semibold tabular-nums {i === 0 ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}">{i + 1}</span>
						<div class="min-w-0 flex-1">
							<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
							{#if r.club}<div class="truncate text-[11px] text-slate-500 dark:text-slate-400">{r.club}</div>{/if}
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
				<span class="flex-1">
					{g.grup_nom ?? 'Grup'}
					{#if g.grup_id < 0}
						<span
							class="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold normal-case tracking-normal text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
							title="Del PDF del calendari: la federació encara no ha publicat aquest grup. Les dates i els emparellaments poden canviar."
							>provisional</span
						>
					{/if}
				</span>
				<span class="font-normal normal-case text-slate-500 dark:text-slate-400">{count(g.grup_id)} {mode}</span>
				<span class="text-slate-500 dark:text-slate-400 transition-transform {collapsed.has(g.grup_id) ? '' : 'rotate-90'}">›</span>
			</button>
			{#if !collapsed.has(g.grup_id)}
				{#if mode === 'equips'}
					<div class="flex items-center gap-2 border-y border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
						<span class="w-5 text-center">#</span>
						<span class="flex-1">Equip</span>
						<span class="w-7 text-center">PJ</span>
						<span class="w-9 text-right">Pts</span>
					</div>
					<ul>
						{#each teamRows(g.grup_id) as r (r.equip)}
							<li class="border-b border-slate-100 dark:border-slate-800 last:border-0">
								<button
									type="button"
									onclick={() => obreEquip(r)}
									class="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800/60"
									title="Qui hi juga"
								>
									<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}">{r.posicio}</span>
									<div class="min-w-0 flex-1">
										<div class="truncate text-sm font-medium leading-tight">{r.equip}</div>
										<div class="text-[11px] tabular-nums text-slate-500 dark:text-slate-400">{r.g}-{r.e}-{r.p}{#if r.penalitzacio}<span class="ml-1 font-medium text-red-500 dark:text-red-400" title="Sanció federativa: −{r.penalitzacio} {r.penalitzacio === 1 ? 'punt' : 'punts'}">· −{r.penalitzacio} sanció</span>{/if}</div>
									</div>
									<span class="w-7 shrink-0 text-center text-sm tabular-nums text-slate-500 dark:text-slate-400">{r.pj}</span>
									<span class="w-9 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
								</button>
							</li>
						{/each}
					</ul>
				{:else}
					<div class="flex items-center gap-2 border-y border-slate-100 dark:border-slate-800 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
						<span class="w-5 text-center">#</span>
						<span class="flex-1">Jugador</span>
						<span class="w-6 text-center">PJ</span> <span class="w-11 text-right">Mitj.</span>
						<span class="w-7 text-right">Pts</span>
					</div>
					<ul>
						{#each playerRows(g.grup_id) as r (r.player_fcb_id)}
							<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
								<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}">{r.posicio}</span>
								<div class="min-w-0 flex-1">
									<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
									{#if r.club}<div class="truncate text-[11px] text-slate-500 dark:text-slate-400">{r.club}</div>{/if}
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
										<span class="shrink-0 rounded bg-slate-100 dark:bg-slate-800 px-1.5 font-mono tabular-nums {e.gols_local == null ? 'text-[10px] font-normal text-slate-500 dark:text-slate-400' : 'font-bold'}"
											>{e.gols_local == null
												? (e.data ?? 'per jugar')
												: `${e.gols_local}–${e.gols_visitant}`}</span
										>
										<span class="flex-1 truncate text-right font-medium">{e.equip_visitant}</span>
									</button>
									{#if expandedEnc.has(e.encontre_id)}
										<div class="border-t border-slate-100 dark:border-slate-800 px-2 py-1">
											{#each partidesCache[e.encontre_id] ?? [] as p}
												<div class="flex items-center gap-2 py-0.5 text-[11px]">
													<span class="flex-1 truncate text-left">{p.jugador_local}</span>
													<span class="shrink-0 font-mono tabular-nums">{p.caramboles_local}–{p.caramboles_visitant}</span>
													<span class="flex-1 truncate text-right">{p.jugador_visitant}</span>
													<span class="w-12 shrink-0 text-right text-slate-500 dark:text-slate-400">{p.entrades} ent</span>
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

<!--
	Qui juga a un equip. La llista ve del rànquing individual del grup i va per
	club: la federació no diu de quin equip és cada partida, o sigui que un club
	amb dos equips al mateix grup els ensenya tots junts.
-->
{#if equipObert}
	<div
		class="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-0 sm:items-center sm:p-4"
		role="button"
		tabindex="-1"
		onclick={() => (equipObert = null)}
		onkeydown={(e) => e.key === 'Escape' && (equipObert = null)}
	>
		<div
			class="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white shadow-xl dark:bg-slate-900 sm:rounded-2xl"
			role="dialog"
			aria-modal="true"
			aria-label="Jugadors de {equipObert.equip}"
			tabindex="-1"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
		>
			<header
				class="sticky top-0 flex items-start justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900"
			>
				<div class="min-w-0">
					<h2 class="truncate font-semibold text-slate-900 dark:text-slate-100">
						{equipObert.equip}
					</h2>
					<p class="text-xs text-slate-500 dark:text-slate-400">
						{jugadorsDeLEquip.length}
						{jugadorsDeLEquip.length === 1 ? 'inscrit' : 'inscrits'} · per l'ordre de la federació
					</p>
				</div>
				<button
					type="button"
					onclick={() => (equipObert = null)}
					class="shrink-0 rounded-lg px-2 py-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
					aria-label="Tanca">✕</button
				>
			</header>

			{#if jugadorsDeLEquip.length === 0}
				<p class="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
					La federació encara no ha publicat qui inscriu aquest club a la lliga.
				</p>
			{:else}
				<div
					class="flex items-center gap-2 border-b border-slate-100 px-4 py-1.5 text-[10px] uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:text-slate-400"
				>
					<span class="w-5 text-center">#</span>
					<span class="flex-1">Jugador</span>
					<span class="w-12 text-right">Mitj.</span>
				</div>
				<ul>
					{#each jugadorsDeLEquip as p (p.jugador)}
						<li
							class="flex items-center gap-2 border-b border-slate-100 px-4 py-2 last:border-0 dark:border-slate-800 {titularsDeLEquip.has(
								p.jugador
							)
								? 'bg-emerald-50 font-medium dark:bg-emerald-950/20'
								: ''}"
						>
							<span class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums text-slate-400"
								>{p.posicio}</span
							>
							<span class="min-w-0 flex-1 truncate text-sm">
								{p.jugador}
								{#if p.fitxatge}
									<span
										class="ml-1 text-[10px] font-normal uppercase tracking-wide text-sky-700 dark:text-sky-400"
										title="Ve d'un altre club: la federació el llista als dos.">fitxatge</span
									>
								{/if}
							</span>
							<span class="w-12 shrink-0 text-right font-mono text-sm tabular-nums"
								>{p.mitjana != null ? p.mitjana.toFixed(3) : '—'}</span
							>
						</li>
					{/each}
				</ul>
				<p class="px-4 py-3 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
					Ombrejats, els quatre que s'esperen en aquest equip. L'ordre és el que fixa la
					federació i diu on pot jugar cadascú: del 1r al 3r només a l'A, del 4t al 8è a l'A
					i al B, del 9è al 12è fins al C, del 13è al 16è fins al D i del 17è endavant fins
					a l'E.
				</p>
			{/if}
		</div>
	</div>
{/if}
