<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type LligaGroup, type StandingRow, type PlayerRankRow } from '$lib/supabase';

	let groups = $state<LligaGroup[]>([]);
	let standings = $state<StandingRow[]>([]);
	let pranks = $state<PlayerRankRow[]>([]);
	let selDiv = $state<number | null>(null);
	let mode = $state<'equips' | 'jugadors'>('equips');
	let scope = $state<'grup' | 'categoria'>('grup');
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const [{ data: g, error: eg }, { data: s, error: es }, { data: pr, error: ep }] =
				await Promise.all([
					supabase.from('lliga_groups').select('*'),
					supabase.from('lliga_standings').select('*').order('posicio'),
					supabase.from('lliga_player_rankings').select('*').order('posicio')
				]);
			if (eg) throw eg;
			if (es) throw es;
			if (ep) throw ep;
			groups = (g ?? []) as LligaGroup[];
			standings = (s ?? []) as StandingRow[];
			pranks = (pr ?? []) as PlayerRankRow[];
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const divisions = $derived.by(() => {
		const m = new Map<number, string>();
		for (const g of groups) if (!m.has(g.divisio_id)) m.set(g.divisio_id, g.divisio_nom ?? `Div ${g.divisio_id}`);
		return [...m.entries()].map(([id, nom]) => ({ id, nom })).sort((a, b) => a.id - b.id);
	});

	$effect(() => {
		if (selDiv == null && divisions.length) selDiv = divisions[0].id;
	});

	const divGroups = $derived(
		groups
			.filter((g) => g.divisio_id === selDiv)
			.sort((a, b) => {
				const fa = (a.grup_nom ?? '').toUpperCase().startsWith('FINAL') ? 1 : 0;
				const fb = (b.grup_nom ?? '').toUpperCase().startsWith('FINAL') ? 1 : 0;
				return fa - fb || (a.grup_nom ?? '').localeCompare(b.grup_nom ?? '');
			})
	);

	function teamRows(gid: number): StandingRow[] {
		return standings
			.filter((s) => s.divisio_id === selDiv && s.grup_id === gid)
			.sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99));
	}
	function playerRows(gid: number): PlayerRankRow[] {
		return pranks
			.filter((s) => s.divisio_id === selDiv && s.grup_id === gid)
			.sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99));
	}
	function count(gid: number): number {
		return mode === 'equips' ? teamRows(gid).length : playerRows(gid).length;
	}
	// Rànquing individual de tota la categoria (tots els grups de la divisió, reordenats).
	const divPlayers = $derived(
		pranks
			.filter((p) => p.divisio_id === selDiv)
			.sort((a, b) => (b.punts ?? 0) - (a.punts ?? 0) || (b.mitjana ?? 0) - (a.mitjana ?? 0))
	);

	let collapsed = $state(new Set<number>());
	function toggle(id: number) {
		const s = new Set(collapsed);
		s.has(id) ? s.delete(id) : s.add(id);
		collapsed = s;
	}
</script>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if divisions.length === 0}
	<p class="py-6 text-center text-sm text-slate-400">Sense classificacions.</p>
{:else}
	<!-- Divisions: xips -->
	<div class="-mx-3 mb-2 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
		{#each divisions as d}
			<button
				onclick={() => (selDiv = d.id)}
				class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium {d.id === selDiv
					? 'bg-slate-900 text-white'
					: 'bg-white text-slate-600 ring-1 ring-slate-200'}">{d.nom}</button>
		{/each}
	</div>

	<!-- Toggle Equips / Jugadors -->
	<div class="mb-3 inline-flex rounded-lg bg-slate-100 p-0.5 text-sm">
		<button
			onclick={() => (mode = 'equips')}
			class="rounded-md px-3 py-1 font-medium {mode === 'equips' ? 'bg-white shadow-sm' : 'text-slate-500'}"
			>Equips</button>
		<button
			onclick={() => (mode = 'jugadors')}
			class="rounded-md px-3 py-1 font-medium {mode === 'jugadors' ? 'bg-white shadow-sm' : 'text-slate-500'}"
			>Jugadors</button>
	</div>

	{#if mode === 'jugadors'}
		<div class="mb-3 ml-2 inline-flex rounded-lg bg-slate-100 p-0.5 text-xs">
			<button
				onclick={() => (scope = 'grup')}
				class="rounded-md px-2.5 py-1 font-medium {scope === 'grup' ? 'bg-white shadow-sm' : 'text-slate-500'}"
				>Per grup</button>
			<button
				onclick={() => (scope = 'categoria')}
				class="rounded-md px-2.5 py-1 font-medium {scope === 'categoria' ? 'bg-white shadow-sm' : 'text-slate-500'}"
				>Tota la categoria</button>
		</div>
	{/if}

	{#if mode === 'jugadors' && scope === 'categoria'}
		<section class="mb-4 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			<header class="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
				Categoria sencera · {divPlayers.length} jugadors
			</header>
			<div class="flex items-center gap-2 border-b border-slate-100 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
				<span class="w-6 text-center">#</span>
				<span class="flex-1">Jugador</span>
				<span class="w-12 text-right">Mitj.</span>
				<span class="w-8 text-right">Pts</span>
			</div>
			<ul>
				{#each divPlayers as r, i (r.player_fcb_id)}
					<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
						<span class="w-6 shrink-0 text-center text-sm font-semibold tabular-nums {i === 0 ? 'text-amber-500' : 'text-slate-400'}">{i + 1}</span>
						<div class="min-w-0 flex-1">
							<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
							{#if r.club}<div class="truncate text-[11px] text-slate-400">{r.club}</div>{/if}
						</div>
						<span class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500">{r.mitjana != null ? r.mitjana.toFixed(3) : '—'}</span>
						<span class="w-8 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
					</li>
				{/each}
			</ul>
		</section>
	{:else}
		{#each divGroups as g (g.grup_id)}
		<section class="mb-4 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			<button
				onclick={() => toggle(g.grup_id)}
				class="flex w-full items-center gap-2 bg-slate-50 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500"
			>
				<span class="flex-1">{g.grup_nom ?? 'Grup'}</span>
				<span class="font-normal normal-case text-slate-400">{count(g.grup_id)} {mode}</span>
				<span class="text-slate-400 transition-transform {collapsed.has(g.grup_id) ? '' : 'rotate-90'}">›</span>
			</button>
			{#if !collapsed.has(g.grup_id)}
				{#if mode === 'equips'}
					<div class="flex items-center gap-2 border-y border-slate-100 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
						<span class="w-5 text-center">#</span>
						<span class="flex-1">Equip</span>
						<span class="w-7 text-center">PJ</span>
						<span class="w-9 text-right">Pts</span>
					</div>
					<ul>
						{#each teamRows(g.grup_id) as r (r.equip)}
							<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
								<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500' : 'text-slate-400'}">{r.posicio}</span>
								<div class="min-w-0 flex-1">
									<div class="truncate text-sm font-medium leading-tight">{r.equip}</div>
									<div class="text-[11px] tabular-nums text-slate-400">{r.g}-{r.e}-{r.p}</div>
								</div>
								<span class="w-7 shrink-0 text-center text-sm tabular-nums text-slate-500">{r.pj}</span>
								<span class="w-9 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
							</li>
						{/each}
					</ul>
				{:else}
					<div class="flex items-center gap-2 border-y border-slate-100 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
						<span class="w-5 text-center">#</span>
						<span class="flex-1">Jugador</span>
						<span class="w-12 text-right">Mitj.</span>
						<span class="w-8 text-right">Pts</span>
					</div>
					<ul>
						{#each playerRows(g.grup_id) as r (r.player_fcb_id)}
							<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
								<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500' : 'text-slate-400'}">{r.posicio}</span>
								<div class="min-w-0 flex-1">
									<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
									{#if r.club}<div class="truncate text-[11px] text-slate-400">{r.club}</div>{/if}
								</div>
								<span class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500">{r.mitjana != null ? r.mitjana.toFixed(3) : '—'}</span>
								<span class="w-8 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
							</li>
						{/each}
					</ul>
				{/if}
			{/if}
		</section>
		{/each}
	{/if}
{/if}
