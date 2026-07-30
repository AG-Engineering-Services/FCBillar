<script lang="ts">
	// Calendari esportiu federatiu, setmana a setmana. Font actual: el PDF de la
	// RFEB (la FCB encara no ha publicat el seu de 26/27; quan ho faci hi entrarà
	// com a font 'FCB' i sortirà a la mateixa llista).
	//
	// El PDF NO concreta dia ni hora: per a cada setmana diu què es juga aquell cap
	// de setmana. Per això la unitat de la pàgina és la setmana, no el dia.
	import { onMount } from 'svelte';
	import {
		supabase,
		type CalendariCanvi,
		type CalendariEvent,
		type CalendariRevisio
	} from '$lib/supabase';

	let events = $state<CalendariEvent[]>([]);
	let revisions = $state<CalendariRevisio[]>([]);
	let canvis = $state<CalendariCanvi[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let temporada = $state<string | null>(null);
	let tipus = $state('tot');
	let ambit = $state('tot');
	let nomesCarambola = $state(true);
	let mostraCanvis = $state(false);
	let mostraPassat = $state(false);

	const OPCIONS_TIPUS: [string, string][] = [
		['tot', 'Tot'],
		['equips', 'Equips'],
		['individual', 'Individual']
	];
	const OPCIONS_AMBIT: [string, string][] = [
		['tot', 'Tots'],
		['nacional', 'Estatal'],
		['internacional', 'Internacional']
	];

	const MESOS = [
		'gener', 'febrer', 'març', 'abril', 'maig', 'juny',
		'juliol', 'agost', 'setembre', 'octubre', 'novembre', 'desembre'
	];
	const MESOS_CURT = ['gen', 'feb', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'oct', 'nov', 'des'];

	// Data local a partir d'un ISO 'yyyy-mm-dd' (evita el desplaçament d'UTC que
	// faria new Date('2026-09-07') a fusos negatius).
	function d(iso: string): Date {
		const [y, m, day] = iso.split('-').map(Number);
		return new Date(y, m - 1, day);
	}
	const fmtCurt = (iso: string) => `${d(iso).getDate()} ${MESOS_CURT[d(iso).getMonth()]}`;
	function fmtRang(inici: string, fi: string): string {
		if (inici === fi) return fmtCurt(inici);
		const a = d(inici);
		const b = d(fi);
		return a.getMonth() === b.getMonth()
			? `${a.getDate()}–${b.getDate()} ${MESOS_CURT[b.getMonth()]}`
			: `${fmtCurt(inici)} – ${fmtCurt(fi)}`;
	}
	function mesTitol(setmana: string): string {
		const dt = d(setmana);
		return `${MESOS[dt.getMonth()]} ${dt.getFullYear()}`;
	}

	// Dilluns de la setmana d'avui, en el mateix format que la columna `setmana`.
	function dillunsAvui(): string {
		const t = new Date();
		t.setHours(0, 0, 0, 0);
		t.setDate(t.getDate() - ((t.getDay() + 6) % 7));
		const p = (n: number) => String(n).padStart(2, '0');
		return `${t.getFullYear()}-${p(t.getMonth() + 1)}-${p(t.getDate())}`;
	}
	const avui = dillunsAvui();

	onMount(async () => {
		try {
			const [ev, rev] = await Promise.all([
				// .range() explícit: PostgREST talla a 1000 files en silenci.
				supabase.from('calendari_events').select('*').order('setmana').range(0, 4999),
				supabase.from('calendari_revisions').select('*')
			]);
			if (ev.error) throw ev.error;
			if (rev.error) throw rev.error;
			events = (ev.data ?? []) as CalendariEvent[];
			revisions = (rev.data ?? []) as CalendariRevisio[];

			// Temporada per defecte: la que té MÉS competicions pendents. A finals de
			// juliol la temporada «en curs» ja s'ha acabat (al calendari de la 25/26 hi
			// queda un sol acte) i el que interessa és la següent, que la RFEB publica
			// amb setmanes d'antelació. Comptar pendents ho encerta en tots dos casos;
			// agafar la primera amb res pendent, no.
			const pendents = new Map<string, number>();
			for (const e of events) {
				if (e.setmana >= avui) pendents.set(e.temporada, (pendents.get(e.temporada) ?? 0) + 1);
			}
			const tots = [...new Set(events.map((e) => e.temporada))].sort();
			temporada =
				[...pendents.entries()].sort((a, b) => b[1] - a[1] || b[0].localeCompare(a[0]))[0]?.[0] ??
				tots[tots.length - 1] ??
				null;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const temporades = $derived([...new Set(events.map((e) => e.temporada))].sort());

	const recent = (a: CalendariRevisio, b: CalendariRevisio) =>
		(b.ingested_at ?? '').localeCompare(a.ingested_at ?? '');

	// Revisió que ha generat els esdeveniments que es mostren. Es demana
	// `n_events > 0` perquè de la FCB en registrem la versió i la URL del PDF sense
	// parsejar-lo: si no, la capçalera atribuiria els esdeveniments a la font
	// equivocada.
	const revisioVigent = $derived(
		revisions.filter((r) => r.temporada === temporada && r.n_events > 0).sort(recent)[0] ?? null
	);
	// Calendari oficial de la FCB: pot existir com a PDF sense estar integrat.
	const revisioFCB = $derived(
		revisions.filter((r) => r.temporada === temporada && r.font === 'FCB').sort(recent)[0] ?? null
	);

	// Els canvis es carreguen a part perquè depenen de la temporada triada: canviar
	// de xip de temporada ha de portar els canvis d'aquella revisió.
	$effect(() => {
		const r = revisioVigent;
		if (!r) {
			canvis = [];
			return;
		}
		let viu = true;
		supabase
			.from('calendari_canvis')
			.select('*')
			.eq('font', r.font)
			.eq('temporada', r.temporada)
			.eq('sha256', r.sha256)
			.order('ord')
			.range(0, 999)
			.then(({ data }) => {
				if (viu) canvis = (data ?? []) as CalendariCanvi[];
			});
		return () => {
			viu = false;
		};
	});

	const filtrats = $derived(
		events
			.filter((e) => e.temporada === temporada)
			.filter((e) => (nomesCarambola ? e.disciplina === 'carambola' : true))
			// Els blocs fusionats del PDF (Nadal, Setmana Santa) no tenen tipus ni
			// àmbit: són avisos de «aquesta setmana no es juga» i no s'han de filtrar.
			.filter((e) => tipus === 'tot' || e.tipus === tipus || e.ambit === 'tot')
			.filter((e) => ambit === 'tot' || e.ambit === ambit || e.ambit === 'tot')
	);

	interface Setmana {
		setmana: string;
		inici: string;
		fi: string;
		items: CalendariEvent[];
	}
	const setmanes = $derived.by(() => {
		const out: Setmana[] = [];
		for (const e of [...filtrats].sort(
			(a, b) =>
				a.setmana.localeCompare(b.setmana) ||
				a.ambit.localeCompare(b.ambit) ||
				a.tipus.localeCompare(b.tipus)
		)) {
			let g = out[out.length - 1];
			if (!g || g.setmana !== e.setmana) {
				g = { setmana: e.setmana, inici: e.data_inici, fi: e.data_fi, items: [] };
				out.push(g);
			}
			if (e.data_inici < g.inici) g.inici = e.data_inici;
			if (e.data_fi > g.fi) g.fi = e.data_fi;
			g.items.push(e);
		}
		return out;
	});

	const setmanaActual = $derived(setmanes.find((s) => s.setmana === avui) ?? null);
	const propera = $derived(setmanes.find((s) => s.setmana > avui) ?? null);
	// Per defecte es mostra d'aquesta setmana endavant: la pàgina serveix per saber
	// què VE. El passat queda plegat darrere d'un botó.
	const passades = $derived(setmanes.filter((s) => s.setmana < avui));
	const llista = $derived(mostraPassat ? setmanes : setmanes.filter((s) => s.setmana >= avui));

	const BADGE_TIPUS: Record<string, string> = {
		equips:
			'bg-indigo-50 text-indigo-700 ring-indigo-200 dark:bg-indigo-950/50 dark:text-indigo-300 dark:ring-indigo-900',
		individual:
			'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:ring-emerald-900'
	};
	const ETIQUETA_TIPUS: Record<string, string> = { equips: 'Equips', individual: 'Individual' };
	const ETIQUETA_AMBIT: Record<string, string> = {
		nacional: 'Estatal',
		internacional: 'Internacional',
		mixt: 'Estatal/Int.'
	};
	const ETIQUETA_DISC: Record<string, string> = {
		carambola: 'Caràmbola',
		pool: 'Pool',
		snooker: 'Snooker'
	};
	const xip = (actiu: boolean) =>
		`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${
			actiu
				? 'bg-slate-900 text-white ring-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:ring-slate-100'
				: 'bg-white text-slate-600 ring-slate-300 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700'
		}`;
</script>

<h1 class="mb-1 text-lg font-bold">Calendari</h1>
<p class="mb-3 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
	Què es juga cada setmana, per equips i individual.
	{#if revisioVigent}
		Font: calendari <b>{revisioVigent.font}</b>{#if revisioVigent.versio}&nbsp;{revisioVigent.versio}{/if}{#if revisioVigent.data_versio}, actualitzat per la federació el {fmtCurt(
				revisioVigent.data_versio
			)}{/if}{#if revisioVigent.last_checked_at} · comprovat el {fmtCurt(
				revisioVigent.last_checked_at.slice(0, 10)
			)}{/if}.
	{/if}
</p>

{#if error}
	<div
		class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300"
	>
		{error}
	</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
{:else if !events.length}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">
		Encara no hi ha cap calendari ingestat.
	</p>
{:else}
	<div class="mb-3 flex flex-wrap items-center gap-1.5">
		{#if temporades.length > 1}
			{#each temporades as t (t)}
				<button type="button" onclick={() => (temporada = t)} class={xip(temporada === t)}>{t}</button>
			{/each}
			<span class="mx-1 h-4 w-px bg-slate-200 dark:bg-slate-700"></span>
		{/if}
		{#each OPCIONS_TIPUS as [v, lbl] (v)}
			<button type="button" onclick={() => (tipus = v)} class={xip(tipus === v)}>{lbl}</button>
		{/each}
		<span class="mx-1 h-4 w-px bg-slate-200 dark:bg-slate-700"></span>
		{#each OPCIONS_AMBIT as [v, lbl] (v)}
			<button type="button" onclick={() => (ambit = v)} class={xip(ambit === v)}>{lbl}</button>
		{/each}
		<label
			class="ml-auto flex cursor-pointer items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400"
		>
			<input type="checkbox" bind:checked={nomesCarambola} class="rounded" />
			només caràmbola
		</label>
	</div>

	<section
		class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800"
	>
		<h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
			Aquesta setmana
		</h2>
		{#if setmanaActual}
			{@render blocs(setmanaActual.items)}
		{:else}
			<p class="text-sm text-slate-400 dark:text-slate-500">Cap competició al calendari.</p>
			{#if propera}
				<h2
					class="mb-2 mt-3 border-t border-slate-100 pt-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:text-slate-400"
				>
					Següent · {fmtRang(propera.inici, propera.fi)}
				</h2>
				{@render blocs(propera.items)}
			{/if}
		{/if}
	</section>

	{#if !llista.length}
		<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">
			Cap competició amb aquests filtres.
		</p>
	{/if}
	{#each llista as s, i (s.setmana)}
		{#if i === 0 || mesTitol(llista[i - 1].setmana) !== mesTitol(s.setmana)}
			<h2
				class="mb-1.5 mt-4 px-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
			>
				{mesTitol(s.setmana)}
			</h2>
		{/if}
		<section
			class="mb-1.5 rounded-xl bg-white p-3 dark:bg-slate-900 {s.setmana === avui
				? 'ring-2 ring-slate-900 dark:ring-slate-100'
				: 'ring-1 ring-slate-200 dark:ring-slate-800'}"
		>
			<div class="mb-1.5 flex items-baseline gap-2">
				<span class="text-sm font-semibold">{fmtRang(s.inici, s.fi)}</span>
				{#if s.setmana === avui}
					<span
						class="text-[10px] font-bold uppercase tracking-wide text-slate-900 dark:text-slate-100"
						>aquesta setmana</span
					>
				{:else if s.setmana < avui}
					<span class="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500"
						>jugat</span
					>
				{/if}
			</div>
			{@render blocs(s.items)}
		</section>
	{/each}

	{#if passades.length && !mostraPassat}
		<button
			type="button"
			onclick={() => (mostraPassat = true)}
			class="mt-2 w-full rounded-lg border border-slate-200 py-2 text-xs font-medium text-slate-500 dark:border-slate-800 dark:text-slate-400"
			>Mostra també les {passades.length} setmanes ja jugades</button
		>
	{/if}

	{#if canvis.length}
		<section class="mt-5">
			<button
				type="button"
				onclick={() => (mostraCanvis = !mostraCanvis)}
				class="flex w-full items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-left text-xs font-semibold text-amber-800 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200"
			>
				<span>{mostraCanvis ? '▾' : '▸'}</span>
				{canvis.length}
				{canvis.length === 1 ? 'canvi' : 'canvis'} a l'última revisió del calendari
			</button>
			{#if mostraCanvis}
				<ul
					class="mt-1.5 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800"
				>
					{#each canvis as c (c.ord)}
						<li
							class="border-b border-slate-100 px-3 py-2 text-xs last:border-0 dark:border-slate-800"
						>
							<div class="flex items-center gap-2">
								<span class="font-mono text-[11px] text-slate-400 dark:text-slate-500"
									>{fmtCurt(c.setmana)}</span
								>
								<span
									class="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase {c.tipus_canvi ===
									'alta'
										? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
										: c.tipus_canvi === 'baixa'
											? 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300'
											: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300'}"
									>{c.tipus_canvi === 'modificacio' ? 'canvi' : c.tipus_canvi}</span
								>
								<span class="text-slate-400 dark:text-slate-500"
									>{[ETIQUETA_DISC[c.disciplina] ?? c.disciplina, ETIQUETA_TIPUS[c.tipus ?? '']]
										.filter(Boolean)
										.join(' · ')}</span
								>
							</div>
							<div class="mt-0.5 leading-snug">
								{#if c.tipus_canvi === 'modificacio'}
									<span class="text-slate-400 line-through dark:text-slate-500">{c.abans}</span>
									<span class="mx-1">→</span><span>{c.despres}</span>
								{:else}
									{c.despres ?? c.abans}
								{/if}
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/if}

	<p class="px-1 py-4 text-center text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
		El calendari federatiu concreta el cap de setmana, no el dia ni l'hora, i pot canviar: el PDF
		d'origen es torna a comprovar cada dia.
		{#if revisioFCB}
			La Federació Catalana té publicat el seu calendari
			{revisioFCB.versio ?? ''} en
			<a href={revisioFCB.url ?? '#'} target="_blank" rel="noopener" class="underline">PDF</a>;
			encara no està integrat en aquesta llista.
		{:else}
			La Federació Catalana encara no ha publicat el seu calendari d'aquesta temporada; quan ho
			faci s'hi afegirà.
		{/if}
		{#if revisioVigent?.url}
			<a href={revisioVigent.url} target="_blank" rel="noopener" class="underline"
				>PDF de la {revisioVigent.font}</a
			>.
		{/if}
	</p>
{/if}

{#snippet blocs(items: CalendariEvent[])}
	<ul class="flex flex-col gap-1.5">
		{#each items as e (e.ambit + e.grup + e.tipus + e.titol)}
			<li class="flex gap-2">
				<div class="flex w-[84px] shrink-0 flex-col gap-1 pt-0.5">
					{#if e.tipus}
						<span
							class="rounded px-1.5 py-0.5 text-center text-[10px] font-bold uppercase tracking-wide ring-1 {BADGE_TIPUS[
								e.tipus
							]}">{ETIQUETA_TIPUS[e.tipus]}</span
						>
					{/if}
					{#if e.ambit !== 'tot'}
						<span
							class="text-center text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500"
							>{ETIQUETA_AMBIT[e.ambit] ?? e.ambit}</span
						>
					{/if}
				</div>
				<div class="min-w-0 flex-1">
					<div class="text-sm font-medium leading-snug">
						{e.titol}
						{#if !nomesCarambola && e.disciplina !== 'carambola'}
							<span class="ml-1 text-[10px] uppercase text-slate-400 dark:text-slate-500"
								>{ETIQUETA_DISC[e.disciplina] ?? e.disciplina}</span
							>
						{/if}
					</div>
					{#if e.dissabte || e.diumenge}
						<div class="text-xs text-slate-500 dark:text-slate-400">
							{#if e.dissabte}<span>ds: {e.dissabte}</span>{/if}{#if e.dissabte && e.diumenge}<span
									class="mx-1 text-slate-300 dark:text-slate-600">·</span
								>{/if}{#if e.diumenge}<span>dg: {e.diumenge}</span>{/if}
						</div>
					{/if}
					{#if e.seu}
						<div class="text-xs text-slate-400 dark:text-slate-500">{e.seu}</div>
					{/if}
				</div>
			</li>
		{/each}
	</ul>
{/snippet}
