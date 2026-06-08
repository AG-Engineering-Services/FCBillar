<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type Open } from '$lib/supabase';

	let opens = $state<Open[]>([]);
	let ranking = $state<any[]>([]);
	let ronda = $state<number | null>(null);
	let q = $state('');
	let cat = $state<'opens' | 'ranking'>('opens');
	let loading = $state(true);
	let error = $state<string | null>(null);

	let expandedPlayer = $state<string | null>(null);
	const genRanking = $derived(ranking.filter((r) => r.genere === 'general'));
	const rondes = $derived([...new Set(genRanking.map((r) => r.ronda as number))].sort((a, b) => a - b));
	$effect(() => {
		if (ronda == null && rondes.length) ronda = rondes[rondes.length - 1];
	});
	const rondaRows = $derived(genRanking.filter((r) => r.ronda === ronda).sort((a, b) => a.posicio - b.posicio));
	const rondaInfo = $derived(genRanking.find((r) => r.ronda === ronda));
	function stepRonda(d: number) {
		const i = rondes.indexOf(ronda as number);
		ronda = rondes[Math.min(rondes.length - 1, Math.max(0, i + d))];
	}

	function norm(s: string): string {
		return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}
	const isOpen = (nom: string) => nom.toUpperCase().includes('OPEN');
	const clean = (nom: string) => nom.replace(/\s*-\s*[ÚU]NICA\s*$/i, '').trim();

	onMount(async () => {
		try {
			const { data, error: e } = await supabase.from('opens').select('*').order('nom');
			if (e) throw e;
			opens = (data ?? []) as Open[];
			// open_ranking pot superar el límit de 1000 files: paginem.
			const all: any[] = [];
			for (let from = 0; ; from += 1000) {
				const { data: rk } = await supabase
					.from('open_ranking')
					.select('*')
					.order('ronda', { ascending: false })
					.range(from, from + 999);
				if (!rk?.length) break;
				all.push(...rk);
				if (rk.length < 1000) break;
			}
			ranking = all;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const filtered = $derived(
		opens
			.filter((o) => isOpen(o.nom))
			.filter((o) => (q.trim() ? norm(o.nom).includes(norm(q.trim())) : true))
	);
</script>

<!-- Toggle Opens / Campionats de Catalunya -->
<div class="mb-3 inline-flex rounded-lg bg-slate-100 p-0.5 text-sm">
	<button
		onclick={() => (cat = 'opens')}
		class="rounded-md px-3 py-1 font-medium {cat === 'opens' ? 'bg-white shadow-sm' : 'text-slate-500'}"
		>Opens</button>
	<button
		onclick={() => (cat = 'ranking')}
		class="rounded-md px-3 py-1 font-medium {cat === 'ranking' ? 'bg-white shadow-sm' : 'text-slate-500'}"
		>Rànquing</button>
</div>

<input
	bind:value={q}
	inputmode="search"
	placeholder="Cerca…"
	class="mb-3 w-full rounded-lg border-slate-300 bg-white py-2.5 px-3 text-sm shadow-sm"
/>

{#if error}
	<div class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if cat === 'ranking'}
	{#if rondes.length === 0}
		<p class="py-6 text-center text-sm text-slate-400">Sense rànquing d'opens.</p>
	{:else}
		<div class="mb-3 flex items-center justify-between gap-2 rounded-lg bg-slate-900 px-2 py-2 text-white">
			<button onclick={() => stepRonda(-1)} class="rounded px-3 py-1 text-lg active:bg-slate-700" aria-label="anterior">‹</button>
			<div class="min-w-0 text-center">
				<div class="truncate text-xs font-semibold">Fins a {rondaInfo?.ronda_nom ?? ''}</div>
				<div class="text-[10px] text-slate-300">{rondaInfo?.ronda_temp ?? ''} · ronda {ronda}/{rondes.length}</div>
			</div>
			<button onclick={() => stepRonda(1)} class="rounded px-3 py-1 text-lg active:bg-slate-700" aria-label="següent">›</button>
		</div>
		<div class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
			<div class="flex items-center gap-2 border-b border-slate-100 px-3 py-1.5 text-[10px] uppercase tracking-wide text-slate-400">
				<span class="w-6 text-center">#</span>
				<span class="flex-1">Jugador</span>
				<span class="w-7 text-center">Op.</span>
				<span class="w-10 text-right">Punts</span>
			</div>
			<ul>
				{#each rondaRows.filter((r) => !q.trim() || norm(r.jugador ?? '').includes(norm(q.trim()))) as r (r.player_fcb_id)}
					<li class="border-b border-slate-100 last:border-0">
						<div class="flex items-center gap-2 px-3 py-2">
							<span class="w-6 shrink-0 text-center text-sm font-semibold tabular-nums {r.posicio === 1 ? 'text-amber-500' : 'text-slate-400'}">{r.posicio}</span>
							<div class="min-w-0 flex-1">
								<a href="/jugador/{r.player_fcb_id}" class="block truncate text-sm font-medium leading-tight active:underline">{r.jugador}</a>
								{#if r.club}<div class="truncate text-[11px] text-slate-400">{r.club}</div>{/if}
							</div>
							<span class="w-7 shrink-0 text-center text-xs tabular-nums text-slate-500">{r.opens_jugats}</span>
							<button
								onclick={() => (expandedPlayer = expandedPlayer === r.player_fcb_id ? null : r.player_fcb_id)}
								class="flex w-12 shrink-0 items-center justify-end gap-0.5 font-mono text-sm font-bold tabular-nums"
							>
								{r.punts}
								<span class="text-[9px] text-slate-400">{expandedPlayer === r.player_fcb_id ? '▴' : '▾'}</span>
							</button>
						</div>
						{#if expandedPlayer === r.player_fcb_id && r.detall?.length}
							<div class="space-y-0.5 bg-slate-50 px-3 pb-2 pl-11 pt-1">
								{#each r.detall as d}
									<div class="flex items-center justify-between gap-2 text-[11px] {d.pos || d.penal || d.absent ? '' : 'opacity-50'}">
										<span class="min-w-0 truncate {d.penal ? 'font-medium text-red-500' : 'text-slate-500'}">
											{d.open}{d.temp ? ` ${d.temp}` : ''} · {d.penal
												? 'no presentat'
												: d.absent
													? 'absència justif.'
													: d.pos
														? `${d.pos}è`
														: 'no inscrit'}
										</span>
										<span class="shrink-0 font-mono font-semibold {d.penal ? 'text-red-500' : 'text-slate-700'}">{d.punts}</span>
									</div>
								{/each}
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		</div>
		<p class="px-1 py-2 text-center text-[10px] text-slate-400">Rànquing Català d'Opens 3 Bandes · suma dels 5 darrers opens (Art. XVIII).</p>
	{/if}
{:else if filtered.length === 0}
	<p class="py-6 text-center text-sm text-slate-400">Cap open.</p>
{:else}
	<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
		{#each filtered as o (o.open_id)}
			<li class="border-b border-slate-100 last:border-0">
				<a href="/opens/{o.open_id}" class="flex items-center gap-3 px-3 py-2.5 active:bg-slate-50">
					<div class="min-w-0 flex-1 truncate text-sm font-medium leading-tight">{clean(o.nom)}</div>
					<span class="shrink-0 text-slate-300">›</span>
				</a>
			</li>
		{/each}
	</ul>
	<p class="px-1 py-3 text-center text-[11px] text-slate-400">
		{filtered.length} opens
	</p>
{/if}
