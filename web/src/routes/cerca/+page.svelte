<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase';

	interface P {
		fcb_id: string;
		nom: string;
		club: string | null;
	}

	let players = $state<P[]>([]);
	let q = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);

	function norm(s: string): string {
		return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
	}

	onMount(async () => {
		try {
			const [{ data: pl, error: ep }, { data: cl, error: ec }] = await Promise.all([
				supabase.from('players').select('fcb_id, nom, club_fcb_id'),
				supabase.from('clubs').select('fcb_id, nom')
			]);
			if (ep) throw ep;
			if (ec) throw ec;
			const clubs = new Map((cl ?? []).map((c) => [c.fcb_id, c.nom]));
			players = (pl ?? [])
				.map((p) => ({ fcb_id: p.fcb_id, nom: p.nom, club: clubs.get(p.club_fcb_id) ?? null }))
				.sort((a, b) => a.nom.localeCompare(b.nom));
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});

	const results = $derived.by(() => {
		const t = norm(q.trim());
		if (!t) return [] as P[];
		return players.filter((p) => norm(p.nom).includes(t)).slice(0, 60);
	});
</script>

<input
	bind:value={q}
	inputmode="search"
	autofocus
	placeholder="Cerca qualsevol jugador…"
	class="mb-3 w-full rounded-lg border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 py-2.5 px-3 text-sm shadow-sm"
/>

{#if error}
	<div class="rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-300">{error}</div>
{:else if loading}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Carregant jugadors…</p>
{:else if !q.trim()}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">
		Escriu un nom per cercar entre {players.length} jugadors.
	</p>
{:else if results.length === 0}
	<p class="py-6 text-center text-sm text-slate-400 dark:text-slate-500">Cap jugador amb «{q}».</p>
{:else}
	<ul class="overflow-hidden rounded-xl bg-white dark:bg-slate-900 ring-1 ring-slate-200 dark:ring-slate-800 lg:columns-2 lg:gap-x-6">
		{#each results as p (p.fcb_id)}
			<li class="break-inside-avoid border-b border-slate-100 dark:border-slate-800 last:border-0">
				<a href="/jugador/{p.fcb_id}" class="flex items-center gap-3 px-3 py-2.5 active:bg-slate-50 dark:active:bg-slate-800/50">
					<div class="min-w-0 flex-1">
						<div class="truncate text-sm font-medium leading-tight">{p.nom}</div>
						{#if p.club}<div class="truncate text-xs text-slate-400 dark:text-slate-500">{p.club}</div>{/if}
					</div>
					<span class="shrink-0 text-slate-300 dark:text-slate-600">›</span>
				</a>
			</li>
		{/each}
	</ul>
{/if}
