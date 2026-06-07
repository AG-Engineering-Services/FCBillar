<script lang="ts">
	import { supabase } from '$lib/supabase';
	import { follows, toggleFollow } from '$lib/follows';

	interface Row {
		fcb_id: string;
		nom: string;
		club: string | null;
		posicio: number | null;
		mitjana: number | null;
	}
	let rows = $state<Row[]>([]);
	let loading = $state(true);

	$effect(() => {
		loadFollowed($follows);
	});

	async function loadFollowed(ids: string[]) {
		loading = true;
		if (!ids.length) {
			rows = [];
			loading = false;
			return;
		}
		const [{ data: pl }, { data: cl }, { data: re }] = await Promise.all([
			supabase.from('players').select('fcb_id, nom, club_fcb_id').in('fcb_id', ids),
			supabase.from('clubs').select('fcb_id, nom'),
			supabase
				.from('ranking_entries')
				.select('player_fcb_id, num_seq, posicio, mitjana_general')
				.eq('modalitat_codi', 1)
				.in('player_fcb_id', ids)
				.order('num_seq', { ascending: false })
		]);
		const clubs = new Map((cl ?? []).map((c) => [c.fcb_id, c.nom]));
		const latest = new Map<string, any>();
		for (const r of re ?? []) if (!latest.has(r.player_fcb_id)) latest.set(r.player_fcb_id, r);
		rows = (pl ?? [])
			.map((p) => ({
				fcb_id: p.fcb_id,
				nom: p.nom,
				club: clubs.get(p.club_fcb_id) ?? null,
				posicio: latest.get(p.fcb_id)?.posicio ?? null,
				mitjana: latest.get(p.fcb_id)?.mitjana_general ?? null
			}))
			.sort((a, b) => (a.posicio ?? 9999) - (b.posicio ?? 9999));
		loading = false;
	}
</script>

<h1 class="mb-1 text-base font-bold">★ Jugadors seguits</h1>
<p class="mb-3 text-[11px] text-slate-400">
	Aquesta llista es guarda en aquest dispositiu. Posició/mitjana del darrer rànquing de 3 bandes.
</p>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if rows.length === 0}
	<div class="rounded-xl bg-white p-6 text-center text-sm text-slate-400 ring-1 ring-slate-200">
		Encara no segueixes ningú.<br />Entra a la fitxa d'un jugador i toca <b>☆ Seguir</b>.
	</div>
{:else}
	<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
		{#each rows as r (r.fcb_id)}
			<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2.5 last:border-0">
				<a href="/jugador/{r.fcb_id}" class="min-w-0 flex-1">
					<div class="truncate text-sm font-medium leading-tight">{r.nom}</div>
					{#if r.club}<div class="truncate text-xs text-slate-400">{r.club}</div>{/if}
				</a>
				{#if r.posicio != null}
					<div class="shrink-0 text-right">
						<div class="font-mono text-sm font-bold tabular-nums">#{r.posicio}</div>
						<div class="text-[10px] text-slate-400">{r.mitjana != null ? r.mitjana.toFixed(3) : ''}</div>
					</div>
				{/if}
				<button
					onclick={() => toggleFollow(r.fcb_id)}
					class="shrink-0 rounded-full px-2 py-1 text-xs text-amber-600"
					aria-label="deixar de seguir">★</button>
			</li>
		{/each}
	</ul>
{/if}
