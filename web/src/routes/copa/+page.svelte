<script lang="ts">
	import { onMount } from 'svelte';
	import {
		supabase,
		type CopaGroup,
		type CopaStanding,
		type PlayerRankRow
	} from '$lib/supabase';

	let groups = $state<CopaGroup[]>([]);
	let standings = $state<CopaStanding[]>([]);
	let pranks = $state<PlayerRankRow[]>([]);
	let selJornada = $state<number | null>(null);
	let mode = $state<'equips' | 'jugadors'>('equips');
	let q = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);

	function norm(s: string): string {
		return (s ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}
	const matchQ = (s: string | null) => !q.trim() || norm(s ?? '').includes(norm(q.trim()));

	onMount(async () => {
		try {
			const [
				{ data: g, error: eg },
				{ data: s, error: es },
				{ data: pr, error: ep },
				{ data: enc }
			] = await Promise.all([
				supabase.from('copa_groups').select('*'),
				supabase.from('copa_standings').select('*').order('posicio'),
				supabase.from('copa_player_rankings').select('*').order('posicio'),
				supabase.from('copa_encontres').select('*')
			]);
			if (eg) throw eg;
			if (es) throw es;
			if (ep) throw ep;
			groups = (g ?? []) as CopaGroup[];
			standings = (s ?? []) as CopaStanding[];
			pranks = (pr ?? []) as PlayerRankRow[];
			encontres = enc ?? [];
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const phases = $derived.by(() => {
		const m = new Map<number, { nom: string; ordre: number }>();
		for (const g of groups)
			if (!m.has(g.jornada))
				m.set(g.jornada, { nom: g.jornada_nom ?? `Fase ${g.jornada}`, ordre: g.ordre ?? g.jornada });
		return [...m.entries()]
			.map(([jornada, v]) => ({ jornada, ...v }))
			.sort((a, b) => a.ordre - b.ordre);
	});

	$effect(() => {
		if (selJornada == null && phases.length) selJornada = phases[0].jornada;
	});

	const phaseGroups = $derived(
		groups
			.filter((g) => g.jornada === selJornada)
			.sort((a, b) => (a.grup_nom ?? '').localeCompare(b.grup_nom ?? ''))
	);

	function rows(gid: number): CopaStanding[] {
		return standings
			.filter((s) => s.jornada === selJornada && s.grup_id === gid && matchQ(s.equip))
			.sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99));
	}
	function playerRows(gid: number): PlayerRankRow[] {
		return pranks
			.filter((s) => s.jornada === selJornada && s.grup_id === gid)
			.sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99));
	}
	function count(gid: number): number {
		return rows(gid).length;
	}
	// Rànquing de tota la competició (jornada=0, grup=0 sentinella).
	const compPlayers = $derived(
		pranks.filter((p) => matchQ(p.jugador)).sort((a, b) => (a.posicio ?? 99) - (b.posicio ?? 99))
	);

	let collapsed = $state(new Set<number>());
	function toggle(id: number) {
		const s = new Set(collapsed);
		s.has(id) ? s.delete(id) : s.add(id);
		collapsed = s;
	}

	// Resultats (encontres) per grup
	let encontres = $state<any[]>([]);
	let partidesCache = $state<Record<number, any[]>>({});
	let expandedEnc = $state(new Set<number>());
	function encOf(gid: number): any[] {
		return encontres.filter((e) => e.jornada === selJornada && e.grup_id === gid);
	}
	async function toggleEnc(encId: number) {
		const s = new Set(expandedEnc);
		if (s.has(encId)) {
			s.delete(encId);
			expandedEnc = s;
			return;
		}
		s.add(encId);
		expandedEnc = s;
		if (!partidesCache[encId]) {
			const { data } = await supabase
				.from('copa_partides')
				.select('*')
				.eq('encontre_id', encId)
				.order('ordre');
			partidesCache = { ...partidesCache, [encId]: data ?? [] };
		}
	}
</script>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if phases.length === 0}
	<p class="py-6 text-center text-sm text-slate-400">Sense classificacions de copa.</p>
{:else}
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

	<input
		bind:value={q}
		inputmode="search"
		placeholder={mode === 'equips' ? 'Filtra equip…' : 'Filtra jugador…'}
		class="mb-3 w-full rounded-lg border-slate-300 bg-white py-2 px-3 text-sm shadow-sm"
	/>

	{#if mode === 'jugadors'}
		<!-- Rànquing de tota la competició -->
		<section class="mb-4 overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			<header class="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
				Rànquing de la Copa · {compPlayers.length} jugadors
			</header>
			<div class="flex items-center gap-2 border-b border-slate-100 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
				<span class="w-6 text-center">#</span>
				<span class="flex-1">Jugador</span>
				<span class="w-6 text-center">PJ</span>
				<span class="w-11 text-right">Mitj.</span>
				<span class="w-7 text-right">Pts</span>
			</div>
			<ul>
				{#each compPlayers as r (r.player_fcb_id)}
					<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
						<span class="w-6 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500' : 'text-slate-400'}">{r.posicio}</span>
						<a href="/jugador/{r.player_fcb_id}" class="min-w-0 flex-1 truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
						<span class="w-6 shrink-0 text-center text-xs tabular-nums text-slate-500">{r.partides}</span>
						<span class="w-11 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500">{r.mitjana != null ? r.mitjana.toFixed(3) : '—'}</span>
						<span class="w-7 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
					</li>
				{/each}
			</ul>
		</section>
	{:else}
		<!-- Fases: xips (només equips) -->
		<div class="-mx-3 mb-3 flex gap-2 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
			{#each phases as f}
				<button
					onclick={() => (selJornada = f.jornada)}
					class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium {f.jornada === selJornada
						? 'bg-slate-900 text-white'
						: 'bg-white text-slate-600 ring-1 ring-slate-200'}">{f.nom}</button>
			{/each}
		</div>

		{#each phaseGroups as g (g.grup_id)}
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
						<span class="w-12 text-right">Mitj.</span>
						<span class="w-9 text-right">Pts</span>
					</div>
					<ul>
						{#each rows(g.grup_id) as r (r.equip)}
							<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
								<span class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500' : 'text-slate-400'}">{r.posicio}</span>
								<div class="min-w-0 flex-1 truncate text-sm font-medium leading-tight">{r.equip}</div>
								<span class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-slate-400">{r.mitjana != null ? r.mitjana.toFixed(3) : '—'}</span>
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
								<a href="/jugador/{r.player_fcb_id}" class="min-w-0 flex-1 truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
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
