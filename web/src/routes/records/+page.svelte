<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';

	type Detail = {
		game_id: string;
		modalitat_codi: number;
		data: string | null;
		rival: string;
		caramboles: number;
		caramboles_rival: number;
		entrades: number;
	};
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
</script>

<h1 class="mb-3 text-lg font-bold">Rècords</h1>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else}
	<div class="-mx-3 mb-3 flex gap-1.5 overflow-x-auto px-3 pb-1 [scrollbar-width:none]">
		{#each mods as m}
			<button
				onclick={() => (selMod = m)}
				class="shrink-0 rounded-full px-3 py-1.5 text-sm font-medium {selMod === m
					? 'bg-slate-900 text-white'
					: 'bg-slate-100 text-slate-500'}">{m}</button>
		{/each}
	</div>

	<div class="space-y-4 lg:grid lg:grid-cols-2 lg:gap-4 lg:space-y-0">
		{#each cats as cat}
			<div class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
				<div class="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
					{shortCat(cat)}
				</div>
				<ul>
					{#each recs.filter((r) => r.categoria === cat) as r (r.ordre)}
						{@const d = detail(r.detall)}
						<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
							<span class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums {r.ordre === 1 ? 'text-amber-500' : 'text-slate-400'}">{r.ordre}</span>
							{#if r.player_fcb_id}
								<a href="/jugador/{r.player_fcb_id}{d ? `?mod=${d.modalitat_codi}&game=${d.game_id}` : ''}" class="min-w-0 flex-1 active:underline">
									<div class="truncate text-sm font-medium leading-tight">{r.jugador}</div>
									{#if d}
										<div class="truncate text-[10px] text-slate-400">{fmtDate(d.data)} · vs {d.rival} · {d.caramboles}–{d.caramboles_rival} / {d.entrades} ent.</div>
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
