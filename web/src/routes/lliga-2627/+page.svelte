<script lang="ts">
	// Projecció de la Lliga de Tres Bandes 2026-27. A diferència de la resta de
	// seccions, NO llegeix de Supabase: és una foto derivada de les classificacions
	// oficials 2025-26 + els play-offs de promoció del 4-5 de juliol de 2026, que es
	// regenera amb `python scripts/projeccio_lliga_2627.py --json web/src/lib/data/lliga2627.json`.
	//
	// El JSON només porta la POSICIÓ de cada jugador a la llista única del club; la
	// banda (a quin equip pot jugar) es deriva aquí segons el repartiment triat,
	// perquè n'hi ha dos sobre la taula. Mateixos talls que `ESQUEMES` al generador.
	import { norm } from '$lib/search';
	import projeccio from '$lib/data/lliga2627.json';

	type Jugador = {
		num: number;
		nom: string;
		mitjana: number;
		pos: number | null;
		de_club: string | null;
		retorn: boolean;
		pj: number;
		taxa: number;
		temporades: number;
	};
	type Equip = {
		lletra: string;
		lletra_2526: string;
		unic: boolean;
		divisio: string;
		distancia: number;
		div_2526: string;
		motiu: string | null;
	};
	type Club = { club: string; nom: string; multi: boolean; equips: Equip[]; llista: Jugador[] };
	type EquipDiv = {
		seed: number;
		alineacio: number[];
		p_alineacio: number;
		taules: { num: number; taula: number; p: number }[];
		presencia: { num: number; p: number }[];
		p_1r: number;
		p_2n: number;
		p_penultim: number;
		p_ultim: number;
		pos_mitjana: number;
		club: string;
		nom: string;
		lletra: string;
		lletra_2526: string;
		unic: boolean;
		div_2526: string;
		motiu: string | null;
	};
	type DivData = {
		distancia: number;
		equips: EquipDiv[];
		grups: { lletra: string; seeds: number[] }[];
		permutes: { slot: number; seed_a: number; seed_b: number }[];
		moguts: number[];
	};

	const clubs = projeccio.clubs as Club[];
	const divisions = projeccio.divisions as Record<string, DivData>;
	const DIVS = ['Honor', '1a', '2a', '3a', '4a'];
	const LLETRES = ['A', 'B', 'C', 'D', 'E'];

	type Esquema = 'fcb' | 'opt' | 'alt' | 'prob';
	const ESQUEMES: Record<
		Esquema,
		{ etiqueta: string; talls: number[]; inici: Record<string, number>; rangs: Record<string, string> }
	> = {
		fcb: {
			etiqueta: '3-5-4-4',
			talls: [3, 8, 12, 16],
			inici: { A: 1, B: 5, C: 9, D: 13, E: 17 },
			rangs: { A: '1-3', B: '4-8', C: '9-12', D: '13-16', E: '17+' }
		},
		opt: {
			etiqueta: '4-4-4-4-4',
			talls: [4, 8, 12, 16],
			inici: { A: 1, B: 5, C: 9, D: 13, E: 17 },
			rangs: { A: '1-4', B: '5-8', C: '9-12', D: '13-16', E: '17+' }
		},
		alt: {
			etiqueta: '4-6-6-6',
			talls: [4, 10, 16, 22],
			inici: { A: 1, B: 5, C: 11, D: 17, E: 23 },
			rangs: { A: '1-4', B: '5-10', C: '11-16', D: '17-22', E: '23+' }
		},
		// Mateixes bandes que la norma, però els quatre que juguen no són els de
		// més mitjana sinó els de més presència: l'alineació que de fet es veu.
		prob: {
			etiqueta: 'més probable',
			talls: [3, 8, 12, 16],
			inici: { A: 1, B: 5, C: 9, D: 13, E: 17 },
			rangs: { A: '1-3', B: '4-8', C: '9-12', D: '13-16', E: '17+' }
		}
	};

	let vista = $state<'club' | 'divisio' | 'grups'>('grups');
	let esquema = $state<Esquema>('fcb');
	let selDiv = $state<string | null>(null);
	let q = $state('');

	const clubPerClau = new Map(clubs.map((c) => [c.club, c]));

	/** A quina banda de la llista única cau el jugador nº num. */
	function banda(num: number, esq: Esquema): string {
		const t = ESQUEMES[esq].talls;
		for (let i = 0; i < t.length; i++) if (num <= t[i]) return LLETRES[i];
		return 'E';
	}
	/** Els quatre que formen l'alineació d'un equip en jornada regular. */
	function referents(llista: Jugador[], lletra: string, esq: Esquema): Jugador[] {
		const s = ESQUEMES[esq].inici[lletra];
		return llista.filter((p) => p.num >= s && p.num <= s + 3);
	}
	/** Tota la banda d'un equip: titulars i suplents. */
	function bandaDe(llista: Jugador[], lletra: string, esq: Esquema): Jugador[] {
		return llista.filter((p) => banda(p.num, esq) === lletra);
	}
	/** Posició en què arrenca la banda d'una lletra (no la dels titulars: amb
	 *  3-5-4-4 la banda del B comença al nº 4, que és qui fa la quarta taula de l'A). */
	function bandaInici(lletra: string, esq: Esquema): number {
		const i = LLETRES.indexOf(lletra);
		return i === 0 ? 1 : ESQUEMES[esq].talls[i - 1] + 1;
	}
	/** La plantilla que la fitxa d'equip ensenya: tota la banda, amb els quatre
	 *  titulars marcats. Amb 3-5-4-4 l'A només té tres jugadors de banda, així que
	 *  s'hi afegeix el nº 4, que és qui n'ocupa la quarta taula.
	 *
	 *  A l'ÚLTIM equip del club s'hi posa tota la cua de la llista, encara que
	 *  passi dels sis: la seva banda és oberta i qui hi hagi a sota només pot
	 *  jugar amb ell o fer de suplent dels de sobre. */
	function plantilla(
		llista: Jugador[],
		lletra: string,
		esq: Esquema,
		ultim = false
	): { p: Jugador; titular: boolean }[] {
		const tit = referents(llista, lletra, esq);
		const nums = new Set(tit.map((p) => p.num));
		const membres = ultim
			? llista.filter((p) => p.num >= bandaInici(lletra, esq))
			: bandaDe(llista, lletra, esq);
		const vistos = new Set<number>();
		return [...tit, ...membres]
			.filter((p) => (vistos.has(p.num) ? false : vistos.add(p.num)))
			.sort((a, b) => a.num - b.num)
			.map((p) => ({ p, titular: nums.has(p.num) }));
	}
	/** L'alineació habitual més probable: els quatre de la plantilla amb més
	 *  presència, que no sempre són els quatre de més mitjana. Hi ha jugadors
	 *  forts que amb prou feines juguen, i és el que decanta molts equips. */
	const habituals = (c: Club, lletra: string) => new Set(alineacio(c, lletra).map((p) => p.num));
	/** L'alineació més probable de cada equip surt de la simulació: és la
	 *  combinació de quatre que més es repeteix en les 10.000 temporades, no els
	 *  quatre de més mitjana ni els quatre més presents per separat. Al motor,
	 *  cada jornada es sorteja qui està disponible i els equips trien per ordre de
	 *  categoria, o sigui que ja hi va inclòs que un jugador no juga amb dos
	 *  equips el mateix dia i que quan l'A puja algú, el B se'n ressent. */
	const alineacioEquip = new Map<
		string,
		{ nums: number[]; p: number; taules: { num: number; taula: number; p: number }[] }
	>();
	for (const d of DIVS) {
		for (const e of divisions[d].equips) {
			alineacioEquip.set(`${e.club}|${e.lletra}`, {
				nums: e.alineacio,
				p: e.p_alineacio,
				taules: e.taules
			});
		}
	}
	const taulesEquip = (c: Club, lletra: string) =>
		alineacioEquip.get(`${c.club}|${lletra}`)?.taules ?? [];
	function alineacio(c: Club, lletra: string): Jugador[] {
		const a = alineacioEquip.get(`${c.club}|${lletra}`);
		if (!a) return [];
		const per = new Map(c.llista.map((p) => [p.num, p]));
		return a.nums
			.map((n) => per.get(n))
			.filter((p): p is Jugador => !!p)
			.sort((x, y) => y.mitjana - x.mitjana);
	}
	const pAlineacio = (c: Club, lletra: string) =>
		alineacioEquip.get(`${c.club}|${lletra}`)?.p ?? 0;
	const esUltim = (c: Club, lletra: string) => c.equips[c.equips.length - 1].lletra === lletra;
	/** Els quatre que juguen. Amb el repartiment «més probable» són els de més
	 *  presència de la plantilla; amb la resta, els de més mitjana de la banda. */
	function titulars(c: Club, lletra: string): Jugador[] {
		if (esquema !== 'prob') return referents(c.llista, lletra, esquema);
		return alineacio(c, lletra);
	}
	const mitjanaEquip = (c: Club, lletra: string) => {
		const t = titulars(c, lletra);
		return t.length ? t.reduce((a, p) => a + p.mitjana, 0) / t.length : 0;
	};

	const matchJugador = (llista: Jugador[]) => llista.some((p) => norm(p.nom).includes(norm(q.trim())));

	/** Cada divisió en l'ordre de sembra oficial, amb el grup que li toca a cada
	 *  equip (serpentí + permutes, calculats al generador). Base de les tres vistes. */
	const ordenades = $derived.by(() =>
		DIVS.map((d) => {
			const D = divisions[d];
			const grupPerSeed = new Map<number, string>();
			for (const g of D.grups) for (const s of g.seeds) grupPerSeed.set(s, g.lletra);
			const moguts = new Set(D.moguts);
			// El favorit de cada plaça és, dins del seu grup, qui té més probabilitat
			// de quedar-hi: 1r puja, 2n juga la promoció, penúltim la permanència i
			// últim baixa.
			// Es marquen quatre equips DIFERENTS per grup: si el mateix equip és el
			// favorit de dues places, la segona va al següent candidat.
			const fav = new Map<number, string>();
			for (const g of D.grups) {
				const eq = g.seeds.map((sd) => D.equips.find((x) => x.seed === sd)!);
				for (const camp of ['p_1r', 'p_2n', 'p_penultim', 'p_ultim'] as const) {
					const lliures = eq.filter((x) => !fav.has(x.seed));
					if (!lliures.length) break;
					fav.set(lliures.reduce((a, b) => (b[camp] > a[camp] ? b : a)).seed, camp);
				}
			}
			return {
				nom: d,
				distancia: D.distancia,
				permutes: D.permutes,
				equips: D.equips.map((e) => {
					const club = clubPerClau.get(e.club)!;
					return {
						e,
						club,
						pos: e.seed,
						grup: grupPerSeed.get(e.seed) ?? 'A',
						mogut: moguts.has(e.seed),
						fav: fav.get(e.seed) ?? null,
						tit: titulars(club, e.lletra),
						plantilla: plantilla(club.llista, e.lletra, esquema, esUltim(club, e.lletra)),
						mit: mitjanaEquip(club, e.lletra)
					};
				})
			};
		})
	);

	const divisionsFiltrades = $derived.by(() => {
		const t = q.trim();
		return ordenades
			.filter((d) => selDiv === null || selDiv === d.nom)
			.map((d) => ({
				...d,
				total: d.equips.length,
				visibles: d.equips.filter(
					(x) =>
						!t || norm(x.e.nom).includes(norm(t)) || x.tit.some((p) => norm(p.nom).includes(norm(t)))
				)
			}));
	});

	const grupsFiltrats = $derived.by(() => {
		const t = q.trim();
		return ordenades
			.filter((d) => selDiv === null || selDiv === d.nom)
			.map((d) => ({
				nom: d.nom,
				distancia: d.distancia,
				permutes: d.permutes,
				grups: (['A', 'B'] as const).map((g) => {
					const eq = d.equips.filter((x) => x.grup === g);
					return {
						g,
						equips: eq,
						mitjana: eq.length ? eq.reduce((a, x) => a + x.mit, 0) / eq.length : 0
					};
				}),
				coincideix:
					!t ||
					d.equips.some(
						(x) =>
							norm(x.e.nom).includes(norm(t)) || x.tit.some((p) => norm(p.nom).includes(norm(t)))
					)
			}))
			.filter((d) => d.coincideix);
	});

	const totalEquips = $derived(divisionsFiltrades.reduce((n, d) => n + d.visibles.length, 0));

	const clubsFiltrats = $derived.by(() => {
		const t = q.trim();
		return clubs.filter(
			(c) =>
				(selDiv === null || c.equips.some((e) => e.divisio === selDiv)) &&
				(!t || norm(c.nom).includes(norm(t)) || matchJugador(c.llista))
		);
	});

	const cognom = (n: string) => (n.includes(',') ? n.slice(0, n.indexOf(',')) : n);
	const nomPropi = (n: string) => (n.includes(',') ? n.slice(n.indexOf(',') + 1).trim() : '');
	const etiquetaDiv = (d: string) => (d === 'Honor' ? "Divisió d'Honor" : `${d} divisió`);
	const nomEquip = (e: EquipDiv) => (e.unic ? e.nom : `${e.nom} ${e.lletra}`);
	function llistaLletres(ls: string[]): string {
		if (!ls.length) return '';
		if (ls.length === 1) return `l'${ls[0]}`;
		return `${ls.slice(0, -1).join(', ')} i ${ls[ls.length - 1]}`;
	}
	const puja = (m: string | null) => !!m && m.startsWith('puja');
	const baixa = (m: string | null) => !!m && m.startsWith('baixa');
	const esSwing = (p: Jugador, c: Club) => esquema === 'fcb' && p.num === 4 && c.multi;
	const FAV: Record<string, { text: string; classe: string }> = {
		p_1r: { text: '1r', classe: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300' },
		p_2n: { text: '2n', classe: 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-300' },
		p_penultim: { text: 'penúlt.', classe: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300' },
		p_ultim: { text: 'últim', classe: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300' }
	};
	const pct = (v: number) => `${Math.round(v * 100)}%`;

	/** Files de la llista d'un club, amb la capçalera de banda quan canvia. */
	function bandes(c: Club) {
		const lletres = c.equips.map((e) => e.lletra);
		const files: { cap?: { b: string; titular: boolean; reserva_de: string[] }; p: Jugador }[] = [];
		let vist: string | null = null;
		for (const p of c.llista) {
			const b = banda(p.num, esquema);
			let cap;
			if (b !== vist) {
				vist = b;
				const titular = lletres.includes(b);
				cap = { b, titular, reserva_de: titular ? lletres.filter((x) => x < b) : lletres.slice() };
			}
			files.push({ cap, p });
		}
		return files;
	}
</script>

<svelte:head><title>Lliga 26/27 · FCBillar</title></svelte:head>

<h1 class="mb-1 text-lg font-bold tracking-tight md:text-xl">Lliga de Tres Bandes 2026-27</h1>
<p class="mb-3 text-sm leading-snug text-slate-500 dark:text-slate-400">
	Projecció a partir de les classificacions oficials del 2025-26 i dels play-offs de promoció del 4 i
	5 de juliol de 2026. Cada club inscriu una sola llista de jugadors, ordenada per rànquing, i les
	bandes diuen a quin equip pot jugar cadascú.
</p>

<!-- vista i repartiment: dos controls independents, perquè el repartiment val
     per a totes tres vistes -->
<div class="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
	<div class="inline-flex rounded-lg bg-slate-100 p-0.5 text-sm dark:bg-slate-800">
		{#each [{ k: 'club', l: 'Per club' }, { k: 'divisio', l: 'Per divisió' }, { k: 'grups', l: 'Per grups' }] as o}
			<button
				type="button"
				onclick={() => (vista = o.k as typeof vista)}
				class="rounded-md px-3 py-1 font-medium {vista === o.k
					? 'bg-white shadow-sm dark:bg-slate-700'
					: 'text-slate-500 dark:text-slate-400'}">{o.l}</button
			>
		{/each}
	</div>
	<div class="inline-flex items-center gap-1.5">
		<span class="text-xs text-slate-400 dark:text-slate-500">bandes</span>
		<div class="inline-flex rounded-lg bg-slate-100 p-0.5 text-sm dark:bg-slate-800">
			{#each ['fcb', 'opt', 'alt', 'prob'] as k}
				<button
					type="button"
					onclick={() => (esquema = k as Esquema)}
					class="rounded-md px-2.5 py-1 text-xs {k === 'prob' ? '' : 'font-mono'} {esquema === k
						? 'bg-white shadow-sm dark:bg-slate-700'
						: 'text-slate-500 dark:text-slate-400'}">{ESQUEMES[k as Esquema].etiqueta}</button
				>
			{/each}
		</div>
	</div>
</div>

<!-- filtre de divisió -->
<div class="-mx-3 mb-2 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
	<button
		type="button"
		onclick={() => (selDiv = null)}
		class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium {selDiv === null
			? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
			: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}">Totes</button
	>
	{#each DIVS as d}
		<button
			type="button"
			onclick={() => (selDiv = d)}
			class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium {selDiv === d
				? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
				: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}">{d}</button
		>
	{/each}
</div>

<input
	bind:value={q}
	placeholder={vista === 'club' ? 'Cerca club o jugador…' : 'Cerca equip o jugador…'}
	class="mb-3 w-full rounded-lg border-slate-300 bg-white px-3 py-2 text-sm shadow-sm dark:border-slate-700 dark:bg-slate-900"
/>

{#if vista === 'grups'}
	{#if grupsFiltrats.length === 0}
		<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Cap grup coincideix.</p>
	{/if}
	{#each grupsFiltrats as d}
		<section class="mb-4">
			<header class="mb-2 flex flex-wrap items-baseline gap-x-2">
				<h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
					{etiquetaDiv(d.nom)}
				</h2>
				<span class="text-[11px] text-slate-400 dark:text-slate-500">
					serpentí 1-4-5-8… · {d.permutes.length === 0
						? 'cap permuta'
						: d.permutes.length === 1
							? '1 permuta'
							: `${d.permutes.length} permutes`} · desequilibri {Math.abs(
						d.grups[0].mitjana - d.grups[1].mitjana
					).toFixed(3)}
				</span>
			</header>
			<div class="grid gap-3 sm:grid-cols-2">
				{#each d.grups as g}
					<div
						class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800"
					>
						<header
							class="flex items-baseline gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/50"
						>
							<span class="text-sm font-bold">Grup {g.g}</span>
							<span class="text-[11px] text-slate-400 dark:text-slate-500">{g.equips.length} equips</span>
							<span class="ml-auto font-mono text-sm font-bold tabular-nums">{g.mitjana.toFixed(3)}</span>
						</header>
						<ul class="divide-y divide-slate-100 dark:divide-slate-800">
							{#each g.equips as x}
								{@const hab = habituals(x.club, x.e.lletra)}
								<li class="px-3 py-1.5">
									<div class="flex items-baseline gap-2">
										<span
											class="w-5 shrink-0 text-right font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500"
											>{x.pos}</span
										>
										<span class="min-w-0 flex-1 truncate text-sm font-medium">
											{nomEquip(x.e)}{#if x.fav}<span
													class="ml-1 rounded px-1 py-0.5 text-[10px] font-bold {FAV[x.fav].classe}"
													title="favorit per quedar {FAV[x.fav].text} del grup"
													>{FAV[x.fav].text} {pct(x.e[x.fav as keyof EquipDiv] as number)}</span
												>{/if}{#if puja(x.e.motiu)}<span
													class="ml-1 text-[11px] text-emerald-600 dark:text-emerald-400">▲</span
												>{:else if baixa(x.e.motiu)}<span class="ml-1 text-[11px] text-red-600 dark:text-red-400"
													>▼</span
												>{/if}{#if x.mogut}<span
													class="ml-1 text-[10px] font-semibold text-amber-600 dark:text-amber-400"
													title="permutat amb l'equip del mateix slot de l'altre grup per no coincidir amb un altre equip del seu club"
													>⇄ permutat</span
												>{/if}
										</span>
										<span class="shrink-0 font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400"
											>{x.mit.toFixed(3)}</span
										>
									</div>
									<p class="ml-7 text-[11px] leading-snug">
										{#each x.plantilla as f, i}<span
												class={hab.has(f.p.num)
													? 'font-semibold text-slate-700 dark:text-slate-200'
													: f.titular
														? 'text-slate-500 dark:text-slate-400'
														: 'text-slate-400 dark:text-slate-500'}
												title={hab.has(f.p.num)
													? `alineació habitual · ${pct(f.p.taxa)} de presència`
													: `${pct(f.p.taxa)} de presència`}
												>{i > 0 ? ' · ' : ''}<span class="font-mono">{f.p.num}</span>&nbsp;{cognom(f.p.nom)}</span
											>{/each}
									</p>
								</li>
							{/each}
						</ul>
					</div>
				{/each}
			</div>
			{#if d.permutes.length}
				<p class="mt-1.5 text-[11px] leading-snug text-slate-400 dark:text-slate-500">
					<span class="font-semibold text-amber-600 dark:text-amber-400">⇄ permutes</span>
					{#each d.permutes as p, i}{i > 0 ? ' · ' : ' '}slot {p.slot}: caps de sèrie
						<span class="font-mono">{p.seed_a}</span> i <span class="font-mono">{p.seed_b}</span>{/each}
				</p>
			{/if}
		</section>
	{/each}
{:else if vista === 'divisio'}
	{#if totalEquips === 0}
		<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Cap equip coincideix.</p>
	{/if}
	{#each divisionsFiltrades as d}
		{#if d.visibles.length}
			<section
				class="mb-4 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800"
			>
				<header
					class="flex items-baseline gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/50"
				>
					<span class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
						>{etiquetaDiv(d.nom)}</span
					>
					<span class="text-[11px] text-slate-400 dark:text-slate-500"
						>{d.total} equips · partides a {d.distancia} caramboles</span
					>
				</header>
				<ul class="divide-y divide-slate-100 dark:divide-slate-800">
					{#each d.visibles as x}
						{@const hab = habituals(x.club, x.e.lletra)}
						<li class="px-3 py-2.5">
							<div class="flex items-baseline gap-2">
								<span
									class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums text-slate-400 dark:text-slate-500"
									>{x.pos}</span
								>
								<span class="min-w-0 flex-1 truncate text-sm font-semibold"
									>{x.e.nom}{#if !x.e.unic}&nbsp;{x.e.lletra}{/if}{#if !x.e.unic && x.e.lletra_2526 && x.e.lletra_2526 !== x.e.lletra}<span
											class="ml-1 text-[11px] font-normal text-amber-600 dark:text-amber-400"
											>era la {x.e.lletra_2526}</span
										>{/if}</span
								>
								<span
									class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] font-bold dark:bg-slate-800"
									>grup {x.grup}</span
								>
								{#if x.fav}
									<span
										class="shrink-0 rounded px-1 py-0.5 text-[10px] font-bold {FAV[x.fav].classe}"
										title="favorit per quedar {FAV[x.fav].text} del grup"
										>{FAV[x.fav].text} {pct(x.e[x.fav as keyof EquipDiv] as number)}</span
									>
								{/if}
								{#if puja(x.e.motiu)}
									<span class="shrink-0 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400"
										>▲ {x.e.div_2526}</span
									>
								{:else if baixa(x.e.motiu)}
									<span class="shrink-0 text-[11px] font-semibold text-red-600 dark:text-red-400"
										>▼ {x.e.div_2526}</span
									>
								{/if}
								<span class="w-12 shrink-0 text-right font-mono text-sm font-bold tabular-nums"
									>{x.mit.toFixed(3)}</span
								>
							</div>
							<p class="ml-7 text-[11px] text-slate-400 dark:text-slate-500">
								banda <span class="font-mono">{ESQUEMES[esquema].rangs[x.e.lletra]}</span> de la llista
								del club{#if x.e.motiu}&nbsp;· {x.e.motiu}{/if}
							</p>
							{#if esquema !== 'prob'}
							<p class="ml-7 mt-0.5 text-[11px] leading-snug">
								<span class="font-semibold text-slate-600 dark:text-slate-300"
									>alineació més probable</span
								><span class="text-slate-400 dark:text-slate-500"
									>&nbsp;({pct(pAlineacio(x.club, x.e.lletra))} de les jornades)</span
								>
								{#each taulesEquip(x.club, x.e.lletra) as t}{@const j = x.club.llista.find(
										(p) => p.num === t.num
									)}<span class="text-slate-500 dark:text-slate-400"
										>{t.taula > 1 ? ' · ' : ' '}<span class="font-mono">{t.taula}</span
										>&nbsp;{j ? cognom(j.nom) : t.num}<span class="text-slate-400 dark:text-slate-500"
											>&nbsp;{pct(t.p)}</span
										></span
									>{/each}
							</p>
							{/if}
							<ol class="ml-7 mt-1.5 space-y-0.5">
								{#each x.plantilla as f}
									<li class="flex items-baseline gap-2 {f.titular ? '' : 'opacity-60'}">
										<span
											class="w-3 shrink-0 text-center text-[10px] leading-none {hab.has(f.p.num)
												? 'text-slate-900 dark:text-slate-100'
												: 'text-transparent'}"
											title={hab.has(f.p.num) ? "de l'alineació habitual més probable" : ''}>●</span
										>
										<span
											class="w-4 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-400 dark:text-slate-500"
											>{f.p.num}</span
										>
										<span class="min-w-0 flex-1 truncate text-xs">
											<span class={f.titular ? 'font-medium' : ''}>{cognom(f.p.nom)}</span><span
												class="text-slate-500 dark:text-slate-400">, {nomPropi(f.p.nom)}</span
											>
											{#if !f.titular}<span class="ml-1 text-[10px] text-slate-400 dark:text-slate-500"
													>suplent</span
												>{/if}
											{#if f.p.de_club}<span
													class="ml-1 text-[10px] font-semibold text-sky-600 dark:text-sky-400">⇄ {f.p.de_club}</span
												>{:else if f.p.retorn}<span
													class="ml-1 text-[10px] font-semibold text-sky-600 dark:text-sky-400">↩ es reincorpora</span
												>{:else if esSwing(f.p, x.club)}<span
													class="ml-1 text-[10px] text-amber-600 dark:text-amber-400"
													>{f.titular ? 'nº4' : "nº4 · juga amb l'A"}</span
												>{/if}
										</span>
										<span class="shrink-0 font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400"
											>{f.p.mitjana.toFixed(3)}</span
										>
										<span
											class="w-8 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-400 dark:text-slate-500"
											title="presència: jornades jugades les dues últimes temporades">{pct(f.p.taxa)}</span
										>
									</li>
								{/each}
							</ol>
						</li>
					{/each}
				</ul>
			</section>
		{/if}
	{/each}
{:else}
	{#if clubsFiltrats.length === 0}
		<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Cap club coincideix.</p>
	{/if}
	{#each clubsFiltrats as c}
		<section
			class="mb-4 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800"
		>
			<header class="border-b border-slate-100 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/50">
				<h2 class="text-sm font-bold">{c.nom}</h2>
				<div class="mt-1.5 flex flex-wrap gap-1.5">
					{#each c.equips as e}
						<span
							class="inline-flex items-baseline gap-1 rounded-md border px-2 py-0.5 text-[11px] {puja(e.motiu)
								? 'border-emerald-300 dark:border-emerald-800'
								: baixa(e.motiu)
									? 'border-red-300 dark:border-red-900'
									: 'border-slate-200 dark:border-slate-700'}"
							title={e.motiu ?? `es manté a ${e.divisio}`}
						>
							{#if puja(e.motiu)}<span class="text-emerald-600 dark:text-emerald-400">▲</span>{/if}
							{#if baixa(e.motiu)}<span class="text-red-600 dark:text-red-400">▼</span>{/if}
							<b class="font-mono font-bold">{e.unic ? 'Únic' : `Equip ${e.lletra}`}</b>
							<span class="text-slate-500 dark:text-slate-400"
								>{e.divisio === 'Honor' ? 'Honor' : `${e.divisio} div.`} · {e.distancia} car.</span
							>
							{#if !e.unic && e.lletra_2526 && e.lletra_2526 !== e.lletra}
								<span class="text-amber-600 dark:text-amber-400">era la {e.lletra_2526}</span>
							{/if}
						</span>
					{/each}
				</div>
			</header>

			{#each bandes(c) as fila}
				{#if fila.cap}
					<div class="flex items-baseline gap-2 border-t border-slate-100 px-3 py-1.5 dark:border-slate-800">
						<span
							class="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold tabular-nums {fila.cap.titular
								? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
								: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300'}"
							>{ESQUEMES[esquema].rangs[fila.cap.b]}</span
						>
						{#if fila.cap.titular}
							<span class="text-xs font-semibold"
								>{c.equips.length === 1 && fila.cap.b === 'A' ? 'Equip únic' : `Equip ${fila.cap.b}`}</span
							>
							{#if fila.cap.reserva_de.length}
								<span class="text-[11px] text-slate-400 dark:text-slate-500"
									>i suplents de {llistaLletres(fila.cap.reserva_de)}</span
								>
							{/if}
						{:else}
							<span class="text-xs font-semibold text-slate-500 dark:text-slate-400">Suplents</span>
							<span class="text-[11px] text-slate-400 dark:text-slate-500"
								>de {llistaLletres(fila.cap.reserva_de)}</span
							>
						{/if}
					</div>
				{/if}
				<div class="flex items-baseline gap-2 px-3 py-1">
					<span class="w-6 shrink-0 text-right font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500"
						>{fila.p.num}</span
					>
					<span class="min-w-0 flex-1">
						<span class="text-sm font-medium">{cognom(fila.p.nom)}</span><span
							class="text-sm text-slate-500 dark:text-slate-400">, {nomPropi(fila.p.nom)}</span
						>
						{#if fila.p.de_club}
							<span class="block text-[10px] font-semibold text-sky-600 dark:text-sky-400"
								>⇄ ve de {fila.p.de_club}</span
							>
						{:else if fila.p.retorn}
							<span class="block text-[10px] font-semibold text-sky-600 dark:text-sky-400"
								>↩ es reincorpora: no va jugar la lliga 2025-26</span
							>
						{:else if esSwing(fila.p, c)}
							<span class="block text-[10px] text-amber-600 dark:text-amber-400"
								>nº 4: mínim 6 jornades amb el B per jugar-hi les decisives</span
							>
						{/if}
					</span>
					<span class="shrink-0 text-right font-mono text-xs tabular-nums">
						{fila.p.mitjana.toFixed(3)}
						<span class="block text-[10px] text-slate-400 dark:text-slate-500"
							>{fila.p.pos ? `#${fila.p.pos}` : 's/r'}</span
						>
					</span>
					<span
						class="w-10 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400"
						title={fila.p.temporades
							? `presència en ${fila.p.temporades == 2 ? 'les dues últimes temporades' : 'la temporada que va jugar'}`
							: 'sense partides les dues últimes temporades: hi posem la mediana del club'}
					>
						{pct(fila.p.taxa)}
						<span class="block text-[10px] text-slate-400 dark:text-slate-500">pres.</span>
					</span>
				</div>
			{/each}
		</section>
	{/each}
{/if}

<details class="mb-4 rounded-xl bg-white px-3 py-2 text-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
	<summary class="cursor-pointer font-semibold text-slate-600 dark:text-slate-300">Com s'ha construït</summary>
	<div class="mt-2 space-y-2 text-[13px] leading-snug text-slate-500 dark:text-slate-400">
		<p>
			<b>Divisions.</b> Puja el campió de cada grup, baixa el vuitè, i el setè es juga la plaça a anada
			i tornada contra el segon de la divisió inferior. Els vuit play-offs del 4 i 5 de juliol de 2026
			ja s'han disputat. Dues eliminatòries van quedar igualades en punts de match i en parcials, i el
			desempat és el <b>total de caramboles</b>: Sant Adrià C hi puja (201-186 al Lleida B) i Sants D
			també (178-177 al Canet B, per una sola carambola). <b>L'ordre de sembra és l'oficial</b>, pres
			de la «Classificació final lligues tres bandes» de la FCB: primer els que baixen de la divisió
			de sobre, després els que s'hi mantenen intercalats per posició de grup, i al final els que hi
			pugen. Aquell document, però, dona el play-off al Canet B: aquí hi corregim la composició —Sants
			D a 2a i Canet B a 3a— i col·loquem cadascun al bloc que li toca, tot i que la posició exacta
			dins del bloc és inferència nostra.
		</p>
		<p>
			<b>Grups.</b> Serpentí <span class="font-mono">A-B-B-A</span> sobre l'ordre de sembra:
			1-4-5-8-9-12-13-16 al grup A i 2-3-6-7-10-11-14-15 al B. A 4a divisió, amb 19 equips, s'estira
			igual (el 17 a l'A; el 18 i el 19 al B). Després s'hi fan les <b>permutes</b> necessàries perquè
			dos equips d'un mateix club no coincideixin de grup: es mou sempre el <b>segon</b> equip del club
			dins del grup, mai el primer, i s'intercanvia amb l'equip que ocupa el mateix slot a l'altre
			grup. Si el Monforte A és el 3r del grup i el Monforte B el 8è, es permuta el Monforte B amb el
			8è de l'altre grup. Així el millor classificat es queda on el posa la sembra i el moviment és
			mínim, perquè els slots homòlegs són sempre posicions consecutives de l'ordre oficial (l'A2 és el
			4 i el B2 el 3; l'A3 és el 5 i el B3 el 6…). En surten sis —dues a Honor, una a 1a, una a 2a i
			dues a 3a— i cap divisió no queda amb equips del mateix club junts. Els moguts van marcats amb ⇄.
		</p>
		<p>
			<b>Presència i alineació habitual.</b> Cada jugador porta el percentatge de jornades que ha
			jugat les <b>dues últimes temporades</b>, sobre les de l'equip on va jugar més cada any i amb
			la temporada 2025-26 pesant el doble que la 2024-25, perquè qui acaba d'agafar la titularitat
			no arrossegui l'any que no jugava. Hi ha 431 jugadors amb les dues temporades i 87 amb una;
			només un no en té cap, i hereta la mediana del seu club. És l'ingredient que les mitjanes no diuen: només
			<b>34 dels 83 equips</b> cobreixen el 80% de les seves taules amb quatre jugadors, i n'hi ha
			que en fan servir catorze. El punt <b>●</b> marca l'<b>alineació habitual més probable</b>: els
			quatre de la plantilla amb més presència, que no sempre són els quatre de més mitjana. El cas
			extrem és el Granollers A, on Mas Canadell, Jiménez Galera i Mata Pardo, els tres millors
			promitjos de la categoria, van jugar entre el 44% i el 69% de les jornades.
		</p>
		<p>
			<b>Pronòstic.</b> Els xips <span class="font-semibold">1r</span>,
			<span class="font-semibold">2n</span>, <span class="font-semibold">penúlt.</span> i
			<span class="font-semibold">últim</span> marquen el favorit de cada plaça dins del seu grup,
			amb la seva probabilitat. Surten de simular <b>10.000 temporades senceres</b>: les cinc
			divisions i els deu grups alhora, jornada a jornada sobre un calendari de doble volta. A cada
			jornada es sorteja qui està a disposició de cada club segons la seva presència i després els
			equips trien per ordre de categoria —els millors disponibles de la seva banda i, si no n'hi ha
			prou, pujant-ne de les de sota—, de manera que <b>un jugador no juga mai amb dos equips el
			mateix dia</b> i que quan l'A puja algú, el B se'n ressent. Cada partida es resol amb un model
			calibrat sobre les 2.433 partides de la lliga 2025-26: la probabilitat de guanyar surt de la
			diferència de mitjanes més l'avantatge de camp, que és real i mesurable (els locals s'enduen el
			55,1% dels parcials, i amb mitjanes iguals el local guanya el 54,5%). Els punts són 3/1/0 i el
			desempat, els parcials, com fa la federació. Validat per trams, el model encerta la freqüència
			real dins d'un o dos punts. No hi entren ni les incompareixences, ni les sancions, ni els
			fitxatges que no coneguem.
		</p>
		<p>
			<b>Llistes.</b> El pool de cada club són els jugadors que van disputar la lliga 2025-26, ordenats
			per la mitjana del rànquing de tres bandes vigent (núm. 124, 27-07-2026) — el mateix criteri que
			aplica la federació sobre la llista única d'inscripció. Tothom pot fer de suplent dels equips
			que té per sobre, i a l'<b>últim equip</b> del club hi consten tots els jugadors que queden,
			encara que passin dels sis: la seva banda és oberta i qui hi hagi a sota només pot jugar amb ell
			o fer de suplent dels de dalt.
		</p>
		<p>
			<b>Repartiment <span class="font-mono">3-5-4-4</span>.</b> 1-3 només equip A; 4-8 titulars del B
			i suplents de l'A; 9-12 el C; 13-16 el D; la resta, E i/o suplents. L'equip A només té tres
			jugadors propis, o sigui que el quart de cada encontre surt de les suplències; i el nº 4, als
			clubs amb més d'un equip, només pot jugar les dues últimes jornades regulars i les finals o
			promocions amb el B si abans hi ha fet un mínim de 6 jornades (Assemblea 03/06/23).
		</p>
		<p>
			<b>Repartiment <span class="font-mono">4-4-4-4-4</span>.</b> 1-4 equip A; 5-8 el B; 9-12 el C;
			13-16 el D; la resta, E. Cada equip amb els seus quatre i cap de compartit: és la millor
			combinació que un club pot presentar en una jornada, perquè tothom juga a l'equip que li toca
			pel rànquing sense haver de cedir ningú. Els quatre titulars són els mateixos que amb
			<span class="font-mono">3-5-4-4</span> —i per tant les mitjanes d'equip i la classificació
			projectada no canvien—; el que desapareix és el jugador frontissa i, amb ell, la incertesa de
			saber amb quin equip juga cada jornada.
		</p>
		<p>
			<b>Repartiment «més probable».</b> Mateixes bandes que la norma, però els quatre que juguen no
			són els de més mitjana de la banda sinó els de <b>més presència</b>: l'alineació que de fet es
			veu cada jornada. És on es nota que hi ha equips que no treuen mai els seus millors promitjos.
			Amb aquesta opció, la mitjana d'equip que es mostra és la d'aquests quatre.
		</p>
		<p>
			<b>Repartiment <span class="font-mono">4-6-6-6</span>.</b> 1-4 equip A; 5-10 equip B; 11-16 el C;
			17-22 el D; la resta, E. Cada equip té els seus quatre titulars propis i el B, el C i el D
			porten dos suplents més dins de la seva banda, així que desapareix el jugador frontissa.
		</p>
		<p>
			<b>Què canvia entre els tres.</b> El <span class="font-mono">3-5-4-4</span> i el
			<span class="font-mono">4-4-4-4-4</span> donen exactament els mateixos quatre titulars a tots els
			equips: només es diferencien en qui hi fa de suplent i en si hi ha jugador frontissa. El
			<span class="font-mono">4-6-6-6</span>, en canvi, mou els titulars de la C cap avall —la banda hi
			arrenca dues posicions més avall—, i afecta 22 dels 83 equips, tots amb pèrdua de mitjana. Els
			equips A i B no es mouen amb cap dels tres, o sigui que la Divisió d'Honor i la 1a, gairebé totes
			d'equips A i B, són sempre iguals.
		</p>
		<p>
			<b>Lletres.</b> Es reparteixen de nou cada temporada per categoria: l'A és sempre l'equip de més
			divisió, i després B, C, D i E. L'únic club que les té creuades és el Sants: la seva D puja a 2a
			i la C es queda a 3a, o sigui que passen a ser <b>Sants C</b> i <b>Sants D</b> respectivament.
			Ho marquem amb un «era la…».
		</p>
		<p>
			<b>Què no cobreix.</b> Altes i baixes de llicència més enllà dels canvis coneguts (marcats amb ⇄
			o ↩), jugadors que el club decideixi no inscriure, equips nous a 4a divisió i renúncies a la
			plaça guanyada.
		</p>
	</div>
</details>
