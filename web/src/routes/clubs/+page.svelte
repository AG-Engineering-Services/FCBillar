<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type Modalitat } from '$lib/supabase';
	import {
		buildClubIndexes,
		rankClubs,
		bestNivellAcrossModalities,
		playersWithNivell,
		type RankEntry,
		type PlayerNivell
	} from '$lib/clubs';
	import ClubScatter from '$lib/components/ClubScatter.svelte';

	type Mod = number | 'global';

	let modalitats = $state<Modalitat[]>([]);
	let latestSeq = new Map<number, number>();
	let clubFcb = $state<Map<string, string>>(new Map());
	let entriesByMod = $state<Map<number, RankEntry[]>>(new Map());

	let selMod = $state<Mod>(1);
	let K = $state(4); // mida d'equip per a la Potència
	let w = $state(0.6); // pes de la Potència al CQI (1−w = Profunditat)
	let selectedClub = $state<string | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const modLabel = $derived(
		selMod === 'global'
			? 'Global (millor disciplina)'
			: (modalitats.find((m) => m.codi_fcb === selMod)?.nom ?? `Mod. ${selMod}`)
	);

	onMount(async () => {
		try {
			const [{ data: mods, error: em }, { data: rks, error: er }, { data: cls, error: ec }] =
				await Promise.all([
					supabase.from('modalitats').select('codi_fcb, nom').order('codi_fcb'),
					supabase.from('rankings').select('modalitat_codi, num_seq'),
					supabase.from('clubs').select('fcb_id, nom')
				]);
			if (em) throw em;
			if (er) throw er;
			if (ec) throw ec;
			modalitats = mods ?? [];
			for (const r of rks ?? []) {
				const prev = latestSeq.get(r.modalitat_codi);
				if (prev == null || r.num_seq > prev) latestSeq.set(r.modalitat_codi, r.num_seq);
			}
			const cm = new Map<string, string>();
			for (const c of cls ?? []) if (c.nom) cm.set(c.nom, c.fcb_id);
			clubFcb = cm;
			await ensureLoaded(selMod);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	async function fetchMod(codi: number): Promise<RankEntry[]> {
		const seq = latestSeq.get(codi);
		if (seq == null) return [];
		const { data, error: e } = await supabase
			.from('ranking_full')
			.select('posicio, player_fcb_id, jugador, club, mitjana_general')
			.eq('modalitat_codi', codi)
			.eq('num_seq', seq)
			.order('posicio', { ascending: true });
		if (e) throw e;
		return (data ?? []) as RankEntry[];
	}

	async function ensureLoaded(mod: Mod) {
		const need =
			mod === 'global' ? modalitats.map((m) => m.codi_fcb) : [mod as number];
		const missing = need.filter((c) => !entriesByMod.has(c));
		if (!missing.length) return;
		loading = true;
		try {
			const fetched = await Promise.all(missing.map((c) => fetchMod(c)));
			const next = new Map(entriesByMod);
			missing.forEach((c, i) => next.set(c, fetched[i]));
			entriesByMod = next;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	async function pickMod(m: Mod) {
		if (m === selMod) return;
		selMod = m;
		selectedClub = null;
		await ensureLoaded(m);
	}

	// Jugadors amb nivell segons la modalitat seleccionada (o global).
	const players = $derived.by<PlayerNivell[]>(() => {
		if (selMod === 'global') {
			const all = modalitats
				.map((m) => entriesByMod.get(m.codi_fcb))
				.filter((x): x is RankEntry[] => !!x);
			return bestNivellAcrossModalities(all);
		}
		return playersWithNivell(entriesByMod.get(selMod) ?? []);
	});

	// Nombre de jugadors del camp de referència (per contextualitzar el percentil).
	const fieldSize = $derived(
		selMod === 'global' ? players.length : (entriesByMod.get(selMod as number)?.length ?? 0)
	);

	const clubs = $derived(rankClubs(buildClubIndexes(players, K), w));
	const detail = $derived(clubs.find((c) => c.club === selectedClub) ?? null);

	function short(name: string): string {
		return name.replace(/^(C\.?B\.?|B\.?C\.?|S\.?B\.?)\s*/i, '').trim() || name;
	}
</script>

<svelte:head><title>Anàlisi de Clubs · FCBillar</title></svelte:head>

<div class="mb-3">
	<h1 class="text-lg font-bold leading-tight md:text-xl">Anàlisi de Clubs</h1>
	<p class="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
		Índex de qualitat a partir del <strong>nivell</strong> dels jugadors (percentil de la seva
		posició al rànquing, comparable entre modalitats). Cada club té dos eixos: <strong>Potència</strong>
		(mitjana dels {K} millors) i <strong>Profunditat</strong> (massa de jugadors per damunt de la
		mediana).
	</p>
</div>

<!-- Controls -->
<div class="mb-4 space-y-3 rounded-xl bg-white p-3 ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
	<div class="flex flex-wrap gap-1.5">
		<button
			onclick={() => pickMod('global')}
			class="rounded-full px-3 py-1 text-sm font-medium {selMod === 'global'
				? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
				: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}">Global</button
		>
		{#each modalitats as m}
			<button
				onclick={() => pickMod(m.codi_fcb)}
				class="rounded-full px-3 py-1 text-sm font-medium {selMod === m.codi_fcb
					? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
					: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}">{m.nom}</button
			>
		{/each}
	</div>
	<div class="grid gap-3 sm:grid-cols-2">
		<label class="block">
			<span class="text-xs font-semibold text-slate-500 dark:text-slate-400"
				>Mida d'equip (K): <span class="font-mono text-slate-900 dark:text-slate-100">{K}</span></span
			>
			<input type="range" min="2" max="8" step="1" bind:value={K} class="mt-1 w-full accent-emerald-600" />
		</label>
		<label class="block">
			<span class="text-xs font-semibold text-slate-500 dark:text-slate-400"
				>Pes al CQI: <span class="font-mono text-slate-900 dark:text-slate-100">{Math.round(w * 100)}%</span>
				Potència · {Math.round((1 - w) * 100)}% Profunditat</span
			>
			<input type="range" min="0" max="1" step="0.05" bind:value={w} class="mt-1 w-full accent-emerald-600" />
		</label>
	</div>
</div>

{#if error}
	<p class="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
{:else if !clubs.length}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Sense dades per a aquesta modalitat.</p>
{:else}
	<div class="mb-1 px-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">
		{modLabel} · {clubs.length} clubs · {fieldSize} jugadors al camp
	</div>
	<div class="mb-4 rounded-xl bg-white p-2 ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
		<ClubScatter {clubs} selected={selectedClub} onselect={(c) => (selectedClub = c)} />
		<p class="px-1 pb-1 text-center text-[11px] text-slate-400 dark:text-slate-500">
			Cada bombolla és un club (mida = jugadors rankejats). Toca'n una per veure'n la plantilla.
		</p>
	</div>

	<!-- Rànquing de clubs -->
	<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
		{#each clubs as c, i (c.club)}
			<li class="border-b border-slate-100 last:border-0 dark:border-slate-800">
				<button
					onclick={() => (selectedClub = selectedClub === c.club ? null : c.club)}
					class="flex w-full items-center gap-2.5 px-3 py-2 text-left {selectedClub === c.club
						? 'bg-emerald-50/60 dark:bg-emerald-950/20'
						: ''}"
				>
					<span class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums text-slate-400 dark:text-slate-500">{i + 1}</span>
					<div class="min-w-0 flex-1">
						<div class="truncate text-sm font-semibold leading-tight">{short(c.club)}</div>
						<div class="mt-1 flex items-center gap-2">
							<div class="flex flex-1 items-center gap-1">
								<span class="w-8 shrink-0 text-[9px] font-medium text-emerald-600 dark:text-emerald-400">POT</span>
								<span class="h-1.5 flex-1 overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
									<span class="block h-full rounded bg-emerald-500" style="width:{c.potencia}%"></span>
								</span>
								<span class="w-7 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-500 dark:text-slate-400">{c.potencia.toFixed(0)}</span>
							</div>
							<div class="flex flex-1 items-center gap-1">
								<span class="w-8 shrink-0 text-[9px] font-medium text-sky-600 dark:text-sky-400">PROF</span>
								<span class="h-1.5 flex-1 overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
									<span class="block h-full rounded bg-sky-500" style="width:{c.depthScore}%"></span>
								</span>
								<span class="w-7 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-500 dark:text-slate-400">{c.depthCount}</span>
							</div>
						</div>
					</div>
					<div class="shrink-0 text-right">
						<div class="font-mono text-base font-bold tabular-nums leading-none">{c.cqi.toFixed(1)}</div>
						<div class="text-[9px] uppercase tracking-wide text-slate-400 dark:text-slate-500">CQI · {c.n}j</div>
					</div>
				</button>

				{#if selectedClub === c.club}
					<div class="border-t border-slate-100 bg-slate-50/60 px-3 py-2 dark:border-slate-800 dark:bg-slate-950/30">
						<div class="mb-1.5 flex items-center justify-between">
							<span class="text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">Plantilla · per nivell</span>
							{#if clubFcb.get(c.club)}
								<a href="/club/{clubFcb.get(c.club)}" class="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">Fitxa del club ↗</a>
							{/if}
						</div>
						<ul class="space-y-0.5">
							{#each c.players.slice(0, 12) as p, pi (p.fcb_id)}
								<li class="flex items-center gap-2 text-sm">
									<span class="w-4 shrink-0 text-center text-[10px] tabular-nums text-slate-400 dark:text-slate-500">{pi + 1}</span>
									{#if pi < K}<span class="shrink-0 rounded bg-emerald-100 px-1 text-[9px] font-bold text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300">TOP{K}</span>{/if}
									<a href="/jugador/{p.fcb_id}" class="min-w-0 flex-1 truncate active:underline">{p.nom}</a>
									{#if selMod !== 'global' && p.mitjana != null}
										<span class="shrink-0 font-mono text-[11px] tabular-nums text-slate-400 dark:text-slate-500">{p.mitjana.toFixed(3)}</span>
									{/if}
									<span class="w-8 shrink-0 text-right font-mono text-xs font-semibold tabular-nums">{p.nivell.toFixed(0)}</span>
								</li>
							{/each}
							{#if c.players.length > 12}
								<li class="pl-6 pt-0.5 text-[11px] text-slate-400 dark:text-slate-500">+{c.players.length - 12} més</li>
							{/if}
						</ul>
					</div>
				{/if}
			</li>
		{/each}
	</ul>

	<p class="mt-3 px-1 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500">
		<strong>Nivell</strong> = percentil de la posició al rànquing (100 = primer). <strong>Potència</strong>
		= mitjana dels {K} millors nivells. <strong>Profunditat</strong> = jugadors per damunt de la mediana
		del camp (la barra n'és la massa relativa). <strong>CQI</strong> = {Math.round(w * 100)}%·Potència +
		{Math.round((1 - w) * 100)}%·Profunditat. Prototip calculat en directe sobre el darrer rànquing
		publicat de cada modalitat.
	</p>
{/if}
