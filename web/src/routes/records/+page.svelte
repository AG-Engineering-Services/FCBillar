<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';

	type GameDetail = {
		kind?: 'game';
		game_id: string;
		modalitat_codi: number;
		data: string | null;
		rival: string;
		caramboles: number;
		caramboles_rival: number;
		entrades: number;
	};
	type RankingDetail = {
		kind: 'ranking';
		modalitat_codi: number;
		num_seq: number;
		any_pub: number | null;
		mes_pub: number | null;
		posicio: number | null;
	};
	type Detail = GameDetail | RankingDetail;
	type Rec = { categoria: string; ordre: number; player_fcb_id: string | null; jugador: string; valor: string; detall: string | null };
	let recs = $state<Rec[]>([]);
	let loading = $state(true);
	let selMod = $state('');

	onMount(async () => {
		const { data } = await supabase
			.from('records')
			.select('categoria, ordre, player_fcb_id, jugador, valor, detall')
			.order('categoria')
			.order('ordre');
		recs = (data ?? []) as Rec[];
		loading = false;
	});

	const ORDER = ['Tres Bandes', 'Lliure', 'Banda', 'Quadre 47/2', 'Quadre 71/2'];
	const mods = $derived(
		[...new Set(recs.map((r) => r.categoria.split(' · ')[0]))].sort(
			(a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99)
		)
	);
	$effect(() => {
		if (!selMod && mods.length) selMod = mods[0];
	});
	const cats = $derived([
		...new Set(recs.filter((r) => r.categoria.startsWith(selMod + ' ·')).map((r) => r.categoria))
	]);
	const shortCat = (c: string) => c.split(' · ')[1] ?? c;
	function detail(raw: string | null): Detail | null {
		if (!raw) return null;
		try {
			return JSON.parse(raw) as Detail;
		} catch {
			return null;
		}
	}
	const fmtDate = (s: string | null) => s ? s.split('-').reverse().join('/') : '';
	const fmtRanking = (d: RankingDetail) => {
		const date = d.any_pub && d.mes_pub ? `${String(d.mes_pub).padStart(2, '0')}/${d.any_pub}` : '';
		const position = d.posicio ? ` · posició ${d.posicio}` : '';
		return `Rànquing ${d.num_seq}${date ? ` · ${date}` : ''}${position}`;
	};
	const playerHref = (fcbId: string, d: Detail | null) =>
		`/jugador/${fcbId}?mod=${d?.modalitat_codi ?? ''}${d && d.kind !== 'ranking' ? `&game=${d.game_id}` : ''}`;
</script>

<h1 class="mb-3 text-lg font-bold">Rècords</h1>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
{:else}
	<div class="-mx-3 mb-3 flex gap-1.5 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
		{#each mods as m}
			<button
				onclick={() => (selMod = m)}
				class="shrink-0 rounded-full px-3 py-1.5 text-sm font-medium {selMod === m
					? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
					: 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'}">{m}</button>
		{/each}
	</div>

	<div class="space-y-4 lg:grid lg:grid-cols-2 lg:gap-4 lg:space-y-0">
		{#each cats as cat}
			<div class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
				<div class="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
					{shortCat(cat)}
				</div>
				<ul>
					{#each recs.filter((r) => r.categoria === cat) as r (r.ordre)}
						{@const d = detail(r.detall)}
						<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
							<span class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums {r.ordre === 1 ? 'text-amber-500 dark:text-amber-400' : 'text-slate-400 dark:text-slate-500'}">{r.ordre}</span>
							{#if r.player_fcb_id}
								<a href={playerHref(r.player_fcb_id, d)} class="min-w-0 flex-1 active:underline">
									<div class="truncate text-sm font-medium leading-tight">{r.jugador}</div>
									{#if d?.kind === 'ranking'}
										<div class="truncate text-[10px] text-slate-400 dark:text-slate-500">{fmtRanking(d)}</div>
									{:else if d}
										<div class="truncate text-[10px] text-slate-400 dark:text-slate-500">{fmtDate(d.data)} · vs {d.rival} · {d.caramboles}–{d.caramboles_rival} / {d.entrades} ent.</div>
									{/if}
								</a>
							{:else}
								<span class="min-w-0 flex-1 truncate text-sm">{r.jugador}</span>
							{/if}
							<span class="shrink-0 font-mono text-sm font-bold tabular-nums">{r.valor}</span>
						</li>
					{/each}
				</ul>
			</div>
		{/each}
	</div>
{/if}
