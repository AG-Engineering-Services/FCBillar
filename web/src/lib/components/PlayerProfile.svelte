<script lang="ts">
	import { page } from '$app/stores';
	import { datesRanquing, ymDelRanquing, type DatesRanquing } from '$lib/dataRanquing';
	import {
		db,
		type GameRow,
		type PendingGameRow,
		type ProvisionalRow,
		nacionalPartidesDelJugador,
		rfebIndividualsDelJugador,
		rfebPartidesDelJugador,
		palmaresDelJugador,
		type PalmaresRow,
		umbDelJugador
	} from '$lib/db';
	import { agrupaUmb, resultatUmb, type UmbProva } from '$lib/internacional';
	import {
		aportacionsNacional,
		aportacionsRfeb,
		aportacionsRfebPartides,
		provesAmbPartidesCompletes,
		aportacionsUmb,
		filtraModalitat,
		efectivitatRfeb,
		finestres,
		gamesDeNacional,
		gamesDeRfeb,
		gamesDeUmb,
		tipusCompeticio,
		type GameRowAmbit,
		modalitatRfeb,
		modalitatsDe,
		modalitatUmb,
		type Indicadors
	} from '$lib/indicadorsAmbit';
	import {
		resultatPartida,
		resultatRfeb,
		type NacionalPartidaRow,
		type RfebIndividualRow,
		type RfebPartidaRow
	} from '$lib/nacional';
	import { follows, toggleFollow } from '$lib/follows';
	import { LLINDAR_RESUM, resumMedalles, resumPerModalitat, type MedallaResumible, type ResumMedalles } from '$lib/palmaresResum';
	import { deLaModalitat, palmaresCatalunya, recomptePerMena, type MenaDePalmares } from '$lib/palmaresCatalunya';
	import RadarChart from '$lib/components/RadarChart.svelte';
	import { theme } from '$lib/theme';
	import { ADMIN_EMAIL, esAdminLocal, marcaAdmin } from '$lib/admin';
	import AvisError from '$lib/components/AvisError.svelte';
	import RivalFilter from '$lib/components/RivalFilter.svelte';
	import type { Rival } from '$lib/rivals';

	// Reutilitzable: la pàgina normal passa kiosk=false; la vista aïllada /fitxa passa
	// kiosk=true (sense botons de navegació ni enllaços que surtin de la vista).
	let { fcbId, kiosk = false }: { fcbId: string; kiosk?: boolean } = $props();

	// Botó de reingesta manual: només a la fitxa de l'Albert Gómez i només amb la
	// marca d'admin (vegeu $lib/admin). Encua una petició a Neon (taula
	// reingest_requests) i crida /reingesta/avisa, que engega reingest-nologin.yml.
	// El correu el torna a validar la RLS.
	const ADMIN_FCB_ID = '278';
	let isAdmin = $state(false);
	$effect(() => {
		isAdmin = fcbId === ADMIN_FCB_ID && esAdminLocal($page.url);
	});
	let formReingesta = $state(false);
	let correuReingesta = $state('');
	let reingestState = $state<'idle' | 'sending' | 'ok' | 'denied' | 'error'>('idle');
	let reingestMsg = $state('');

	async function requestReingest(ev: SubmitEvent) {
		ev.preventDefault();
		if (correuReingesta.trim().toLowerCase() !== ADMIN_EMAIL) {
			reingestState = 'denied';
			reingestMsg = 'Correu no autoritzat.';
			return;
		}
		// Aquest dispositiu queda marcat: la Cataleg, el Traductor i aquest botó
		// s'hi ensenyaran sense el `?admin`.
		marcaAdmin();
		reingestState = 'sending';
		reingestMsg = '';
		const { error: e } = await db
			.from('reingest_requests')
			.insert({ requested_email: ADMIN_EMAIL, source: `fitxa/${fcbId}` });
		if (e) {
			reingestState = 'error';
			reingestMsg = `No s'ha pogut encuar: ${e.message}`;
			return;
		}
		let avisat = false;
		let motiu = '';
		try {
			const r = await fetch('/reingesta/avisa', { method: 'POST' });
			({ avisat, motiu = '' } = await r.json());
		} catch (err) {
			motiu = err instanceof Error ? err.message : String(err);
		}
		formReingesta = false;
		if (avisat) {
			reingestState = 'ok';
			reingestMsg = 'Reingesta engegada a GitHub Actions. Tarda uns 25 minuts.';
		} else if (motiu === 'massa aviat') {
			reingestState = 'ok';
			reingestMsg = "Ja se n'ha engegat una fa menys d'un minut.";
		} else {
			reingestState = 'error';
			reingestMsg = `Petició desada, però la reingesta no s'ha engegat (${motiu || 'sense resposta'}). Llança-la des de GitHub Actions.`;
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
			tipus: MenaDePalmares;
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
		rivalSel = null;
		if (id) loadAll(id);
	});

	// Apartat a part: si la consulta falla (p. ex. el cache d'esquemes de Neon encara
	// no veu nacional_partides_fitxa) o no hi ha partides, simplement no surt.
	let nacional = $state<NacionalPartidaRow[]>([]);
	$effect(() => {
		const id = fcbId;
		let viu = true;
		nacional = [];
		if (id)
			nacionalPartidesDelJugador(id)
				.then((r) => {
					if (viu) nacional = r;
				})
				.catch((e) => console.warn('Lliga Nacional no disponible', e));
		return () => {
			viu = false;
		};
	});

	let individuals = $state<RfebIndividualRow[]>([]);
	$effect(() => {
		const id = fcbId;
		let viu = true;
		individuals = [];
		if (id)
			rfebIndividualsDelJugador(id)
				.then((r) => {
					if (viu) individuals = r;
				})
				.catch((e) => console.warn('Campionats individuals RFEB no disponibles', e));
		return () => {
			viu = false;
		};
	});

	// Les partides una a una de les proves de la RFEB que en publiquen el detall
	// (fulls de desenvolupament, PDF de fases antics).
	let rfebPartides = $state<RfebPartidaRow[]>([]);
	$effect(() => {
		const id = fcbId;
		let viu = true;
		rfebPartides = [];
		if (id)
			rfebPartidesDelJugador(id)
				.then((r) => {
					if (viu) rfebPartides = r;
				})
				.catch((e) => console.warn('Partides de la RFEB no disponibles', e));
		return () => {
			viu = false;
		};
	});
	const provesAmbPartides = $derived(new Set(rfebPartides.map((r) => r.prova_id)));
	// Per a les targetes: només les proves on les partides quadren amb el total oficial.
	const provesCompletes = $derived(provesAmbPartidesCompletes(rfebPartides, individuals));

	// Les medalles del Quadre d'Honor de la FCB i dels campionats d'Espanya (RFEB) i d'Europa (CEB).
	let medalles = $state<PalmaresRow[]>([]);
	$effect(() => {
		const id = fcbId;
		let viu = true;
		medalles = [];
		if (id)
			palmaresDelJugador(id)
				.then((r) => {
					if (viu) medalles = r;
				})
				.catch((e) => console.warn('Palmarès no disponible', e));
		return () => {
			viu = false;
		};
	});
	// Per any, del més recent al més antic; les edicions sense any, al final.
	// Al medaller de la RFEB, la competició que porta el nom d'una modalitat és el campionat d'Espanya.
	const MODALITATS_RFEB = new Set(['Tres bandes', 'Lliure', 'Una banda', 'Quadre 47/1', 'Quadre 47/2', 'Quadre 71/2', 'Artístic']);
	const NOMS_RFEB: Record<string, string> = {
		"Gran Premi d'Espanya tres bandes": "Gran Premi d'Espanya de Tres Bandes",
		'Seleccions autonòmiques tres bandes': 'Seleccions Autonòmiques de Tres Bandes'
	};
	const nomCampionatEspanya = (c: string) =>
		NOMS_RFEB[c] ??
		(MODALITATS_RFEB.has(c) ? `Campionat d'Espanya de ${c.replace(/(^|\s)\p{L}/gu, (x) => x.toUpperCase())}` : c);
	function medallesPerAny(font: PalmaresRow['font'], treu: (m: PalmaresRow) => boolean = () => false) {
		const grups = new Map<string, PalmaresRow[]>();
		const files = medalles
			.filter((m) => m.font === font && !treu(m))
			.map((m) =>
				font === 'rfeb'
					? { ...m, competicio: nomCampionatEspanya(m.competicio), categoria: m.categoria === 'seleccions' ? 'absolut' : m.categoria }
					: m
			)
			.sort((a, b) => (b.any_edicio ?? 0) - (a.any_edicio ?? 0) || a.posicio - b.posicio);
		for (const m of files) {
			const clau = m.any_edicio != null ? String(m.any_edicio) : 'Sense any';
			grups.set(clau, [...(grups.get(clau) ?? []), m]);
		}
		return [...grups].map(([any, entries]) => ({ any, entries }));
	}
	const medallesEsp = $derived(medalles.length ? medallesPerAny('rfeb') : []);
	const medallesInt = $derived(medalles.length ? medallesPerAny('ceb') : []);
	// Catalunya en una sola llista: el Quadre d'Honor i els podis de la web, sense repetir títols.
	const MENA_PLURAL: Record<MenaDePalmares, string> = {
		campionat: 'Campionats de Catalunya',
		open: 'Opens',
		torneig: 'Altres tornejos oficials'
	};
	// De la modalitat triada; el que no té pestanya (chapó, quilles, trofeus) surt sempre.
	const palmaresCat = $derived(
		deLaModalitat(
			palmaresCatalunya(palmares, medalles.filter((m) => m.font === 'fcb')),
			selMod,
			new Set(modalitats.map((m) => m.codi))
		)
	);
	/** El campionat primer; la modalitat només quan no és la de la pestanya. */
	const titolPalmares = (e: { tipus: MenaDePalmares; nom: string; modalitat: number | null }) =>
		e.tipus !== 'campionat' ? e.nom : e.modalitat === selMod ? 'Campionat de Catalunya' : `Campionat de Catalunya · ${e.nom}`;
	const recompteCat = $derived(recomptePerMena(palmaresCat));
	const campionatsCat = $derived(
		palmaresCat.flatMap((g) =>
			g.entries
				.filter((e) => e.tipus === 'campionat' && e.posicio <= 3)
				.map((e) => ({ competicio: e.nom, categoria: e.categoria || 'absolut', posicio: e.posicio as 1 | 2 | 3 }))
		)
	);

	let internacional = $state<UmbProva[]>([]);
	$effect(() => {
		const id = fcbId;
		let viu = true;
		internacional = [];
		if (id)
			umbDelJugador(id)
				.then((r) => {
					if (viu) internacional = agrupaUmb(r.partides, r.classificacions);
				})
				.catch((e) => console.warn('Proves internacionals no disponibles', e));
		return () => {
			viu = false;
		};
	});

	// Catalunya, Espanya i Internacional no es barregen; cada opció surt només si té dades.
	type Ambit = 'cat' | 'esp' | 'int';
	let ambit = $state<Ambit>('cat');
	const teEspanya = $derived(
		nacional.length > 0 || individuals.length > 0 || rfebPartides.length > 0 || medallesEsp.length > 0
	);
	const teInternacional = $derived(internacional.length > 0 || medallesInt.length > 0);
	const ambits = $derived(
		(
			[
				['cat', 'Catalunya', true],
				['esp', 'Espanya', teEspanya],
				['int', 'Internacional', teInternacional]
			] as [Ambit, string, boolean][]
		).filter((a) => a[2])
	);
	const veuEspanya = $derived(ambit === 'esp' && teEspanya);
	const veuInternacional = $derived(ambit === 'int' && teInternacional);

	// «Partides contra…»: els rivals de l'àmbit que es mira, de totes les
	// modalitats. Amb un de triat, només s'ensenyen les partides contra ell. Els
	// àmbits no es barregen: canviar d'àmbit buida el filtre.
	let rivalSel = $state<Rival | null>(null);
	$effect(() => {
		void ambit;
		rivalSel = null;
	});
	const clauRival = (id: string | null, nom: string) => id ?? nom;
	const rivals = $derived.by(() => {
		const map = new Map<string, Rival>();
		const compta = (key: string, nom: string) => {
			const r = map.get(key);
			if (r) r.partides++;
			else map.set(key, { key, nom, partides: 1 });
		};
		if (veuInternacional) {
			for (const pr of internacional) for (const r of pr.partides) compta(clauRival(r.rival_fcb_id, r.rival), r.rival);
		} else if (veuEspanya) {
			for (const r of nacional) compta(clauRival(r.rival_fcb_id, r.rival), r.rival);
			for (const r of rfebPartides) compta(clauRival(r.rival_fcb_id, r.rival), r.rival);
		} else {
			for (const g of games) {
				const p = persp(g);
				compta(clauRival(p.oppId, p.opp), p.opp);
			}
		}
		return [...map.values()];
	});
	const esRival = (id: string | null, nom: string) => rivalSel != null && clauRival(id, nom) === rivalSel.key;

	// Tots els apartats de la fitxa surten d'aquesta llista. A Espanya i Internacional
	// són les partides de la Lliga Nacional i de la UMB/CEB escrites com les catalanes,
	// i així els tres àmbits tenen els mateixos apartats calculats igual.
	const gamesAmbit = $derived<GameRowAmbit[]>(
		(veuEspanya
			? [...gamesDeNacional(fcbId, nacional), ...gamesDeRfeb(fcbId, rfebPartides)]
			: veuInternacional
				? gamesDeUmb(fcbId, internacional)
				: []
		)
			// La més recent primer, com les catalanes.
			.sort((a, b) => (b.data_partida ?? '').localeCompare(a.data_partida ?? ''))
	);
	// Les partides de l'àmbit que es mira: les catalanes, o les d'Espanya o
	// Internacional escrites com les catalanes (`gamesAmbit`, més avall).
	const rivalGames = $derived(
		rivalSel
			? (veuEspanya || veuInternacional ? gamesAmbit : games).filter((g) => {
					const p = persp(g);
					return esRival(p.oppId, p.opp);
				})
			: []
	);
	const nacionalFiltrat = $derived(rivalSel ? nacional.filter((r) => esRival(r.rival_fcb_id, r.rival)) : nacional);
	const rfebFiltrat = $derived(rivalSel ? rfebPartides.filter((r) => esRival(r.rival_fcb_id, r.rival)) : rfebPartides);
	const internacionalFiltrat = $derived(
		rivalSel
			? internacional
					.map((pr) => ({ ...pr, partides: pr.partides.filter((r) => esRival(r.rival_fcb_id, r.rival)) }))
					.filter((pr) => pr.partides.length)
			: internacional
	);
	// Balanç contra el rival, només amb les partides de l'àmbit que es mira.
	const rivalKpi = $derived.by(() => {
		let n = 0, w = 0, t = 0, l = 0, car = 0, ent = 0;
		const suma = (res: 'G' | 'E' | 'P', c: number | null, e: number | null) => {
			n++;
			if (res === 'G') w++;
			else if (res === 'E') t++;
			else l++;
			if (c != null && e) {
				car += c;
				ent += e;
			}
		};
		if (!rivalSel) return { n, w, t, l, mitjana: 0 };
		if (veuInternacional) {
			for (const pr of internacionalFiltrat) for (const r of pr.partides) suma(resultatUmb(r), r.caramboles, r.entrades);
		} else if (veuEspanya) {
			for (const r of nacionalFiltrat) suma(resultatPartida(r.caramboles, r.caramboles_rival), r.caramboles, r.entrades);
			for (const r of rfebFiltrat) suma(resultatRfeb(r), r.caramboles, r.entrades);
		} else {
			for (const g of rivalGames) {
				const p = persp(g);
				suma(p.tie ? 'E' : p.won ? 'G' : 'P', p.myCar, p.ent);
			}
		}
		return { n, w, t, l, mitjana: ent ? car / ent : 0 };
	});
	// Indicadors d'Espanya i Internacional: es calculen amb les dades de l'àmbit i,
	// com a Catalunya, d'una sola modalitat (la més jugada, si no se'n tria una).
	const apsAmbit = $derived(
		veuInternacional
			? aportacionsUmb(internacional)
			: veuEspanya
				? [
						...aportacionsNacional(nacional),
						...aportacionsRfebPartides(rfebPartides.filter((r) => provesCompletes.has(r.prova_id))),
						...aportacionsRfeb(individuals, provesCompletes)
					]
				: []
	);
	const opcionsMod = $derived(modalitatsDe(apsAmbit.map((a) => a.modalitat)));
	let selModAlt = $state<string | null>(null);
	const modAlt = $derived(opcionsMod.some((o) => o.clau === selModAlt) ? selModAlt : (opcionsMod[0]?.clau ?? null));
	const kpiAmbit = $derived(finestres(filtraModalitat(apsAmbit, modAlt)));
	const ambitAnterior = $derived(kpiAmbit.anterior.n || kpiAmbit.anterior.nomesMitjana ? kpiAmbit.anterior : null);
	const individualsLlista = $derived(modAlt == null ? individuals : individuals.filter((r) => modalitatRfeb(r.modalitat) === modAlt));
	type TargetaKpi = Omit<Indicadors, 'nomesMitjana'> & { nomesMitjana?: number };
	const nomModalitat = (codi: number | null) => modalitats.find((m) => m.codi === codi)?.nom ?? null;

	async function loadAll(id: string) {
		loading = true;
		error = null;
		try {
			const { data: p } = await db
				.from('players')
				.select('nom, club_fcb_id')
				.eq('fcb_id', id)
				.maybeSingle();
			nom = p?.nom ?? id;
			clubId = p?.club_fcb_id ?? null;
			if (p?.club_fcb_id) {
				const { data: c } = await db
					.from('clubs')
					.select('nom')
					.eq('fcb_id', p.club_fcb_id)
					.maybeSingle();
				club = c?.nom ?? null;
			} else {
				club = null;
			}

			const { data: g, error: e } = await db
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
			const { data: pg } = await db
				.from('pending_games')
				.select(
					'modalitat_codi, competicio, font, opponent_nom, caramboles, caramboles_opp, entrades, serie, data'
				)
				.eq('player_fcb_id', id);
			// Només les d'aquesta temporada (les sense data són de la copa en curs). La
			// llista no ensenya la data i una de fa anys semblaria d'aquesta setmana.
			const iniciTemporada = (() => {
				const d = new Date();
				return `${d.getMonth() + 1 >= 8 ? d.getFullYear() : d.getFullYear() - 1}-08-01`;
			})();
			pendingRows = ((pg ?? []) as (PendingGameRow & { data: string | null })[]).filter(
				(r) => r.data == null || r.data >= iniciTemporada
			);

			// Projecció del proper rànquing (autoritativa, computada al backend).
			const { data: pr } = await db
				.from('ranking_provisional')
				.select(
					'player_fcb_id, modalitat_codi, posicio_oficial, mitjana_oficial, posicio_provisional, mitjana_provisional, partides_post, proj_won, proj_lost, proj_tie, window_game_ids, current_game_ids'
				)
				.eq('player_fcb_id', id);
			provByMod = new Map((pr ?? []).map((r: any) => [r.modalitat_codi, r as ProvisionalRow]));

			const { data: pc } = await db
				.from('player_clubs')
				.select('temporada, club')
				.eq('player_fcb_id', id)
				.order('temporada', { ascending: false });
			clubHist = pc ?? [];

			const { data: podiums } = await db
				.from('open_classifications')
				.select('open_id, posicio, club')
				.eq('player_fcb_id', id)
				.gte('posicio', 1)
				.lte('posicio', 3);
			const openIds = [...new Set((podiums ?? []).map((x) => x.open_id))];
			const { data: podiumOpens } = openIds.length
				? await db.from('opens').select('open_id, nom, temporada').in('open_id', openIds)
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
							/CAMPIONAT\s+CATALUNYA|CATALUNYA|^(?:TRES BANDES|3 BANDES|LLIURE|BANDA|QUADRE 47\/2|QUADRE 71\/2)(?:\s+INDIVIDUAL)?\s+-/i.test(
								rawNom
							) ||
							/\b(?:TRES BANDES|3 BANDES|LLIURE|BANDA|QUADRE 47\/2|QUADRE 71\/2)\s+(?:FEMEN[IÍ]|JUNIOR)\b/i.test(
								rawNom
							));
					const categoria = isChampionship ? championshipCategory : !isOpen && parts.length > 1 ? parts.at(-1)! : null;
					const tipus: MenaDePalmares = isOpen ? 'open' : isChampionship ? 'campionat' : 'torneig';
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

			const { data: or } = await db
				.from('open_ranking')
				.select('ronda, posicio, punts, detall')
				.eq('player_fcb_id', id)
				.eq('genere', 'general');
			openRank = or ?? [];

			const { data: orf } = await db
				.from('open_ranking')
				.select('ronda, posicio, punts, detall')
				.eq('player_fcb_id', id)
				.eq('genere', 'femeni');
			openRankFem = orf ?? [];

			const present = [...new Set(games.map((x) => x.modalitat_codi).filter((v) => v != null))];
			const { data: md } = await db
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
	const modGames = $derived<GameRow[]>(
		veuEspanya || veuInternacional
			? gamesAmbit.filter((g) => modAlt == null || g.modAmbit === modAlt)
			: games.filter((g) => selMod == null || g.modalitat_codi === selMod)
	);
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
		const ambitClau = veuEspanya ? 'esp' : veuInternacional ? 'int' : 'cat';
		const kind = (c: string | null) => tipusCompeticio(ambitClau, c);
		const map = new Map<string, { w: number; e: number; l: number; n: number }>();
		// Les partides d'una prova de la RFEB que no quadren amb el total oficial no
		// hi compten: hi compta el total (més avall), com a les targetes.
		const deProvaIncompleta = (id: string) =>
			id.startsWith('rfeb:') && !provesCompletes.has(id.slice(5).split(':')[0]!);
		for (const g of modGames.filter((g) => !deProvaIncompleta(g.id))) {
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
		// Dels campionats d'Espanya només hi ha els totals de cada jugador.
		if (veuEspanya)
			for (const r of efectivitatRfeb(individualsLlista, provesCompletes)) {
				const b = map.get(r.tipus) ?? { w: 0, e: 0, l: 0, n: 0 };
				map.set(r.tipus, { w: b.w + r.w, e: b.e + r.e, l: b.l + r.l, n: b.n + r.n });
			}
		return [...map.entries()]
			.map(([tipus, b]) => {
				const winVal = tipus === 'Copa' ? 3 : 2;
				return { tipus, ...b, pct: b.n ? Math.round((100 * (b.w * winVal + b.e)) / (b.n * winVal)) : 0 };
			})
			.sort((a, b) => b.pct - a.pct);
	});
	const displayGames = $derived(
		rivalSel
			? rivalGames
			: serieFilter && kpi.sm > 0
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
	let dates = $state<DatesRanquing>(new Map());
	$effect(() => {
		const id = fcbId;
		const mod = selMod;
		if (id && mod != null) loadRankHist(id, mod);
		else rankHist = [];
	});
	async function loadRankHist(id: string, mod: number) {
		const [{ data }, { data: publicats }] = await Promise.all([
			db
				.from('ranking_entries')
				.select('num_seq, posicio, mitjana_general')
				.eq('player_fcb_id', id)
				.eq('modalitat_codi', mod)
				.order('num_seq', { ascending: true }),
			db.from('rankings').select('num_seq, any_pub, mes_pub').eq('modalitat_codi', mod)
		]);
		dates = datesRanquing(publicats ?? []);
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
		const { data: members } = await db
			.from('players')
			.select('fcb_id')
			.eq('club_fcb_id', cid);
		const ids = (members ?? []).map((m) => m.fcb_id);
		if (!ids.length) {
			clubRank = null;
			return;
		}
		const { data: ent } = await db
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
		const { data } = await db
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
		const { data: idx } = await db
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
	// Les 15 partides que computen a la mitjana del rànquing OFICIAL vigent. Font
	// autoritativa: ranking_provisional.current_game_ids (de ranking_game_links,
	// és a dir, les que la federació mateixa llista). Fallback a la reconstrucció
	// heurística per dates si no hi ha dades publicades.
	const currentRank15Games = $derived.by(() => {
		const ids = provRow?.current_game_ids ?? null;
		if (ids && ids.length) {
			const set = new Set(ids);
			return modGames.filter((g) => set.has(g.id));
		}
		const latestSeq = rankHist.at(-1)?.num_seq;
		if (latestSeq == null) return [] as GameRow[];
		const [rankYear, rankMonth] = ymFromSeq(latestSeq);
		const cutoff = `${rankYear}-${String(rankMonth).padStart(2, '0')}-01`;
		const ageCutoff = monthOffset(rankYear, rankMonth, -24);
		return sortedModGames
			.filter((g) => (g.data_partida ?? '') >= ageCutoff && (g.data_partida ?? '') < cutoff)
			.slice(0, 15);
	});
	// Marca a la llista de partides: quines computen ara mateix al rànquing.
	const currentIds = $derived(new Set(currentRank15Games.map((g) => g.id)));
	const currentRank15 = $derived(summarizeGames(currentRank15Games));
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
	// Partides ja jugades que encara NO computen però entraran al proper rànquing
	// (la finestra projectada menys les que ja hi computen). Sense partides noves
	// les dues finestres coincideixen i aquest conjunt queda buit.
	const nextOnlyIds = $derived(
		new Set([...rank15.ids].filter((gid) => !currentIds.has(gid)))
	);

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
	// Àmbit de l'histograma: tot l'històric de la modalitat o només la temporada
	// en curs. La temporada només s'ofereix si hi ha prou partides per a que la
	// distribució digui alguna cosa (les mateixes 5 que demana `histo`).
	type HistoScope = 'tot' | 'temporada';
	let histoScope = $state<HistoScope>('tot');
	const histoSeasonGames = $derived(
		modGames.filter((g) => (g.data_partida ?? '') >= seasonStart)
	);
	const histoHasSeason = $derived(
		histoSeasonGames.map(persp).filter((p) => p.ent > 0).length >= 5
	);
	// Si la modalitat triada no té prou partides de temporada, torna a "tot".
	$effect(() => {
		if (!histoHasSeason && histoScope === 'temporada') histoScope = 'tot';
	});

	const histo = $derived.by(() => {
		const src = histoScope === 'temporada' ? histoSeasonGames : modGames;
		const avgs = src
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
		// Desviació típica de les mitjanes per partida respecte la mitjana del
		// mateix àmbit, per quantificar i dibuixar la dispersió típica del
		// rendiment (franja ±1σ). Amb l'àmbit de temporada, el centre ha de ser
		// la mitjana de la temporada, no la de tot l'històric.
		const center = histoScope === 'temporada' ? seasonKpi.mitjana : kpi.mitjana;
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
		void histoScope;
		histoSel = null; // reinicia la selecció en canviar de modalitat o d'àmbit
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

	const MESOS_NOM = [
		'Gener', 'Febrer', 'Març', 'Abril', 'Maig', 'Juny',
		'Juliol', 'Agost', 'Setembre', 'Octubre', 'Novembre', 'Desembre'
	];
	function ymFromSeq(seq: number): [number, number] {
		return ymDelRanquing(seq, dates);
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
	<button type="button" onclick={back} class="mb-2 inline-flex min-h-11 items-center gap-1 text-sm text-slate-500 dark:text-slate-400 print:hidden">
		<span aria-hidden="true">←</span> Torna
	</button>
{/if}

{#if error}
	<AvisError missatge="No s'ha pogut carregar la fitxa del jugador." detall={error} onretry={() => location.reload()} />
{:else}
	<div class="mb-3 flex items-start justify-between gap-3">
		<div class="min-w-0">
			<h1 class="text-lg font-bold leading-tight">{nom}</h1>
			{#if club}
				{#if kiosk}<span class="text-sm text-slate-500 dark:text-slate-400">{club}</span>
				{:else}<a href="/club/{clubId}" class="text-sm text-slate-500 dark:text-slate-400 active:underline">{club}</a>{/if}
			{/if}
		</div>
		<div class="flex shrink-0 items-center gap-2 print:hidden">
			{#if isAdmin}
				<button
					type="button"
					onclick={() => (formReingesta = !formReingesta)}
					aria-expanded={formReingesta}
					disabled={reingestState === 'sending'}
					class="min-h-11 rounded-sm bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
				>
					{reingestState === 'sending' ? 'Enviant…' : '↻ Reingesta'}
				</button>
			{/if}
			{#if !kiosk}
				<button
					type="button"
					onclick={() => toggleFollow(fcbId)}
					aria-pressed={$follows.includes(fcbId)}
					class="min-h-11 rounded-sm px-3 py-1.5 text-sm font-medium {$follows.includes(fcbId)
						? 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100 ring-1 ring-slate-300 dark:ring-slate-600'
						: 'bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-900'}"
				>
					{$follows.includes(fcbId) ? '★ Seguint' : '☆ Seguir'}
				</button>
			{/if}
		</div>
	</div>

	{#if isAdmin && formReingesta}
		<form onsubmit={requestReingest} class="mb-3 flex flex-wrap items-end gap-2 print:hidden">
			<label class="flex min-w-0 flex-1 flex-col gap-1 text-xs text-slate-600 dark:text-slate-300">
				Correu autoritzat per llançar la reingesta de la federació
				<input
					type="email"
					required
					autocomplete="email"
					bind:value={correuReingesta}
					class="rounded-sm border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
				/>
			</label>
			<button
				type="submit"
				disabled={reingestState === 'sending'}
				class="min-h-11 rounded-sm bg-emerald-600 px-3 text-sm font-medium text-white disabled:opacity-50"
				>Llança la reingesta</button
			>
		</form>
	{/if}

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

	{#if ambits.length > 1}
		<div class="mb-3 grid {ambits.length === 3 ? 'grid-cols-3' : 'grid-cols-2'} overflow-hidden rounded-lg ring-1 ring-slate-300 dark:ring-slate-700 print:hidden" role="group" aria-label="Competicions">
			{#each ambits as [k, etiq] (k)}
				<button
					type="button"
					onclick={() => (ambit = k)}
					aria-pressed={ambit === k}
					class="min-h-11 text-sm font-semibold {ambit === k
						? 'bg-slate-800 text-white dark:bg-slate-100 dark:text-slate-900'
						: 'bg-white text-slate-600 dark:bg-slate-900 dark:text-slate-300'}"
				>{etiq}</button>
			{/each}
		</div>
		<p class="mb-3 hidden text-sm font-medium print:block">{veuInternacional ? 'Competicions de la UMB i la CEB' : veuEspanya ? 'Competicions de la RFEB' : 'Competicions de la FCB'}</p>
	{/if}

	{#if !loading && rivals.length}
		<div class="mb-3 max-w-md">
			<RivalFilter {rivals} bind:selected={rivalSel} />
			{#if rivalSel}
				<p class="-mt-0.5 px-1 text-sm text-slate-700 dark:text-slate-200" aria-live="polite">
					{rivalKpi.n} {rivalKpi.n === 1 ? 'partida' : 'partides'} ·
					<span class="font-semibold text-emerald-700 dark:text-emerald-400">{rivalKpi.w} G</span>
					· <span class="text-slate-600 dark:text-slate-300">{rivalKpi.t} E</span>
					· <span class="font-semibold text-red-700 dark:text-red-400">{rivalKpi.l} P</span>
					{#if rivalKpi.mitjana} · mitjana <span class="font-mono tabular-nums">{rivalKpi.mitjana.toFixed(3)}</span>{/if}
				</p>
			{/if}
		</div>
	{/if}

	{#if veuInternacional || veuEspanya}
		{#if opcionsMod.length > 1}
			{@render selectorModalitat(
				opcionsMod.map((o) => ({ id: o.clau, nom: o.clau })),
				modAlt,
				(id) => {
					selModAlt = id as string;
					shown = 60;
				}
			)}
			<p class="mb-3 hidden text-sm font-medium print:block">Modalitat: {modAlt ?? '—'}</p>
		{/if}
	{:else if modalitats.length > 1}
		{@render selectorModalitat(
			modalitats.map((m) => ({ id: m.codi, nom: m.nom })),
			selMod,
			(id) => {
				selMod = id as number;
				shown = 60;
			}
		)}
		<p class="mb-3 hidden text-sm font-medium print:block">
			Modalitat: {modalitats.find((m) => m.codi === selMod)?.nom ?? '—'}
		</p>
	{/if}

	{#if loading}
		<p class="py-6 text-center text-sm text-slate-500 dark:text-slate-400">Carregant…</p>
	{:else}
		<div class="profile-root lg:grid lg:grid-cols-2 lg:gap-6 lg:items-start print:block">
			<div class="min-w-0">
			{#if veuEspanya || veuInternacional}
				{@render targetesIndicadors(kpiAmbit.historic, kpiAmbit.actual, ambitAnterior, false)}
			{:else}
				{@render targetesIndicadors(kpi, seasonKpi, prevSeasonKpi.n ? prevSeasonKpi : null, true)}
			{/if}
			{#if serieFilter}
				<p class="mb-2 px-1 text-[11px] text-blue-600 dark:text-blue-400">Partides amb la sèrie màxima ({kpi.sm}). Torna a tocar «Sèrie màx» per desfer.</p>
			{/if}

		{#if !veuEspanya && !veuInternacional && currentPos != null}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<!-- La finestra no és 15 a totes les modalitats (tres bandes 15, la resta
				     10) i els no definitius en tenen menys: el nombre surt de les
				     partides realment marcades. -->
				<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Rànquing actual{currentIds.size ? ` · ${currentIds.size} ${currentIds.size === 1 ? 'partida' : 'partides'}` : ''}</div>
				<div class="grid grid-cols-3 gap-2">
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">#{currentPos}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">{lastMitjana != null ? lastMitjana.toFixed(3) : '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">mitjana</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">{currentRank15.sm || '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">S.M.</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums text-slate-900 dark:text-slate-100">#{bestPos ?? '—'}</div>
						<div class="text-2xs uppercase leading-tight tracking-wide text-slate-500 dark:text-slate-400">millor pos. rànquing</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums text-emerald-600 dark:text-emerald-400">{bestMitjana != null ? bestMitjana.toFixed(3) : '—'}</div>
						<div class="text-2xs uppercase leading-tight tracking-wide text-slate-500 dark:text-slate-400">millor mitjana rànquing</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums {rank15.hasChanges && lastMitjana != null && rank15.mitjana != null && rank15.mitjana > lastMitjana ? 'text-emerald-600 dark:text-emerald-400' : rank15.hasChanges && lastMitjana != null && rank15.mitjana != null && rank15.mitjana < lastMitjana ? 'text-red-500 dark:text-red-400' : ''}">{rank15.mitjana != null ? rank15.mitjana.toFixed(3) : '—'}</div>
						<div class="text-2xs uppercase leading-tight tracking-wide text-slate-500 dark:text-slate-400">mitjana proper rànq.</div>
						{#if rank15.hasChanges && rank15.posicio != null}
							{@const dp = (currentPos ?? 0) - rank15.posicio}
							<div class="mt-0.5 text-[11px] font-bold tabular-nums {dp > 0 ? 'text-emerald-600 dark:text-emerald-400' : dp < 0 ? 'text-red-500 dark:text-red-400' : 'text-slate-500 dark:text-slate-400'}">#{rank15.posicio}{dp > 0 ? ` ▲${dp}` : dp < 0 ? ` ▼${-dp}` : ''}</div>
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
				<div class="text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Efectivitat per competició</div>
				{#each compBuckets as c}
					<div class="flex items-center gap-2 text-sm">
						<span class="shrink-0 text-slate-600 dark:text-slate-300">{c.tipus}</span>
						<span class="min-w-0 flex-1 text-right font-mono text-[11px] tabular-nums">
							<span class="text-emerald-600 dark:text-emerald-400">{c.w}</span><span class="text-slate-500 dark:text-slate-400">-</span><span class="text-amber-600 dark:text-amber-400">{c.e}</span><span class="text-slate-500 dark:text-slate-400">-</span><span class="text-red-500 dark:text-red-400">{c.l}</span>
						</span>
						<span class="w-11 shrink-0 text-right font-mono font-bold tabular-nums">{c.pct}%</span>
					</div>
				{/each}
			</div>
		{/if}

		{#if !veuEspanya && !veuInternacional && openRank.length}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Rànquing d'Opens 3 Bandes</div>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">#{openCur?.posicio ?? '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">posició actual</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-emerald-600 dark:text-emerald-400">#{openBest ?? '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">millor posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-slate-900 dark:text-slate-100">#{openBestResult ?? '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">millor en un open</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">{openCur?.punts ?? '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">punts</div>
					</div>
				</div>
			</div>
		{/if}

		{#if !veuEspanya && !veuInternacional && openRankFem.length}
			<div class="mb-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 p-3 ring-1 ring-rose-200 dark:ring-rose-900/50">
				<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-rose-400 dark:text-rose-400">
					Rànquing Circuit Català Tres Bandes Femení
				</div>
				<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">#{openFemCur?.posicio ?? '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">posició actual</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-emerald-600 dark:text-emerald-400">#{openFemBest ?? '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">millor posició</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums text-slate-900 dark:text-slate-100">#{openFemBestResult ?? '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">millor en una prova</div>
					</div>
					<div class="text-center">
						<div class="font-mono text-lg font-bold tabular-nums">{openFemCur?.punts ?? '—'}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">punts</div>
					</div>
				</div>
			</div>
		{/if}

		{#if (veuEspanya ? medallesEsp : veuInternacional ? medallesInt : []).length}
			{@const grups = veuEspanya ? medallesEsp : medallesInt}
			{@const total = grups.reduce((n, g) => n + g.entries.length, 0)}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
					Palmarès individual · {veuEspanya ? 'Espanya' : 'Internacional'} · {total}
				</div>
				{#if total > LLINDAR_RESUM}
					{@const r = resumMedalles(grups.flatMap((g) => g.entries))}
					{@render recompteMedalles(r)}
					<details class="mt-2">
						<summary class="min-h-11 cursor-pointer py-3 text-sm font-medium">Per modalitat i per anys</summary>
						{@render perModalitat(grups.flatMap((g) => g.entries))}
						{@render llistaMedalles(grups, false)}
					</details>
				{:else}
					{@render llistaMedalles(grups, false)}
				{/if}
			</div>
		{/if}

		{#if !veuEspanya && !veuInternacional && palmaresCat.length}
			{@const total = palmaresCat.reduce((n, g) => n + g.entries.length, 0)}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Palmarès individual · {total}</div>
				<table class="w-full text-sm">
					<thead>
						<tr class="text-2xs text-slate-500 dark:text-slate-400">
							<th scope="col" class="py-1 text-left font-medium"><span class="sr-only">Competició</span></th>
							<th scope="col" class="w-12 text-right font-medium">1r</th>
							<th scope="col" class="w-12 text-right font-medium">2n</th>
							<th scope="col" class="w-12 text-right font-medium">3r</th>
						</tr>
					</thead>
					<tbody>
						{#each recompteCat as f (f.tipus)}
							<tr class="border-t border-slate-100 dark:border-slate-800">
								<th scope="row" class="py-1.5 text-left font-medium">{MENA_PLURAL[f.tipus]}</th>
								{#each [f.primers, f.segons, f.tercers] as n}
									<td class="text-right font-mono text-lg tabular-nums {n ? 'font-bold' : 'text-slate-500 dark:text-slate-400'}">{n}</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
				{#if campionatsCat.length > LLINDAR_RESUM}
					<details class="mt-2">
						<summary class="min-h-11 cursor-pointer py-3 text-sm font-medium">Campionats de Catalunya per modalitat</summary>
						{@render perModalitat(campionatsCat)}
					</details>
				{/if}
				{#if total > LLINDAR_RESUM}
					<details>
						<summary class="min-h-11 cursor-pointer py-3 text-sm font-medium">Llista per temporades</summary>
						{@render llistaPalmaresCat()}
					</details>
				{:else}
					<div class="mt-3">{@render llistaPalmaresCat()}</div>
				{/if}
			</div>
		{/if}

		{#snippet llistaPalmaresCat()}
				<div class="space-y-3">
					{#each palmaresCat as season (season.temporada)}
						<div>
							<div class="mb-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">{season.temporada}</div>
							<ul class="space-y-1">
								{#each season.entries as p}
									<li class="flex items-center gap-2 rounded-lg px-1.5 py-1 text-sm {p.tipus === 'campionat' ? 'bg-blue-50 dark:bg-blue-950/40 ring-1 ring-blue-100 dark:ring-blue-900/50' : ''}">
										<span class="w-6 shrink-0 text-center font-mono font-bold {p.posicio <= 3 ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}">{ordinal(p.posicio)}</span>
										<div class="min-w-0 flex-1">
											<div class="mb-0.5 flex items-center gap-1.5">
												<span class="shrink-0 rounded px-1 py-0.5 text-2xs font-bold uppercase tracking-wide {p.tipus === 'campionat' ? 'bg-blue-600 text-white' : p.tipus === 'open' ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'}">{p.tipus === 'campionat' ? 'Camp. Catalunya' : p.tipus === 'open' ? 'Open' : 'Torneig oficial'}</span>
												{#if kiosk || p.openId == null}<span class="min-w-0 truncate font-medium">{titolPalmares(p)}</span>
												{:else}<a href="/opens/{p.openId}" class="min-w-0 truncate font-medium active:underline">{titolPalmares(p)}</a>{/if}
											</div>
											{#if p.categoria}<div class="truncate text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Categoria · {p.categoria}</div>{/if}
										</div>
										{#if p.club}<span class="max-w-24 shrink-0 truncate text-2xs text-slate-500 dark:text-slate-400">{p.club}</span>{/if}
									</li>
								{/each}
							</ul>
						</div>
					{/each}
				</div>
		{/snippet}

		{#if h2h.played.length || h2h.won.length || h2h.lost.length}
			<div class="mb-4 space-y-2 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Rivals destacats (històric)</div>
				{#each [['played', 'Rivals habituals'], ['won', 'Més victòries'], ['lost', 'Més derrotes']] as [k, title]}
					{@const list = h2h[k as 'played' | 'won' | 'lost']}
					{#if list.length}
						<div class="flex items-start gap-2 text-sm">
							<span class="shrink-0 text-slate-500 dark:text-slate-400">{title}</span>
							<div class="min-w-0 flex-1 space-y-0.5 text-right font-medium">
								{#each list as e}
									<div class="truncate">
										{#if kiosk}<span>{e.nom}</span>{:else}<a href="/jugador/{e.id}" class="active:underline">{e.nom}</a>{/if}
										<span class="font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400">{#if k === 'played'}({e.total} / <span class="text-emerald-600 dark:text-emerald-400">{e.won}</span>-<span class="text-amber-600 dark:text-amber-400">{e.draws}</span>-<span class="text-red-500 dark:text-red-400">{e.lost}</span>){:else if k === 'won'}(<span class="text-emerald-600 dark:text-emerald-400">{e.won}G</span>){:else}(<span class="text-red-500 dark:text-red-400">{e.lost}P</span>){/if}</span>
									</div>
								{/each}
							</div>
						</div>
					{/if}
				{/each}
			</div>
		{/if}

		{#if kpi.best != null && bestGames.length}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
					Millor partida{bestGames.length > 1 ? ` · ${bestGames.length}` : ''} · mitjana {kpi.best.toFixed(3)}
				</div>
				<div class="divide-y divide-slate-100 dark:divide-slate-800">
					{#each bestGames as g}
						<div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 py-1.5 text-sm">
							<span
								class="rounded px-1 py-0.5 text-2xs font-semibold {g.won
									? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300'
									: g.tie
										? 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
										: 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400'}"
								>{g.won ? 'G' : g.tie ? 'E' : 'P'}</span
							>
							{#if g.oppId && !kiosk}
								<a href="/jugador/{g.oppId}" class="font-medium active:underline">{g.opp}</a>
							{:else}<span class="font-medium">{g.opp}</span>{/if}
							<span class="font-mono text-slate-500 dark:text-slate-400">{g.myCar}–{g.oppCar} · {g.ent} ent.</span>
							<span class="font-mono font-bold">{(g.myCar / g.ent).toFixed(3)}</span>
							{#if g.comp}<span class="text-[11px] text-slate-500 dark:text-slate-400">{g.comp}</span>{/if}
							<span class="ml-auto text-[11px] text-slate-500 dark:text-slate-400"
								>{g.date ? g.date.split('-').reverse().join('/') : ''}</span
							>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Rendiment per nivell d'oponent (aranya, per modalitat) -->
		{#if !veuEspanya && !veuInternacional && selMod != null && ratingBuckets.some((b) => b.wins + b.losses > 0)}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-1 flex items-center justify-between">
					<div class="text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
						Rendiment per nivell d'oponent
					</div>
					<div class="inline-flex overflow-hidden rounded-md border border-slate-300 dark:border-slate-700 text-2xs print:hidden">
						<button
							type="button"
							aria-pressed={radarMode === 'abs'}
							class="min-h-11 min-w-11 px-2 py-0.5 {radarMode === 'abs' ? 'bg-sky-600 text-white' : 'text-slate-600 dark:text-slate-300'}"
							onclick={() => (radarMode = 'abs')}>Absolut</button
						>
						<button
							type="button"
							aria-pressed={radarMode === 'pct'}
							class="min-h-11 min-w-11 px-2 py-0.5 {radarMode === 'pct' ? 'bg-sky-600 text-white' : 'text-slate-600 dark:text-slate-300'}"
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
										>{ratingCrossover.toFixed(2)}</span
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

		{#if !veuEspanya && !veuInternacional && mitjanaChart}
			{#if selIdx != null && rankHist[selIdx]}
				<div class="mb-2 flex items-center justify-center gap-3 rounded-lg bg-slate-900 dark:bg-slate-700 px-3 py-1.5 text-xs text-white">
					<span class="font-semibold">{dateFromSeq(rankHist[selIdx].num_seq)}</span>
					<span>mitjana <span class="font-mono font-bold">{rankHist[selIdx].mitjana?.toFixed(3) ?? '—'}</span></span>
					<span>posició <span class="font-mono font-bold">#{rankHist[selIdx].posicio ?? '—'}</span></span>
				</div>
			{:else}
				<p class="mb-2 text-center text-[11px] text-slate-500 dark:text-slate-400 print:hidden">Toca un gràfic o mou el lliscador per veure els valors d'un rànquing</p>
			{/if}
			{#if rankHist.length > 1}
				<label class="block print:hidden">
					<span class="sr-only">Rànquing a consultar</span>
					<input
						type="range"
						min="0"
						max={rankHist.length - 1}
						step="1"
						value={selIdx ?? rankHist.length - 1}
						oninput={(e) => (selIdx = +(e.currentTarget as HTMLInputElement).value)}
						aria-valuetext={selIdx != null && rankHist[selIdx] ? dateFromSeq(rankHist[selIdx].num_seq) : undefined}
						class="ag-range"
					/>
				</label>
			{/if}
			<div class="mb-4 space-y-3">
				<div class="rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
					<div class="mb-2 flex items-end justify-between">
						<span class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
							>Mitjana al rànquing</span>
						<div class="flex gap-4 text-right">
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums">
									{lastMitjana != null ? lastMitjana.toFixed(3) : '—'}
								</div>
								<div class="text-2xs text-slate-500 dark:text-slate-400">actual</div>
							</div>
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums text-emerald-600 dark:text-emerald-400">
									{mitjanaChart.hi.toFixed(3)}
								</div>
								<div class="text-2xs text-slate-500 dark:text-slate-400">millor</div>
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
					<div class="flex justify-between px-0.5 text-2xs tabular-nums text-slate-500 dark:text-slate-400">
						{#each xTicks as t}<span>{t.label}</span>{/each}
					</div>
				</div>
				<div class="rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
					<div class="mb-2 flex items-end justify-between">
						<span class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
							>Posició al rànquing</span>
						<div class="flex gap-4 text-right">
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums">
									#{currentPos ?? '—'}
								</div>
								<div class="text-2xs text-slate-500 dark:text-slate-400">actual</div>
							</div>
							<div>
								<div class="font-mono text-base font-bold leading-none tabular-nums text-slate-900 dark:text-slate-100">
									#{bestPos ?? '—'}
								</div>
								<div class="text-2xs text-slate-500 dark:text-slate-400">millor</div>
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
						<div class="flex justify-between px-0.5 text-2xs tabular-nums text-slate-500 dark:text-slate-400">
							{#each xTicks as t}<span>{t.label}</span>{/each}
						</div>
						<p class="mt-1 text-right text-2xs text-slate-500 dark:text-slate-400">{posChart.n} rànquings · amunt = millor</p>
					{/if}
				</div>
			</div>
		{/if}

		{#if rollChart && roll15.length}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-1 flex items-end justify-between">
					<span class="text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Mitjana mòbil · 15 partides</span>
					{#if rollSel != null && roll15[rollSel]}
						<div class="text-right">
							<div class="font-mono text-base font-bold leading-none tabular-nums text-blue-600 dark:text-blue-400">{roll15[rollSel].avg.toFixed(3)}</div>
							<div class="text-2xs text-slate-500 dark:text-slate-400">{fmtDate(roll15[rollSel].from)} – {fmtDate(roll15[rollSel].to)}</div>
						</div>
					{/if}
				</div>
				{#if rollSel != null && roll15[rollSel]}
					<div class="mb-1 flex items-center justify-between gap-2 rounded-lg bg-slate-900 dark:bg-slate-700 px-2 py-1 text-[11px] text-white">
						<span class="min-w-0 truncate">
							{#if roll15[rollSel].oppId && !kiosk}<a href="/jugador/{roll15[rollSel].oppId}" class="font-medium active:underline">{roll15[rollSel].opp}</a>{:else}<span class="font-medium">{roll15[rollSel].opp}</span>{/if}
							<span class="text-slate-300">· {fmtDate(roll15[rollSel].date)}</span>
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
				<div class="flex justify-between px-0.5 text-2xs tabular-nums text-slate-500 dark:text-slate-400">
					<span>mín {rollChart.lo.toFixed(3)}</span>
					<span>màx {rollChart.hi.toFixed(3)}</span>
				</div>
				{#if roll15.length > 1}
					<input type="range" min="0" max={roll15.length - 1} step="1" bind:value={rollSel} aria-label="Partida de la mitjana mòbil" class="ag-range mt-2 print:hidden" />
					<p class="text-center text-2xs text-slate-500 dark:text-slate-400 print:hidden">punt {(rollSel ?? 0) + 1} de {roll15.length} · finestra {rollStart + 1}–{Math.min(rollStart + WIN, roll15.length)}</p>
				{/if}
			</div>
		{/if}

		{#if histo}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-1 flex items-end justify-between">
					<div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
						<span class="text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Distribució de la mitjana · per partida</span>
						{#if histoHasSeason}
							<div class="flex shrink-0 items-center gap-1 print:hidden">
								{#each [['tot', 'Tot'], ['temporada', 'Temporada']] as [val, label]}
									<button
										type="button"
										onclick={() => (histoScope = val as HistoScope)}
										aria-pressed={histoScope === val}
										class="min-h-11 rounded-sm px-2 py-0.5 text-2xs font-medium transition-colors {histoScope === val
											? 'bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-900'
											: 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'}"
									>{label}</button>
								{/each}
							</div>
						{/if}
					</div>
					<div class="flex shrink-0 items-center gap-3">
						<div class="flex items-center gap-1.5">
							<span class="inline-block h-2 w-2 rounded-full bg-emerald-500"></span>
							<span class="font-mono text-base font-bold leading-none tabular-nums">{histo.mitjana.toFixed(3)}</span>
						</div>
						<div class="flex items-baseline gap-1">
							<span class="text-2xs font-semibold text-slate-500 dark:text-slate-400">σ</span>
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
					<p class="mb-1 text-center text-[11px] text-slate-500 dark:text-slate-400 print:hidden">Toca una barra o mou el lliscador per veure el detall</p>
				{/if}
				<label class="block print:hidden">
					<span class="sr-only">Franja de mitjana</span>
					<input
						type="range"
						min="0"
						max={histo.bins.length - 1}
						step="1"
						value={histoSel ?? 0}
						oninput={(e) => (histoSel = +(e.currentTarget as HTMLInputElement).value)}
						aria-valuetext={histoSel != null && histo.bins[histoSel] ? `${fmtAvg(histo.bins[histoSel].x0, histo.step)} a ${fmtAvg(histo.bins[histoSel].x1, histo.step)}: ${histo.bins[histoSel].count} partides` : undefined}
						class="ag-range"
					/>
				</label>
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
				<div class="flex justify-between px-0.5 text-2xs tabular-nums text-slate-500 dark:text-slate-400">
					{#each histoTicks as t}<span>{t}</span>{/each}
				</div>
				<p class="mt-1 text-right text-2xs text-slate-500 dark:text-slate-400">{histo.n} partides{histoScope === 'temporada' ? ' de la temporada' : ''} · línia = mitjana · franja = ±1σ</p>
			</div>
		{/if}

		{#if !veuEspanya && !veuInternacional && clubGroups.length}
			<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Clubs</div>
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
			<!-- El mateix llistat als tres àmbits. A Espanya i Internacional, les
			     partides de la Lliga Nacional, dels campionats de la RFEB i de la
			     UMB/CEB, totes juntes com les catalanes. -->
			{#if veuEspanya && individuals.some((r) => !provesAmbPartides.has(r.prova_id)) && !rivalSel}
				<p class="mb-2 px-1 text-[11px] text-slate-500 dark:text-slate-400">
					De la majoria de Campionats d'Espanya i GPE la RFEB només publica la classificació final, sense les partides: compten a les targetes i a l'efectivitat, però no surten en aquesta llista.
				</p>
			{/if}
			{#if copaPend.length && !rivalSel && !veuEspanya && !veuInternacional}
				<div class="mb-3 rounded-xl border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-950/40 p-3">
					<div class="mb-1.5 text-2xs font-bold uppercase tracking-wide text-blue-700 dark:text-blue-300">
						{copaPend.length} {copaPend.length === 1 ? 'partida pendent' : 'partides pendents'} · incloses a la previsió del proper rànquing
					</div>
					<ul class="space-y-1.5">
						{#each copaPend as cp}
							<li class="flex items-center gap-3 text-sm">
								<span class="w-5 shrink-0 text-center text-xs font-bold {cp.myCar > cp.oppCar ? 'text-emerald-600 dark:text-emerald-400' : cp.myCar < cp.oppCar ? 'text-red-500 dark:text-red-400' : 'text-slate-500 dark:text-slate-400'}">{cp.myCar > cp.oppCar ? 'G' : cp.myCar < cp.oppCar ? 'P' : 'E'}</span>
								<div class="min-w-0 flex-1">
									<div class="truncate leading-tight">{cp.opp}</div>
									<div class="truncate text-2xs uppercase tracking-wide text-blue-600 dark:text-blue-400">{cp.grup}</div>
								</div>
								<div class="shrink-0 text-right">
									<div class="font-mono text-sm tabular-nums">{cp.myCar}–{cp.oppCar}</div>
									<div class="font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400">{cp.ent ? `${(cp.myCar / cp.ent).toFixed(3)} · ${cp.ent} ent.` : '—'}</div>
								</div>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			{#if (currentIds.size || nextOnlyIds.size) && !veuEspanya && !veuInternacional}
				<div class="mb-2 space-y-0.5 px-1 text-[11px] text-slate-500 dark:text-slate-400">
					{#if currentIds.size}
						<p class="flex items-center gap-1.5">
							<span class="inline-block h-3 w-3 shrink-0 rounded bg-slate-100 dark:bg-slate-800 ring-1 ring-slate-300 dark:ring-slate-600"></span>
							les {currentIds.size} {currentIds.size === 1 ? 'partida que computa' : 'partides que computen'} a la mitjana del rànquing vigent
						</p>
					{/if}
					{#if nextOnlyIds.size}
						<p class="flex items-center gap-1.5">
							<span class="inline-block h-3 w-3 shrink-0 rounded bg-sky-50 dark:bg-sky-950/40 ring-1 ring-sky-200 dark:ring-sky-900/50"></span>
							{nextOnlyIds.size} {nextOnlyIds.size === 1 ? 'partida nova que entrarà' : 'partides noves que entraran'} al proper rànquing
						</p>
					{/if}
				</div>
			{/if}
		{#if rivalSel && !rivalGames.length}
			<p class="rounded-xl bg-white px-3 py-4 text-sm text-slate-600 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-800">
				Cap partida {veuEspanya ? "de les competicions de la RFEB" : veuInternacional ? 'de les proves de la UMB i la CEB' : 'dels campionats catalans'} contra {rivalSel.nom}.
			</p>
		{:else}
		<div class="games-wrap overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
			<table class="w-full text-sm">
				<thead class="print-only bg-slate-50 text-left text-2xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
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
						{@const inCur = currentIds.has(g.id)}
						{@const inNext = nextOnlyIds.has(g.id)}
						<tr
							id="game-{g.id}"
							class="border-b border-slate-100 dark:border-slate-800 last:border-b-0 {inCur
								? 'bg-slate-100 dark:bg-slate-800'
								: inNext
									? 'bg-sky-50 dark:bg-sky-950/40'
									: $page.url.searchParams.get('game') === g.id
										? 'bg-blue-50 dark:bg-blue-950/40'
										: ''}"
						>
							<td class="w-8 px-2 py-2 text-center sm:px-3">
								<span class="inline-block w-6 rounded text-center text-xs font-bold {p.tie
									? 'text-slate-500 dark:text-slate-400'
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
									<div class="truncate text-[11px] text-slate-500 dark:text-slate-400">
										{#if inCur}<span class="mr-1 rounded bg-slate-200 px-1 py-px text-2xs font-bold uppercase tracking-wide text-slate-700 dark:bg-slate-700 dark:text-slate-200" title="Computa a la mitjana del rànquing vigent">rànquing</span>{:else if inNext}<span class="mr-1 rounded bg-sky-100 px-1 py-px text-2xs font-bold uppercase tracking-wide text-sky-700 dark:bg-sky-900/60 dark:text-sky-300" title="Entrarà al proper rànquing">proper</span>{/if}{fmtDate(p.date)}{#if rivalSel && modalitats.length > 1 && nomModalitat(g.modalitat_codi)} · {nomModalitat(g.modalitat_codi)}{/if}{#if p.comp} · {p.comp}{/if}{#if p.mySerie} · S.M. {p.mySerie}{/if}
									</div>
									{#if (g as GameRowAmbit).detall}
										<div class="truncate text-[11px] text-slate-500 dark:text-slate-400">{(g as GameRowAmbit).detall}</div>
									{/if}
								</td>
								<td class="whitespace-nowrap px-2 py-2 text-right font-mono text-sm tabular-nums sm:px-3">{p.myCar}–{p.oppCar}</td>
								<td class="whitespace-nowrap px-2 py-2 text-right text-[11px] tabular-nums text-slate-500 dark:text-slate-400 sm:px-3">
									{p.ent ? `${(p.myCar / p.ent).toFixed(3)} · ${p.ent} ent.` : '—'}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
		{#if rivalSel}
			<!-- Sense paginació: contra un rival les partides són poques. -->
		{:else if !serieFilter && modGames.length > shown}
			<button
				type="button"
				onclick={() => (shown += 60)}
				class="mt-2 min-h-11 w-full rounded-lg bg-white dark:bg-slate-900 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-800 active:bg-slate-50 dark:active:bg-slate-800/50 print:hidden"
			>
				Carregar més ({shown} de {modGames.length})
			</button>
		{:else if modGames.length > 60}
			<p class="px-1 py-3 text-center text-[11px] text-slate-500 dark:text-slate-400 print:hidden">{modGames.length} partides</p>
		{/if}

			</div>
		</div>
	{/if}
{/if}

{#snippet recompteMedalles(r: ResumMedalles)}
	<dl class="grid grid-cols-3 gap-2 text-center">
		{#each [['Primers', r.primers], ['Segons', r.segons], ['Tercers', r.tercers]] as [nom, n]}
			<div class="rounded-lg bg-slate-50 dark:bg-slate-800/60 px-2 py-2">
				<dt class="text-2xs text-slate-500 dark:text-slate-400">{nom} llocs</dt>
				<dd class="font-mono text-xl font-bold tabular-nums">{n}</dd>
			</div>
		{/each}
	</dl>
{/snippet}

{#snippet perModalitat(ms: MedallaResumible[])}
	{#each resumPerModalitat(ms) as g (g.modalitat)}
		<div class="mb-1 mt-2 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
			{g.modalitat} · {g.resum.primers} 1r · {g.resum.segons} 2n · {g.resum.tercers} 3r
		</div>
		{@render taulaResum(g.resum)}
	{/each}
{/snippet}

{#snippet taulaResum(r: ResumMedalles)}
	<table class="mb-3 w-full text-sm">
		<thead>
			<tr class="text-2xs text-slate-500 dark:text-slate-400">
				<th scope="col" class="py-1 text-left font-medium">Competició</th>
				<th scope="col" class="w-9 text-right font-medium">1r</th>
				<th scope="col" class="w-9 text-right font-medium">2n</th>
				<th scope="col" class="w-9 text-right font-medium">3r</th>
			</tr>
		</thead>
		<tbody>
			{#each r.perCompeticio as f (f.competicio)}
				<tr class="border-t border-slate-100 dark:border-slate-800">
					<td class="max-w-0 truncate py-1 pr-2" title={f.competicio}>{f.competicio}</td>
					{#each [f.primers, f.segons, f.tercers] as n}
						<td class="text-right font-mono tabular-nums {n ? 'font-bold' : 'text-slate-500 dark:text-slate-400'}">{n}</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
{/snippet}

{#snippet llistaMedalles(grups: { any: string; entries: PalmaresRow[] }[], quadreHonor: boolean)}
	<div class="space-y-3">
		{#each grups as g}
			<div>
				<div class="mb-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">{quadreHonor ? g.entries[0].edicio : g.any}</div>
				<ul class="space-y-1">
					{#each g.entries as m}
						<li class="flex items-center gap-2 px-1.5 py-1 text-sm">
							<span class="w-6 shrink-0 text-center font-mono font-bold">{ordinal(m.posicio)}</span>
							<div class="min-w-0 flex-1">
								<div class="truncate font-medium">{m.competicio}{m.categoria !== 'absolut' ? ` · ${m.categoria}` : ''}</div>
								{#if quadreHonor}
									{#if m.lloc}<div class="truncate text-2xs text-slate-500 dark:text-slate-400">{m.lloc}</div>{/if}
								{:else}
									<div class="truncate text-2xs text-slate-500 dark:text-slate-400">Edició {m.edicio}{m.lloc ? ` · ${m.lloc}` : ''}</div>
								{/if}
							</div>
							{#if !quadreHonor && m.mitjana != null}<span class="shrink-0 font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400">{m.mitjana.toLocaleString('ca', { maximumFractionDigits: 3 })}{m.competicio.startsWith('Art') ? ' %' : ''}</span>{/if}
						</li>
					{/each}
				</ul>
			</div>
		{/each}
	</div>
{/snippet}

{#snippet selectorModalitat(opcions: { id: string | number | null; nom: string }[], triada: string | number | null, tria: (id: string | number | null) => void)}
	<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none] print:hidden">
		{#each opcions as m (m.id)}
			<button
				type="button"
				onclick={() => tria(m.id)}
				aria-pressed={m.id === triada}
				class="min-h-11 shrink-0 rounded-sm px-3 py-1 text-sm font-medium {m.id === triada
					? 'bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-900'
					: 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 ring-1 ring-slate-200 dark:ring-slate-800'}"
			>{m.nom}</button>
		{/each}
	</div>
{/snippet}

{#snippet peuTargeta(k: TargetaKpi)}
	<p class="mt-2 px-1 text-[11px] text-slate-500 dark:text-slate-400">
		{#if !k.n && !k.nomesMitjana}Cap partida en aquest període.{:else}{k.w} G · {k.l} P{k.t ? ` · ${k.t} E` : ''}{/if}
	</p>
	{#if k.nomesMitjana}
		<p class="mt-1 px-1 text-[11px] text-slate-500 dark:text-slate-400">
			{k.nomesMitjana} {k.nomesMitjana === 1 ? 'campionat sense partides publicades compta' : 'campionats sense partides publicades compten'} només per a la mitjana.
		</p>
	{/if}
{/snippet}

<!-- Les mateixes tres targetes a Catalunya, Espanya i Internacional; a Catalunya la sèrie màxima filtra les partides. -->
{#snippet targetesIndicadors(k: TargetaKpi, s: TargetaKpi, p: TargetaKpi | null, serieBtn: boolean)}
	{@const mit = (x: TargetaKpi) => (x.mitjana ? x.mitjana.toFixed(3) : '—')}
	{@const pct = (x: TargetaKpi) => (x.w + x.t + x.l ? x.pct + '%' : '—')}
	<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
		<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Històric</div>
		<div class="grid grid-cols-5 gap-2">
			{#each [['Partides', k.n, ''], ['Mitjana', mit(k), ''], ['Sèrie màx', k.sm ?? '—', 'sm'], ['% vict.', pct(k), ''], [k.bestN > 1 ? `Millor mitj. ×${k.bestN}` : 'Millor mitj.', k.best != null ? k.best.toFixed(3) : '—', '']] as [label, val, key]}
				{#if key === 'sm' && serieBtn}
					<!-- L'única xifra que fa alguna cosa: filtra les partides amb la sèrie màxima -->
					<button type="button" onclick={() => (serieFilter = !serieFilter)} aria-pressed={serieFilter} class="min-h-11 rounded-lg py-0.5 text-center underline decoration-dotted underline-offset-4 {serieFilter ? 'ring-2 ring-blue-500' : ''}">
						<div class="font-mono text-base font-bold tabular-nums">{val}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
					</button>
				{:else}
					<div class="py-0.5 text-center">
						<div class="font-mono text-base font-bold tabular-nums">{val}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
					</div>
				{/if}
			{/each}
		</div>
		{@render peuTargeta(k)}
	</div>
	<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
		<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Temporada actual</div>
		<div class="grid grid-cols-4 gap-2">
			{#each [['Partides', s.n], ['Mitjana', mit(s)], ['Sèrie màx', s.sm ?? '—'], ['% vict.', pct(s)]] as [label, val]}
				<div class="text-center">
					<div class="font-mono text-base font-bold tabular-nums">{val}</div>
					<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
				</div>
			{/each}
		</div>
		{@render peuTargeta(s)}
	</div>
	{#if p}
		<div class="mb-4 rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
			<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Temporada anterior</div>
			<div class="grid grid-cols-4 gap-2">
				{#each [['Partides', p.n], ['Mitjana', mit(p)], ['Sèrie màx', p.sm ?? '—'], ['% vict.', pct(p)]] as [label, val]}
					<div class="text-center">
						<div class="font-mono text-base font-bold tabular-nums">{val}</div>
						<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
					</div>
				{/each}
			</div>
			{@render peuTargeta(p)}
		</div>
	{/if}
{/snippet}


<style>
	/* A pantalla la capçalera no es veu, però el lector de pantalla hi troba els
	   noms de les columnes. */
	.print-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
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
			position: static;
			width: auto;
			height: auto;
			overflow: visible;
			clip: auto;
			white-space: normal;
			display: table-header-group !important;
		}
		.print-only tr {
			break-inside: avoid;
			page-break-inside: avoid;
		}
	}
</style>
