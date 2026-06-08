<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type Modalitat, type Snapshot, type RankingRow } from '$lib/supabase';

	let modalitats = $state<Modalitat[]>([]);
	let snapshots = $state<Snapshot[]>([]);
	let rows = $state<RankingRow[]>([]);
	let selMod = $state<number | null>(null);
	let selSeq = $state<number | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let search = $state('');

	function norm(s: string): string {
		return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}

	const MESOS = [
		'gener', 'febrer', 'març', 'abril', 'maig', 'juny',
		'juliol', 'agost', 'setembre', 'octubre', 'novembre', 'desembre'
	];
	function snapLabel(s: Snapshot): string {
		if (s.mes_pub && s.any_pub) {
			const m = MESOS[s.mes_pub - 1] ?? String(s.mes_pub);
			return `${m.charAt(0).toUpperCase()}${m.slice(1)} ${s.any_pub}`;
		}
		return `Rànquing #${s.num_seq}`;
	}
	const filtered = $derived(
		search.trim()
			? rows.filter(
					(r) =>
						norm(r.jugador).includes(norm(search.trim())) ||
						norm(r.club ?? '').includes(norm(search.trim()))
				)
			: rows
	);

	onMount(async () => {
		try {
			const { data, error: e } = await supabase
				.from('modalitats')
				.select('codi_fcb, nom')
				.order('codi_fcb');
			if (e) throw e;
			modalitats = data ?? [];
			selMod = modalitats.find((m) => m.codi_fcb === 1)?.codi_fcb ?? modalitats[0]?.codi_fcb ?? null;
			await loadSnapshots();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	async function loadSnapshots() {
		if (selMod == null) return;
		const { data, error: e } = await supabase
			.from('rankings')
			.select('num_seq, any_pub, mes_pub')
			.eq('modalitat_codi', selMod)
			.order('num_seq', { ascending: false });
		if (e) {
			error = e.message;
			return;
		}
		snapshots = data ?? [];
		selSeq = snapshots[0]?.num_seq ?? null;
		await loadRows();
	}

	async function loadRows() {
		if (selMod == null || selSeq == null) {
			rows = [];
			return;
		}
		loading = true;
		const { data, error: e } = await supabase
			.from('ranking_full')
			.select('posicio, player_fcb_id, jugador, club, mitjana_general, partides')
			.eq('modalitat_codi', selMod)
			.eq('num_seq', selSeq)
			.order('posicio', { ascending: true });
		loading = false;
		if (e) {
			error = e.message;
			return;
		}
		rows = (data ?? []) as RankingRow[];
	}

	async function pickMod(codi: number) {
		if (codi === selMod) return;
		selMod = codi;
		search = '';
		await loadSnapshots();
	}
	async function pickSeq(e: Event) {
		selSeq = Number((e.target as HTMLSelectElement).value);
		await loadRows();
	}
</script>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
		{error}
	</div>
{/if}

<!-- Modalitats: xips amb scroll horitzontal -->
<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
	{#each modalitats as m}
		<button
			onclick={() => pickMod(m.codi_fcb)}
			class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors {m.codi_fcb ===
			selMod
				? 'bg-slate-900 text-white'
				: 'bg-white text-slate-600 ring-1 ring-slate-200'}"
		>
			{m.nom}
		</button>
	{/each}
</div>

<!-- Selector de rànquing + cerca -->
<div class="mb-3 flex items-center gap-2">
	<select
		onchange={pickSeq}
		value={selSeq}
		class="rounded-lg border-slate-300 bg-white py-2 pl-3 pr-8 text-sm shadow-sm"
	>
		{#each snapshots as s}
			<option value={s.num_seq}>{snapLabel(s)}</option>
		{/each}
	</select>
	<input
		bind:value={search}
		inputmode="search"
		placeholder="Cerca jugador o club…"
		class="min-w-0 flex-1 rounded-lg border-slate-300 bg-white py-2 px-3 text-sm shadow-sm"
	/>
</div>

{#if loading}
	<p class="px-1 py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if filtered.length === 0}
	<p class="px-1 py-6 text-center text-sm text-slate-400">Sense resultats.</p>
{:else}
	<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200 lg:columns-2 lg:gap-x-6">
		{#each filtered as r (r.player_fcb_id + '-' + r.posicio)}
			<li class="break-inside-avoid border-b border-slate-100 last:border-0">
				<a
					href="/jugador/{r.player_fcb_id}"
					class="flex items-center gap-3 px-3 py-2.5 active:bg-slate-50"
				>
					<span
						class="w-7 shrink-0 text-center text-sm font-semibold tabular-nums text-slate-400"
					>{r.posicio ?? '—'}</span>
					<div class="min-w-0 flex-1">
						<div class="truncate text-sm font-medium leading-tight">{r.jugador}</div>
						{#if r.club}<div class="truncate text-xs text-slate-400">{r.club}</div>{/if}
					</div>
					<span class="shrink-0 font-mono text-sm font-semibold tabular-nums">
						{r.mitjana_general != null ? r.mitjana_general.toFixed(3) : '—'}
					</span>
					<span class="shrink-0 text-slate-300">›</span>
				</a>
			</li>
		{/each}
	</ul>
	<p class="px-1 py-3 text-center text-[11px] text-slate-400">{filtered.length} jugadors</p>
{/if}
