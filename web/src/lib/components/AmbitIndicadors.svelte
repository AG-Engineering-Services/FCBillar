<script lang="ts">
	// Indicadors i competicions d'un jugador a Espanya o a l'estranger. Les dades
	// arriben ja filtrades per modalitat; aquí només es calcula i s'ensenya.
	import {
		competicions,
		indicadors,
		nomTipus,
		resultatDe,
		temporadaActual,
		type DadesExternes
	} from '$lib/externes';
	import { temporadaCurta } from '$lib/nacional';

	let {
		dades,
		ambit,
		rival = null,
		kiosk = false
	}: {
		dades: DadesExternes;
		ambit: 'espanya' | 'internacional';
		/** Clau del rival triat al filtre «Partides contra»: només les seves partides. */
		rival?: string | null;
		kiosk?: boolean;
	} = $props();

	const temporada = temporadaActual();
	const kpi = $derived(indicadors(dades, ambit));
	const kpiTemporada = $derived(indicadors(dades, ambit, temporada));
	const totes = $derived(competicions(dades, ambit));
	const llista = $derived(
		rival
			? totes
					.map((c) => ({ ...c, partides: c.partides.filter((p) => (p.rival_fcb_id ?? p.rival) === rival) }))
					.filter((c) => c.partides.length)
			: totes
	);
	let mostrades = $state(8);

	const xifra = (v: number | null, decimals = 3) => (v == null ? '—' : v.toFixed(decimals));
	const nomAmbit = $derived(ambit === 'espanya' ? 'Espanya' : 'Internacional');
	const fmtData = (d: string | null) => (d ? d.split('-').reverse().join('/') : '');
</script>

<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
	<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Històric · {nomAmbit}</div>
	{#if kpi.n || kpi.mitjana}
		<div class="grid grid-cols-5 gap-2">
			{#each [['Partides', kpi.n || '—'], ['Mitjana', xifra(kpi.mitjana || null)], ['Sèrie màx', kpi.sm ?? '—'], ['% vict.', kpi.w + kpi.e + kpi.l ? kpi.pct + '%' : '—'], [kpi.bestN > 1 ? `Millor mitj. ×${kpi.bestN}` : 'Millor mitj.', xifra(kpi.best)]] as [label, val]}
				<div class="py-0.5 text-center">
					<div class="font-mono text-base font-bold tabular-nums">{val}</div>
					<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
				</div>
			{/each}
		</div>
		<p class="mt-2 px-1 text-[11px] text-slate-500 dark:text-slate-400">
			{kpi.w} G · {kpi.l} P{kpi.e ? ` · ${kpi.e} E` : ''}
		</p>
		{#if kpi.senseDetall}
			<p class="mt-1 px-1 text-[11px] text-slate-500 dark:text-slate-400">
				{kpi.senseDetall === 1 ? "D'un campionat" : `De ${kpi.senseDetall} campionats`} la RFEB només publica les caramboles i les entrades: compten per a la mitjana, no per a les partides ni el % de victòries.
			</p>
		{/if}
	{:else}
		<p class="px-1 text-sm text-slate-500 dark:text-slate-400">Cap partida d'aquesta modalitat.</p>
	{/if}
</div>

{#if kpiTemporada.n || kpiTemporada.mitjana}
	<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
		<div class="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Temporada actual · {nomAmbit}</div>
		<div class="grid grid-cols-4 gap-2">
			{#each [['Partides', kpiTemporada.n || '—'], ['Mitjana', xifra(kpiTemporada.mitjana || null)], ['Sèrie màx', kpiTemporada.sm ?? '—'], ['% vict.', kpiTemporada.w + kpiTemporada.e + kpiTemporada.l ? kpiTemporada.pct + '%' : '—']] as [label, val]}
				<div class="text-center">
					<div class="font-mono text-base font-bold tabular-nums">{val}</div>
					<div class="text-2xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
				</div>
			{/each}
		</div>
		<p class="mt-2 px-1 text-[11px] text-slate-500 dark:text-slate-400">
			{kpiTemporada.w} G · {kpiTemporada.l} P{kpiTemporada.e ? ` · ${kpiTemporada.e} E` : ''}
		</p>
	</div>
{/if}

{#if llista.length}
	<div class="mb-4 rounded-xl bg-white p-3 ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
		<div class="text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
			{ambit === 'espanya' ? "Campionats d'Espanya" : 'Europeus, Mundials i Copes del Món'}
		</div>
		<p class="mb-2 text-2xs text-slate-500 dark:text-slate-400">
			{ambit === 'espanya'
				? 'RFEB. La Lliga Nacional és al seu apartat.'
				: 'CEB i UMB.'} No compta per als rànquings, les mitjanes ni els gràfics catalans.
		</p>
		<div class="space-y-3">
			{#each llista.slice(0, mostrades) as c (c.clau)}
				<section>
					<div class="mb-1 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
						<h3 class="min-w-0 text-sm font-semibold leading-tight">
							{temporadaCurta(c.temporada)} · {nomTipus(c.tipus)} · {c.nom}
						</h3>
						<p class="whitespace-nowrap text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
							{#if c.posicio != null}{c.posicio}a posició · {/if}{#if c.resum.n != null}{c.resum.n} PJ · {c.resum.w}-{c.resum.e}-{c.resum.l} · {/if}<span class="font-mono font-bold">{xifra(c.resum.mitjana)}</span>
						</p>
					</div>
					{#if c.partides.length}
						<div class="overflow-hidden rounded-lg ring-1 ring-slate-200 dark:ring-slate-800">
							<table class="w-full text-sm">
								<caption class="sr-only">Partides de {c.nom}</caption>
								<thead class="print-only bg-slate-50 text-left text-2xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
									<tr>
										<th scope="col" class="px-3 py-1.5 font-medium">Res.</th>
										<th scope="col" class="px-3 py-1.5 font-medium">Rival · Fase</th>
										<th scope="col" class="px-3 py-1.5 text-right font-medium">Marcador</th>
										<th scope="col" class="px-3 py-1.5 text-right font-medium">Mitjana</th>
									</tr>
								</thead>
								<tbody>
									{#each c.partides as p (p.ordre)}
										{@const res = resultatDe(p)}
										<tr class="border-b border-slate-100 last:border-b-0 dark:border-slate-800">
											<td class="w-8 px-2 py-2 text-center sm:px-3">
												<span
													class="inline-block w-6 rounded text-center text-xs font-bold {res === 'E'
														? 'text-slate-500 dark:text-slate-400'
														: res === 'G'
															? 'text-emerald-600 dark:text-emerald-400'
															: 'text-red-500 dark:text-red-400'}">{res}</span
												>
											</td>
											<td class="w-full max-w-0 px-2 py-2 sm:px-3">
												{#if p.rival_fcb_id && !kiosk}
													<a
														href="/jugador/{p.rival_fcb_id}"
														class="block truncate text-sm font-medium leading-tight underline-offset-2 active:underline">{p.rival}</a
													>
												{:else}
													<div class="truncate text-sm leading-tight">{p.rival}{p.nacio_rival ? ` (${p.nacio_rival})` : ''}</div>
												{/if}
												<div class="truncate text-[11px] text-slate-500 dark:text-slate-400">
													{#if p.data}{fmtData(p.data)} · {/if}{p.fase}{p.grup && p.grup !== p.fase ? ` · ${p.grup}` : ''}
												</div>
											</td>
											<td class="whitespace-nowrap px-2 py-2 text-right font-mono text-sm tabular-nums sm:px-3">{p.caramboles ?? '—'}–{p.caramboles_rival ?? '—'}</td>
											<td class="whitespace-nowrap px-2 py-2 text-right text-[11px] tabular-nums text-slate-500 dark:text-slate-400 sm:px-3">
												{p.entrades ? `${((p.caramboles ?? 0) / p.entrades).toFixed(3)} · ${p.entrades} ent.` : '—'}{p.serie != null ? ` · SM ${p.serie}` : ''}
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{/if}
				</section>
			{/each}
		</div>
		{#if llista.length > mostrades}
			<button
				type="button"
				onclick={() => (mostrades += 8)}
				class="mt-2 min-h-11 w-full rounded-lg bg-white py-2 text-sm font-medium text-slate-600 ring-1 ring-slate-200 active:bg-slate-50 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-800 dark:active:bg-slate-800/50 print:hidden"
			>
				Carregar més ({mostrades} de {llista.length})
			</button>
		{/if}
	</div>
{/if}
