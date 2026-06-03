<script lang="ts">
	import { api } from '$lib/opens/api';
	import type {
		DiffDiscrepancy,
		DiffKind,
		DiffOverrideDecision,
		DiffReportResponse
	} from '$lib/opens/types';

	let report = $state<DiffReportResponse | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	// Tracks whether the user explicitly asked to bypass the cache. The
	// initial load reuses the 1h PDF cache; the "Refresca" button forces
	// a fresh fetch.
	let lastForce = $state(false);
	// Per-row "saving" flags so we can show feedback without blocking other rows.
	let savingKey = $state<string | null>(null);
	// Free-text note buffer per discrepancy (keyed by player+kind). Persists
	// only in this view session.
	let noteByKey = $state<Record<string, string>>({});
	let openSetExpanded = $state(false);

	async function loadDiff(force: boolean) {
		loading = true;
		error = null;
		lastForce = force;
		try {
			report = await api.getOfficialDiff({ force });
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		// Initial load on mount; reuses the cache.
		if (report === null && !loading && error === null) {
			loadDiff(false);
		}
	});

	function rowKey(d: DiffDiscrepancy): string {
		return `${d.player.display_name}::${d.kind}`;
	}

	async function setDecision(d: DiffDiscrepancy, decision: DiffOverrideDecision) {
		const key = rowKey(d);
		savingKey = key;
		try {
			const note = noteByKey[key] ?? d.override?.note ?? null;
			const saved = await api.upsertDiffOverride({
				player_name: d.player.display_name,
				discrepancy_kind: d.kind,
				decision,
				note: note && note.length > 0 ? note : null,
				official_total: d.official_total,
				computed_total: d.computed_total
			});
			// Mutate the existing row in place so the UI updates without a full reload.
			d.override = saved;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			savingKey = null;
		}
	}

	async function clearDecision(d: DiffDiscrepancy) {
		const key = rowKey(d);
		savingKey = key;
		try {
			const targetKind = d.override?.discrepancy_kind ?? d.kind;
			await api.deleteDiffOverride(d.player.display_name, targetKind);
			d.override = null;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			savingKey = null;
		}
	}

	const KIND_META: Record<
		DiffKind,
		{ label: string; severity: 'error' | 'warning' | 'info' | 'ok'; description: string }
	> = {
		matched: {
			label: 'Coincidents',
			severity: 'ok',
			description: 'Mateix total i posició al PDF i al càlcul.'
		},
		position_only: {
			label: 'Diferència de posició',
			severity: 'warning',
			description:
				'Mateix total però posició diferent — possible diferència en l\'algorisme de tiebreak.'
		},
		total_points: {
			label: 'Diferència de punts',
			severity: 'error',
			description:
				'El PDF i el càlcul difereixen en el total. Bug real — cal investigar.'
		},
		per_open: {
			label: 'Diferència per Open',
			severity: 'error',
			description:
				'Mateix total però per-Open diferent — l\'agregació coincideix per casualitat.'
		},
		penalty_expected: {
			label: 'Penalitzacions -20 (estructural)',
			severity: 'info',
			description:
				'Diferència explicada per penalitzacions -20 al PDF que la BD no emmagatzema. No és un bug.'
		},
		penalty_cascade: {
			label: 'Cascada de penalitzacions',
			severity: 'info',
			description:
				'Petites diferències per desplaçament de posicions causat per -20 dels jugadors superiors.'
		},
		position_cascade: {
			label: 'Cascada de posicions',
			severity: 'info',
			description:
				'POSITION_ONLY explicat completament per intruders/extruders amb anomalia upstream.'
		},
		source_mismatch: {
			label: 'Discrepància de font',
			severity: 'info',
			description:
				'PDF i HTML atribueixen les participacions del jugador a Opens diferents (problema FCB).'
		},
		missing_in_official: {
			label: 'Absent del PDF oficial',
			severity: 'warning',
			description: 'Jugador present al càlcul però no al PDF oficial.'
		},
		missing_in_computed: {
			label: 'Absent del càlcul',
			severity: 'warning',
			description: 'Jugador al PDF oficial però no a la BD local.'
		}
	};

	const KIND_ORDER: DiffKind[] = [
		'total_points',
		'per_open',
		'position_only',
		'missing_in_computed',
		'missing_in_official',
		'position_cascade',
		'penalty_cascade',
		'penalty_expected',
		'source_mismatch'
	];

	function severityClass(sev: 'error' | 'warning' | 'info' | 'ok'): string {
		switch (sev) {
			case 'error':
				return 'border-l-red-500';
			case 'warning':
				return 'border-l-amber-500';
			case 'info':
				return 'border-l-blue-500';
			default:
				return 'border-l-emerald-500';
		}
	}

	function severityBadge(sev: 'error' | 'warning' | 'info' | 'ok'): string {
		switch (sev) {
			case 'error':
				return 'badge-error';
			case 'warning':
				return 'badge-warn';
			case 'info':
				return 'badge-info';
			default:
				return 'badge-ok';
		}
	}

	const groupedDiscrepancies = $derived.by<Record<DiffKind, DiffDiscrepancy[]>>(() => {
		const out: Record<string, DiffDiscrepancy[]> = {};
		for (const d of report?.discrepancies ?? []) {
			if (!out[d.kind]) out[d.kind] = [];
			out[d.kind].push(d);
		}
		return out as Record<DiffKind, DiffDiscrepancy[]>;
	});

	const decisionCounts = $derived.by(() => {
		const counts = { keep_computed: 0, use_official: 0, dismissed: 0, none: 0 };
		for (const d of report?.discrepancies ?? []) {
			if (d.override) counts[d.override.decision] += 1;
			else counts.none += 1;
		}
		return counts;
	});

	function fmtTotal(n: number | null): string {
		return n === null ? '—' : String(n);
	}

	function fmtPos(n: number | null): string {
		return n === null ? '—' : `#${n}`;
	}

	function decisionLabel(decision: DiffOverrideDecision): string {
		switch (decision) {
			case 'keep_computed':
				return 'Manté calc';
			case 'use_official':
				return 'Força PDF';
			case 'dismissed':
				return 'Descarta';
		}
	}

	function decisionBadge(decision: DiffOverrideDecision): string {
		switch (decision) {
			case 'keep_computed':
				return 'badge-info';
			case 'use_official':
				return 'badge-warn';
			case 'dismissed':
				return 'badge-ok';
		}
	}

	function effectiveTotal(d: DiffDiscrepancy): number | null {
		// Apply the override's preferred side if set.
		if (d.override?.decision === 'use_official') return d.official_total;
		if (d.override?.decision === 'keep_computed') return d.computed_total;
		return d.computed_total;
	}

	function overrideStale(d: DiffDiscrepancy): boolean {
		// True when the user's saved decision was based on totals different
		// from the ones we're currently showing. They probably want to revisit.
		const ov = d.override;
		if (!ov) return false;
		if (ov.discrepancy_kind !== d.kind) return true;
		if (ov.official_total !== d.official_total) return true;
		if (ov.computed_total !== d.computed_total) return true;
		return false;
	}
</script>

<div class="mb-4 flex flex-wrap items-baseline justify-between gap-3">
	<div>
		<h1 class="text-2xl font-semibold">Validació oficial</h1>
		<p class="mt-1 text-sm text-slate-500">
			Comparació del rànquing d'Opens calculat localment contra el PDF oficial publicat
			per la FCB. Anomalies classificades segons la taxonomia
			<code class="text-xs">diff.py</code>. Per cada discrepància pots forçar quin
			valor val (calcul o PDF) o descartar-la.
		</p>
	</div>
	<div class="flex gap-2">
		<button
			class="btn-secondary"
			onclick={() => loadDiff(false)}
			disabled={loading}
		>
			{loading && !lastForce ? 'Carregant…' : 'Recarregar (cache)'}
		</button>
		<button
			class="btn-primary"
			onclick={() => loadDiff(true)}
			disabled={loading}
		>
			{loading && lastForce ? 'Refrescant PDF…' : 'Refrescar PDF FCB'}
		</button>
	</div>
</div>

{#if error}
	<div class="card mb-6 border-red-200 bg-red-50 text-red-800">
		<p class="font-medium">Error</p>
		<p class="mt-1 text-sm">{error}</p>
	</div>
{/if}

{#if report}
	<!-- Open-set comparison panel: must be the first thing the user checks. -->
	<section class="mb-6">
		<div
			class="card border-l-4 {report.opens_set_match
				? 'border-l-emerald-500 bg-emerald-50'
				: 'border-l-red-500 bg-red-50'}"
		>
			<div class="flex flex-wrap items-baseline justify-between gap-3">
				<div>
					<p class="font-semibold">
						{#if report.opens_set_match}
							✓ El conjunt d'Opens coincideix
						{:else}
							⚠ El conjunt d'Opens NO coincideix
						{/if}
					</p>
					<p class="mt-1 text-xs text-slate-700">
						PDF: {report.official_opens.length} opens · Càlcul: {report.computed_opens.length} opens.
						{#if !report.opens_set_match}
							La comparació de punts és <strong>només significativa si totes dues
							fonts cobreixen els mateixos Opens</strong>. Sincronitza les dades FCB i refresca
							el PDF si cal.
						{/if}
					</p>
				</div>
				<button
					class="btn-secondary text-xs"
					onclick={() => (openSetExpanded = !openSetExpanded)}
				>
					{openSetExpanded ? 'Amaga detall' : 'Veure detall'}
				</button>
			</div>

			{#if openSetExpanded}
				<div class="mt-4 grid gap-4 md:grid-cols-2">
					<div>
						<p class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-600">
							Opens al PDF oficial
						</p>
						<ol class="space-y-1 text-xs">
							{#each report.official_opens as o}
								<li class="rounded bg-white px-2 py-1">
									<span class="font-mono text-slate-500">{o.index + 1}.</span>
									<strong class="ml-1">{o.label}</strong>
									<span class="ml-1 text-slate-600">{o.name}</span>
									{#if o.season}<span class="ml-1 text-slate-500">({o.season})</span>{/if}
								</li>
							{/each}
						</ol>
					</div>
					<div>
						<p class="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-600">
							Opens utilitzats pel càlcul (BD local)
						</p>
						<ol class="space-y-1 text-xs">
							{#each report.computed_opens as o}
								<li class="rounded bg-white px-2 py-1">
									<span class="font-mono text-slate-500">{o.index + 1}.</span>
									<strong class="ml-1">{o.name}</strong>
									{#if o.fcb_division_id !== null}
										<span class="ml-1 font-mono text-slate-400">
											(div #{o.fcb_division_id})
										</span>
									{/if}
									{#if o.season}<span class="ml-1 text-slate-500">{o.season}</span>{/if}
								</li>
							{/each}
						</ol>
					</div>
				</div>
			{/if}
		</div>
	</section>

	<!-- Summary -->
	<section class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
		<div class="card">
			<p class="text-xs uppercase tracking-wider text-slate-500">Coincidents</p>
			<p class="mt-1 text-2xl font-semibold text-emerald-700">{report.matched_count}</p>
			<p class="mt-1 text-xs text-slate-500">de {report.official_size} oficials</p>
		</div>
		<div class="card">
			<p class="text-xs uppercase tracking-wider text-slate-500">Discrepàncies</p>
			<p class="mt-1 text-2xl font-semibold">{report.discrepancies.length}</p>
			<p class="mt-1 text-xs text-slate-500">
				{decisionCounts.none} pendents
			</p>
		</div>
		<div class="card">
			<p class="text-xs uppercase tracking-wider text-slate-500">Decisions</p>
			<p class="mt-1 text-sm">
				<span class="badge-info">calc {decisionCounts.keep_computed}</span>
				<span class="ml-1 badge-warn">PDF {decisionCounts.use_official}</span>
				<span class="ml-1 badge-ok">desc. {decisionCounts.dismissed}</span>
			</p>
		</div>
		<div class="card">
			<p class="text-xs uppercase tracking-wider text-slate-500">Última comparació</p>
			<p class="mt-1 text-sm font-mono text-slate-600">
				{new Date(report.fetched_at).toLocaleString('ca-ES')}
			</p>
		</div>
	</section>

	<!-- Counts table -->
	<section class="mb-6">
		<h2 class="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-500">
			Distribució per categoria
		</h2>
		<div class="card p-0">
			<table class="table-clean">
				<thead>
					<tr>
						<th>Categoria</th>
						<th class="text-right">Comptatge</th>
						<th>Severitat</th>
						<th>Descripció</th>
					</tr>
				</thead>
				<tbody>
					{#each KIND_ORDER as kind}
						{@const count = report.counts_by_kind[kind] ?? 0}
						{#if count > 0}
							<tr>
								<td class="font-medium">
									<a href="#kind-{kind}" class="hover:underline">{KIND_META[kind].label}</a>
								</td>
								<td class="text-right font-mono">{count}</td>
								<td>
									<span class={severityBadge(KIND_META[kind].severity)}>
										{KIND_META[kind].severity}
									</span>
								</td>
								<td class="text-xs text-slate-600">{KIND_META[kind].description}</td>
							</tr>
						{/if}
					{/each}
					{#if report.discrepancies.length === 0}
						<tr>
							<td colspan="4" class="py-4 text-center text-sm text-emerald-700">
								Sense discrepàncies — el càlcul coincideix exactament amb el PDF oficial.
							</td>
						</tr>
					{/if}
				</tbody>
			</table>
		</div>
		<p class="mt-2 text-xs text-slate-500">
			Font: <a
				href={report.official_source}
				target="_blank"
				rel="noopener noreferrer"
				class="text-slate-700 hover:underline"
			>
				PDF oficial FCB
			</a>
		</p>
	</section>

	<!-- Per-kind drill-down -->
	{#each KIND_ORDER as kind}
		{@const items = groupedDiscrepancies[kind] ?? []}
		{#if items.length > 0}
			<section id="kind-{kind}" class="mb-6 scroll-mt-4">
				<div class="mb-3 flex items-baseline gap-3">
					<span class={severityBadge(KIND_META[kind].severity)}>
						{KIND_META[kind].severity}
					</span>
					<h2 class="text-lg font-semibold">{KIND_META[kind].label}</h2>
					<span class="text-sm text-slate-500">({items.length})</span>
				</div>
				<p class="mb-3 text-xs text-slate-500">{KIND_META[kind].description}</p>

				<div class="card border-l-4 p-0 {severityClass(KIND_META[kind].severity)}">
					<table class="table-clean">
						<thead>
							<tr>
								<th class="w-14">PDF</th>
								<th class="w-14">Calc</th>
								<th>Jugador</th>
								<th class="text-right">PDF tot.</th>
								<th class="text-right">Calc tot.</th>
								<th class="text-right">Δ</th>
								<th class="text-right">Efectiu</th>
								<th>Decisió</th>
								<th>Detalls</th>
							</tr>
						</thead>
						<tbody>
							{#each items as d}
								{@const key = rowKey(d)}
								{@const delta =
									d.official_total !== null && d.computed_total !== null
										? d.official_total - d.computed_total
										: null}
								{@const ov = d.override}
								{@const stale = overrideStale(d)}
								<tr class={ov ? 'bg-slate-50' : ''}>
									<td class="font-mono text-slate-500">{fmtPos(d.official_position)}</td>
									<td class="font-mono text-slate-500">{fmtPos(d.computed_position)}</td>
									<td class="font-medium">
										{#if d.player.player_id !== null}
											<a href="/players/{d.player.player_id}" class="hover:underline">
												{d.player.display_name}
											</a>
										{:else}
											{d.player.display_name}
										{/if}
										{#if d.player.club}
											<span class="ml-1 text-xs text-slate-500">{d.player.club}</span>
										{/if}
									</td>
									<td class="text-right font-mono">{fmtTotal(d.official_total)}</td>
									<td class="text-right font-mono">{fmtTotal(d.computed_total)}</td>
									<td
										class="text-right font-mono {delta !== null && delta !== 0
											? 'text-amber-700'
											: 'text-slate-400'}"
									>
										{delta === null ? '—' : delta > 0 ? `+${delta}` : delta}
									</td>
									<td
										class="text-right font-mono {ov?.decision === 'use_official'
											? 'font-semibold text-amber-700'
											: ov?.decision === 'keep_computed'
												? 'font-semibold text-blue-700'
												: 'text-slate-500'}"
									>
										{fmtTotal(effectiveTotal(d))}
									</td>
									<td>
										<div class="flex flex-wrap items-center gap-1">
											{#if ov}
												<span class={decisionBadge(ov.decision)}
													>{decisionLabel(ov.decision)}</span
												>
												{#if stale}
													<span
														class="badge-warn"
														title="La discrepància ha canviat des de la decisió"
														>obsolet</span
													>
												{/if}
												<button
													class="text-xs text-slate-500 hover:text-red-600"
													onclick={() => clearDecision(d)}
													disabled={savingKey === key}
													title="Esborrar decisió"
												>
													✕
												</button>
											{:else}
												<div class="flex flex-wrap gap-1">
													<button
														class="rounded border border-blue-300 bg-blue-50 px-2 py-0.5 text-xs text-blue-800 hover:bg-blue-100 disabled:opacity-50"
														onclick={() => setDecision(d, 'keep_computed')}
														disabled={savingKey === key}
													>
														Manté calc
													</button>
													<button
														class="rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs text-amber-800 hover:bg-amber-100 disabled:opacity-50"
														onclick={() => setDecision(d, 'use_official')}
														disabled={savingKey === key}
													>
														Força PDF
													</button>
													<button
														class="rounded border border-slate-300 bg-slate-50 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-50"
														onclick={() => setDecision(d, 'dismissed')}
														disabled={savingKey === key}
													>
														Descarta
													</button>
												</div>
											{/if}
										</div>
									</td>
									<td class="text-xs text-slate-600">
										<div>{d.details}</div>
										{#if ov?.note}
											<div class="mt-1 italic text-slate-700">"{ov.note}"</div>
										{/if}
										{#if !ov}
											<input
												type="text"
												placeholder="Nota (opcional)"
												bind:value={noteByKey[key]}
												class="mt-1 w-full rounded border-slate-300 text-xs"
											/>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}
	{/each}
{:else if loading}
	<div class="card">
		<p class="text-sm text-slate-500">
			Carregant PDF oficial i calculant rànquing… La primera càrrega pot trigar uns segons.
		</p>
	</div>
{/if}
