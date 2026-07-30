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
		club: string;
		nom: string;
		lletra: string;
		lletra_2526: string;
		unic: boolean;
		div_2526: string;
		motiu: string | null;
	};

	const clubs = projeccio.clubs as Club[];
	const divisions = projeccio.divisions as Record<string, { distancia: number; equips: EquipDiv[] }>;
	const DIVS = ['Honor', '1a', '2a', '3a', '4a'];
	const LLETRES = ['A', 'B', 'C', 'D', 'E'];

	type Esquema = 'fcb' | 'alt';
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
		alt: {
			etiqueta: '4-6-6-6',
			talls: [4, 10, 16, 22],
			inici: { A: 1, B: 5, C: 11, D: 17, E: 23 },
			rangs: { A: '1-4', B: '5-10', C: '11-16', D: '17-22', E: '23+' }
		}
	};

	let vista = $state<'club' | 'divisio'>('club');
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
	/** Tota la banda d'un equip: els titulars més els suplents que li pertoquen.
	 *  És on es veu el repartiment: amb 3-5-4-4 el B té el nº 4 (que juga amb l'A)
	 *  i amb 4-6-6-6 en té dos de propis al final de la banda. */
	function bandaDe(llista: Jugador[], lletra: string, esq: Esquema): Jugador[] {
		return llista.filter((p) => banda(p.num, esq) === lletra);
	}
	function suplentsBanda(llista: Jugador[], lletra: string, esq: Esquema): Jugador[] {
		const nums = new Set(referents(llista, lletra, esq).map((p) => p.num));
		return bandaDe(llista, lletra, esq).filter((p) => !nums.has(p.num));
	}
	const mitjanaEquip = (llista: Jugador[], lletra: string, esq: Esquema) => {
		const t = referents(llista, lletra, esq);
		return t.length ? t.reduce((a, p) => a + p.mitjana, 0) / t.length : 0;
	};

	const matchJugador = (llista: Jugador[]) => llista.some((p) => norm(p.nom).includes(norm(q.trim())));

	const divisionsFiltrades = $derived.by(() => {
		const t = q.trim();
		return DIVS.filter((d) => selDiv === null || selDiv === d).map((d) => {
			const amb = divisions[d].equips.map((e) => {
				const club = clubPerClau.get(e.club)!;
				return {
					e,
					club,
					tit: referents(club.llista, e.lletra, esquema),
					sup: suplentsBanda(club.llista, e.lletra, esquema)
				};
			});
			amb.sort(
				(a, b) =>
					mitjanaEquip(b.club.llista, b.e.lletra, esquema) -
					mitjanaEquip(a.club.llista, a.e.lletra, esquema)
			);
			return {
				nom: d,
				distancia: divisions[d].distancia,
				total: amb.length,
				equips: amb
					.map((x, i) => ({ ...x, pos: i + 1 }))
					.filter(
						(x) =>
							!t ||
							norm(x.e.nom).includes(norm(t)) ||
							x.tit.some((p) => norm(p.nom).includes(norm(t)))
					)
			};
		});
	});

	const clubsFiltrats = $derived.by(() => {
		const t = q.trim();
		return clubs.filter(
			(c) =>
				(selDiv === null || c.equips.some((e) => e.divisio === selDiv)) &&
				(!t || norm(c.nom).includes(norm(t)) || matchJugador(c.llista))
		);
	});

	const totalEquips = $derived(divisionsFiltrades.reduce((n, d) => n + d.equips.length, 0));

	const cognom = (n: string) => (n.includes(',') ? n.slice(0, n.indexOf(',')) : n);
	const nomPropi = (n: string) => (n.includes(',') ? n.slice(n.indexOf(',') + 1).trim() : '');
	const etiquetaDiv = (d: string) => (d === 'Honor' ? "Divisió d'Honor" : `${d} divisió`);
	function llistaLletres(ls: string[]): string {
		if (!ls.length) return '';
		if (ls.length === 1) return `l'${ls[0]}`;
		return `${ls.slice(0, -1).join(', ')} i ${ls[ls.length - 1]}`;
	}
	const puja = (m: string | null) => !!m && m.startsWith('puja');
	const baixa = (m: string | null) => !!m && m.startsWith('baixa');
	const esSwing = (p: Jugador, c: Club) => esquema === 'fcb' && p.num === 4 && c.multi;

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
				cap = {
					b,
					titular,
					reserva_de: titular ? lletres.filter((x) => x < b) : lletres.slice()
				};
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

<!-- selector de vista i de repartiment: dos controls independents, perquè el
     repartiment val per a totes dues vistes -->
<div class="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
	<div class="inline-flex rounded-lg bg-slate-100 p-0.5 text-sm dark:bg-slate-800">
		<button
			type="button"
			onclick={() => (vista = 'club')}
			class="rounded-md px-3 py-1 font-medium {vista === 'club'
				? 'bg-white shadow-sm dark:bg-slate-700'
				: 'text-slate-500 dark:text-slate-400'}">Per club</button
		>
		<button
			type="button"
			onclick={() => (vista = 'divisio')}
			class="rounded-md px-3 py-1 font-medium {vista === 'divisio'
				? 'bg-white shadow-sm dark:bg-slate-700'
				: 'text-slate-500 dark:text-slate-400'}">Per divisió</button
		>
	</div>
	<div class="inline-flex items-center gap-1.5">
		<span class="text-xs text-slate-400 dark:text-slate-500">bandes</span>
		<div class="inline-flex rounded-lg bg-slate-100 p-0.5 text-sm dark:bg-slate-800">
			{#each ['fcb', 'alt'] as k}
				<button
					type="button"
					onclick={() => (esquema = k as Esquema)}
					class="rounded-md px-2.5 py-1 font-mono text-xs {esquema === k
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

{#if vista === 'divisio'}
	{#if totalEquips === 0}
		<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Cap equip coincideix.</p>
	{/if}
	{#each divisionsFiltrades as d}
		{#if d.equips.length}
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
					{#each d.equips as x}
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
									>{mitjanaEquip(x.club.llista, x.e.lletra, esquema).toFixed(3)}</span
								>
							</div>
							<p class="ml-7 text-[11px] text-slate-400 dark:text-slate-500">
								banda <span class="font-mono">{ESQUEMES[esquema].rangs[x.e.lletra]}</span> de la llista
								del club{#if x.e.motiu}&nbsp;· {x.e.motiu}{/if}
							</p>
							<ol class="ml-7 mt-1.5 space-y-0.5">
								{#each x.tit as p}
									<li class="flex items-baseline gap-2">
										<span
											class="w-4 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-400 dark:text-slate-500"
											>{p.num}</span
										>
										<span class="min-w-0 flex-1 truncate text-xs">
											<span class="font-medium">{cognom(p.nom)}</span><span
												class="text-slate-500 dark:text-slate-400">, {nomPropi(p.nom)}</span
											>
											{#if p.de_club}<span class="ml-1 text-[10px] font-semibold text-sky-600 dark:text-sky-400"
													>⇄ {p.de_club}</span
												>{:else if p.retorn}<span
													class="ml-1 text-[10px] font-semibold text-sky-600 dark:text-sky-400">↩ es reincorpora</span
												>{:else if esSwing(p, x.club)}<span
													class="ml-1 text-[10px] text-amber-600 dark:text-amber-400">nº4</span
												>{/if}
										</span>
										<span class="shrink-0 font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400"
											>{p.mitjana.toFixed(3)}</span
										>
									</li>
								{/each}
							</ol>
							{#if x.sup.length}
								<p class="ml-7 mt-1 text-[11px] leading-snug text-slate-400 dark:text-slate-500">
									<span class="font-semibold">suplents de la banda:</span>
									{#each x.sup.slice(0, 4) as p, i}{i > 0 ? ' · ' : ' '}<span class="font-mono">{p.num}</span
										>&nbsp;{cognom(p.nom)}{#if esSwing(p, x.club)}<span
											class="text-amber-600 dark:text-amber-400">&nbsp;(juga amb l'A)</span
										>{/if}{/each}{#if x.sup.length > 4}&nbsp;· i {x.sup.length - 4} més{/if}
								</p>
							{/if}
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
					<div
						class="flex items-baseline gap-2 border-t border-slate-100 px-3 py-1.5 dark:border-slate-800"
					>
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
			ja s'han disputat. Dos van quedar igualats en punts de match i en parcials i s'han resolt pel
			total de caramboles: Sant Adrià C 201-186 Lleida B i Sants D 178-177 Canet B. Si la federació hi
			aplica un altre desempat, aquestes dues places s'intercanvien.
		</p>
		<p>
			<b>Llistes.</b> El pool de cada club són els jugadors que van disputar la lliga 2025-26, ordenats
			per la mitjana del rànquing de tres bandes vigent (núm. 124, 27-07-2026) — el mateix criteri que
			aplica la federació sobre la llista única d'inscripció. Tothom pot fer de suplent dels equips
			que té per sobre.
		</p>
		<p>
			<b>Repartiment <span class="font-mono">3-5-4-4</span>.</b> 1-3 només equip A; 4-8 titulars del B
			i suplents de l'A; 9-12 el C; 13-16 el D; la resta, E i/o suplents. L'equip A només té tres
			jugadors propis, o sigui que el quart de cada encontre surt de les suplències; i el nº 4, als
			clubs amb més d'un equip, només pot jugar les dues últimes jornades regulars i les finals o
			promocions amb el B si abans hi ha fet un mínim de 6 jornades (Assemblea 03/06/23). Per això, a
			la vista per divisió, l'A hi surt amb els nº 1-4 i el B amb els 5-8.
		</p>
		<p>
			<b>Repartiment <span class="font-mono">4-6-6-6</span>.</b> 1-4 equip A; 5-10 equip B; 11-16 el C;
			17-22 el D; la resta, E. Cada equip té els seus quatre titulars propis i el B, el C i el D
			porten dos suplents més dins de la seva banda, així que desapareix el jugador frontissa.
		</p>
		<p>
			<b>Què canvia entre els dos.</b> Els equips A i B tenen els mateixos quatre titulars en tots dos
			casos (1-4 i 5-8), o sigui que la Divisió d'Honor i la 1a —gairebé tots equips A i B— no es
			mouen de mitjana; el que hi canvia és qui els fa de suplent. Els titulars sí que canvien de la C
			cap avall, on la banda arrenca dues posicions més amunt amb <span class="font-mono">3-5-4-4</span
			> (9-12 i 13-16) que amb <span class="font-mono">4-6-6-6</span> (11-16 i 17-22): són 22 dels 83
			equips, i tots hi perden mitjana amb el segon repartiment.
		</p>
		<p>
			<b>Lletres.</b> Es reparteixen de nou cada temporada per categoria: l'A és sempre l'equip de més
			divisió, i després B, C, D i E. Per això on el 2025-26 van quedar creuades —el Sants va pujar la
			D a 2a mentre la C es quedava a 3a— aquí surten ja intercanviades, amb la nota «era la…».
		</p>
		<p>
			<b>Què no cobreix.</b> Altes i baixes de llicència més enllà dels canvis coneguts (marcats amb ⇄
			o ↩), jugadors que el club decideixi no inscriure, equips nous a 4a divisió i renúncies a la
			plaça guanyada.
		</p>
	</div>
</details>
