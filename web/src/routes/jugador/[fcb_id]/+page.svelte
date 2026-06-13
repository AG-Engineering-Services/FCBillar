<script lang="ts">
	import { page } from '$app/stores';
	import { supabase, type GameRow } from '$lib/supabase';
	import { follows, toggleFollow } from '$lib/follows';
	import RadarChart from '$lib/components/RadarChart.svelte';

	const fcbId = $derived($page.params.fcb_id);

	let nom = $state('');
	let club = $state<string | null>(null);
	let clubId = $state<string | null>(null);
	let games = $state<GameRow[]>([]);
	let modalitats = $state<{ codi: number; nom: string }[]>([]);
	let selMod = $state<number | null>(null);
	let shown = $state(60);
	let serieFilter = $state(false);
	let clubHist = $state<{ temporada: string; club: string | null }[]>([]);
	let palmares = $state<
		{
			openId: number;
			nom: string;
			categoria: string | null;
			modalitat: number | null;
			tipus: 'campionat' | 'open' | 'torneig';
			temporada: string;
			posicio: number;
			club: string | null;
		}[]
	>([]);
	let copaPend = $state<
		{ encontreId: number; ordre: number; opp: string; myCar: number; oppCar: number; ent: number; grup: string }[]
	>([]);
	let openRank = $state<
		{ ronda: number; posicio: number; punts: number; detall?: { pos: number | null }[] }[]
	>([]);
	const openCur = $derived.by(() => {
		if (!openRank.length) return null;
		const maxR = Math.max(...openRank.map((o) => o.ronda));
		return openRank.find((o) => o.ronda === maxR) ?? null;
	});
	const openBest = $derived(openRank.length ? Math.min(...openRank.map((o) => o.posicio)) : null);
	const openBestResult = $derived.by(() => {
		let best: number | null = null;
		for (const o of openRank)
			for (const d of o.detall ?? [])
				if (d.pos != null && (best == null || d.pos < best)) best = d.pos;
		return best;
	});
	// Rànquing del Circuit Català Tres Bandes Femení (independent del general).
	let openRankFem = $state<
		{ ronda: number; posicio: number; punts: number; detall?: { pos: number | null }[] }[]
	>([]);
	const openFemCur = $derived.by(() => {
		if (!openRankFem.length) return null;
		const maxR = Math.max(...openRankFem.map((o) => o.ronda));
		return openRankFem.find((o) => o.ronda === maxR) ?? null;
	});
	const openFemBest = $derived(
		openRankFem.length ? Math.min(...openRankFem.map((o) => o.posicio)) : null
	);
	const openFemBestResult = $derived.by(() => {
		let best: number | null = null;
		for (const o of openRankFem)
			for (const d of o.detall ?? [])
				if (d.pos != null && (best == null || d.pos < best)) best = d.pos;
		return best;
	});
	// Agrupa temporades consecutives al mateix club en un sol tram.
	const clubGroups = $derived.by(() => {
		const sorted = [...clubHist].sort((a, b) => a.temporada.localeCompare(b.temporada));
		const groups: { club: string | null; y1: number; y2: number }[] = [];
		for (const ch of sorted) {
			const [a, b] = ch.temporada.split('-').map(Number);
			const last = groups[groups.length - 1];
			if (last && last.club === ch.club && last.y2 === a) last.y2 = b;
			else groups.push({ club: ch.club, y1: a, y2: b });
		}
		return groups
			.reverse()
			.map((g) => ({ club: g.club, label: `${g.y1}-${g.y2}` }));
	});
	const palmaresBySeason = $derived.by(() => {
		const groups = new Map<
			string,
			{
				openId: number;
				nom: string;
				categoria: string | null;
				modalitat: number | null;
				tipus: 'campionat' | 'open' | 'torneig';
				temporada: string;
				posicio: number;
				club: string | null;
			}[]
		>();
		for (const p of palmares.filter((x) => x.modalitat === selMod)) {
			const season = p.temporada || 'Temporada desconeguda';
			if (!groups.has(season)) groups.set(season, []);
			groups.get(season)!.push(p);
		}
		return [...groups.entries()]
			.sort(([a], [b]) => b.localeCompare(a))
			.map(([temporada, entries]) => ({
				temporada,
				entries: entries.sort((a, b) => a.posicio - b.posicio || a.nom.localeCompare(b.nom))
			}));
	});
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
			clubId = p?.club_fcb_id ?? null;
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

			// Copa recent que encara no compta (a copa_partides però no a games).
			const copaSig = new Set(
				games
					.filter((x) => x.competicio === 'COPA')
					.map(
						(x) =>
							[
								`${(x.player1_nom ?? '').toLowerCase()}:${x.caramboles1 ?? ''}`,
								`${(x.player2_nom ?? '').toLowerCase()}:${x.caramboles2 ?? ''}`
							]
								.sort()
								.join('|') +
							'|' +
							(x.entrades ?? '')
					)
			);
			const csel =
				'encontre_id, ordre, jugador_local, caramboles_local, jugador_visitant, caramboles_visitant, entrades';
			const [{ data: cl }, { data: cv }] = await Promise.all([
				supabase.from('copa_partides').select(csel).eq('jugador_local', nom),
				supabase.from('copa_partides').select(csel).eq('jugador_visitant', nom)
			]);
			copaPend = [...(cl ?? []), ...(cv ?? [])]
				.filter(
					(cp: any) =>
						!copaSig.has(
							[
								`${(cp.jugador_local ?? '').toLowerCase()}:${cp.caramboles_local ?? ''}`,
								`${(cp.jugador_visitant ?? '').toLowerCase()}:${cp.caramboles_visitant ?? ''}`
							]
								.sort()
								.join('|') +
								'|' +
								(cp.entrades ?? '')
						)
				)
				.map((cp: any) => {
					const meLocal = cp.jugador_local === nom;
					return {
						encontreId: cp.encontre_id ?? 0,
						ordre: cp.ordre ?? 0,
						opp: (meLocal ? cp.jugador_visitant : cp.jugador_local) ?? '—',
						myCar: (meLocal ? cp.caramboles_local : cp.caramboles_visitant) ?? 0,
						oppCar: (meLocal ? cp.caramboles_visitant : cp.caramboles_local) ?? 0,
						ent: cp.entrades ?? 0,
						grup: 'Copa'
					};
				})
				.sort((a, b) => b.encontreId - a.encontreId || b.ordre - a.ordre);

			const { data: pc } = await supabase
				.from('player_clubs')
				.select('temporada, club')
				.eq('player_fcb_id', id)
				.order('temporada', { ascending: false });
			clubHist = pc ?? [];

			const { data: podiums } = await supabase
				.from('open_classifications')
				.select('open_id, posicio, club')
				.eq('player_fcb_id', id)
				.gte('posicio', 1)
				.lte('posicio', 3);
			const openIds = [...new Set((podiums ?? []).map((x) => x.open_id))];
			const { data: podiumOpens } = openIds.length
				? await supabase.from('opens').select('open_id, nom, temporada').in('open_id', openIds)
				: { data: [] };
			const openById = new Map((podiumOpens ?? []).map((x) => [x.open_id, x]));
			palmares = (podiums ?? [])
				.map((p) => {
					const o = openById.get(p.open_id);
					const rawNom = o?.nom.trim() ?? '';
					const isOpen = rawNom.toUpperCase().includes('OPEN');
					const parts = rawNom.split(/\s+-\s+/);
					const upperNom = rawNom.toUpperCase();
					const modalitat = upperNom.includes('QUADRE 71/2')
						? 6
						: upperNom.includes('QUADRE 47/2')
							? 3
							: upperNom.includes('LLIURE')
								? 2
								: upperNom.includes('BANDA') &&
									  !upperNom.includes('TRES BANDES') &&
									  !upperNom.includes('3 BANDES')
									? 4
									: ['SNOOKER', 'QUILLES', 'ARTISTIC', 'BIATHL'].some((x) => upperNom.includes(x))
										? null
										: 1;
					const modalityOnly =
						/^(?:CAMPIONAT CATALUNYA\s+|ABSOLUT\s+)?(?:TRES BANDES|3 BANDES|LLIURE|BANDA|QUADRE 47\/2|QUADRE 71\/2)(?:\s+CATALUNYA)?$/i;
					const championshipCategory =
						parts.length > 1
							? parts.at(-1)!
							: /\bFEMEN[IÍ]\b/i.test(rawNom)
								? 'FEMENÍ'
								: /\bJUNIOR\b/i.test(rawNom)
									? 'JUNIOR'
									: /\bABSOLUT\b/i.test(rawNom)
										? 'ABSOLUT'
										: 'ÚNICA';
					const isChampionship =
						!isOpen &&
						(modalityOnly.test(rawNom) ||
							/CAMPIONAT\s+CATALUNYA|CATALUNYA|^(?:TRES BANDES|3 BANDES|LLIURE|BANDA|QUADRE 47\/2|QUADRE 71\/2)\s+-/i.test(
								rawNom
							) ||
							/\b(?:TRES BANDES|3 BANDES|LLIURE|BANDA|QUADRE 47\/2|QUADRE 71\/2)\s+(?:FEMEN[IÍ]|JUNIOR)\b/i.test(
								rawNom
							));
					const categoria = isChampionship ? championshipCategory : !isOpen && parts.length > 1 ? parts.at(-1)! : null;
					const tipus = isOpen ? 'open' : isChampionship ? 'campionat' : 'torneig';
					return o
						? {
								openId: p.open_id,
								nom:
									tipus === 'campionat'
										? 'Campionat de Catalunya'
										: isOpen
											? rawNom.replace(/\s*-\s*[ÚU]NICA\s*$/i, '').trim()
											: parts.length > 1
												? parts.slice(0, -1).join(' - ').trim()
												: rawNom,
								categoria,
								modalitat,
								tipus,
								temporada: o.temporada ?? '',
								posicio: p.posicio,
								club: p.club
							}
						: null;
				})
				.filter((p): p is NonNullable<typeof p> => p != null);

			const { data: or } = await supabase
				.from('open_ranking')
				.select('ronda, posicio, punts, detall')
				.eq('player_fcb_id', id)
				.eq('genere', 'general');
			openRank = or ?? [];

			const { data: orf } = await supabase
				.from('open_ranking')
				.select('ronda, posicio, punts, detall')
				.eq('player_fcb_id', id)
				.eq('genere', 'femeni');
			openRankFem = orf ?? [];

			const present = [...new Set(games.map((x) => x.modalitat_codi).filter((v) => v != null))];
			const { data: md } = await supabase
				.from('modalitats')
				.select('codi_fcb, nom')
				.in('codi_fcb', present.length ? present : [1]);
			const cnt = (c: number) => games.filter((x) => x.modalitat_codi === c).length;
			modalitats = (md ?? [])
				.map((m) => ({ codi: m.codi_fcb, nom: m.nom }))
				.sort((a, b) => cnt(b.codi) - cnt(a.codi));
			const requestedMod = Number($page.url.searchParams.get('mod'));
			const requestedGame = $page.url.searchParams.get('game');
			selMod = modalitats.some((m) => m.codi === requestedMod) ? requestedMod : modalitats[0]?.codi ?? null;
			if (requestedGame && selMod != null) {
				const visible = games.filter((x) => x.modalitat_codi === selMod);
				const index = visible.findIndex((x) => x.id === requestedGame);
				if (index >= 0) shown = Math.max(60, index + 1);
				setTimeout(() => document.getElementById(`game-${requestedGame}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
			}
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
	function computeKpi(gs: GameRow[]) {
		let car = 0, ent = 0, w = 0, l = 0, t = 0, sm = 0, n = 0;
		let best: number | null = null, bestN = 0;
		for (const g of gs) {
			const p = persp(g);
			n++;
			car += p.myCar;
			ent += p.ent;
			sm = Math.max(sm, p.mySerie);
			if (p.tie) t++;
			else if (p.won) w++;
			else l++;
			if (p.ent > 0) {
				const a = p.myCar / p.ent;
				if (best == null || a > best + 1e-9) {
					best = a;
					bestN = 1;
				} else if (Math.abs(a - best) < 1e-9) {
					bestN++;
				}
			}
		}
		return {
			n, mitjana: ent ? car / ent : 0, sm, w, l, t,
			pct: n ? Math.round((100 * w) / n) : 0,
			best, bestN
		};
	}
	const kpi = $derived(computeKpi(modGames));
	// Partida(es) amb la millor mitjana (contra qui, resultat, mitjana, competició).
	const bestGames = $derived.by(() => {
		if (kpi.best == null) return [] as ReturnType<typeof persp>[];
		return modGames
			.map(persp)
			.filter((p) => p.ent > 0 && Math.abs(p.myCar / p.ent - (kpi.best as number)) < 1e-9)
			.sort((a, b) => (b.date ?? '').localeCompare(a.date ?? ''));
	});
	// Temporada actual: comença l'1 d'agost.
	const seasonStart = (() => {
		const d = new Date();
		return `${d.getMonth() + 1 >= 8 ? d.getFullYear() : d.getFullYear() - 1}-08-01`;
	})();
	const seasonKpi = $derived(computeKpi(modGames.filter((g) => (g.data_partida ?? '') >= seasonStart)));
	const displayGames = $derived(
		serieFilter && kpi.sm > 0
			? modGames.filter((g) => persp(g).mySerie === kpi.sm)
			: modGames.slice(0, shown)
	);
	// Cara a cara (només històric): rival amb més victòries / derrotes / partides (si >1).
	const h2h = $derived.by(() => {
		const map = new Map<string, { nom: string; id: string | null; won: number; lost: number; total: number }>();
		for (const g of modGames) {
			const p = persp(g);
			const key = p.oppId ?? p.opp;
			if (!map.has(key)) map.set(key, { nom: p.opp, id: p.oppId, won: 0, lost: 0, total: 0 });
			const e = map.get(key)!;
			e.total++;
			if (!p.tie) {
				if (p.won) e.won++;
				else e.lost++;
			}
		}
		const arr = [...map.values()];
		// Només els del valor màxim de cada categoria (i >1); si empaten, tots ells.
		const topTier = (sel: (e: (typeof arr)[number]) => number) => {
			const f = arr.filter((e) => sel(e) >= 2);
			if (!f.length) return [];
			const mx = Math.max(...f.map(sel));
			return f.filter((e) => sel(e) === mx).sort((a, b) => (a.nom ?? '').localeCompare(b.nom ?? ''));
		};
		return {
			played: topTier((e) => e.total),
			won: topTier((e) => e.won),
			lost: topTier((e) => e.lost)
		};
	});

	// Evolució al rànquing (per la modalitat seleccionada): mitjana i posició.
	let rankHist = $state<{ num_seq: number; posicio: number | null; mitjana: number | null }[]>([]);
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
		rankHist = (data ?? []).map((r) => ({
			num_seq: r.num_seq,
			posicio: r.posicio,
			mitjana: r.mitjana_general
		}));
		selIdx = null;
	}

	// Rendiment per nivell d'oponent (aranya, quantils) per a la modalitat seleccionada.
	let ratingBuckets = $state<{ label: string; wins: number; losses: number; draws: number }[]>([]);
	let ratingIndex = $state<number | null>(null);
	let ratingCrossover = $state<number | null>(null);
	let radarMode = $state<'abs' | 'pct'>('abs');
	$effect(() => {
		const id = fcbId;
		const mod = selMod;
		if (id && mod != null) loadRatingBuckets(id, mod);
		else {
			ratingBuckets = [];
			ratingIndex = null;
			ratingCrossover = null;
		}
	});
	async function loadRatingBuckets(id: string, mod: number) {
		const { data } = await supabase
			.from('player_rating_buckets')
			.select('bucket_order, label, wins, losses, draws')
			.eq('player_fcb_id', id)
			.eq('modalitat_codi', mod)
			.order('bucket_order', { ascending: true });
		ratingBuckets = (data ?? []).map((r) => ({
			label: r.label,
			wins: r.wins ?? 0,
			losses: r.losses ?? 0,
			draws: r.draws ?? 0
		}));
		const { data: idx } = await supabase
			.from('player_rating_index')
			.select('weighted_index, crossover')
			.eq('player_fcb_id', id)
			.eq('modalitat_codi', mod)
			.maybeSingle();
		ratingIndex = idx?.weighted_index ?? null;
		ratingCrossover = idx?.crossover ?? null;
	}
	// Marques de l'eix X (divisions) amb el número de rànquing de referència.
	const xTicks = $derived.by(() => {
		const n = rankHist.length;
		if (n < 2) return [] as { x: number; label: string }[];
		const k = Math.min(4, n);
		const ticks: { x: number; label: string }[] = [];
		for (let i = 0; i < k; i++) {
			const idx = Math.round((i * (n - 1)) / (k - 1));
			ticks.push({ x: PAD + (idx / (n - 1)) * (VBW - 2 * PAD), label: dateShort(rankHist[idx].num_seq) });
		}
		return ticks;
	});
	const bestPos = $derived.by(() => {
		const ps = rankHist.map((r) => r.posicio).filter((v): v is number => v != null);
		return ps.length ? Math.min(...ps) : null;
	});
	const bestMitjana = $derived.by(() => {
		const ms = rankHist.map((r) => r.mitjana).filter((v): v is number => v != null);
		return ms.length ? Math.max(...ms) : null;
	});
	const lastMitjana = $derived(rankHist.at(-1)?.mitjana ?? null);
	const currentPos = $derived(rankHist.at(-1)?.posicio ?? null);
	const sortedModGames = $derived(
		[...modGames].sort((a, b) => {
			const da = a.data_partida ?? '',
				db = b.data_partida ?? '';
			if (da !== db) return db.localeCompare(da);
			const pa = persp(a),
				pb = persp(b);
			return (pb.ent ? pb.myCar / pb.ent : 0) - (pa.ent ? pa.myCar / pa.ent : 0);
		})
	);
	function summarizeGames(w: GameRow[]) {
		let car = 0,
			ent = 0,
			sm = 0,
			won = 0,
			lost = 0,
			tie = 0;
		for (const g of w) {
			const p = persp(g);
			car += p.myCar;
			ent += p.ent;
			sm = Math.max(sm, p.mySerie);
			if (p.tie) tie++;
			else if (p.won) won++;
			else lost++;
		}
		return { n: w.length, car, ent, sm, won, lost, tie };
	}
	// Reconstrucció de les 15 partides del rànquing publicat, sense les
	// disputades dins o després del seu mes de publicació.
	const currentRank15 = $derived.by(() => {
		const latestSeq = rankHist.at(-1)?.num_seq;
		if (latestSeq == null) return summarizeGames([]);
		const [rankYear, rankMonth] = ymFromSeq(latestSeq);
		const cutoff = `${rankYear}-${String(rankMonth).padStart(2, '0')}-01`;
		const ageCutoff = monthOffset(rankYear, rankMonth, -24);
		return summarizeGames(
			sortedModGames
				.filter((g) => (g.data_partida ?? '') >= ageCutoff && (g.data_partida ?? '') < cutoff)
				.slice(0, 15)
		);
	});
	// Previsió del proper rànquing: Copa pendent primer i després les partides de
	// games per data desc (mateix dia → millor promig dins), fins arribar a 15.
	const rank15 = $derived.by(() => {
		// La Copa publicada separadament encara no té data ni modalitat al núvol.
		// És Copa de 3 bandes i, com que encara no és a games, és posterior a les
		// partides reals que ja hi consten.
		const pending = selMod === 1 ? copaPend.slice(0, 15) : [];
		const latestSeq = rankHist.at(-1)?.num_seq;
		const [rankYear, rankMonth] = latestSeq != null ? ymFromSeq(latestSeq) : [0, 0];
		const rankCutoff =
			latestSeq != null ? `${rankYear}-${String(rankMonth).padStart(2, '0')}-01` : null;
		const [nextYear, nextMonth] = nextRankingMonth(rankYear, rankMonth);
		const eligible = sortedModGames.filter(
			(g) => latestSeq == null || (g.data_partida ?? '') >= monthOffset(nextYear, nextMonth, -24)
		);
		const w = eligible.slice(0, Math.max(0, 15 - pending.length));
		const currentIds = new Set(
			latestSeq != null
				? sortedModGames
						.filter(
							(g) =>
								(g.data_partida ?? '') >= monthOffset(rankYear, rankMonth, -24) &&
								(g.data_partida ?? '') < rankCutoff!
						)
						.slice(0, 15)
						.map((g) => g.id)
				: []
		);
		const newN = rankCutoff
			? eligible.filter((g) => (g.data_partida ?? '') >= rankCutoff).length
			: 0;
		const stats = summarizeGames(w);
		let { car, ent, sm, won, lost, tie } = stats;
		for (const cp of pending) {
			car += cp.myCar;
			ent += cp.ent;
			if (cp.myCar === cp.oppCar) tie++;
			else if (cp.myCar > cp.oppCar) won++;
			else lost++;
		}
		const calculated = ent ? car / ent : 0;
		const hasChanges =
			pending.length > 0 || w.length !== currentIds.size || w.some((g) => !currentIds.has(g.id));
		return {
			n: stats.n + pending.length,
			pendingN: pending.length,
			newN,
			hasChanges,
			mitjana: !hasChanges && lastMitjana != null ? lastMitjana : calculated,
			sm,
			won,
			lost,
			tie,
			ids: new Set(w.map((g) => g.id))
		};
	});

	const VBW = 300;
	const VBH = 84;
	const PAD = 10;
	function chartData(vals: (number | null)[], invert = false) {
		const valid = vals.filter((v): v is number => v != null);
		if (valid.length < 2) return null;
		const lo = Math.min(...valid);
		const hi = Math.max(...valid);
		let min = lo;
		let max = hi;
		if (min === max) {
			min -= 0.5;
			max += 0.5;
		}
		const n = vals.length;
		const pts: { x: number; y: number; v: number }[] = [];
		vals.forEach((v, i) => {
			if (v == null) return;
			const x = n > 1 ? PAD + (i / (n - 1)) * (VBW - 2 * PAD) : VBW / 2;
			let t = (v - min) / (max - min);
			if (invert) t = 1 - t;
			pts.push({ x, y: VBH - PAD - t * (VBH - 2 * PAD), v });
		});
		const line = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
		const base = (VBH - PAD).toFixed(1);
		const area = `${pts[0].x.toFixed(1)},${base} ${line} ${pts.at(-1)!.x.toFixed(1)},${base}`;
		return { line, area, lo, hi, last: pts.at(-1)!, n: valid.length, pts };
	}
	const mitjanaChart = $derived(chartData(rankHist.map((r) => r.mitjana)));
	const posChart = $derived(chartData(rankHist.map((r) => r.posicio), true));

	// Mitjana mòbil de 15 partides: a cada posició, la mitjana de les 15 acabant allà.
	const roll15 = $derived.by(() => {
		const asc = [...modGames].sort((a, b) => (a.data_partida ?? '').localeCompare(b.data_partida ?? ''));
		const out: {
			avg: number;
			g: number;
			opp: string;
			oppId: string | null;
			date: string | null;
			from: string | null;
			to: string | null;
		}[] = [];
		for (let i = 14; i < asc.length; i++) {
			let car = 0,
				ent = 0;
			for (let j = i - 14; j <= i; j++) {
				const p = persp(asc[j]);
				car += p.myCar;
				ent += p.ent;
			}
			const pg = persp(asc[i]);
			out.push({
				avg: ent ? car / ent : 0,
				g: pg.ent ? pg.myCar / pg.ent : 0,
				opp: pg.opp,
				oppId: pg.oppId,
				date: pg.date,
				from: asc[i - 14].data_partida,
				to: asc[i].data_partida
			});
		}
		return out;
	});
	// Finestra visible de 25 punts; l'slider mou el punt seleccionat un a un i
	// la finestra es desplaça en packs de 25 quan el punt en surt.
	const WIN = 25;
	const rollMaxStart = $derived(Math.max(0, roll15.length - WIN));
	let rollSel = $state<number | null>(null);
	$effect(() => {
		rollSel = roll15.length ? roll15.length - 1 : null; // per defecte, el més recent
	});
	const rollStart = $derived(
		rollSel == null ? 0 : Math.min(Math.floor(rollSel / WIN) * WIN, rollMaxStart)
	);
	const rollWin = $derived(roll15.slice(rollStart, rollStart + WIN));
	const rollChart = $derived.by(() => {
		if (!rollWin.length) return null;
		const all = [...rollWin.map((r) => r.avg), ...rollWin.map((r) => r.g)];
		const lo = Math.min(...all),
			hi = Math.max(...all),
			range = hi - lo || 1,
			n = rollWin.length;
		const X = (i: number) => PAD + (n === 1 ? 0.5 : i / (n - 1)) * (VBW - 2 * PAD);
		const Y = (v: number) => VBH - PAD - ((v - lo) / range) * (VBH - 2 * PAD);
		const pts = rollWin.map((r, i) => ({ x: X(i), y: Y(r.avg) }));
		const gpts = rollWin.map((r, i) => ({ x: X(i), y: Y(r.g) }));
		return {
			pts,
			gpts,
			lo,
			hi,
			line: pts.map((p) => `${p.x},${p.y}`).join(' '),
			gline: gpts.map((p) => `${p.x},${p.y}`).join(' ')
		};
	});
	function pickRoll(ev: MouseEvent) {
		const el = ev.currentTarget as Element;
		const rect = el.getBoundingClientRect();
		const n = rollWin.length;
		if (n < 1) return;
		const frac = (ev.clientX - rect.left) / rect.width;
		rollSel = rollStart + Math.max(0, Math.min(n - 1, Math.round(frac * (n - 1))));
	}

	// Selecció de punt (clic): mostra els valors del punt més proper als dos gràfics.
	let selIdx = $state<number | null>(null);
	function pickPoint(ev: MouseEvent) {
		const el = ev.currentTarget as Element;
		const rect = el.getBoundingClientRect();
		const n = rankHist.length;
		if (n < 2) return;
		const frac = (ev.clientX - rect.left) / rect.width;
		selIdx = Math.max(0, Math.min(n - 1, Math.round(frac * (n - 1))));
	}

	// Data de publicació d'un rànquing (122 = juny 2026, mensual saltant agost).
	const MESOS_NOM = [
		'Gener', 'Febrer', 'Març', 'Abril', 'Maig', 'Juny',
		'Juliol', 'Agost', 'Setembre', 'Octubre', 'Novembre', 'Desembre'
	];
	function ymFromSeq(seq: number): [number, number] {
		let y = 2026,
			m = 6;
		for (let i = 0; i < 122 - seq; i++) {
			m--;
			if (m === 0) {
				y--;
				m = 12;
			}
			if (m === 8) m = 7;
		}
		return [y, m];
	}
	function nextRankingMonth(year: number, month: number): [number, number] {
		let y = year,
			m = month + 1;
		if (m === 8) m = 9;
		if (m === 13) {
			y++;
			m = 1;
		}
		return [y, m];
	}
	function monthOffset(year: number, month: number, offset: number): string {
		const d = new Date(Date.UTC(year, month - 1 + offset, 1));
		return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-01`;
	}
	function dateFromSeq(seq: number): string {
		const [y, m] = ymFromSeq(seq);
		return `${MESOS_NOM[m - 1]} '${String(y).slice(2)}`;
	}
	function dateShort(seq: number): string {
		const [y, m] = ymFromSeq(seq);
		return `${String(m).padStart(2, '0')}/${String(y).slice(2)}`;
	}

	function fmtDate(d: string | null): string {
		if (!d) return '';
		const [y, m, day] = d.split('-');
		return `${day}/${m}/${y.slice(2)}`;
	}
	function ordinal(pos: number): string {
		return pos === 1 ? '1r' : pos === 2 ? '2n' : '3r';
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
	<div class="mb-3 flex items-start justify-between gap-3">
		<div class="min-w-0">
			<h1 class="text-lg font-bold leading-tight">{nom}</h1>
			{#if club}<a href="/club/{clubId}" class="text-sm text-slate-400 active:underline">{club}</a>{/if}
		</div>
		<button
			onclick={() => toggleFollow(fcbId)}
			class="shrink-0 rounded-full px-3 py-1.5 text-sm font-medium {$follows.includes(fcbId)
				? 'bg-amber-100 text-amber-700 ring-1 ring-amber-300'
				: 'bg-slate-900 text-white'}"
		>
			{$follows.includes(fcbId) ? '★ Seguint' : '☆ Seguir'}
		</button>
	</div>

	{#if modalitats.length > 1}
		<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
			{#each modalitats as m}
				<button
					onclick={() => {
						selMod = m.codi;
						shown = 60;
					}}
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
		<div class="lg:grid lg:grid-cols-2 lg:gap-6 lg:items-start">
			<div class="min-w-0">
			<!-- KPIs -->
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Històric</div>
				<div class="grid grid-cols-5 gap-2">
					{#each [['Partides', kpi.n, ''], ['Mitjana', kpi.mitjana.toFixed(3), ''], ['Sèrie màx', kpi.sm, 'sm'], ['% vict.', kpi.pct + '%', ''], [kpi.bestN > 1 ? `Millor mitj. ×${kpi.bestN}` : 'Millor mitj.', kpi.best != null ? kpi.best.toFixed(3) : '—', '']] as [label, val, key]}
						<button onclick={() => { if (key === 'sm') serieFilter = !serieFilter; }} class="rounded-lg py-0.5 text-center {key === 'sm' && serieFilter ? 'ring-2 ring-blue-500' : ''}">
							<div class="font-mono text-base font-bold tabular-nums">{val}</div>
							<div class="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
						</button>
					{/each}
				</div>
				<p class="mt-2 px-1 text-[11px] text-slate-400">{kpi.w} G · {kpi.l} P{kpi.t ? ` · ${kpi.t} E` : ''}</p>
			</div>
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Temporada actual</div>
				<div class="grid grid-cols-4 gap-2">
					{#each [['Partides', seasonKpi.n], ['Mitjana', seasonKpi.mitjana.toFixed(3)], ['Sèrie màx', seasonKpi.sm], ['% vict.', seasonKpi.pct + '%']] as [label, val]}
						<div class="text-center">
							<div class="font-mono text-base font-bold tabular-nums">{val}</div>
							<div class="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
						</div>
					{/each}
				</div>
				<p class="mt-2 px-1 text-[11px] text-slate-400">{seasonKpi.w} G · {seasonKpi.l} P{seasonKpi.t ? ` · ${seasonKpi.t} E` : ''}</p>
			</div>
			{#if serieFilter}
				<p class="mb-2 px-1 text-[11px] text-blue-600">Partides amb la sèrie màxima ({kpi.sm}). Torna a tocar «Sèrie màx» per desfer.</p>
			{/if}

		{#if currentPos != null}
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Rànquing actual · 15 partides</div>
				<div class="grid grid-cols-3 gap-2">
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">#{currentPos}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">{lastMitjana != null ? lastMitjana.toFixed(3) : '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">mitjana</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">{currentRank15.sm || '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">S.M.</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums text-amber-500">#{bestPos ?? '—'}</div>
						<div class="text-[10px] uppercase leading-tight tracking-wide text-slate-400">millor pos. rànquing</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums text-emerald-600">{bestMitjana != null ? bestMitjana.toFixed(3) : '—'}</div>
						<div class="text-[10px] uppercase leading-tight tracking-wide text-slate-400">millor mitjana rànquing</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums {lastMitjana != null && rank15.mitjana > lastMitjana ? 'text-emerald-600' : lastMitjana != null && rank15.mitjana < lastMitjana ? 'text-red-500' : ''}">{rank15.n ? rank15.mitjana.toFixed(3) : '—'}</div>
						<div class="text-[10px] uppercase leading-tight tracking-wide text-slate-400">mitjana proper rànquing</div>
					</div>
				</div>
				<div class="mt-2 space-y-1 rounded-lg bg-slate-50 px-2 py-1.5 text-[11px] text-slate-500">
					<p>
						<span class="font-semibold text-slate-700">Actual:</span>
						{currentRank15.won} G · {currentRank15.lost} P{currentRank15.tie ? ` · ${currentRank15.tie} E` : ''}
					</p>
					<p>
						<span class="font-semibold text-slate-700">Previsió:</span>
						{rank15.won} G · {rank15.lost} P{rank15.tie ? ` · ${rank15.tie} E` : ''}
						{rank15.pendingN
							? ` · ${rank15.pendingN} de Copa ${rank15.pendingN === 1 ? 'pendent' : 'pendents'}`
							: ''}
						{!rank15.hasChanges ? ' · sense partides noves' : ''}
					</p>
				</div>
			</div>
		{/if}

		{#if openRank.length}
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Rànquing d'Opens 3 Bandes</div>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">#{openCur?.posicio ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">posició actual</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-emerald-600">#{openBest ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">millor posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-amber-500">#{openBestResult ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">millor en un open</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">{openCur?.punts ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">punts</div>
					</div>
				</div>
			</div>
		{/if}

		{#if openRankFem.length}
			<div class="mb-4 rounded-xl bg-rose-50 p-3 ring-1 ring-rose-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-rose-400">
					Rànquing Circuit Català Femení 3 Bandes
				</div>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">#{openFemCur?.posicio ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">posició actual</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-emerald-600">#{openFemBest ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">millor posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-amber-500">#{openFemBestResult ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">millor en una prova</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">{openFemCur?.punts ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400">punts</div>
					</div>
				</div>
			</div>
		{/if}

		{#if palmaresBySeason.length}
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Palmarès individual</div>
				<div class="space-y-3">
					{#each palmaresBySeason as season}
						<div>
							<div class="mb-1 text-[11px] font-semibold text-slate-500">{season.temporada}</div>
							<ul class="space-y-1">
								{#each season.entries as p}
									<li class="flex items-center gap-2 rounded-lg px-1.5 py-1 text-sm {p.tipus === 'campionat' ? 'bg-blue-50 ring-1 ring-blue-100' : ''}">
										<span class="w-6 shrink-0 text-center font-mono font-bold {p.posicio === 1 ? 'text-amber-500' : p.posicio === 2 ? 'text-slate-400' : 'text-orange-700'}">{ordinal(p.posicio)}</span>
										<div class="min-w-0 flex-1">
											<div class="mb-0.5 flex items-center gap-1.5">
												<span class="shrink-0 rounded px-1 py-0.5 text-[8px] font-bold uppercase tracking-wide {p.tipus === 'campionat' ? 'bg-blue-600 text-white' : p.tipus === 'open' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}">{p.tipus === 'campionat' ? 'Camp. Catalunya' : p.tipus === 'open' ? 'Open' : 'Torneig'}</span>
												<a href="/opens/{p.openId}" class="min-w-0 truncate font-medium active:underline">{p.nom}</a>
											</div>
											{#if p.categoria}<div class="truncate text-[10px] uppercase tracking-wide text-slate-400">Categoria · {p.categoria}</div>{/if}
										</div>
										{#if p.club}<span class="max-w-24 shrink-0 truncate text-[10px] text-slate-400">{p.club}</span>{/if}
									</li>
								{/each}
							</ul>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		{#if h2h.played.length || h2h.won.length || h2h.lost.length}
			<div class="mb-4 space-y-2 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="text-[10px] font-bold uppercase tracking-wide text-slate-400">Cara a cara (històric)</div>
				{#each [['played', 'Més jugat amb', 'total', '', ''], ['won', 'Més guanyat a', 'won', 'text-emerald-600', ' G'], ['lost', 'Més perdut amb', 'lost', 'text-red-500', ' P']] as [k, title, field, color, suf]}
					{@const list = h2h[k]}
					{#if list.length}
						<div class="flex items-start gap-2 text-sm">
							<span class="shrink-0 text-slate-500">{title}</span>
							<div class="min-w-0 flex-1 space-y-0.5 text-right font-medium">
								{#each list as e}<a
										href="/jugador/{e.id}"
										class="block truncate active:underline">{e.nom}</a
									>{/each}
							</div>
							<span class="shrink-0 font-mono font-bold tabular-nums {color}">{(list[0] as any)[field]}{suf}</span>
						</div>
					{/if}
				{/each}
			</div>
		{/if}

		<!-- Millor partida (per mitjana) -->
		{#if kpi.best != null && bestGames.length}
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">
					Millor partida{bestGames.length > 1 ? ` · ${bestGames.length}` : ''} · mitjana {kpi.best.toFixed(3)}
				</div>
				<div class="divide-y divide-slate-100">
					{#each bestGames as g}
						<div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 py-1.5 text-sm">
							<span
								class="rounded px-1 py-0.5 text-[10px] font-semibold {g.won
									? 'bg-emerald-100 text-emerald-700'
									: g.tie
										? 'bg-slate-100 text-slate-500'
										: 'bg-red-100 text-red-600'}"
								>{g.won ? 'V' : g.tie ? 'E' : 'D'}</span
							>
							{#if g.oppId}
								<a href="/jugador/{g.oppId}" class="font-medium active:underline">{g.opp}</a>
							{:else}<span class="font-medium">{g.opp}</span>{/if}
							<span class="font-mono text-slate-500">{g.myCar}–{g.oppCar} · {g.ent} ent.</span>
							<span class="font-mono font-bold">{(g.myCar / g.ent).toFixed(3)}</span>
							{#if g.comp}<span class="text-[11px] text-slate-400">{g.comp}</span>{/if}
							<span class="ml-auto text-[11px] text-slate-400"
								>{g.date ? g.date.split('-').reverse().join('/') : ''}</span
							>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Rendiment per nivell d'oponent (aranya, per modalitat) -->
		{#if selMod != null && ratingBuckets.some((b) => b.wins + b.losses > 0)}
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-1 flex items-center justify-between">
					<div class="text-[10px] font-bold uppercase tracking-wide text-slate-400">
						Rendiment per nivell d'oponent
					</div>
					<div class="inline-flex overflow-hidden rounded-md border border-slate-300 text-[10px]">
						<button
							class="px-2 py-0.5 {radarMode === 'abs' ? 'bg-slate-800 text-white' : 'text-slate-600'}"
							onclick={() => (radarMode = 'abs')}>Absolut</button
						>
						<button
							class="px-2 py-0.5 {radarMode === 'pct' ? 'bg-slate-800 text-white' : 'text-slate-600'}"
							onclick={() => (radarMode = 'pct')}>%</button
						>
					</div>
				</div>
				<RadarChart buckets={ratingBuckets} mode={radarMode} />
				{#if ratingIndex != null || ratingCrossover != null}
					<div class="mt-2 flex justify-center gap-8">
						{#if ratingIndex != null}
							<div class="text-center">
								<div class="font-mono text-base font-bold tabular-nums">{ratingIndex}</div>
								<div class="text-[10px] uppercase tracking-wide text-slate-400">índex rendiment</div>
							</div>
						{/if}
						{#if ratingCrossover != null}
							<div class="text-center">
								<div class="font-mono text-base font-bold tabular-nums">
									{ratingCrossover.toFixed(2).replace('.', ',')}
								</div>
								<div class="text-[10px] uppercase tracking-wide text-slate-400">competitiu fins a ~</div>
							</div>
						{/if}
					</div>
				{/if}
				<p class="mt-2 text-center text-[10px] text-slate-400">
					8 franges amb el mateix nombre de partides cada una (els rangs s'estrenyen on hi ha més
					rivals), per mitjana de rànquing del rival al moment de la partida. L'índex pondera les
					victòries pel nivell del rival.
				</p>
			</div>
		{/if}

		<!-- Evolució al rànquing -->
		{#if mitjanaChart}
			{#if selIdx != null && rankHist[selIdx]}
				<div class="mb-2 flex items-center justify-center gap-3 rounded-lg bg-slate-900 px-3 py-1.5 text-xs text-white">
					<span class="font-semibold">{dateFromSeq(rankHist[selIdx].num_seq)}</span>
					<span>mitjana <span class="font-mono font-bold">{rankHist[selIdx].mitjana?.toFixed(3) ?? '—'}</span></span>
					<span>posició <span class="font-mono font-bold">#{rankHist[selIdx].posicio ?? '—'}</span></span>
				</div>
			{:else}
				<p class="mb-2 text-center text-[11px] text-slate-400">Toca un gràfic per veure els valors d'un rànquing</p>
			{/if}
			<div class="mb-4 space-y-3">
				<!-- Mitjana -->
				<div class="rounded-xl bg-white p-3 ring-1 ring-slate-200">
					<div class="mb-2 flex items-end justify-between">
						<span class="text-xs font-semibold uppercase tracking-wide text-slate-400"
							>Mitjana al rànquing</span>
						<div class="flex gap-4 text-right">
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums">
									{lastMitjana != null ? lastMitjana.toFixed(3) : '—'}
								</div>
								<div class="text-[10px] text-slate-400">actual</div>
							</div>
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums text-emerald-600">
									{mitjanaChart.hi.toFixed(3)}
								</div>
								<div class="text-[10px] text-slate-400">millor</div>
							</div>
						</div>
					</div>
					<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickPoint} role="presentation" class="h-24 w-full cursor-pointer">
							{#each [0, 0.25, 0.5, 0.75, 1] as f}
								<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke="#eef2f7" stroke-width="1" vector-effect="non-scaling-stroke" />
							{/each}
						{#each xTicks as t}
							<line x1={t.x} y1="2" x2={t.x} y2={VBH - 2} stroke="#e2e8f0" stroke-width="1" vector-effect="non-scaling-stroke" />
						{/each}
						<polyline points={mitjanaChart.area} fill="#0f172a" opacity="0.06" />
						<polyline
							points={mitjanaChart.line}
							fill="none"
							stroke="#0f172a"
							stroke-width="1.5"
							stroke-linejoin="round"
							vector-effect="non-scaling-stroke" />
						<circle cx={mitjanaChart.last.x} cy={mitjanaChart.last.y} r="3" fill="#0f172a" />
							{#if selIdx != null && mitjanaChart.pts[selIdx]}
								<line x1={mitjanaChart.pts[selIdx].x} y1="2" x2={mitjanaChart.pts[selIdx].x} y2={VBH - 2} stroke="#0f172a" stroke-width="1" vector-effect="non-scaling-stroke" />
								<circle cx={mitjanaChart.pts[selIdx].x} cy={mitjanaChart.pts[selIdx].y} r="4" fill="#0f172a" stroke="#fff" stroke-width="1.5" />
							{/if}
					</svg>
					<div class="flex justify-between px-0.5 text-[9px] tabular-nums text-slate-300">
						{#each xTicks as t}<span>{t.label}</span>{/each}
					</div>
				</div>
				<!-- Posició -->
				<div class="rounded-xl bg-white p-3 ring-1 ring-slate-200">
					<div class="mb-2 flex items-end justify-between">
						<span class="text-xs font-semibold uppercase tracking-wide text-slate-400"
							>Posició al rànquing</span>
						<div class="flex gap-4 text-right">
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums">
									#{currentPos ?? '—'}
								</div>
								<div class="text-[10px] text-slate-400">actual</div>
							</div>
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums text-amber-500">
									#{bestPos ?? '—'}
								</div>
								<div class="text-[10px] text-slate-400">millor</div>
							</div>
						</div>
					</div>
					{#if posChart}
						<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickPoint} role="presentation" class="h-24 w-full cursor-pointer">
							{#each [0, 0.25, 0.5, 0.75, 1] as f}
								<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke="#eef2f7" stroke-width="1" vector-effect="non-scaling-stroke" />
							{/each}
							{#each xTicks as t}
								<line x1={t.x} y1="2" x2={t.x} y2={VBH - 2} stroke="#fde68a" stroke-width="1" vector-effect="non-scaling-stroke" />
							{/each}
							<polyline points={posChart.area} fill="#f59e0b" opacity="0.08" />
							<polyline
								points={posChart.line}
								fill="none"
								stroke="#f59e0b"
								stroke-width="1.5"
								stroke-linejoin="round"
								vector-effect="non-scaling-stroke" />
							<circle cx={posChart.last.x} cy={posChart.last.y} r="3" fill="#f59e0b" />
								{#if selIdx != null && posChart.pts[selIdx]}
									<line x1={posChart.pts[selIdx].x} y1="2" x2={posChart.pts[selIdx].x} y2={VBH - 2} stroke="#b45309" stroke-width="1" vector-effect="non-scaling-stroke" />
									<circle cx={posChart.pts[selIdx].x} cy={posChart.pts[selIdx].y} r="4" fill="#f59e0b" stroke="#fff" stroke-width="1.5" />
								{/if}
						</svg>
						<div class="flex justify-between px-0.5 text-[9px] tabular-nums text-slate-300">
							{#each xTicks as t}<span>{t.label}</span>{/each}
						</div>
						<p class="mt-1 text-right text-[10px] text-slate-300">{posChart.n} rànquings · amunt = millor</p>
					{/if}
				</div>
			</div>
		{/if}

		{#if rollChart && roll15.length}
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-1 flex items-end justify-between">
					<span class="text-[10px] font-bold uppercase tracking-wide text-slate-400">Mitjana mòbil · 15 partides</span>
					{#if rollSel != null && roll15[rollSel]}
						<div class="text-right">
							<div class="font-mono text-base font-bold leading-none tabular-nums text-blue-600">{roll15[rollSel].avg.toFixed(3)}</div>
							<div class="text-[9px] text-slate-400">{fmtDate(roll15[rollSel].from)} – {fmtDate(roll15[rollSel].to)}</div>
						</div>
					{/if}
				</div>
				{#if rollSel != null && roll15[rollSel]}
					<div class="mb-1 flex items-center justify-between gap-2 rounded-lg bg-slate-900 px-2 py-1 text-[11px] text-white">
						<span class="min-w-0 truncate">
							{#if roll15[rollSel].oppId}<a href="/jugador/{roll15[rollSel].oppId}" class="font-medium active:underline">{roll15[rollSel].opp}</a>{:else}<span class="font-medium">{roll15[rollSel].opp}</span>{/if}
							<span class="text-slate-300">· {fmtDate(roll15[rollSel].date)}</span>
						</span>
						<span class="shrink-0">partida <span class="font-mono font-bold">{roll15[rollSel].g.toFixed(3)}</span></span>
					</div>
				{/if}
				<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickRoll} role="presentation" class="h-24 w-full cursor-pointer">
					{#each [0, 0.25, 0.5, 0.75, 1] as f}
						<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke="#eef2f7" stroke-width="1" vector-effect="non-scaling-stroke" />
					{/each}
					<polyline points={rollChart.gline} fill="none" stroke="#94a3b8" stroke-width="1" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
					{#each rollChart.gpts as gp}
						<circle cx={gp.x} cy={gp.y} r="1.6" fill="#94a3b8" />
					{/each}
					<polyline points={rollChart.line} fill="none" stroke="#2563eb" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
					{#if rollSel != null && rollSel - rollStart >= 0 && rollSel - rollStart < rollWin.length}
						{@const li = rollSel - rollStart}
						<line x1={rollChart.pts[li].x} y1="2" x2={rollChart.pts[li].x} y2={VBH - 2} stroke="#2563eb" stroke-width="1" vector-effect="non-scaling-stroke" />
						<circle cx={rollChart.pts[li].x} cy={rollChart.pts[li].y} r="4" fill="#2563eb" stroke="#fff" stroke-width="1.5" />
						<circle cx={rollChart.gpts[li].x} cy={rollChart.gpts[li].y} r="3.5" fill="#475569" stroke="#fff" stroke-width="1.5" />
					{/if}
				</svg>
				<div class="flex justify-between px-0.5 text-[9px] tabular-nums text-slate-400">
					<span>mín {rollChart.lo.toFixed(3)}</span>
					<span>màx {rollChart.hi.toFixed(3)}</span>
				</div>
				{#if roll15.length > 1}
					<input type="range" min="0" max={roll15.length - 1} step="1" bind:value={rollSel} class="thin-range mt-2 w-full" />
					<p class="text-center text-[10px] text-slate-400">punt {(rollSel ?? 0) + 1} de {roll15.length} · finestra {rollStart + 1}–{Math.min(rollStart + WIN, roll15.length)}</p>
				{/if}
			</div>
		{/if}

		{#if clubGroups.length}
			<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400">Clubs</div>
				<div class="flex flex-wrap gap-1.5">
					{#each clubGroups as g}
						<div class="rounded-lg bg-slate-50 px-2 py-1 text-[11px] ring-1 ring-slate-200">
							<span class="font-semibold text-slate-700">{g.label}</span>
							<span class="text-slate-500">· {g.club ?? '—'}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

			</div>
			<div class="min-w-0">
			<!-- Partides recents -->
			{#if selMod === 1 && copaPend.length}
				<div class="mb-3 rounded-xl border border-blue-200 bg-blue-50 p-3">
					<div class="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-blue-700">
						Recents · incloses a la previsió del proper rànquing
					</div>
					<ul class="space-y-1">
						{#each copaPend as cp}
							<li class="flex items-center gap-3 text-sm">
								<span class="w-5 shrink-0 text-center text-xs font-bold {cp.myCar > cp.oppCar ? 'text-emerald-600' : cp.myCar < cp.oppCar ? 'text-red-500' : 'text-slate-400'}">{cp.myCar > cp.oppCar ? 'G' : cp.myCar < cp.oppCar ? 'P' : 'E'}</span>
								<span class="min-w-0 flex-1 truncate">{cp.opp}</span>
								<span class="shrink-0 text-[10px] uppercase text-blue-600">{cp.grup}</span>
								<div class="shrink-0 text-right">
									<div class="font-mono text-sm tabular-nums">{cp.myCar}–{cp.oppCar}</div>
									<div class="font-mono text-[11px] tabular-nums text-slate-400">{cp.ent ? `${(cp.myCar / cp.ent).toFixed(3)} · ${cp.ent} ent.` : '—'}</div>
								</div>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			{#if rank15.ids.size}
				<p class="mb-2 flex items-center gap-1.5 px-1 text-[11px] text-slate-400">
					<span class="inline-block h-3 w-3 rounded bg-amber-50 ring-1 ring-amber-200"></span>
					les {rank15.ids.size} de games que entren a la previsió del proper rànquing
				</p>
			{/if}
		<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			{#each displayGames as g (g.id)}
				{@const p = persp(g)}
				<li
					id="game-{g.id}"
					class="flex items-center gap-3 border-b border-slate-100 px-3 py-2 last:border-0 {rank15.ids.has(g.id)
						? 'bg-amber-50'
						: $page.url.searchParams.get('game') === g.id
							? 'bg-blue-50 ring-1 ring-inset ring-blue-300'
							: ''}"
				>
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
						<div class="text-[11px] text-slate-400">
							{fmtDate(p.date)} · {p.comp ?? ''}{p.mySerie ? ` · S.M. ${p.mySerie}` : ''}
						</div>
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
		{#if !serieFilter && modGames.length > shown}
			<button
				onclick={() => (shown += 60)}
				class="mt-2 w-full rounded-lg bg-white py-2 text-sm font-medium text-slate-600 ring-1 ring-slate-200 active:bg-slate-50"
			>
				Carregar més ({shown} de {modGames.length})
			</button>
		{:else if modGames.length > 60}
			<p class="px-1 py-3 text-center text-[11px] text-slate-400">{modGames.length} partides</p>
		{/if}
			</div>
		</div>
	{/if}
{/if}

<style>
	.thin-range {
		-webkit-appearance: none;
		appearance: none;
		height: 2px;
		border-radius: 9999px;
		background: #e2e8f0;
		cursor: pointer;
	}
	.thin-range::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 11px;
		height: 11px;
		border-radius: 9999px;
		background: #2563eb;
		cursor: pointer;
	}
	.thin-range::-moz-range-thumb {
		width: 11px;
		height: 11px;
		border: none;
		border-radius: 9999px;
		background: #2563eb;
		cursor: pointer;
	}
</style>
