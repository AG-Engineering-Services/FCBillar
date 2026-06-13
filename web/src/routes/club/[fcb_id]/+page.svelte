<script lang="ts">
	import { page } from '$app/stores';
	import { supabase } from '$lib/supabase';
	import { clubFollows, toggleClubFollow } from '$lib/follows';

	const fcbId = $derived($page.params.fcb_id);
	let clubNom = $state('');
	let players = $state<
		{ fcb_id: string; nom: string; rank: { posicio: number; mitjana: number } | null }[]
	>([]);
	let loading = $state(true);

	$effect(() => {
		if (fcbId) load(fcbId);
	});

	async function load(id: string) {
		loading = true;
		const [{ data: c }, { data: pl }, { data: maxR }] = await Promise.all([
			supabase.from('clubs').select('nom').eq('fcb_id', id).maybeSingle(),
			supabase.from('players').select('fcb_id, nom').eq('club_fcb_id', id),
			supabase
				.from('rankings')
				.select('num_seq')
				.eq('modalitat_codi', 1)
				.order('num_seq', { ascending: false })
				.limit(1)
		]);
		clubNom = c?.nom ?? id;
		const ids = (pl ?? []).map((p) => p.fcb_id);
		const latest = maxR?.[0]?.num_seq;
		const rankMap = new Map<string, { posicio: number; mitjana: number }>();
		if (latest != null && ids.length) {
			const { data: re } = await supabase
				.from('ranking_entries')
				.select('player_fcb_id, posicio, mitjana_general')
				.eq('modalitat_codi', 1)
				.eq('num_seq', latest)
				.in('player_fcb_id', ids);
			for (const r of re ?? [])
				rankMap.set(r.player_fcb_id, { posicio: r.posicio, mitjana: r.mitjana_general });
		}
		players = (pl ?? [])
			.map((p) => ({ ...p, rank: rankMap.get(p.fcb_id) ?? null }))
			.sort(
				(a, b) =>
					(b.rank?.mitjana ?? -1) - (a.rank?.mitjana ?? -1) || a.nom.localeCompare(b.nom)
			);
		loading = false;
	}

	const ranked = $derived(players.filter((p) => p.rank));
	const unranked = $derived(players.filter((p) => !p.rank));

	function back() {
		if (typeof history !== 'undefined' && history.length > 1) history.back();
		else location.href = '/';
	}
</script>

<button onclick={back} class="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
	<span aria-hidden="true">←</span> Enrere
</button>

<div class="mb-3 flex items-start justify-between gap-3">
	<div class="min-w-0">
		<h1 class="text-lg font-bold leading-tight">{clubNom}</h1>
		<p class="text-sm text-slate-400 dark:text-slate-500">{players.length} jugadors · {ranked.length} al rànquing</p>
	</div>
	<button
		onclick={() => toggleClubFollow(fcbId)}
		class="shrink-0 rounded-full px-3 py-1.5 text-sm font-medium {$clubFollows.includes(fcbId)
			? 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 ring-1 ring-amber-300 dark:ring-amber-900/50'
			: 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'}"
	>
		{$clubFollows.includes(fcbId) ? '★ Seguint' : '☆ Seguir club'}
	</button>
</div>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant…</p>
{:else if players.length === 0}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Cap jugador en aquest club.</p>
{:else}
	<div class="mb-1 px-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">
		Al rànquing (3 bandes) · per mitjana
	</div>
	<ul class="mb-4 overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
		{#each ranked as p, i (p.fcb_id)}
			<li class="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-3 py-2 last:border-0">
				<span class="w-5 shrink-0 text-center text-xs font-semibold tabular-nums text-slate-400 dark:text-slate-500"
					>{i + 1}</span>
				<a
					href="/jugador/{p.fcb_id}"
					class="min-w-0 flex-1 truncate text-sm font-medium leading-tight active:underline"
					>{p.nom}</a>
				<div class="shrink-0 text-right">
					<div class="font-mono text-sm font-bold tabular-nums">{p.rank?.mitjana?.toFixed(3)}</div>
					<div class="text-[10px] text-slate-400 dark:text-slate-500">#{p.rank?.posicio}</div>
				</div>
			</li>
		{/each}
	</ul>
	{#if unranked.length}
		<div class="mb-1 px-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-400 dark:text-slate-500">
			Altres jugadors ({unranked.length})
		</div>
		<ul class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800">
			{#each unranked as p (p.fcb_id)}
				<li class="border-b border-slate-100 dark:border-slate-800 last:border-0">
					<a
						href="/jugador/{p.fcb_id}"
						class="block truncate px-3 py-2 text-sm leading-tight active:bg-slate-50 dark:active:bg-slate-800/50">{p.nom}</a>
				</li>
			{/each}
		</ul>
	{/if}
{/if}
