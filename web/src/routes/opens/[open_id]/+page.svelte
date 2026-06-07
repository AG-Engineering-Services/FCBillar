<script lang="ts">
	import { page } from '$app/stores';
	import { supabase, type Open, type OpenClassification } from '$lib/supabase';

	const openId = $derived(Number($page.params.open_id));
	let open = $state<Open | null>(null);
	let rows = $state<OpenClassification[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		const id = openId;
		if (!Number.isNaN(id)) load(id);
	});

	async function load(id: number) {
		loading = true;
		error = null;
		try {
			const [{ data: o }, { data: cl, error: e }] = await Promise.all([
				supabase.from('opens').select('*').eq('open_id', id).maybeSingle(),
				supabase
					.from('open_classifications')
					.select('*')
					.eq('open_id', id)
					.order('posicio', { ascending: true })
			]);
			if (e) throw e;
			open = (o ?? null) as Open | null;
			rows = (cl ?? []) as OpenClassification[];
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}
</script>

<a href="/opens" class="mb-2 inline-flex items-center gap-1 text-sm text-slate-500">
	<span aria-hidden="true">←</span> Opens
</a>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
{:else}
	<h1 class="mb-3 text-base font-bold leading-tight">{open?.nom ?? '…'}</h1>

	{#if loading}
		<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
	{:else if rows.length === 0}
		<p class="py-6 text-center text-sm text-slate-400">Sense classificació disponible.</p>
	{:else}
		<div class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			<div class="flex items-center gap-2 border-b border-slate-100 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
				<span class="w-5 text-center">#</span>
				<span class="flex-1">Jugador</span>
				<span class="w-7 text-center">PJ</span>
				<span class="w-12 text-right">Mitj.</span>
				<span class="w-8 text-right">Pts</span>
			</div>
			<ul>
				{#each rows as r (r.player_fcb_id)}
					<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2 last:border-0">
						<span
							class="w-5 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1
								? 'text-amber-500'
								: 'text-slate-400'}">{r.posicio}</span>
						<div class="min-w-0 flex-1">
							{#if r.player_fcb_id}
								<a
									href="/jugador/{r.player_fcb_id}"
									class="block truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
							{:else}
								<div class="truncate text-sm font-medium leading-tight">{r.jugador}</div>
							{/if}
							{#if r.club}<div class="truncate text-[11px] text-slate-400">{r.club}</div>{/if}
						</div>
						<span class="w-7 shrink-0 text-center text-sm tabular-nums text-slate-500">{r.partides}</span>
						<span class="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-slate-500">
							{r.mitjana_general != null ? r.mitjana_general.toFixed(3) : '—'}
						</span>
						<span class="w-8 shrink-0 text-right font-mono text-sm font-bold tabular-nums">{r.punts}</span>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
{/if}
