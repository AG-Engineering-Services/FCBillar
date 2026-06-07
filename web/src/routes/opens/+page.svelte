<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase, type Open } from '$lib/supabase';

	let opens = $state<Open[]>([]);
	let ranking = $state<any[]>([]);
	let ronda = $state<number | null>(null);
	let q = $state('');
	let cat = $state<'opens' | 'camp' | 'ranking'>('opens');
	let loading = $state(true);
	let error = $state<string | null>(null);

	const rondes = $derived([...new Set(ranking.map((r) => r.ronda as number))].sort((a, b) => a - b));
	$effect(() => {
		if (ronda == null && rondes.length) ronda = rondes[rondes.length - 1];
	});
	const rondaRows = $derived(ranking.filter((r) => r.ronda === ronda).sort((a, b) => a.posicio - b.posicio));
	const rondaInfo = $derived(ranking.find((r) => r.ronda === ronda));
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
			const [{ data, error: e }, { data: rk }] = await Promise.all([
				supabase.from('opens').select('*').order('nom'),
				supabase.from('open_ranking').select('*')
			]);
			if (e) throw e;
			opens = (data ?? []) as Open[];
			ranking = rk ?? [];
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const filtered = $derived(
		opens
			.filter((o) => (cat === 'opens' ? isOpen(o.nom) : !isOpen(o.nom)))
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
		onclick={() => (cat = 'camp')}
		class="rounded-md px-3 py-1 font-medium {cat === 'camp' ? 'bg-white shadow-sm' : 'text-slate-500'}"
		>Camp. Catalunya</button>
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
		{filtered.length} {cat === 'opens' ? 'opens' : 'campionats'}
	</p>
{/if}
