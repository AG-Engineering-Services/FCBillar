<script module lang="ts">
	import type { OpenLiveRow } from '$lib/supabase';
	// Cache per divisió: en tornar enrere des d'una fitxa de jugador, la pàgina
	// es repinta a l'instant (contingut complet) i la restauració d'scroll de
	// SvelteKit recupera el punt on era l'usuari sense esperar la xarxa.
	const rowCache = new Map<number, OpenLiveRow>();
	const phaseCache = new Map<number, number>();
</script>

<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { supabase, type OpenLivePhase, type OpenLiveGroup, type OpenLiveMatch, type OpenLiveScore, type OpenLiveClassRow } from '$lib/supabase';

	const id0 = Number($page.params.id);
	let row = $state<OpenLiveRow | null>(rowCache.get(id0) ?? null);
	let loading = $state(rowCache.get(id0) == null);
	let error = $state<string | null>(null);
	let selectedPhase = $state<number | null>(phaseCache.get(id0) ?? null);
	let scores = $state<OpenLiveScore[]>([]);
	let showClassif = $state(false); // pestanya "Classificació" (paral·lela a les fases)
	let timer: ReturnType<typeof setInterval> | null = null;
	let scoresTimer: ReturnType<typeof setInterval> | null = null;

	const divisionId = $derived(Number($page.params.id));
	const payload = $derived(row?.payload_json ?? null);
	const phases = $derived(payload?.phases ?? []);
	// Open PROJECTAT (rànquing inicial, abans del sorteig oficial FCB).
	const projected = $derived(!!payload?.projected);

	// Classificació provisional (jugadors ELIMINATS, per tram segons la fase on cauen),
	// agrupada per ronda i ordenada pel millor lloc. Es va omplint a mesura que cauen.
	const classByRound = $derived.by(() => {
		const m = new Map<string, OpenLiveClassRow[]>();
		for (const r of payload?.classification ?? []) {
			if (!m.has(r.round_label)) m.set(r.round_label, []);
			m.get(r.round_label)!.push(r);
		}
		return [...m.entries()]
			.map(([round, rows]) => ({ round, rows: rows.slice().sort((a, b) => a.position - b.position) }))
			.sort((a, b) => a.rows[0].position - b.rows[0].position);
	});


	// --- Premis per banda de rànquing 3B (recàlcul al navegador) ----------------
	// El payload porta rank3b/prize precalculats amb el DARRER rànquing publicat,
	// però el premi s'ha de calcular amb el rànquing vigent EN EL MOMENT DE LA
	// CONVOCATÒRIA (sovint no és el darrer). L'usuari tria quina seqüència del
	// rànquing de TRES BANDES (modalitat_codi=1) s'aplica i ho recalculem aquí,
	// sense dependre de cap republicació. Només per a opens de 3 bandes.
	const CA_MONTHS = ['Gener','Febrer','Març','Abril','Maig','Juny','Juliol','Agost','Setembre','Octubre','Novembre','Desembre'];
	const is3b = $derived(/TRES\s*BANDES|3\s*BANDES|\b3B\b/i.test(payload?.name ?? ''));
	
	type RankSeq = { num_seq: number; any_pub: number | null; mes_pub: number | null };
	let rankSeqs = $state<RankSeq[]>([]);
	let selectedSeq = $state<number | null>(null);
	let posByFcbId = $state<Map<string, number>>(new Map());
	
	const seqLabel = (s: RankSeq) =>
		s.mes_pub && s.any_pub ? `${CA_MONTHS[(s.mes_pub - 1) % 12]} ${s.any_pub}` : `#${s.num_seq}`;
	const seqKey = (div: number) => `fcb_open_prize_seq_${div}`;
	
	async function loadRankSeqs() {
		const { data } = await supabase
			.from('rankings')
			.select('num_seq, any_pub, mes_pub')
			.eq('modalitat_codi', 1)
			.order('num_seq', { ascending: false });
		rankSeqs = (data ?? []) as RankSeq[];
		if (selectedSeq === null && rankSeqs.length) {
			let stored: number | null = null;
			try {
				const raw = localStorage.getItem(seqKey(divisionId));
				if (raw != null) stored = Number(raw);
			} catch { /* ignore */ }
			// Prioritat: tria desada al navegador > rànquing fixat al publicador
			// (payload.prize_num_seq, el de la convocatòria) > darrer publicat.
			const pinned = payload?.prize_num_seq ?? null;
			selectedSeq =
				stored != null && rankSeqs.some((s) => s.num_seq === stored)
					? stored
					: pinned != null && rankSeqs.some((s) => s.num_seq === pinned)
						? pinned
						: rankSeqs[0].num_seq;
		}
	}
	
	async function loadRankEntries(seq: number) {
		const { data } = await supabase
			.from('ranking_entries')
			.select('player_fcb_id, posicio')
			.eq('modalitat_codi', 1)
			.eq('num_seq', seq);
		const m = new Map<string, number>();
		for (const r of (data ?? []) as { player_fcb_id: string | null; posicio: number | null }[]) {
			if (r.player_fcb_id != null && r.posicio != null) m.set(String(r.player_fcb_id), Number(r.posicio));
		}
		posByFcbId = m;
	}
	
	function onSelectSeq(seq: number) {
		selectedSeq = seq;
		try { localStorage.setItem(seqKey(divisionId), String(seq)); } catch { /* ignore */ }
		loadRankEntries(seq);
	}
	
	// rank3b + premi per banda recalculats per a la seqüència triada (per jugador).
	// Reprodueix la lògica del publicador (cloud_sync._enrich_live_payload): millor
	// classificat (posició més petita) de la banda 61-180 i de la 181+/sense rànquing.
	const prizeByPlayer = $derived.by(() => {
		const out = new Map<string, { rank3b?: number; prize?: string }>();
		if (!is3b || posByFcbId.size === 0) return out;
		const ids = payload?.player_ids ?? {};
		let bestA: { pos: number; name: string } | null = null;
		let bestB: { pos: number; name: string } | null = null;
		for (const r of payload?.classification ?? []) {
			const fid = ids[r.player_name];
			const pos3b = fid != null ? posByFcbId.get(String(fid)) : undefined;
			const entry: { rank3b?: number; prize?: string } = {};
			if (pos3b != null) entry.rank3b = pos3b;
			out.set(r.player_name, entry);
			if (typeof r.position !== 'number') continue;
			if (pos3b != null && pos3b >= 61 && pos3b <= 180) {
				if (bestA === null || r.position < bestA.pos) bestA = { pos: r.position, name: r.player_name };
			} else if (pos3b == null || pos3b >= 181) {
				if (bestB === null || r.position < bestB.pos) bestB = { pos: r.position, name: r.player_name };
			}
		}
		if (bestA) out.get(bestA.name)!.prize = 'Millor 61-180';
		if (bestB) out.get(bestB.name)!.prize = 'Millor 181+';
		return out;
	});
	
	// Valors a mostrar: recalculats si tenim rànquing triat, si no els del payload.
	function effClass(r: OpenLiveClassRow): { rank3b?: number; prize?: string } {
		return is3b && posByFcbId.size ? (prizeByPlayer.get(r.player_name) ?? {}) : { rank3b: r.rank3b, prize: r.prize };
	}

	// Millor sèrie major del torneig (màxim de totes les partides jugades).
	const bestSerie = $derived.by(() => {
		// Premi de millor sèrie: NOMÉS per als jugadors que NO queden entre els 8
		// primers classificats (els llocs 1-8 ja tenen premi propi).
		const top8 = new Set(
			(payload?.classification ?? [])
				.filter((r) => r.position <= 8)
				.map((r) => canonName(r.player_name))
		);
		let best = 0;
		const who: string[] = [];
		const consider = (name: string | null | undefined, sm: number) => {
			if (!name || !sm) return;
			if (top8.has(canonName(name))) return; // fora els 8 millors classificats
			if (sm > best) { best = sm; who.length = 0; who.push(name); }
			else if (sm === best && !who.includes(name)) who.push(name);
		};
		for (const ph of phases) {
			for (const g of ph.groups) for (const mm of g.matches) {
				if (!mm.is_played) continue;
				consider(mm.player_a, mm.serie_major_a);
				consider(mm.player_b, mm.serie_major_b);
			}
			for (const mm of ph.ko_matches) {
				if (!mm.is_played) continue;
				consider(mm.player_a, mm.serie_major_a);
				consider(mm.player_b, mm.serie_major_b);
			}
		}
		return best > 0 ? { sm: best, players: who } : null;
	});

	// Marcadors en viu (OCR) per grup. Normalitzem l'etiqueta (de vegades "T",
	// de vegades "Grup T") perquè casi amb el grup de la classificació.
	const normGroup = (s: string | null) => (s ?? '').replace(/grup\s*/i, '').toUpperCase().trim();
	// Només marcadors FRESCS: si fa més de 12 min que no es refresquen, la partida
	// pot haver acabat o estar en pausa → no mostrem un valor potser obsolet.
	const FRESH_MS = 12 * 60 * 1000;

	// Un marcador OCR és OBSOLET si, segons el payload oficial, ja no hi pot haver
	// partida en joc en aquell grup: el grup ja està tancat (totes les partides
	// jugades) o el mateix emparellament ja consta com a partida disputada. Passa
	// quan el worker d'OCR deixa el marcador congelat (el stream continua amb una
	// altra taula o s'atura sense que en detecti el final). Sense aquest filtre un
	// grup acabat surt com a "en joc" tot i que ja no s'hi juga res.
	function scoreIsStale(sc: OpenLiveScore): boolean {
		if (sc.finished) return true;
		const gk = normGroup(sc.group_label);
		const pair = [canonName(sc.player_a), canonName(sc.player_b)].sort().join('|');
		for (const ph of phases) {
			for (const g of ph.groups) {
				if (normGroup(g.label) !== gk) continue;
				if (groupClosed(g)) return true;
				for (const m of g.matches) {
					if (m.is_played && [canonName(m.player_a), canonName(m.player_b)].sort().join('|') === pair)
						return true;
				}
			}
		}
		return false;
	}

	// Marcadors EN VIU vàlids: frescos i encara coherents amb el payload oficial.
	const liveScores = $derived(
		scores.filter((s) => Date.now() - new Date(s.captured_at).getTime() < FRESH_MS && !scoreIsStale(s))
	);
	function liveForGroup(label: string): OpenLiveScore[] {
		const k = normGroup(label);
		return liveScores.filter((s) => normGroup(s.group_label) === k);
	}

	// Recorda la fase seleccionada per divisió (per restaurar-la en tornar enrere).
	$effect(() => {
		if (selectedPhase !== null) phaseCache.set(divisionId, selectedPhase);
	});

	function playerHref(name: string): string | null {
		const id = payload?.player_ids?.[name];
		return id ? `/jugador/${id}` : null;
	}

	// Marcadors en viu (OCR): taula minúscula, és el que canvia més sovint → es
	// refresca tot sol cada 30 s (independent del payload pesat de la federació).
	function loadScores() {
		supabase
			.from('open_live_scores')
			.select('*')
			.eq('fcb_division_id', divisionId)
			.then(({ data }) => (scores = (data ?? []) as OpenLiveScore[]));
	}

	async function load() {
		const { data, error: e } = await supabase
			.from('open_live')
			.select('*')
			.eq('fcb_division_id', divisionId)
			.maybeSingle();
		if (e) {
			error = e.message;
		} else if (!data) {
			error = 'Aquest Open ja no està en curs.';
			row = null;
			rowCache.delete(divisionId);
		} else {
			row = data as OpenLiveRow;
			rowCache.set(divisionId, row);
			error = null;
			if (selectedPhase === null) {
				// Obre a la primera fase INCOMPLETA (encara en joc), no a una de ja
				// tancada. Si totes estan acabades, mostra l'última.
				const ph = row.payload_json.phases ?? [];
				const firstIncomplete = ph.findIndex((p) => phaseStatus(p) !== 'done');
				selectedPhase = firstIncomplete >= 0 ? firstIncomplete : Math.max(0, ph.length - 1);
			}
			// Premis 3B: carrega les seqüències del rànquing i les posicions del mes triat.
			const nm3b = (row.payload_json?.name ?? '').toUpperCase();
			if (/TRES\s*BANDES|3\s*BANDES|3B/.test(nm3b)) {
				if (!rankSeqs.length) await loadRankSeqs();
				if (selectedSeq != null && posByFcbId.size === 0) await loadRankEntries(selectedSeq);
			}
		}
		// Marcadors en viu (OCR) — no bloqueja; es refresca a cada poll.
		loadScores();
		loading = false;
	}

	onMount(() => {
		load();
		// Payload de la federació (pesat, canvia lent): cada 90 s.
		timer = setInterval(() => {
			if (document.visibilityState === 'visible') load();
		}, 90_000);
		// Marcadors en viu (lleuger, canvia sovint): cada 30 s.
		scoresTimer = setInterval(() => {
			if (document.visibilityState === 'visible') loadScores();
		}, 30_000);
	});
	onDestroy(() => {
		if (timer) clearInterval(timer);
		if (scoresTimer) clearInterval(scoresTimer);
	});

	function agoText(iso: string): string {
		const ms = Date.now() - new Date(iso).getTime();
		const min = Math.floor(ms / 60000);
		if (min < 1) return 'ara mateix';
		if (min < 60) return `fa ${min} min`;
		const h = Math.floor(min / 60);
		return `fa ${h} h`;
	}

	// Horari de grup (opens projectats): "dg 19/07" + etiqueta del tipus de partida.
	const WD = ['dg', 'dl', 'dt', 'dc', 'dj', 'dv', 'ds'];
	function fmtGroupDay(iso: string | null): string {
		if (!iso) return '';
		const [y, m, d] = iso.split('-').map(Number);
		if (!y || !m || !d) return '';
		const wd = WD[new Date(y, m - 1, d).getDay()];
		return `${wd} ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`;
	}
	const MATCH_TYPE: Record<string, string> = { '2-3': '2n·3r', '1-P': '1r·perd', '1-G': '1r·guany' };
	const matchTypeLabel = (t: string) => MATCH_TYPE[t] ?? t;

	const canonName = (s: string | null | undefined) =>
		(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/[^A-Z0-9]/g, '');

	// Un grup està TANCAT (places decidides) quan totes les partides estan jugades,
	// O BÉ —grup de 3 amb un jugador que NO es presenta— quan les partides jugades
	// són totes del MATEIX parell: els 2 presents juguen dos cops i el grup queda
	// tancat amb 2 partides, encara que la federació mantingui n_matches_total=3.
	function groupClosed(g: OpenLiveGroup): boolean {
		if (g.n_matches_total > 0 && g.n_matches_played === g.n_matches_total) return true;
		const played = (g.matches ?? []).filter((m) => m.is_played && m.player_a && m.player_b);
		if (played.length >= 2) {
			const pairs = new Set(played.map((m) => [canonName(m.player_a), canonName(m.player_b)].sort().join('|')));
			if (pairs.size === 1) return true; // totes les jugades són el mateix parell → no-show
		}
		return false;
	}

	function phaseStatus(p: OpenLivePhase): 'done' | 'active' | 'pending' {
		if (p.kind === 'group') {
			const total = p.groups.reduce((a, g) => a + g.n_matches_total, 0);
			const played = p.groups.reduce((a, g) => a + g.n_matches_played, 0);
			if (total === 0 || played === 0) return 'pending';
			return p.groups.every(groupClosed) ? 'done' : 'active';
		}
		if (p.ko_matches.length === 0) return 'pending';
		const played = p.ko_matches.filter((m) => m.is_played).length;
		if (played === 0) return 'pending';
		return played === p.ko_matches.length ? 'done' : 'active';
	}

	// Posició d'un jugador dins el seu grup segons els classificats provisionals
	// (1 = guanyador de grup). Retorna 0 si no hi és.
	function provPos(phase: OpenLivePhase, group: string, name: string): number {
		const q = phase.provisional_qualifiers.find(
			(x) => x.player_name === name && x.group_label === group
		);
		return q?.position_in_group ?? 0;
	}

	// Costat guanyador d'una partida KO jugada: per punts i, si empaten (la FCB
	// no sempre omple la columna PUNTS al KO), per caramboles. null si no jugada
	// o empat real (es resol per observacions, que aquí no pintem).
	function koWinnerSide(m: OpenLiveMatch): 'a' | 'b' | null {
		if (!m.is_played) return null;
		if (m.punts_a !== m.punts_b) return m.punts_a > m.punts_b ? 'a' : 'b';
		if (m.caramboles_a !== m.caramboles_b) return m.caramboles_a > m.caramboles_b ? 'a' : 'b';
		return null;
	}

	// Cognoms (vista de partides en directe): el nom ve "COGNOM1 [COGNOM2], NOM" →
	// mostrem tot el tros abans de la coma (els DOS cognoms, compostos inclosos com
	// "DE LA HOZ") i deixem fora el nom de pila.
	function surnamesOnly(name: string | null | undefined): string {
		if (!name || name === '—') return name ?? '—';
		return (name.includes(',') ? name.split(',')[0] : name).trim() || name;
	}
</script>

<!-- Nom de jugador: enllaç a la fitxa si el podem resoldre, si no text pla. -->
{#snippet player(name: string, cls: string)}
	{@const href = playerHref(name)}
	{#if href}
		<a {href} class="{cls} hover:underline active:underline">{name}</a>
	{:else}
		<span class={cls}>{name}</span>
	{/if}
{/snippet}

<!-- Igual que player() però mostra els dos COGNOMS, sense el nom (partides en directe). -->
{#snippet playerShort(name: string, cls: string)}
	{@const href = playerHref(name)}
	{#if href}
		<a {href} class="{cls} hover:underline active:underline">{surnamesOnly(name)}</a>
	{:else}
		<span class={cls}>{surnamesOnly(name)}</span>
	{/if}
{/snippet}

<!-- Una fila d'emparellament KO. `calc` = aparellament calculat (no publicat per la FCB). -->
{#snippet koMatch(m: OpenLiveMatch, calc: boolean)}
	{@const w = koWinnerSide(m)}
	{@const aCls = m.is_played ? (w === 'a' ? 'font-semibold text-emerald-600 dark:text-emerald-400' : w === 'b' ? 'text-red-600 dark:text-red-400' : '') : ''}
	{@const bCls = m.is_played ? (w === 'b' ? 'font-semibold text-emerald-600 dark:text-emerald-400' : w === 'a' ? 'text-red-600 dark:text-red-400' : '') : ''}
	<li class="border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
		<div class="flex items-center justify-between gap-2 text-sm">
			{#if m.player_a}{@render player(m.player_a, 'min-w-0 flex-1 truncate ' + aCls)}{:else}<span class="min-w-0 flex-1 truncate text-slate-400 dark:text-slate-500">—</span>{/if}
			{#if m.is_played}
				<span class="shrink-0 font-mono text-xs">{m.caramboles_a}–{m.caramboles_b}</span>
			{:else}
				<span class="shrink-0 font-mono text-xs text-slate-300 dark:text-slate-600">vs</span>
			{/if}
			{#if m.player_b}{@render player(m.player_b, 'min-w-0 flex-1 truncate text-right ' + bCls)}{:else}<span class="min-w-0 flex-1 truncate text-right text-slate-400 dark:text-slate-500">—</span>{/if}
		</div>
		{#if m.is_played}
			<div class="mt-0.5 text-center text-[10px] text-slate-400 dark:text-slate-500">{m.entrades} ent.</div>
		{:else}
			<div class="mt-0.5 text-center text-[10px] {calc ? 'text-sky-600 dark:text-sky-400' : 'text-amber-600 dark:text-amber-400'}">{calc ? 'calculat' : 'pendent'}</div>
		{/if}
	</li>
{/snippet}

<a href="/opens" class="mb-3 inline-block text-sm text-slate-400 dark:text-slate-500 active:underline">‹ Opens</a>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
{:else if error}
	<div class="rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-sm text-amber-800 dark:text-amber-300">{error}</div>
{:else if row && payload}
	<div class="mb-3">
		<div class="flex flex-wrap items-center gap-2">
			<h1 class="text-lg font-bold leading-tight">{payload.name}</h1>
			{#if row.modality}
				<span class="shrink-0 rounded bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300">{row.modality}</span>
			{/if}
			{#if projected}
				<span class="shrink-0 rounded bg-amber-100 dark:bg-amber-900/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">Projecció · no oficial</span>
			{:else}
				<span class="shrink-0 rounded bg-emerald-100 dark:bg-emerald-900/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">En directe</span>
			{/if}
		</div>
		<p class="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">
			{#if projected}Sorteig <strong>projectat</strong> · encara no oficial{:else}Actualitzat {agoText(row.captured_at)} · es refresca sol{/if}
		</p>
	</div>

	{#if projected}
		<div class="mb-3 flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-[11px] leading-snug text-amber-800 dark:text-amber-300">
			<span class="mt-0.5 shrink-0">⚠</span>
			<span>
				Quadre <strong>projectat</strong> a partir del rànquing inicial (sembra de
				l'Art. XVIII i fases del reglament){payload?.num_inscriptions ? ` · ${payload.num_inscriptions} inscrits` : ''}.
				<strong>No és el sorteig oficial</strong>: quan la federació el publiqui, aquesta
				pàgina passarà a mostrar el seguiment real. Els grups de cada fase es mostren
				amb la sembra; els guanyadors de fases inferiors i els emparellaments de la
				fase final apareixen com a pendents.
			</span>
		</div>
	{/if}

	{#if bestSerie}
		<div class="mb-3 rounded-xl bg-violet-50 dark:bg-violet-950/40 px-3 py-2 ring-1 ring-violet-200 dark:ring-violet-900/50">
			<div class="flex items-center justify-between gap-2">
				<span class="text-[11px] font-semibold uppercase tracking-wide text-violet-700 dark:text-violet-300" title="Millor sèrie major d'entre els jugadors que no queden entre els 8 primers">Millor sèrie<span class="font-normal normal-case"> (fora top 8)</span></span>
				<span class="shrink-0 font-mono text-lg font-bold leading-none text-violet-700 dark:text-violet-300">{bestSerie.sm}</span>
			</div>
			<div class="mt-1 flex flex-col gap-0.5 text-sm leading-snug">
				{#each bestSerie.players as p}<span class="truncate">{@render player(p, 'font-bold')}</span>{/each}
			</div>
		</div>
	{/if}

	<!-- Selector de fases -->
	<div class="mb-3 flex flex-wrap gap-1.5">
		{#each phases as p, i}
			{@const st = phaseStatus(p)}
			<button
				onclick={() => { selectedPhase = i; showClassif = false; }}
				title={p.projected ? 'Fase projectada des del rànquing inicial: encara no publicada al web de la FCB' : ''}
				class="rounded-lg border px-2.5 py-1 text-xs font-medium {selectedPhase === i && !showClassif ? 'ring-2 ring-slate-400 dark:ring-slate-600' : ''} {p.projected
					? 'border-dashed border-amber-400 dark:border-amber-700 bg-amber-50/70 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400'
					: st === 'done'
						? 'border-emerald-300 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300'
						: st === 'active'
							? 'border-amber-300 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300'
							: 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-slate-400 dark:text-slate-500'}"
			>
				{p.label}
				{p.projected ? '· proj' : st === 'done' ? '✓' : st === 'active' ? '●' : '○'}
			</button>
		{/each}
		{#if classByRound.length}
			<button
				onclick={() => (showClassif = true)}
				class="rounded-lg border px-2.5 py-1 text-xs font-medium {showClassif ? 'ring-2 ring-slate-400 dark:ring-slate-600 ' : ''}border-violet-300 dark:border-violet-900/50 bg-violet-50 dark:bg-violet-950/40 text-violet-700 dark:text-violet-300"
			>
				Classificació
			</button>
		{/if}
	</div>

	{#if showClassif}
		{@render classifView()}
	{:else if selectedPhase !== null && phases[selectedPhase]}
		{@const phase = phases[selectedPhase]}
		{#if phase.projected}
			<div class="mb-3 flex items-start gap-2 rounded-lg border border-dashed border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-[11px] leading-snug text-amber-800 dark:text-amber-300">
				<span class="mt-0.5 shrink-0">⚠</span>
				<span>Fase <strong>projectada</strong> des del rànquing inicial (sembra de l'Art. XVIII, amb els horaris oficials). La federació encara no l'ha publicada al seu web en directe; quan ho faci, aquí es veuran els grups i els resultats reals.</span>
			</div>
		{/if}
		{#if phase.kind === 'group'}
			{@const quals = phase.provisional_qualifiers
				.slice()
				.sort((a, b) => a.position_in_group - b.position_in_group || b.punts - a.punts || b.mitjana - a.mitjana || b.serie_major - a.serie_major || a.player_name.localeCompare(b.player_name))}
			{@const nSeconds = quals.filter((q) => q.position_in_group > 1).length}
			{@const phaseComplete = phase.groups.every(groupClosed)}
			{#if quals.length}
				<div class="mb-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 p-3 ring-1 ring-emerald-200 dark:ring-emerald-900/50">
					<div class="mb-1.5 flex items-center gap-2">
						<span class="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
							Classificats per a la següent ronda ({quals.length}){#if nSeconds} · 1rs + {nSeconds} {nSeconds === 1 ? 'millor 2n' : 'millors 2ns'}{/if}
						</span>
						{#if !phaseComplete}
							<span class="shrink-0 rounded bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">Provisional</span>
						{/if}
					</div>
					<!-- Capçalera de columnes (només PC/tablet) -->
					<div class="hidden items-center gap-2 border-b border-emerald-200/70 dark:border-emerald-900/50 px-1 pb-1 text-[9px] font-semibold uppercase tracking-wider text-emerald-700/70 dark:text-emerald-300 md:flex">
						<span class="w-4 text-right">#</span>
						<span class="w-6">Gr</span>
						<span class="flex-1">Jugador</span>
						<span class="w-8 text-right">PJ</span>
						<span class="w-8 text-right">Pts</span>
						<span class="w-12 text-right">C</span>
						<span class="w-12 text-right">E</span>
						<span class="w-14 text-right">Mitjana</span><span class="w-10 text-right" title="Sèrie major (desempat a igualtat de mitjana)">SM</span>
					</div>
					<ol class="space-y-0.5">
						{#each quals as q, i}
							{@const grp = phase.groups.find((gg) => gg.label === q.group_label)}
							{@const sure = q.position_in_group > 1 || (!!grp && groupClosed(grp))}
							<li class="flex items-center gap-2 text-sm {q.position_in_group > 1 ? '-mx-1 rounded bg-amber-50/70 dark:bg-amber-950/40 px-1' : ''}">
								<span class="w-4 shrink-0 text-right font-mono text-[11px] text-slate-400 dark:text-slate-500">{i + 1}</span>
								<span class="w-6 shrink-0 rounded bg-white/70 dark:bg-slate-900/70 text-center font-mono text-[10px] text-slate-500 dark:text-slate-400">{q.group_label.replace('Grup ', '')}</span>
								<span class="flex min-w-0 flex-1 items-center gap-1">
									{@render player(q.player_name, 'truncate ' + (sure ? 'font-bold' : ''))}
									{#if q.position_in_group > 1}<span class="shrink-0 rounded bg-amber-100 dark:bg-amber-900/40 px-1 text-[9px] font-semibold uppercase text-amber-700 dark:text-amber-300" title="Millor 2n: classificat per omplir la següent ronda">2n</span>{/if}{#if sure}<span class="shrink-0 text-emerald-600 dark:text-emerald-400" title={q.position_in_group > 1 ? 'Classificat (millor 2n, col·locat per la federació)' : 'Classificació assegurada (grup acabat)'}>✓</span>{/if}
								</span>
								<!-- Estadístiques completes: només PC/tablet -->
								<span class="hidden w-8 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400 md:inline">{q.pj ?? 0}</span>
								<span class="hidden w-8 shrink-0 text-right font-mono text-[11px] font-semibold text-slate-700 dark:text-slate-200 md:inline">{q.punts}</span>
								<span class="hidden w-12 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400 md:inline">{q.caramboles ?? 0}</span>
								<span class="hidden w-12 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400 md:inline">{q.entrades ?? 0}</span>
								<span class="w-14 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400">{q.mitjana.toFixed(3)}</span><span class="w-10 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400" title="Sèrie major">{q.serie_major ?? 0}</span>
							</li>
						{/each}
					</ol>
					<p class="mt-1.5 text-[10px] text-slate-400 dark:text-slate-500">Tots els 1rs de grup + els millors 2ns que calguin per omplir la següent ronda. ✓ = plaça assegurada.</p>
				</div>
			{/if}
			{@const liveNow = liveScores.map((sc) => ({ sc, grp: sc.group_label || '—' }))}
			{#if liveNow.length}
				<div class="mb-3 rounded-xl bg-red-50 p-3 ring-1 ring-red-200 dark:bg-red-950/40 dark:ring-red-900/50">
					<div class="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-red-700 dark:text-red-400">
						<span class="relative inline-flex h-1.5 w-1.5"><span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75"></span><span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500"></span></span>
						En joc ara ({liveNow.length})
					</div>
					<ul class="space-y-1">
						{#each liveNow as { sc, grp } (sc.video_id)}
							{@const aW = (sc.car_a ?? 0) > (sc.car_b ?? 0)}
							{@const bW = (sc.car_b ?? 0) > (sc.car_a ?? 0)}
							{@const warm = sc.car_a == null && sc.car_b == null}
							<li class="flex items-center gap-2 text-xs">
								<span class="w-6 shrink-0 rounded bg-white/70 text-center font-mono text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">{grp.replace('Grup ', '')}</span>
								{@render playerShort(sc.player_a ?? '—', 'min-w-0 flex-1 truncate font-bold ' + (aW ? 'text-emerald-600 dark:text-emerald-400' : bW ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
								{#if warm}<span class="shrink-0 rounded bg-amber-100 px-1.5 text-[9px] font-semibold uppercase text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">escalfament</span>{:else}<span class="shrink-0 font-mono font-bold text-slate-700 dark:text-slate-200">{sc.car_a}–{sc.car_b}</span>{/if}
								{@render playerShort(sc.player_b ?? '—', 'min-w-0 flex-1 truncate text-right font-bold ' + (bW ? 'text-emerald-600 dark:text-emerald-400' : aW ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
								{#if sc.entrades}<span class="shrink-0 font-mono text-[10px] text-slate-400 dark:text-slate-500">{sc.entrades}e</span>{/if}
								<a href="https://www.youtube.com/watch?v={sc.video_id}" target="_blank" rel="noopener" title="Veure a YouTube" class="shrink-0 text-red-600 hover:opacity-80 dark:text-red-400"><svg viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor" aria-hidden="true"><path d="M23.5 6.2a3 3 0 0 0-2.11-2.12C21.5 3.55 12 3.55 12 3.55s-9.5 0-11.39.53A3 3 0 0 0 .5 6.2 31.4 31.4 0 0 0 0 12a31.4 31.4 0 0 0 .5 5.8 3 3 0 0 0 2.11 2.12C4.5 20.45 12 20.45 12 20.45s9.5 0 11.39-.53A3 3 0 0 0 23.5 17.8 31.4 31.4 0 0 0 24 12a31.4 31.4 0 0 0-.5-5.8zM9.55 15.57V8.43L15.82 12z"/></svg></a>
							</li>
						{/each}
					</ul>
					<p class="mt-1.5 text-[10px] leading-tight text-red-700/70 dark:text-red-400/70">Lectura automàtica del marcador (OCR): pot portar un cert retard i tenir errors puntuals respecte al resultat real.</p>
				</div>
			{/if}
			<div class="grid gap-2.5 sm:grid-cols-2">
				{#each phase.groups as g (g.label)}
					{@const done = groupClosed(g)}
					{@const played = g.matches.filter((m) => m.is_played)}
					<div class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 {liveForGroup(g.label).length ? 'ring-red-200 dark:ring-red-900/50' : done ? 'ring-emerald-200 dark:ring-emerald-900/50' : 'ring-slate-200 dark:ring-slate-800'}">
						<div class="flex items-center justify-between gap-2 px-3 py-1.5 {done ? 'bg-emerald-50 dark:bg-emerald-950/40' : 'bg-slate-50 dark:bg-slate-800/50'}">
							<span class="text-sm font-semibold">{g.label}</span>
							<span class="text-[11px] {done ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'}">{g.n_matches_played}/{done ? g.n_matches_played : g.n_matches_total}</span>
						</div>
						{#if g.schedule}
							<div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 px-3 pt-1 text-[10px] text-slate-500 dark:text-slate-400">
								{#if g.schedule.date}<span class="font-semibold">{fmtGroupDay(g.schedule.date)}</span>{/if}
								{#if g.schedule.billar}<span class="rounded bg-slate-100 dark:bg-slate-800 px-1 font-medium">Billar {g.schedule.billar}</span>{/if}
								{#each g.schedule.matches as m}
									<span class="tabular-nums"><span class="text-slate-400 dark:text-slate-500">{matchTypeLabel(m.type)}</span> {m.time}</span>
								{/each}
							</div>
						{:else if g.venue}<div class="px-3 pt-1 text-[10px] text-slate-400 dark:text-slate-500">{g.venue}</div>{/if}
						{#if g.standings.length}
							<ol class="px-2 py-1">
								{#each g.standings as s, idx}
									{@const pos = provPos(phase, g.label, s.player_name)}
									<li class="flex items-center gap-2 rounded px-1 py-1 {pos === 1 ? 'bg-emerald-50 dark:bg-emerald-950/40' : pos >= 2 ? 'bg-amber-50/60 dark:bg-amber-950/40' : ''}">
										<span class="w-4 text-center text-xs font-mono {pos === 1 ? 'text-emerald-600 dark:text-emerald-400' : pos >= 2 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-400 dark:text-slate-500'}">{pos === 1 ? '▸' : idx + 1}</span>
										<span class="flex min-w-0 flex-1 items-center gap-1">
											{@render player(s.player_name, 'truncate text-sm' + (s.incoming ? ' text-sky-700 dark:text-sky-300' : ''))}
											{#if s.incoming}<span class="shrink-0 rounded bg-sky-100 dark:bg-sky-900/40 px-1 text-[9px] font-semibold uppercase tracking-wider text-sky-700 dark:text-sky-300" title="Classificat que entra d'una ronda inferior (encara no col·locat oficialment per la FCB)">▸ {s.from_group?.replace('Grup ', '') ?? 'class.'}</span>{/if}
										</span>
										<span class="shrink-0 font-mono text-[11px] text-slate-400 dark:text-slate-500">{s.mitjana.toFixed(3)}</span>
										<span class="w-5 shrink-0 text-right font-mono text-sm font-semibold">{s.punts}</span>
									</li>
								{/each}
							</ol>
						{:else}
							<p class="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">Sense classificació encara.</p>
						{/if}
						{#if liveForGroup(g.label).length}
								<div class="border-t border-red-100 dark:border-red-900/50 px-3 py-2">
									<div class="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-red-600 dark:text-red-400">
										<span class="relative inline-flex h-1.5 w-1.5">
											<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75"></span>
											<span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500"></span>
										</span>
										En joc ara
									</div>
									<ul class="space-y-1.5">
										{#each liveForGroup(g.label) as sc (sc.video_id)}
											{@const aW = (sc.car_a ?? 0) > (sc.car_b ?? 0)}
											{@const bW = (sc.car_b ?? 0) > (sc.car_a ?? 0)}
											<li>
												<div class="flex items-center justify-between gap-2 text-xs">
													{@render playerShort(sc.player_a ?? '—', 'min-w-0 flex-1 truncate font-bold ' + (aW ? 'text-emerald-600 dark:text-emerald-400' : bW ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
													<span class="shrink-0 font-mono font-bold text-slate-700 dark:text-slate-200">{sc.car_a}–{sc.car_b}</span>
													{@render playerShort(sc.player_b ?? '—', 'min-w-0 flex-1 truncate text-right font-bold ' + (bW ? 'text-emerald-600 dark:text-emerald-400' : aW ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
												</div>
												<div class="mt-0.5 flex items-center justify-center gap-2 text-[10px] text-slate-400 dark:text-slate-500">
													{#if sc.entrades}<span>{sc.entrades} ent.</span>{/if}
													<a href="https://www.youtube.com/watch?v={sc.video_id}" target="_blank" rel="noopener" title="Veure a YouTube" class="inline-flex items-center gap-0.5 font-semibold text-red-600 hover:underline active:underline dark:text-red-400">
														<svg viewBox="0 0 24 24" class="h-3.5 w-3.5" fill="currentColor" aria-hidden="true"><path d="M23.5 6.2a3 3 0 0 0-2.11-2.12C21.5 3.55 12 3.55 12 3.55s-9.5 0-11.39.53A3 3 0 0 0 .5 6.2 31.4 31.4 0 0 0 0 12a31.4 31.4 0 0 0 .5 5.8 3 3 0 0 0 2.11 2.12C4.5 20.45 12 20.45 12 20.45s9.5 0 11.39-.53A3 3 0 0 0 23.5 17.8 31.4 31.4 0 0 0 24 12a31.4 31.4 0 0 0-.5-5.8zM9.55 15.57V8.43L15.82 12z"/></svg>
														vídeo
													</a>
												</div>
											</li>
										{/each}
									</ul>
								</div>
							{/if}
							{#if played.length}
							<div class="border-t border-slate-100 dark:border-slate-800 px-3 py-2">
								<div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
									Partides disputades
								</div>
								<ul class="space-y-1.5">
									{#each played as m}
										{@const aWin = m.caramboles_a > m.caramboles_b}
										{@const bWin = m.caramboles_b > m.caramboles_a}
										<li>
											<div class="flex items-center justify-between gap-2 text-xs">
												{@render player(m.player_a, 'min-w-0 flex-1 truncate font-bold ' + (aWin ? 'text-emerald-600 dark:text-emerald-400' : bWin ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
												<span class="shrink-0 font-mono font-bold text-slate-700 dark:text-slate-200">{m.caramboles_a}–{m.caramboles_b}</span>
												{@render player(m.player_b, 'min-w-0 flex-1 truncate text-right font-bold ' + (bWin ? 'text-emerald-600 dark:text-emerald-400' : aWin ? 'text-red-600 dark:text-red-400' : 'text-slate-900 dark:text-slate-100'))}
											</div>
											{#if m.entrades}<div class="text-center text-[10px] text-slate-400 dark:text-slate-500">{m.entrades} ent.</div>{/if}
										</li>
									{/each}
								</ul>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{:else}
			<!-- Fase KO: classificats ordenats + emparellaments oficials i calculats -->
			{@const official = phase.ko_matches}
			{@const calc = phase.provisional_matches ?? []}
			{@const seeds = phase.provisional_players ?? []}
			{#if seeds.length}
				<div class="mb-3 rounded-xl bg-sky-50 dark:bg-sky-950/40 p-3 ring-1 ring-sky-200 dark:ring-sky-900/50">
					<div class="mb-1.5 flex items-center gap-2">
						<span class="text-xs font-semibold uppercase tracking-wide text-sky-700 dark:text-sky-300">Classificats per a aquesta ronda ({seeds.length})</span>
						{#if official.length === 0}<span class="shrink-0 rounded bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">Provisional</span>{/if}
					</div>
					<ol class="space-y-0.5">
						{#each seeds as s, i}
							<li class="flex items-center gap-2 text-sm">
								<span class="w-4 shrink-0 text-right font-mono text-[11px] text-slate-400 dark:text-slate-500">{i + 1}</span>
								<span class="flex min-w-0 flex-1 items-center gap-1">
									{@render player(s.name, 'truncate')}
									{#if s.source === 'reservat'}<span class="shrink-0 rounded bg-violet-100 dark:bg-violet-900/40 px-1 text-[9px] font-semibold uppercase text-violet-700 dark:text-violet-300" title="Cap de sèrie reservat (no juga la prèvia)">res</span>{/if}
								</span>
								{#if s.serie_major}<span class="hidden w-10 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400 sm:inline" title="Sèrie major">{s.serie_major}</span>{/if}
								<span class="w-14 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400" title="Mitjana amb què entra a la ronda">{s.mitjana ? s.mitjana.toFixed(3) : '—'}</span>
							</li>
						{/each}
					</ol>
					<p class="mt-1.5 text-[10px] leading-tight text-slate-400 dark:text-slate-500">Ordre per la mitjana de la ronda anterior (sèrie major com a desempat). Fixa l'aparellament 1-N de sota.</p>
				</div>
			{/if}

			{#if official.length === 0 && calc.length === 0}
				<p class="py-4 text-center text-sm text-slate-400 dark:text-slate-500">Encara no hi ha emparellaments d'aquesta ronda.</p>
			{:else}
				{#if calc.length}
					<p class="mb-1.5 text-[10px] text-sky-600 dark:text-sky-400">{official.length ? 'Oficials + calculats (mentre la federació no publiqui la resta).' : 'Emparellaments calculats: la federació encara no els ha publicat.'}</p>
				{/if}
				<ul class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
					{#each official as m}{@render koMatch(m, false)}{/each}
					{#each calc as m}{@render koMatch(m, true)}{/each}
				</ul>
			{/if}
		{/if}
	{/if}

{/if}

{#snippet classifView()}
	<div class="rounded-xl bg-white dark:bg-slate-900 p-3 ring-1 ring-slate-200 dark:ring-slate-800">
		<div class="mb-2">
			<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-200">Classificació provisional</h2>
			<p class="mt-0.5 text-[10px] leading-tight text-slate-400 dark:text-slate-500">A dalt, els jugadors encara EN JOC: primer els caps de sèrie (reservats) pel rànquing d'opens, després els classificats de la prèvia per ordre de classificació. A sota, els ja eliminats per la ronda on cauen. Tot és provisional (*) fins a la classificació definitiva.</p>
		</div>
		{#if is3b && rankSeqs.length}
			<div class="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
				<label for="prize-seq" class="font-medium text-slate-600 dark:text-slate-300">Rànquing premis:</label>
				<select
					id="prize-seq"
					class="rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-1 text-[11px]"
					bind:value={selectedSeq}
					onchange={() => { if (selectedSeq != null) onSelectSeq(selectedSeq); }}
				>
					{#each rankSeqs as s, i (s.num_seq)}
						<option value={s.num_seq}>{seqLabel(s)}{i === 0 ? ' · darrer' : ''}</option>
					{/each}
				</select>
				<span class="text-slate-400 dark:text-slate-500">premis per banda recalculats al navegador segons el rànquing de la convocatòria</span>
			</div>
		{/if}
		<div class="space-y-3">
			{#each classByRound as tier (tier.round)}
				{@const alive = tier.round === 'EN JOC'}
				{@const lo = tier.rows[0].position}
				{@const hi = tier.rows[tier.rows.length - 1].position}
				<div>
					<div class="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider {alive ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-500 dark:text-slate-400'}">
						<span>{alive ? 'Encara en competició' : tier.round}</span>
						<span class="font-mono font-normal text-slate-400 dark:text-slate-500">llocs {lo === hi ? lo : `${lo}–${hi}`}</span>
						{#if alive}<span class="rounded bg-amber-100 dark:bg-amber-900/40 px-1 text-[9px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">provisional</span>{/if}
					</div>
					<ol class="space-y-0.5">
						{#each tier.rows as r (r.player_name)}
							{@const ec = effClass(r)}
							<li class="flex items-center gap-2 text-sm">
								<span class="w-8 shrink-0 text-right font-mono text-[11px] text-slate-400 dark:text-slate-500">{r.position}{#if r.is_provisional_position}<span class="text-amber-500" title="Posició provisional">*</span>{/if}</span>
								<span class="flex min-w-0 flex-1 items-baseline gap-1 truncate">
									{@render player(r.player_name, (!alive && r.position <= 8 ? 'font-semibold ' : '') + 'truncate')}
									{#if ec.rank3b}<span class="shrink-0 font-mono text-[10px] text-slate-400 dark:text-slate-500" title="Posició al rànquing de 3 bandes">({ec.rank3b})</span>{/if}
								</span>
								{#if ec.prize}<span class="shrink-0 rounded bg-violet-100 dark:bg-violet-900/40 px-1 text-[9px] font-semibold uppercase text-violet-700 dark:text-violet-300" title="Premi especial (opens 3 bandes): millor classificat de la seva banda del rànquing">{ec.prize}</span>{/if}
								{#if !alive && r.position <= 8}<span class="shrink-0 rounded bg-yellow-100 dark:bg-yellow-900/40 px-1 text-[9px] font-semibold uppercase text-yellow-700 dark:text-yellow-300" title="Premi: {r.position === 1 ? '1r' : r.position === 2 ? '2n' : r.position <= 4 ? '3r-4t' : '5è-8è'} classificat">premi</span>{/if}
								<span class="hidden w-14 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400 sm:inline">{r.mitjana ? r.mitjana.toFixed(3) : '—'}</span>
								<span class="w-10 shrink-0 text-right font-mono text-[11px] font-semibold text-slate-700 dark:text-slate-200" title={alive ? 'Punts pendents: encara en competició' : 'Punts de rànquing segons el lloc (reglament dels opens)'}>{alive ? '—' : r.open_points}</span>
							</li>
						{/each}
					</ol>
				</div>
			{/each}
		</div>
		<p class="mt-2 text-[10px] leading-tight text-slate-400 dark:text-slate-500"><span class="text-amber-500">*</span> provisional · (n) = rànquing 3B · <span class="text-violet-600 dark:text-violet-300">premi</span> per posició (1-8) o per banda de rànquing. Punts segons el reglament.</p>
	</div>
{/snippet}
