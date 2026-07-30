<script lang="ts">
	// Projecció de la Lliga de Tres Bandes 2026-27. A diferència de la resta de
	// seccions, NO llegeix de Supabase: és una foto derivada de les classificacions
	// oficials 2025-26 + els play-offs de promoció del 4-5 de juliol de 2026, que es
	// regenera amb `python scripts/projeccio_lliga_2627.py --json web/src/lib/data/lliga2627.json`.
	import { norm } from '$lib/search';
	import projeccio from '$lib/data/lliga2627.json';

	type Jugador = {
		num: number;
		banda: string;
		titular: boolean;
		reserva_de: string[];
		swing: boolean;
		nom: string;
		mitjana: number;
		pos: number | null;
		de_club: string | null;
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
		mitjana_equip: number;
	};

	const clubs = projeccio.clubs as Club[];
	const divisions = projeccio.divisions as Record<string, { distancia: number; equips: EquipDiv[] }>;
	const DIVS = ['Honor', '1a', '2a', '3a', '4a'];
	const RANG: Record<string, string> = { A: '1-3', B: '4-8', C: '9-12', D: '13-16', E: '17+' };

	let vista = $state<'divisio' | 'club'>('divisio');
	let selDiv = $state<string | null>(null);
	let q = $state('');

	const clubPerClau = new Map(clubs.map((c) => [c.club, c]));

	/** Els quatre que formen l'alineació en jornada regular. L'equip A només té tres
	 *  jugadors propis (1-3) i el quart surt de la banda del B —normalment el nº 4—,
	 *  així que el B tira dels nº 5-8. Mateixa regla que al generador Python. */
	function referents(llista: Jugador[], lletra: string): Jugador[] {
		if (lletra === 'A') return llista.filter((p) => p.num <= 4);
		if (lletra === 'B') return llista.filter((p) => p.num >= 5 && p.num <= 8);
		return llista.filter((p) => p.banda === lletra).slice(0, 4);
	}

	const matchJugador = (llista: Jugador[]) => llista.some((p) => norm(p.nom).includes(norm(q.trim())));

	const divisionsFiltrades = $derived.by(() => {
		const t = q.trim();
		return DIVS.filter((d) => selDiv === null || selDiv === d).map((d) => ({
			nom: d,
			distancia: divisions[d].distancia,
			total: divisions[d].equips.length,
			equips: divisions[d].equips.filter((e) => {
				if (!t) return true;
				const club = clubPerClau.get(e.club);
				return norm(e.nom).includes(norm(t)) || (club ? matchJugador(referents(club.llista, e.lletra)) : false);
			})
		}));
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
		if (ls.length === 1) return `l'${ls[0]}`;
		return `${ls.slice(0, -1).join(', ')} i ${ls[ls.length - 1]}`;
	}
	const puja = (m: string | null) => !!m && m.startsWith('puja');
	const baixa = (m: string | null) => !!m && m.startsWith('baixa');
</script>

<svelte:head><title>Lliga 26/27 · FCBillar</title></svelte:head>

<h1 class="mb-1 text-lg font-bold tracking-tight md:text-xl">Lliga de Tres Bandes 2026-27</h1>
<p class="mb-3 text-sm leading-snug text-slate-500 dark:text-slate-400">
	Projecció a partir de les classificacions oficials del 2025-26 i dels play-offs de promoció del 4 i
	5 de juliol de 2026. Les alineacions surten d'ordenar cada club pel rànquing vigent i aplicar-hi
	les bandes d'inscripció de la federació.
</p>

<!-- selector de vista -->
<div class="mb-3 inline-flex rounded-lg bg-slate-100 p-0.5 text-sm dark:bg-slate-800">
	<button
		type="button"
		onclick={() => (vista = 'divisio')}
		class="rounded-md px-3 py-1 font-medium {vista === 'divisio'
			? 'bg-white shadow-sm dark:bg-slate-700'
			: 'text-slate-500 dark:text-slate-400'}">Per divisió</button
	>
	<button
		type="button"
		onclick={() => (vista = 'club')}
		class="rounded-md px-3 py-1 font-medium {vista === 'club'
			? 'bg-white shadow-sm dark:bg-slate-700'
			: 'text-slate-500 dark:text-slate-400'}">Per club</button
	>
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
			<section class="mb-4 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
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
					{#each d.equips as e, i}
						{@const club = clubPerClau.get(e.club)}
						{@const tit = club ? referents(club.llista, e.lletra) : []}
						<li class="px-3 py-2.5">
							<div class="flex items-baseline gap-2">
								<span
									class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums text-slate-400 dark:text-slate-500"
									>{i + 1}</span
								>
								<span class="min-w-0 flex-1 truncate text-sm font-semibold"
									>{e.nom}{#if !e.unic}&nbsp;{e.lletra}{/if}{#if !e.unic && e.lletra_2526 && e.lletra_2526 !== e.lletra}<span
											class="ml-1 text-[11px] font-normal text-amber-600 dark:text-amber-400"
											>era la {e.lletra_2526}</span
										>{/if}</span
								>
								{#if puja(e.motiu)}
									<span class="shrink-0 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400"
										>▲ {e.div_2526}</span
									>
								{:else if baixa(e.motiu)}
									<span class="shrink-0 text-[11px] font-semibold text-red-600 dark:text-red-400"
										>▼ {e.div_2526}</span
									>
								{/if}
								<span class="w-12 shrink-0 text-right font-mono text-sm font-bold tabular-nums"
									>{e.mitjana_equip.toFixed(3)}</span
								>
							</div>
							{#if e.motiu}
								<p class="ml-7 text-[11px] text-slate-400 dark:text-slate-500">{e.motiu}</p>
							{/if}
							<ol class="ml-7 mt-1.5 space-y-0.5">
								{#each tit as p}
									<li class="flex items-baseline gap-2">
										<span class="w-4 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-400 dark:text-slate-500"
											>{p.num}</span
										>
										<span class="min-w-0 flex-1 truncate text-xs">
											<span class="font-medium">{cognom(p.nom)}</span><span
												class="text-slate-500 dark:text-slate-400">, {nomPropi(p.nom)}</span
											>
											{#if p.de_club}<span class="ml-1 text-[10px] font-semibold text-sky-600 dark:text-sky-400"
													>⇄ {p.de_club}</span
												>{:else if p.swing}<span class="ml-1 text-[10px] text-amber-600 dark:text-amber-400"
													>nº4</span
												>{/if}
										</span>
										<span class="shrink-0 font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400"
											>{p.mitjana.toFixed(3)}</span
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
		<section class="mb-4 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
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

			{#each c.llista as p, i}
				{#if i === 0 || c.llista[i - 1].banda !== p.banda}
					<div
						class="flex items-baseline gap-2 border-t border-slate-100 px-3 py-1.5 first:border-t-0 dark:border-slate-800"
					>
						<span
							class="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold tabular-nums {p.titular
								? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
								: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300'}">{RANG[p.banda]}</span
						>
						{#if p.titular}
							<span class="text-xs font-semibold"
								>{c.equips.length === 1 && p.banda === 'A' ? 'Equip únic' : `Equip ${p.banda}`}</span
							>
							{#if p.reserva_de.length}
								<span class="text-[11px] text-slate-400 dark:text-slate-500"
									>i reserves de {llistaLletres(p.reserva_de)}</span
								>
							{/if}
						{:else}
							<span class="text-xs font-semibold text-slate-500 dark:text-slate-400">Reserves</span>
							<span class="text-[11px] text-slate-400 dark:text-slate-500">de {llistaLletres(p.reserva_de)}</span>
						{/if}
					</div>
				{/if}
				<div class="flex items-baseline gap-2 px-3 py-1">
					<span class="w-6 shrink-0 text-right font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500"
						>{p.num}</span
					>
					<span class="min-w-0 flex-1">
						<span class="text-sm font-medium">{cognom(p.nom)}</span><span
							class="text-sm text-slate-500 dark:text-slate-400">, {nomPropi(p.nom)}</span
						>
						{#if p.de_club}
							<span class="block text-[10px] font-semibold text-sky-600 dark:text-sky-400">⇄ ve de {p.de_club}</span>
						{:else if p.swing}
							<span class="block text-[10px] text-amber-600 dark:text-amber-400"
								>nº 4: mínim 6 jornades amb el B per jugar-hi les decisives</span
							>
						{/if}
					</span>
					<span class="shrink-0 text-right font-mono text-xs tabular-nums">
						{p.mitjana.toFixed(3)}
						<span class="block text-[10px] text-slate-400 dark:text-slate-500"
							>{p.pos ? `#${p.pos}` : 's/r'}</span
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
			<b>Lletres.</b> Es reparteixen de nou cada temporada per categoria: l'A és sempre l'equip de més
			divisió, i després B, C, D i E. Per això on el 2025-26 van quedar creuades —el Sants va pujar
			la D a 2a mentre la C es quedava a 3a— aquí surten ja intercanviades, amb la nota «era la…».
		</p>
		<p>
			<b>Llistes.</b> El pool de cada club són els jugadors que van disputar la lliga 2025-26, ordenats
			per la mitjana del rànquing de tres bandes vigent (núm. 124, 27-07-2026) — el mateix criteri que
			aplica la federació sobre la llista única d'inscripció. Bandes: 1-3 només equip A; 4-8 titulars
			del B i reserves de l'A; 9-12 titulars del C; 13-16 titulars del D; la resta, equip E i/o
			reserves. L'equip A només té tres jugadors propis, o sigui que el quart de cada encontre surt
			sempre de les reserves; i el nº 4, als clubs amb més d'un equip, només pot jugar les dues
			últimes jornades regulars i les finals o promocions amb el B si abans hi ha fet un mínim de 6
			jornades (Assemblea 03/06/23).
		</p>
		<p>
			<b>Què no cobreix.</b> Altes i baixes de llicència més enllà dels traspassos coneguts (marcats amb
			⇄), jugadors que el club decideixi no inscriure, equips nous a 4a divisió i renúncies a la plaça
			guanyada.
		</p>
	</div>
</details>
