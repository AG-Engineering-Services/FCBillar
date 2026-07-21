<script lang="ts">
	import { page } from '$app/stores';
	import {
		supabase,
		type GameRow,
		type PendingGameRow,
		type ProvisionalRow
	} from '$lib/supabase';
	import { follows, toggleFollow } from '$lib/follows';
	import RadarChart from '$lib/components/RadarChart.svelte';
	import { theme } from '$lib/theme';

	// Reutilitzable: la pàgina normal passa kiosk=false; la vista aïllada /fitxa passa
	// kiosk=true (sense botons de navegació ni enllaços que surtin de la vista).
	let { fcbId, kiosk = false }: { fcbId: string; kiosk?: boolean } = $props();

	// --- Botó de reingesta manual (NOMÉS a la fitxa de l'Albert Gómez) --------
	// Dispara la reingesta de la federació, que ARA corre al núvol (GitHub Actions).
	// El botó només encua una petició a Supabase (taula reingest_requests); el
	// workflow reingest-dispatch.yml la consulta cada pocs minuts i dispara la
	// reingesta al núvol. Gate: cal el correu autoritzat (validat també per RLS al
	// servidor).
	const ADMIN_FCB_ID = '278';
	const ADMIN_EMAIL = 'algoam@gmail.com';
	const isAdmin = $derived(fcbId === ADMIN_FCB_ID);
	let reingestState = $state<'idle' | 'sending' | 'ok' | 'denied' | 'error'>('idle');
	let reingestMsg = $state('');

	async function requestReingest() {
		const email = prompt('Correu autoritzat per llançar la reingesta de la federació:');
		if (email === null) return; // cancel·lat
		if (email.trim().toLowerCase() !== ADMIN_EMAIL) {
			reingestState = 'denied';
			reingestMsg = 'Correu no autoritzat.';
			return;
		}
		// Marca aquest dispositiu com a admin perquè el layout mostri l'avís de
		// sessió caducada (cloud_status.session_ok=false) només a qui pot actuar-hi.
		try {
			localStorage.setItem('fcb_admin', '1');
		} catch {
			/* localStorage no disponible: no és crític */
		}
		reingestState = 'sending';
		reingestMsg = '';
		const { error: e } = await supabase
			.from('reingest_requests')
			.insert({ requested_email: ADMIN_EMAIL, source: `fitxa/${fcbId}` });
		if (e) {
			reingestState = 'error';
			reingestMsg = `No s'ha pogut encuar: ${e.message}`;
		} else {
			reingestState = 'ok';
			reingestMsg = "Petició enviada. La reingesta s'executarà al núvol en pocs minuts.";
		}
	}

	// Colors dels gràfics SVG reactius al tema (clar/fosc).
	const cGrid = $derived($theme === 'dark' ? '#1e293b' : '#eef2f7'); // graella horitzontal
	const cAxis = $derived($theme === 'dark' ? '#334155' : '#e2e8f0'); // guies verticals
	const cAxisAmber = $derived($theme === 'dark' ? '#78350f' : '#fde68a');
	const cInk = $derived($theme === 'dark' ? '#e2e8f0' : '#0f172a'); // línia/àrea principal
	const cHalo = $derived($theme === 'dark' ? '#0f172a' : '#fff'); // halo dels punts
	const cHisto = $derived($theme === 'dark' ? '#4f46e5' : '#c7d2fe'); // barres histograma
	const cHistoSel = $derived($theme === 'dark' ? '#a5b4fc' : '#4f46e5'); // barra seleccionada

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
	// Partides pendents (totes les competicions en curs) llegides de pending_games;
	// la dedup contra `games` ja la fa el publisher server-side.
	let pendingRows = $state<PendingGameRow[]>([]);
	// Projecció AUTORITATIVA del proper rànquing (taula ranking_provisional), per
	// modalitat. La fitxa ja no recalcula res: en llegeix mitjana, posició i G/P/E.
	let provByMod = $state<Map<number, ProvisionalRow>>(new Map());
	const provRow = $derived(selMod != null ? (provByMod.get(selMod) ?? null) : null);
	const copaPend = $derived(
		pendingRows
			.filter((r) => r.modalitat_codi === selMod)
			.map((r) => ({
				opp: r.opponent_nom ?? '—',
				myCar: r.caramboles ?? 0,
				oppCar: r.caramboles_opp ?? 0,
				ent: r.entrades ?? 0,
				grup: r.competicio ?? 'Pendent'
			}))
	);
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
	let shownBeforePrint = 60;

	// A l'imprimir es mostren totes les partides de la modalitat; després es
	// restaurem el nombre de files que hi havia abans.
	$effect(() => {
		if (typeof window === 'undefined') return;
		const expand = () => {
			shownBeforePrint = shown;
			shown = modGames.length;
		};
		const collapse = () => {
			shown = shownBeforePrint;
		};
		window.addEventListener('beforeprint', expand);
		window.addEventListener('afterprint', collapse);
		return () => {
			window.removeEventListener('beforeprint', expand);
			window.removeEventListener('afterprint', collapse);
		};
	});

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

			// Partides pendents de TOTES les competicions en curs (copa, opens…) que
			// encara no compten al rànquing. La dedup contra `games` ja la fa el
			// publisher server-side; aquí només llegim.
			const { data: pg } = await supabase
				.from('pending_games')
				.select(
					'modalitat_codi, competicio, font, opponent_nom, caramboles, caramboles_opp, entrades, serie'
				)
				.eq('player_fcb_id', id);
			pendingRows = (pg ?? []) as PendingGameRow[];

			// Projecció del proper rànquing (autoritativa, computada al backend).
			const { data: pr } = await supabase
				.from('ranking_provisional')
				.select(
					'player_fcb_id, modalitat_codi, posicio_oficial, mitjana_oficial, posicio_provisional, mitjana_provisional, partides_post, proj_won, proj_lost, proj_tie, window_game_ids, current_game_ids'
				)
				.eq('player_fcb_id', id);
			provByMod = new Map((pr ?? []).map((r: any) => [r.modalitat_codi, r as ProvisionalRow]));

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
	// Temporada anterior: finestra [prevSeasonStart, seasonStart).
	const prevSeasonStart = (() => {
		const d = new Date();
		const y = d.getMonth() + 1 >= 8 ? d.getFullYear() : d.getFullYear() - 1;
		return `${y - 1}-08-01`;
	})();
	const prevSeasonKpi = $derived(
		computeKpi(
			modGames.filter(
				(g) => (g.data_partida ?? '') >= prevSeasonStart && (g.data_partida ?? '') < seasonStart
			)
		)
	);
	// Efectivitat per competició (Lliga / Open / Individual / Copa) sobre la modalitat.
	// Punts: victòria = 2 (copa 3), empat = 1, derrota = 0.
	const compBuckets = $derived.by(() => {
		const kind = (c: string | null): string | null => {
			const s = (c ?? '').toLowerCase();
			if (s.includes('lliga') || s.includes('liga')) return 'Lliga';
			if (s.includes('open')) return 'Open';
			if (s.includes('individual') || s.includes('catalunya')) return 'Individual';
			if (s.includes('copa')) return 'Copa';
			return null;
		};
		const map = new Map<string, { w: number; e: number; l: number; n: number }>();
		for (const g of modGames) {
			const p = persp(g);
			const k = kind(p.comp);
			if (!k) continue;
			if (!map.has(k)) map.set(k, { w: 0, e: 0, l: 0, n: 0 });
			const b = map.get(k)!;
			b.n++;
			if (p.tie) b.e++;
			else if (p.won) b.w++;
			else b.l++;
		}
		return [...map.entries()]
			.map(([tipus, b]) => {
				const winVal = tipus === 'Copa' ? 3 : 2;
				return { tipus, ...b, pct: b.n ? Math.round((100 * (b.w * winVal + b.e)) / (b.n * winVal)) : 0 };
			})
			.sort((a, b) => b.pct - a.pct);
	});
	const displayGames = $derived(
		serieFilter && kpi.sm > 0
			? modGames.filter((g) => persp(g).mySerie === kpi.sm)
			: modGames.slice(0, shown)
	);
	// Cara a cara (només històric): rival amb més victòries / derrotes / partides (si >1).
	const h2h = $derived.by(() => {
		const map = new Map<string, { nom: string; id: string | null; won: number; draws: number; lost: number; total: number }>();
		for (const g of modGames) {
			const p = persp(g);
			const key = p.oppId ?? p.opp;
			if (!map.has(key)) map.set(key, { nom: p.opp, id: p.oppId, won: 0, draws: 0, lost: 0, total: 0 });
			const e = map.get(key)!;
			e.total++;
			if (p.tie) e.draws++;
			else if (p.won) e.won++;
			else e.lost++;
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

	// Posició del jugador dins del rànquing (per modalitat) dels membres del seu club
	// (tot el planter federat: players.club_fcb_id), al darrer rànquing publicat.
	let clubRank = $state<{ posicio: number; total: number } | null>(null);
	$effect(() => {
		const cid = clubId;
		const mod = selMod;
		const seq = rankHist.at(-1)?.num_seq ?? null;
		if (cid && mod != null && seq != null) loadClubRank(cid, mod, seq);
		else clubRank = null;
	});
	async function loadClubRank(cid: string, mod: number, seq: number) {
		const { data: members } = await supabase
			.from('players')
			.select('fcb_id')
			.eq('club_fcb_id', cid);
		const ids = (members ?? []).map((m) => m.fcb_id);
		if (!ids.length) {
			clubRank = null;
			return;
		}
		const { data: ent } = await supabase
			.from('ranking_entries')
			.select('player_fcb_id, mitjana_general')
			.eq('modalitat_codi', mod)
			.eq('num_seq', seq)
			.in('player_fcb_id', ids);
		const ranked = (ent ?? [])
			.filter((e) => e.mitjana_general != null)
			.sort((a, b) => (b.mitjana_general ?? 0) - (a.mitjana_general ?? 0));
		const pos = ranked.findIndex((e) => e.player_fcb_id === fcbId) + 1;
		clubRank = pos > 0 ? { posicio: pos, total: ranked.length } : null;
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
	// Posició a l'inici de la temporada en curs (primer rànquing de la temporada,
	// agost-juliol), per veure la progressió inici→actual.
	const seasonStartRank = $derived.by(() => {
		if (!rankHist.length) return null;
		const [ly, lm] = ymFromSeq(rankHist[rankHist.length - 1].num_seq);
		const sy = lm >= 8 ? ly : ly - 1;
		const inSeason = rankHist.filter((r) => {
			const [y, m] = ymFromSeq(r.num_seq);
			return (y === sy && m >= 8) || (y === sy + 1 && m <= 7);
		});
		return inSeason.length ? inSeason[0] : null;
	});
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
	// Les 15 partides del rànquing OFICIAL vigent. Font autoritativa:
	// ranking_provisional.current_game_ids (de ranking_game_links). Fallback a la
	// reconstrucció heurística per dates si no hi ha dades (altres modalitats, o
	// cap moviment publicat).
	const currentRank15 = $derived.by(() => {
		const ids = provRow?.current_game_ids ?? null;
		if (ids && ids.length) {
			const set = new Set(ids);
			return summarizeGames(modGames.filter((g) => set.has(g.id)));
		}
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
	// Previsió del proper rànquing: AUTORITATIVA (taula ranking_provisional,
	// computada al backend amb la mateixa font de pendents). La fitxa no recalcula.
	const rank15 = $derived.by(() => {
		const r = provRow;
		const changes = !!r && (r.partides_post ?? 0) > 0;
		const won = r?.proj_won ?? 0;
		const lost = r?.proj_lost ?? 0;
		const tie = r?.proj_tie ?? 0;
		return {
			pendingN: r?.partides_post ?? 0,
			hasChanges: changes,
			// Sense canvis: la mitjana del proper rànquing és l'oficial vigent.
			mitjana: changes ? (r?.mitjana_provisional ?? null) : lastMitjana,
			posicio: changes ? (r?.posicio_provisional ?? null) : null,
			won,
			lost,
			tie,
			ids: new Set<string>((r?.window_game_ids as string[] | null) ?? [])
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

	// Histograma: distribució de la mitjana per partida (caramboles/entrades) de la
	// modalitat seleccionada. Els intervals (bins) tenen una mida "rodona" derivada
	// del rang, de manera que funciona igual a 3 bandes (~0,2) que a lliure (~2,5).
	function niceStep(raw: number) {
		const pow = Math.pow(10, Math.floor(Math.log10(raw)));
		const n = raw / pow;
		return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * pow;
	}
	function fmtAvg(v: number, step: number) {
		const d = step >= 5 ? 0 : step >= 1 ? 1 : step >= 0.1 ? 2 : 3;
		return v.toFixed(d);
	}
	const histo = $derived.by(() => {
		const avgs = modGames
			.map(persp)
			.filter((p) => p.ent > 0)
			.map((p) => p.myCar / p.ent);
		if (avgs.length < 5) return null;
		const lo = Math.min(...avgs);
		const hi = Math.max(...avgs);
		const step = niceStep((hi - lo) / 12 || 0.1);
		const start = Math.floor(lo / step) * step;
		const nBins = Math.max(1, Math.round((hi - start) / step + 1e-9) + 1);
		const bins = Array.from({ length: nBins }, (_, i) => ({
			x0: start + i * step,
			x1: start + (i + 1) * step,
			count: 0
		}));
		for (const a of avgs) {
			let i = Math.floor((a - start) / step + 1e-9);
			if (i < 0) i = 0;
			if (i >= nBins) i = nBins - 1;
			bins[i].count++;
		}
		const maxCount = Math.max(...bins.map((b) => b.count));
		// Desviació típica de les mitjanes per partida respecte la mitjana oficial,
		// per quantificar i dibuixar la dispersió típica del rendiment (franja ±1σ).
		const center = kpi.mitjana;
		const sd = Math.sqrt(avgs.reduce((s, a) => s + (a - center) ** 2, 0) / avgs.length);
		return { bins, maxCount, step, n: avgs.length, lo, hi, mitjana: center, sd };
	});
	// Posició x de la línia de referència de la mitjana global dins l'histograma.
	const histoMeanX = $derived.by(() => {
		if (!histo) return null;
		const span = histo.bins.length * histo.step;
		const f = span ? (histo.mitjana - histo.bins[0].x0) / span : 0;
		return PAD + Math.max(0, Math.min(1, f)) * (VBW - 2 * PAD);
	});
	// Franja ±1σ al voltant de la mitjana, en coordenades x de l'SVG.
	const histoSdBand = $derived.by(() => {
		if (!histo || !histo.sd) return null;
		const span = histo.bins.length * histo.step;
		if (!span) return null;
		const toX = (v: number) =>
			PAD + Math.max(0, Math.min(1, (v - histo.bins[0].x0) / span)) * (VBW - 2 * PAD);
		return { x1: toX(histo.mitjana - histo.sd), x2: toX(histo.mitjana + histo.sd) };
	});
	// Etiquetes de l'eix X: ~4 vores de bin repartides + la vora final.
	const histoTicks = $derived.by(() => {
		if (!histo) return [] as string[];
		const b = histo.bins;
		const k = Math.min(4, b.length);
		const out: string[] = [];
		for (let i = 0; i < k; i++) {
			const idx = Math.round((i * (b.length - 1)) / Math.max(1, k - 1));
			out.push(fmtAvg(b[idx].x0, histo.step));
		}
		out.push(fmtAvg(b[b.length - 1].x1, histo.step));
		return out;
	});
	let histoSel = $state<number | null>(null);
	$effect(() => {
		void selMod;
		histoSel = null; // reinicia la selecció en canviar de modalitat
	});
	function pickHisto(ev: MouseEvent) {
		const el = ev.currentTarget as Element;
		const rect = el.getBoundingClientRect();
		const n = histo?.bins.length ?? 0;
		if (!n) return;
		const frac = (ev.clientX - rect.left) / rect.width;
		histoSel = Math.max(0, Math.min(n - 1, Math.floor(frac * n)));
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

{#if !kiosk}
	<button onclick={back} class="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400 print:hidden">
		<span aria-hidden="true">←</span> Rànquings
	</button>
{/if}

{#if error}
	<div class="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-300">{error}</div>
{:else}
	<div class="mb-3 flex items-start justify-between gap-3">
		<div class="min-w-0">
			<h1 class="text-lg font-bold leading-tight">{nom}</h1>
			{#if club}
				{#if kiosk}<span class="text-sm text-slate-400 dark:text-slate-500">{club}</span>
				{:else}<a href="/club/{clubId}" class="text-sm text-slate-400 dark:text-slate-500 active:underline">{club}</a>{/if}
			{/if}
		</div>
		<div class="flex shrink-0 items-center gap-2 print:hidden">
			{#if isAdmin}
				<button
					onclick={requestReingest}
					disabled={reingestState === 'sending'}
					title="Reingesta del web de la federació (detecta partides noves)"
					class="rounded-full bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-emerald-500"
				>
					{reingestState === 'sending' ? 'Enviant…' : '↻ Reingesta'}
				</button>
			{/if}
			{#if !kiosk}
				<button
					onclick={() => toggleFollow(fcbId)}
					class="rounded-full px-3 py-1.5 text-sm font-medium {$follows.includes(fcbId)
						? 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 ring-1 ring-amber-300 dark:ring-amber-900/50'
						: 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'}"
				>
					{$follows.includes(fcbId) ? '★ Seguint' : '☆ Seguir'}
				</button>
			{/if}
		</div>
	</div>

	{#if isAdmin && reingestState !== 'idle'}
		<div
			class="mb-3 rounded-lg px-3 py-2 text-sm print:hidden {reingestState === 'ok'
				? 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900/50'
				: reingestState === 'sending'
					? 'bg-slate-50 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-800'
					: 'bg-red-50 text-red-800 ring-1 ring-red-200 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-900/50'}"
		>
			{reingestMsg}
		</div>
	{/if}

	{#if modalitats.length > 1}
		<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none] print:hidden">
			{#each modalitats as m}
				<button
					onclick={() => {
						selMod = m.codi;
						shown = 60;
					}}
					class="shrink-0 rounded-full px-3 py-1 text-sm font-medium {m.codi === selMod
						? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
						: 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-800'}"
				>{m.nom}</button>
			{/each}
		</div>
		<p class="mb-3 hidden text-sm font-medium print:block">
			Modalitat: {modalitats.find((m) => m.codi === selMod)?.nom ?? '—'}
		</p>
	{/if}

	{#if loading}
		<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
	{:else}
		<div class="profile-root lg:grid lg:grid-cols-2 lg:gap-6 lg:items-start print:block">
			<div class="min-w-0">
			<!-- KPIs -->
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Històric</div>
				<div class="grid grid-cols-5 gap-2">
					{#each [['Partides', kpi.n, ''], ['Mitjana', kpi.mitjana.toFixed(3), ''], ['Sèrie màx', kpi.sm, 'sm'], ['% vict.', kpi.pct + '%', ''], [kpi.bestN > 1 ? `Millor mitj. ×${kpi.bestN}` : 'Millor mitj.', kpi.best != null ? kpi.best.toFixed(3) : '—', '']] as [label, val, key]}
						<button onclick={() => { if (key === 'sm') serieFilter = !serieFilter; }} class="rounded-lg py-0.5 text-center {key === 'sm' && serieFilter ? 'ring-2 ring-blue-500' : ''}">
							<div class="font-mono text-base font-bold tabular-nums">{val}</div>
							<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</div>
						</button>
					{/each}
				</div>
				<p class="mt-2 px-1 text-[11px] text-slate-400 dark:text-slate-500">{kpi.w} G · {kpi.l} P{kpi.t ? ` · ${kpi.t} E` : ''}</p>
			</div>
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Temporada actual</div>
				<div class="grid grid-cols-4 gap-2">
					{#each [['Partides', seasonKpi.n], ['Mitjana', seasonKpi.mitjana.toFixed(3)], ['Sèrie màx', seasonKpi.sm], ['% vict.', seasonKpi.pct + '%']] as [label, val]}
						<div class="text-center">
							<div class="font-mono text-base font-bold tabular-nums">{val}</div>
							<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</div>
						</div>
					{/each}
				</div>
				<p class="mt-2 px-1 text-[11px] text-slate-400 dark:text-slate-500">{seasonKpi.w} G · {seasonKpi.l} P{seasonKpi.t ? ` · ${seasonKpi.t} E` : ''}</p>
			</div>
			{#if prevSeasonKpi.n}
				<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
					<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Temporada anterior</div>
					<div class="grid grid-cols-4 gap-2">
						{#each [['Partides', prevSeasonKpi.n], ['Mitjana', prevSeasonKpi.mitjana.toFixed(3)], ['Sèrie màx', prevSeasonKpi.sm], ['% vict.', prevSeasonKpi.pct + '%']] as [label, val]}
							<div class="text-center">
								<div class="font-mono text-base font-bold tabular-nums">{val}</div>
								<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</div>
							</div>
						{/each}
					</div>
					<p class="mt-2 px-1 text-[11px] text-slate-400 dark:text-slate-500">{prevSeasonKpi.w} G · {prevSeasonKpi.l} P{prevSeasonKpi.t ? ` · ${prevSeasonKpi.t} E` : ''}</p>
				</div>
			{/if}
			{#if serieFilter}
				<p class="mb-2 px-1 text-[11px] text-blue-600 dark:text-blue-400">Partides amb la sèrie màxima ({kpi.sm}). Torna a tocar «Sèrie màx» per desfer.</p>
			{/if}

		{#if currentPos != null}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Rànquing actual · 15 partides</div>
				<div class="grid grid-cols-3 gap-2">
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">#{currentPos}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">{lastMitjana != null ? lastMitjana.toFixed(3) : '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">mitjana</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">{currentRank15.sm || '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">S.M.</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums text-amber-500 dark:text-amber-400">#{bestPos ?? '—'}</div>
						<div class="text-[10px] uppercase leading-tight tracking-wide text-slate-400 dark:text-slate-500">millor pos. rànquing</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums text-emerald-600 dark:text-emerald-400">{bestMitjana != null ? bestMitjana.toFixed(3) : '—'}</div>
						<div class="text-[10px] uppercase leading-tight tracking-wide text-slate-400 dark:text-slate-500">millor mitjana rànquing</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums {rank15.hasChanges && lastMitjana != null && rank15.mitjana != null && rank15.mitjana > lastMitjana ? 'text-emerald-600 dark:text-emerald-400' : rank15.hasChanges && lastMitjana != null && rank15.mitjana != null && rank15.mitjana < lastMitjana ? 'text-red-500 dark:text-red-400' : ''}">{rank15.mitjana != null ? rank15.mitjana.toFixed(3) : '—'}</div>
						<div class="text-[10px] uppercase leading-tight tracking-wide text-slate-400 dark:text-slate-500">mitjana proper rànq.</div>
						{#if rank15.hasChanges && rank15.posicio != null}
							{@const dp = (currentPos ?? 0) - rank15.posicio}
							<div class="mt-0.5 text-[11px] font-bold tabular-nums {dp > 0 ? 'text-emerald-600 dark:text-emerald-400' : dp < 0 ? 'text-red-500 dark:text-red-400' : 'text-slate-400 dark:text-slate-500'}">#{rank15.posicio}{dp > 0 ? ` ▲${dp}` : dp < 0 ? ` ▼${-dp}` : ''}</div>
						{/if}
					</div>
				</div>
				{#if seasonStartRank?.posicio != null || clubRank}
					<div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-0.5 px-1 text-[11px] text-slate-500 dark:text-slate-400">
						{#if seasonStartRank?.posicio != null}
							{@const dsp = seasonStartRank.posicio - (currentPos ?? seasonStartRank.posicio)}
							<span>Inici temporada <span class="font-mono font-bold text-slate-700 dark:text-slate-200">#{seasonStartRank.posicio}</span>{#if dsp !== 0}<span class="font-bold {dsp > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500 dark:text-red-400'}"> {dsp > 0 ? `▲${dsp}` : `▼${-dsp}`}</span>{/if}</span>
						{/if}
						{#if clubRank}
							<span>Al club <span class="font-mono font-bold text-slate-700 dark:text-slate-200">#{clubRank.posicio}</span> de {clubRank.total}</span>
						{/if}
					</div>
				{/if}
				<div class="mt-2 space-y-1 rounded-lg bg-slate-50 dark:bg-slate-800/50 px-2 py-1.5 text-[11px] text-slate-500 dark:text-slate-400">
					<p>
						<span class="font-semibold text-slate-700 dark:text-slate-200">Actual:</span>
						{currentRank15.won} G · {currentRank15.lost} P{currentRank15.tie ? ` · ${currentRank15.tie} E` : ''}
					</p>
					<p>
						<span class="font-semibold text-slate-700 dark:text-slate-200">Previsió:</span>
						{#if rank15.hasChanges}
							{rank15.won} G · {rank15.lost} P{rank15.tie ? ` · ${rank15.tie} E` : ''}
							{rank15.pendingN
								? ` · ${rank15.pendingN} ${rank15.pendingN === 1 ? 'pendent' : 'pendents'}`
								: ''}
						{:else}
							sense partides noves
						{/if}
					</p>
				</div>
			</div>
		{/if}

		{#if compBuckets.length}
			<div class="mb-4 space-y-1.5 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Efectivitat per competició</div>
				{#each compBuckets as c}
					<div class="flex items-center gap-2 text-sm">
						<span class="shrink-0 text-slate-600 dark:text-slate-300">{c.tipus}</span>
						<span class="min-w-0 flex-1 text-right font-mono text-[11px] tabular-nums">
							<span class="text-emerald-600 dark:text-emerald-400">{c.w}</span><span class="text-slate-300 dark:text-slate-600">-</span><span class="text-amber-600 dark:text-amber-400">{c.e}</span><span class="text-slate-300 dark:text-slate-600">-</span><span class="text-red-500 dark:text-red-400">{c.l}</span>
						</span>
						<span class="w-11 shrink-0 text-right font-mono font-bold tabular-nums">{c.pct}%</span>
					</div>
				{/each}
			</div>
		{/if}

		{#if openRank.length}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Rànquing d'Opens 3 Bandes</div>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">#{openCur?.posicio ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">posició actual</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-emerald-600 dark:text-emerald-400">#{openBest ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">millor posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-amber-500 dark:text-amber-400">#{openBestResult ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">millor en un open</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">{openCur?.punts ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">punts</div>
					</div>
				</div>
			</div>
		{/if}

		{#if openRankFem.length}
			<div class="mb-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 p-3 ring-1 ring-rose-200 dark:ring-rose-900/50">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-rose-400 dark:text-rose-400">
					Rànquing Circuit Català Tres Bandes Femení
				</div>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">#{openFemCur?.posicio ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">posició actual</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-emerald-600 dark:text-emerald-400">#{openFemBest ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">millor posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-amber-500 dark:text-amber-400">#{openFemBestResult ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">millor en una prova</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">{openFemCur?.punts ?? '—'}</div>
						<div class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">punts</div>
					</div>
				</div>
			</div>
		{/if}

		{#if palmaresBySeason.length}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Palmarès individual</div>
				<div class="space-y-3">
					{#each palmaresBySeason as season}
						<div>
							<div class="mb-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">{season.temporada}</div>
							<ul class="space-y-1">
								{#each season.entries as p}
									<li class="flex items-center gap-2 rounded-lg px-1.5 py-1 text-sm {p.tipus === 'campionat' ? 'bg-blue-50 dark:bg-blue-950/40 ring-1 ring-blue-100 dark:ring-blue-900/50' : ''}">
										<span class="w-6 shrink-0 text-center font-mono font-bold {p.posicio === 1 ? 'text-amber-500 dark:text-amber-400' : p.posicio === 2 ? 'text-slate-400 dark:text-slate-500' : 'text-orange-700 dark:text-orange-300'}">{ordinal(p.posicio)}</span>
										<div class="min-w-0 flex-1">
											<div class="mb-0.5 flex items-center gap-1.5">
												<span class="shrink-0 rounded px-1 py-0.5 text-[8px] font-bold uppercase tracking-wide {p.tipus === 'campionat' ? 'bg-blue-600 text-white' : p.tipus === 'open' ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'}">{p.tipus === 'campionat' ? 'Camp. Catalunya' : p.tipus === 'open' ? 'Open' : 'Torneig'}</span>
												{#if kiosk}<span class="min-w-0 truncate font-medium">{p.nom}</span>
												{:else}<a href="/opens/{p.openId}" class="min-w-0 truncate font-medium active:underline">{p.nom}</a>{/if}
											</div>
											{#if p.categoria}<div class="truncate text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500">Categoria · {p.categoria}</div>{/if}
										</div>
										{#if p.club}<span class="max-w-24 shrink-0 truncate text-[10px] text-slate-400 dark:text-slate-500">{p.club}</span>{/if}
									</li>
								{/each}
							</ul>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		{#if h2h.played.length || h2h.won.length || h2h.lost.length}
			<div class="mb-4 space-y-2 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Rivals destacats (històric)</div>
				{#each [['played', 'Rivals habituals'], ['won', 'Més victòries'], ['lost', 'Més derrotes']] as [k, title]}
					{@const list = h2h[k as 'played' | 'won' | 'lost']}
					{#if list.length}
						<div class="flex items-start gap-2 text-sm">
							<span class="shrink-0 text-slate-500 dark:text-slate-400">{title}</span>
							<div class="min-w-0 flex-1 space-y-0.5 text-right font-medium">
								{#each list as e}
									<div class="truncate">
										{#if kiosk}<span>{e.nom}</span>{:else}<a href="/jugador/{e.id}" class="active:underline">{e.nom}</a>{/if}
										<span class="font-mono text-[11px] tabular-nums text-slate-400 dark:text-slate-500">{#if k === 'played'}({e.total} / <span class="text-emerald-600 dark:text-emerald-400">{e.won}</span>-<span class="text-amber-600 dark:text-amber-400">{e.draws}</span>-<span class="text-red-500 dark:text-red-400">{e.lost}</span>){:else if k === 'won'}(<span class="text-emerald-600 dark:text-emerald-400">{e.won}V</span>){:else}(<span class="text-red-500 dark:text-red-400">{e.lost}D</span>){/if}</span>
									</div>
								{/each}
							</div>
						</div>
					{/if}
				{/each}
			</div>
		{/if}

		<!-- Millor partida (per mitjana) -->
		{#if kpi.best != null && bestGames.length}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">
					Millor partida{bestGames.length > 1 ? ` · ${bestGames.length}` : ''} · mitjana {kpi.best.toFixed(3)}
				</div>
				<div class="divide-y divide-slate-100 dark:divide-slate-800">
					{#each bestGames as g}
						<div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 py-1.5 text-sm">
							<span
								class="rounded px-1 py-0.5 text-[10px] font-semibold {g.won
									? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300'
									: g.tie
										? 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
										: 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400'}"
								>{g.won ? 'V' : g.tie ? 'E' : 'D'}</span
							>
							{#if g.oppId && !kiosk}
								<a href="/jugador/{g.oppId}" class="font-medium active:underline">{g.opp}</a>
							{:else}<span class="font-medium">{g.opp}</span>{/if}
							<span class="font-mono text-slate-500 dark:text-slate-400">{g.myCar}–{g.oppCar} · {g.ent} ent.</span>
							<span class="font-mono font-bold">{(g.myCar / g.ent).toFixed(3)}</span>
							{#if g.comp}<span class="text-[11px] text-slate-400 dark:text-slate-500">{g.comp}</span>{/if}
							<span class="ml-auto text-[11px] text-slate-400 dark:text-slate-500"
								>{g.date ? g.date.split('-').reverse().join('/') : ''}</span
							>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Rendiment per nivell d'oponent (aranya, per modalitat) -->
		{#if selMod != null && ratingBuckets.some((b) => b.wins + b.losses > 0)}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-1 flex items-center justify-between">
					<div class="text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">
						Rendiment per nivell d'oponent
					</div>
					<div class="inline-flex overflow-hidden rounded-md border border-slate-300 dark:border-slate-700 text-[10px] print:hidden">
						<button
							class="px-2 py-0.5 {radarMode === 'abs' ? 'bg-slate-800 text-white' : 'text-slate-600 dark:text-slate-300'}"
							onclick={() => (radarMode = 'abs')}>Absolut</button
						>
						<button
							class="px-2 py-0.5 {radarMode === 'pct' ? 'bg-slate-800 text-white' : 'text-slate-600 dark:text-slate-300'}"
							onclick={() => (radarMode = 'pct')}>%</button
						>
					</div>
				</div>
				<RadarChart buckets={ratingBuckets} mode={radarMode} />
				{#if ratingIndex != null || ratingCrossover != null}
					<div class="mt-3 grid grid-cols-1 gap-2">
						{#if ratingIndex != null}
							<div class="rounded-lg bg-slate-50 dark:bg-slate-800/50 p-2">
								<div class="flex items-baseline gap-2">
									<span class="font-mono text-lg font-bold tabular-nums">{ratingIndex}</span>
									<span class="text-[11px] font-semibold text-slate-600 dark:text-slate-300">Índex de rendiment</span>
								</div>
								<p class="text-[11px] leading-snug text-slate-500 dark:text-slate-400">
									Com el % de victòries, però cada partida pesa segons el nivell del rival:
									guanyar als forts compta més. De 0 a 100 (~50 = equilibrat).
								</p>
							</div>
						{/if}
						{#if ratingCrossover != null}
							<div class="rounded-lg bg-slate-50 dark:bg-slate-800/50 p-2">
								<div class="flex items-baseline gap-2">
									<span class="font-mono text-lg font-bold tabular-nums"
										>{ratingCrossover.toFixed(2).replace('.', ',')}</span
									>
									<span class="text-[11px] font-semibold text-slate-600 dark:text-slate-300">Nivell de competitivitat</span>
								</div>
								<p class="text-[11px] leading-snug text-slate-500 dark:text-slate-400">
									Mitjana de rival on comences a perdre més partides de les que guanyes (la taxa
									de victòries creua el 50%). Ets competitiu fins aquest nivell.
								</p>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		{/if}

		<!-- Evolució al rànquing -->
		{#if mitjanaChart}
			{#if selIdx != null && rankHist[selIdx]}
				<div class="mb-2 flex items-center justify-center gap-3 rounded-lg bg-slate-900 dark:bg-slate-700 px-3 py-1.5 text-xs text-white">
					<span class="font-semibold">{dateFromSeq(rankHist[selIdx].num_seq)}</span>
					<span>mitjana <span class="font-mono font-bold">{rankHist[selIdx].mitjana?.toFixed(3) ?? '—'}</span></span>
					<span>posició <span class="font-mono font-bold">#{rankHist[selIdx].posicio ?? '—'}</span></span>
				</div>
			{:else}
				<p class="mb-2 text-center text-[11px] text-slate-400 dark:text-slate-500 print:hidden">Toca un gràfic per veure els valors d'un rànquing</p>
			{/if}
			<div class="mb-4 space-y-3">
				<!-- Mitjana -->
				<div class="rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
					<div class="mb-2 flex items-end justify-between">
						<span class="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500"
							>Mitjana al rànquing</span>
						<div class="flex gap-4 text-right">
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums">
									{lastMitjana != null ? lastMitjana.toFixed(3) : '—'}
								</div>
								<div class="text-[10px] text-slate-400 dark:text-slate-500">actual</div>
							</div>
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums text-emerald-600 dark:text-emerald-400">
									{mitjanaChart.hi.toFixed(3)}
								</div>
								<div class="text-[10px] text-slate-400 dark:text-slate-500">millor</div>
							</div>
						</div>
					</div>
					<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickPoint} role="presentation" class="h-24 w-full cursor-pointer print:h-16">
							{#each [0, 0.25, 0.5, 0.75, 1] as f}
								<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke={cGrid} stroke-width="1" vector-effect="non-scaling-stroke" />
							{/each}
						{#each xTicks as t}
							<line x1={t.x} y1="2" x2={t.x} y2={VBH - 2} stroke={cAxis} stroke-width="1" vector-effect="non-scaling-stroke" />
						{/each}
						<polyline points={mitjanaChart.area} fill={cInk} opacity="0.06" />
						<polyline
							points={mitjanaChart.line}
							fill="none"
							stroke={cInk}
							stroke-width="1.5"
							stroke-linejoin="round"
							vector-effect="non-scaling-stroke" />
						<circle cx={mitjanaChart.last.x} cy={mitjanaChart.last.y} r="3" fill={cInk} />
							{#if selIdx != null && mitjanaChart.pts[selIdx]}
								<line x1={mitjanaChart.pts[selIdx].x} y1="2" x2={mitjanaChart.pts[selIdx].x} y2={VBH - 2} stroke={cInk} stroke-width="1" vector-effect="non-scaling-stroke" />
								<circle cx={mitjanaChart.pts[selIdx].x} cy={mitjanaChart.pts[selIdx].y} r="4" fill={cInk} stroke={cHalo} stroke-width="1.5" />
							{/if}
					</svg>
					<div class="flex justify-between px-0.5 text-[9px] tabular-nums text-slate-300 dark:text-slate-600">
						{#each xTicks as t}<span>{t.label}</span>{/each}
					</div>
				</div>
				<!-- Posició -->
				<div class="rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
					<div class="mb-2 flex items-end justify-between">
						<span class="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500"
							>Posició al rànquing</span>
						<div class="flex gap-4 text-right">
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums">
									#{currentPos ?? '—'}
								</div>
								<div class="text-[10px] text-slate-400 dark:text-slate-500">actual</div>
							</div>
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums text-amber-500 dark:text-amber-400">
									#{bestPos ?? '—'}
								</div>
								<div class="text-[10px] text-slate-400 dark:text-slate-500">millor</div>
							</div>
						</div>
					</div>
					{#if posChart}
						<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickPoint} role="presentation" class="h-24 w-full cursor-pointer print:h-16">
							{#each [0, 0.25, 0.5, 0.75, 1] as f}
								<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke={cGrid} stroke-width="1" vector-effect="non-scaling-stroke" />
							{/each}
							{#each xTicks as t}
								<line x1={t.x} y1="2" x2={t.x} y2={VBH - 2} stroke={cAxisAmber} stroke-width="1" vector-effect="non-scaling-stroke" />
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
									<circle cx={posChart.pts[selIdx].x} cy={posChart.pts[selIdx].y} r="4" fill="#f59e0b" stroke={cHalo} stroke-width="1.5" />
								{/if}
						</svg>
						<div class="flex justify-between px-0.5 text-[9px] tabular-nums text-slate-300 dark:text-slate-600">
							{#each xTicks as t}<span>{t.label}</span>{/each}
						</div>
						<p class="mt-1 text-right text-[10px] text-slate-300 dark:text-slate-600">{posChart.n} rànquings · amunt = millor</p>
					{/if}
				</div>
			</div>
		{/if}

		{#if rollChart && roll15.length}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-1 flex items-end justify-between">
					<span class="text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Mitjana mòbil · 15 partides</span>
					{#if rollSel != null && roll15[rollSel]}
						<div class="text-right">
							<div class="font-mono text-base font-bold leading-none tabular-nums text-blue-600 dark:text-blue-400">{roll15[rollSel].avg.toFixed(3)}</div>
							<div class="text-[9px] text-slate-400 dark:text-slate-500">{fmtDate(roll15[rollSel].from)} – {fmtDate(roll15[rollSel].to)}</div>
						</div>
					{/if}
				</div>
				{#if rollSel != null && roll15[rollSel]}
					<div class="mb-1 flex items-center justify-between gap-2 rounded-lg bg-slate-900 dark:bg-slate-700 px-2 py-1 text-[11px] text-white">
						<span class="min-w-0 truncate">
							{#if roll15[rollSel].oppId && !kiosk}<a href="/jugador/{roll15[rollSel].oppId}" class="font-medium active:underline">{roll15[rollSel].opp}</a>{:else}<span class="font-medium">{roll15[rollSel].opp}</span>{/if}
							<span class="text-slate-300 dark:text-slate-600">· {fmtDate(roll15[rollSel].date)}</span>
						</span>
						<span class="shrink-0">partida <span class="font-mono font-bold">{roll15[rollSel].g.toFixed(3)}</span></span>
					</div>
				{/if}
				<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickRoll} role="presentation" class="h-24 w-full cursor-pointer print:h-16">
					{#each [0, 0.25, 0.5, 0.75, 1] as f}
						<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke={cGrid} stroke-width="1" vector-effect="non-scaling-stroke" />
					{/each}
					<polyline points={rollChart.gline} fill="none" stroke="#94a3b8" stroke-width="1" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
					{#each rollChart.gpts as gp}
						<circle cx={gp.x} cy={gp.y} r="1.6" fill="#94a3b8" />
					{/each}
					<polyline points={rollChart.line} fill="none" stroke="#2563eb" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
					{#if rollSel != null && rollSel - rollStart >= 0 && rollSel - rollStart < rollWin.length}
						{@const li = rollSel - rollStart}
						<line x1={rollChart.pts[li].x} y1="2" x2={rollChart.pts[li].x} y2={VBH - 2} stroke="#2563eb" stroke-width="1" vector-effect="non-scaling-stroke" />
						<circle cx={rollChart.pts[li].x} cy={rollChart.pts[li].y} r="4" fill="#2563eb" stroke={cHalo} stroke-width="1.5" />
						<circle cx={rollChart.gpts[li].x} cy={rollChart.gpts[li].y} r="3.5" fill="#475569" stroke={cHalo} stroke-width="1.5" />
					{/if}
				</svg>
				<div class="flex justify-between px-0.5 text-[9px] tabular-nums text-slate-400 dark:text-slate-500">
					<span>mín {rollChart.lo.toFixed(3)}</span>
					<span>màx {rollChart.hi.toFixed(3)}</span>
				</div>
				{#if roll15.length > 1}
					<input type="range" min="0" max={roll15.length - 1} step="1" bind:value={rollSel} class="thin-range mt-2 w-full print:hidden" />
					<p class="text-center text-[10px] text-slate-400 dark:text-slate-500 print:hidden">punt {(rollSel ?? 0) + 1} de {roll15.length} · finestra {rollStart + 1}–{Math.min(rollStart + WIN, roll15.length)}</p>
				{/if}
			</div>
		{/if}

		{#if histo}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-1 flex items-end justify-between">
					<span class="text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Distribució de la mitjana · per partida</span>
					<div class="flex items-center gap-3">
						<div class="flex items-center gap-1.5">
							<span class="inline-block h-2 w-2 rounded-full bg-emerald-500"></span>
							<span class="font-mono text-base font-bold leading-none tabular-nums">{histo.mitjana.toFixed(3)}</span>
						</div>
						<div class="flex items-baseline gap-1">
							<span class="text-[10px] font-semibold text-slate-400 dark:text-slate-500">σ</span>
							<span class="font-mono text-sm font-bold leading-none tabular-nums">{histo.sd.toFixed(3)}</span>
						</div>
					</div>
				</div>
				{#if histoSel != null && histo.bins[histoSel]}
					{@const b = histo.bins[histoSel]}
					<div class="mb-1 flex items-center justify-between gap-2 rounded-lg bg-slate-900 dark:bg-slate-700 px-2 py-1 text-[11px] text-white">
						<span>mitjana <span class="font-mono font-bold">{fmtAvg(b.x0, histo.step)}–{fmtAvg(b.x1, histo.step)}</span></span>
						<span class="font-mono font-bold">{b.count} {b.count === 1 ? 'partida' : 'partides'} · {Math.round((100 * b.count) / histo.n)}%</span>
					</div>
				{:else}
					<p class="mb-1 text-center text-[11px] text-slate-400 dark:text-slate-500 print:hidden">Toca una barra per veure el detall</p>
				{/if}
				<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" onclick={pickHisto} role="presentation" class="h-24 w-full cursor-pointer print:h-16">
					{#each [0, 0.25, 0.5, 0.75, 1] as f}
						<line x1="0" y1={PAD + f * (VBH - 2 * PAD)} x2={VBW} y2={PAD + f * (VBH - 2 * PAD)} stroke={cGrid} stroke-width="1" vector-effect="non-scaling-stroke" />
					{/each}
					{#if histoSdBand}
						<rect x={histoSdBand.x1} y={PAD} width={Math.max(0, histoSdBand.x2 - histoSdBand.x1)} height={VBH - 2 * PAD} fill="#10b981" opacity="0.1" />
					{/if}
					{#each histo.bins as b, i}
						{@const bw = (VBW - 2 * PAD) / histo.bins.length}
						{@const h = histo.maxCount ? (b.count / histo.maxCount) * (VBH - 2 * PAD) : 0}
						<rect x={PAD + i * bw + bw * 0.1} y={VBH - PAD - h} width={bw * 0.8} height={h} fill={histoSel === i ? cHistoSel : cHisto} />
					{/each}
					{#if histoMeanX != null}
						<line x1={histoMeanX} y1="2" x2={histoMeanX} y2={VBH - 2} stroke="#10b981" stroke-width="1.5" stroke-dasharray="3 2" vector-effect="non-scaling-stroke" />
					{/if}
				</svg>
				<div class="flex justify-between px-0.5 text-[9px] tabular-nums text-slate-300 dark:text-slate-600">
					{#each histoTicks as t}<span>{t}</span>{/each}
				</div>
				<p class="mt-1 text-right text-[10px] text-slate-300 dark:text-slate-600">{histo.n} partides · línia = mitjana · franja = ±1σ</p>
			</div>
		{/if}

		{#if clubGroups.length}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Clubs</div>
				<div class="flex flex-wrap gap-1.5">
					{#each clubGroups as g}
						<div class="rounded-lg bg-slate-50 dark:bg-slate-800/50 px-2 py-1 text-[11px] ring-1 ring-slate-200 dark:ring-slate-800">
							<span class="font-semibold text-slate-700 dark:text-slate-200">{g.label}</span>
							<span class="text-slate-500 dark:text-slate-400">· {g.club ?? '—'}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

			</div>
			<div class="min-w-0">
			<!-- Partides recents -->
			{#if copaPend.length}
				<div class="mb-3 rounded-xl border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/40 p-3">
					<div class="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-blue-700 dark:text-blue-300">
						{copaPend.length} {copaPend.length === 1 ? 'partida pendent' : 'partides pendents'} · incloses a la previsió del proper rànquing
					</div>
					<ul class="space-y-1.5">
						{#each copaPend as cp}
							<li class="flex items-center gap-3 text-sm">
								<span class="w-5 shrink-0 text-center text-xs font-bold {cp.myCar > cp.oppCar ? 'text-emerald-600 dark:text-emerald-400' : cp.myCar < cp.oppCar ? 'text-red-500 dark:text-red-400' : 'text-slate-400 dark:text-slate-500'}">{cp.myCar > cp.oppCar ? 'G' : cp.myCar < cp.oppCar ? 'P' : 'E'}</span>
								<div class="min-w-0 flex-1">
									<div class="truncate leading-tight">{cp.opp}</div>
									<div class="truncate text-[10px] uppercase tracking-wide text-blue-600 dark:text-blue-400">{cp.grup}</div>
								</div>
								<div class="shrink-0 text-right">
									<div class="font-mono text-sm tabular-nums">{cp.myCar}–{cp.oppCar}</div>
									<div class="font-mono text-[11px] tabular-nums text-slate-400 dark:text-slate-500">{cp.ent ? `${(cp.myCar / cp.ent).toFixed(3)} · ${cp.ent} ent.` : '—'}</div>
								</div>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			{#if rank15.ids.size}
				<p class="mb-2 flex items-center gap-1.5 px-1 text-[11px] text-slate-400 dark:text-slate-500">
					<span class="inline-block h-3 w-3 rounded bg-amber-50 dark:bg-amber-950/40 ring-1 ring-amber-200 dark:ring-amber-900/50"></span>
					{#if rank15.hasChanges}
						les {rank15.ids.size} de games que entren a la previsió del proper rànquing
					{:else}
						les {rank15.ids.size} de games que computen al rànquing actual
					{/if}
				</p>
			{/if}
		<div class="games-wrap overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
			<table class="w-full text-sm">
				<thead class="print-only bg-slate-50 text-left text-[10px] uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
					<tr>
						<th class="px-3 py-1.5 font-medium">Res.</th>
						<th class="px-3 py-1.5 font-medium">Rival · Competició</th>
						<th class="px-3 py-1.5 text-right font-medium">Marcador</th>
						<th class="px-3 py-1.5 text-right font-medium">Mitjana</th>
					</tr>
				</thead>
				<tbody>
					{#each displayGames as g (g.id)}
						{@const p = persp(g)}
						<tr
							id="game-{g.id}"
							class="border-b border-slate-100 dark:border-slate-800 last:border-b-0 {rank15.ids.has(g.id)
								? 'bg-amber-50 dark:bg-amber-950/40'
								: $page.url.searchParams.get('game') === g.id
									? 'bg-blue-50 dark:bg-blue-950/40'
									: ''}"
						>
							<td class="w-8 px-2 py-2 text-center sm:px-3">
								<span class="inline-block w-6 rounded text-center text-xs font-bold {p.tie
									? 'text-slate-400 dark:text-slate-500'
									: p.won
										? 'text-emerald-600 dark:text-emerald-400'
										: 'text-red-500 dark:text-red-400'}">{p.tie ? 'E' : p.won ? 'G' : 'P'}</span>
							</td>
							<td class="w-full max-w-0 px-2 py-2 sm:px-3">
								{#if p.oppId && !kiosk}
									<a
										href="/jugador/{p.oppId}"
										class="block truncate text-sm font-medium leading-tight underline-offset-2 active:underline"
										>{p.opp}</a>
									{:else}
										<div class="truncate text-sm leading-tight">{p.opp}</div>
									{/if}
									<div class="truncate text-[11px] text-slate-400 dark:text-slate-500">
										{fmtDate(p.date)}{#if p.comp} · {p.comp}{/if}{#if p.mySerie} · S.M. {p.mySerie}{/if}
									</div>
								</td>
								<td class="whitespace-nowrap px-2 py-2 text-right font-mono text-sm tabular-nums sm:px-3">{p.myCar}–{p.oppCar}</td>
								<td class="whitespace-nowrap px-2 py-2 text-right text-[11px] tabular-nums text-slate-400 dark:text-slate-500 sm:px-3">
									{p.ent ? `${(p.myCar / p.ent).toFixed(3)} · ${p.ent} ent.` : '—'}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{#if !serieFilter && modGames.length > shown}
			<button
				onclick={() => (shown += 60)}
				class="mt-2 w-full rounded-lg bg-white dark:bg-slate-900 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-800 active:bg-slate-50 dark:active:bg-slate-800/50 print:hidden"
			>
				Carregar més ({shown} de {modGames.length})
			</button>
		{:else if modGames.length > 60}
			<p class="px-1 py-3 text-center text-[11px] text-slate-400 dark:text-slate-500 print:hidden">{modGames.length} partides</p>
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
	:global(html.dark) .thin-range {
		background: #334155; /* slate-700 */
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

	.print-only {
		display: none;
	}

	@media print {
		.profile-root :global(.rounded-xl:not(.games-wrap)) {
			break-inside: avoid;
			page-break-inside: avoid;
		}
		.games-wrap {
			break-inside: auto;
			overflow: visible !important;
		}
		/* A pantalla la cel·la del rival té max-width:0 perquè el truncate retalli i no
		   empenyi el marcador fora de la vista; a l'imprimir la pàgina és ampla, així que
		   alliberem la restricció i deixem que els noms i la competició es mostrin sencers. */
		.games-wrap td {
			max-width: none !important;
			white-space: normal !important;
		}
		.games-wrap tbody tr {
			break-inside: avoid;
			page-break-inside: avoid;
		}
		.print-only {
			display: table-header-group !important;
		}
		.print-only tr {
			break-inside: avoid;
			page-break-inside: avoid;
		}
	}
</style>
