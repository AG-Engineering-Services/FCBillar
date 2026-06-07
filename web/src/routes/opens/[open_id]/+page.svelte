<script lang="ts">
	import { page } from '$app/stores';
	import { supabase, type Open, type OpenClassification } from '$lib/supabase';

	const openId = $derived(Number($page.params.open_id));
	let open = $state<Open | null>(null);
	let rows = $state<OpenClassification[]>([]);
	let partides = $state<any[]>([]);
	let expanded = $state<string | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let q = $state('');
	const filteredRows = $derived(
		q.trim() ? rows.filter((r) => norm(r.jugador).includes(norm(q.trim()))) : rows
	);

	$effect(() => {
		const id = openId;
		if (!Number.isNaN(id)) load(id);
	});

	async function load(id: number) {
		loading = true;
		error = null;
		expanded = null;
		try {
			const [{ data: o }, { data: cl, error: e }, { data: op }] = await Promise.all([
				supabase.from('opens').select('*').eq('open_id', id).maybeSingle(),
				supabase.from('open_classifications').select('*').eq('open_id', id).order('posicio'),
				supabase.from('open_partides').select('*').eq('open_id', id)
			]);
			if (e) throw e;
			open = (o ?? null) as Open | null;
			rows = (cl ?? []) as OpenClassification[];
			partides = op ?? [];
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	function norm(s: string | null): string {
		return (s ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();
	}
	function gamesOf(nom: string) {
		const n = norm(nom);
		return partides
			.filter((p) => norm(p.jugador_local) === n || norm(p.jugador_visitant) === n)
			.map((p) => {
				const loc = norm(p.jugador_local) === n;
				return {
					opp: loc ? p.jugador_visitant : p.jugador_local,
					my: loc ? p.caramboles_local : p.caramboles_visitant,
					oppc: loc ? p.caramboles_visitant : p.caramboles_local,
					ent: p.entrades
				};
			});
	}
	function toggle(nom: string) {
		expanded = expanded === nom ? null : nom;
	}
</script>

<a href="/opens" class="mb-2 inline-flex items-center gap-1 text-sm text-slate-500">
	<span aria-hidden="true">←</span> Opens
</a>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
{:else}
	<h1 class="mb-1 text-base font-bold leading-tight">
		{open ? open.nom.replace(/\s*-\s*[ÚU]NICA\s*$/i, '').trim() : '…'}
	</h1>
	{#if partides.length}
		<p class="mb-3 text-[11px] text-slate-400">Toca un jugador per veure els seus partits (eliminatòries).</p>
	{/if}

	{#if loading}
		<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
	{:else if rows.length === 0}
		<p class="py-6 text-center text-sm text-slate-400">Sense classificació disponible.</p>
	{:else}
		{#if rows.length > 10}
			<input
				bind:value={q}
				inputmode="search"
				placeholder="Cerca jugador…"
				class="mb-3 w-full rounded-lg border-slate-300 bg-white py-2 px-3 text-sm shadow-sm"
			/>
		{/if}
		<div class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			<div class="flex items-center gap-2 border-b border-slate-100 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
				<span class="w-5 text-center">#</span>
				<span class="flex-1">Jugador</span>
				<span class="w-7 text-center">PJ</span>
				<span class="w-12 text-right">Mitj.</span>
				<span class="w-8 text-right">Pts</span>
			</div>
			<ul>
				{#each filteredRows as r (r.player_fcb_id)}
					<li class="border-b border-slate-100 last:border-0">
						<button onclick={() => toggle(r.jugador ?? '')} class="flex w-full items-center gap-2 px-3 py-2 text-left active:bg-slate-50">
							<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500' : 'text-slate-400'}">{r.posicio}</span>
							<div class="min-w-0 flex-1">
								<div class="truncate text-sm font-medium leading-tight">{r.jugador}</div>
								{#if r.club}<div class="truncate text-[11px] text-slate-400">{r.club}</div>{/if}
							</div>
							<span class="w-7 shrink-0 text-center text-sm tabular-nums text-slate-500">{r.partides}</span>
							<span class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500">{r.mitjana_general != null ? r.mitjana_general.toFixed(3) : '—'}</span>
							<span class="w-8 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
						</button>
						{#if expanded === r.jugador}
							<div class="border-t border-slate-100 bg-slate-50/60 px-3 py-2">
								{#each gamesOf(r.jugador ?? '') as g}
									<div class="flex items-center gap-2 py-0.5 text-[11px]">
										<span class="flex-1 truncate">vs {g.opp}</span>
										<span class="font-mono tabular-nums {g.my > g.oppc ? 'font-bold text-emerald-600' : 'text-slate-500'}">{g.my}–{g.oppc}</span>
										<span class="w-12 text-right text-slate-400">{g.ent} ent</span>
									</div>
								{:else}
									<p class="py-1 text-[11px] text-slate-400">Només té partits de fase de grups (no publicats individualment).</p>
								{/each}
								{#if r.player_fcb_id}
									<a href="/jugador/{r.player_fcb_id}" class="mt-1 inline-block text-[11px] text-slate-500 underline">Fitxa completa →</a>
								{/if}
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		</div>
	{/if}
{/if}
