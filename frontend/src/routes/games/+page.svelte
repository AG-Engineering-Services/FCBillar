<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { GameRow, Modalitat } from '$lib/types';
	import Collapsible from '$lib/components/Collapsible.svelte';
	import SortableTable from '$lib/components/SortableTable.svelte';
	import { winnerBadge, fmtDate, mitjana, fmtMitjana } from '$lib/format';

	// Filter state
	let playerFilter = '';
	let clubFilter = '';
	let modalitatFilter: number | undefined = undefined;
	let competicioFilter = '';
	let seasonOnly = false;

	// Data
	let modalitats: Modalitat[] = [];
	let games: GameRow[] = [];
	let loading = true;
	let error = '';

	async function search() {
		loading = true;
		error = '';
		try {
			const params = new URLSearchParams();
			if (playerFilter.trim()) params.set('player', encodeURIComponent(playerFilter.trim()));
			if (clubFilter.trim()) params.set('club', encodeURIComponent(clubFilter.trim()));
			if (modalitatFilter !== undefined) params.set('modalitat', String(modalitatFilter));
			if (competicioFilter) params.set('competicio', competicioFilter);
			if (seasonOnly) params.set('season_only', 'true');
			params.set('limit', '300');

			// Rebuild with proper encoding (URLSearchParams already encodes values)
			// but our api() just fetches the path directly, so build manually:
			const qs = buildQuery();
			games = await api<GameRow[]>(`/api/games?${qs}`);
		} catch (e: any) {
			error = e.message ?? 'Error desconegut';
			games = [];
		} finally {
			loading = false;
		}
	}

	function buildQuery(): string {
		const parts: string[] = [];
		if (playerFilter.trim()) parts.push(`player=${encodeURIComponent(playerFilter.trim())}`);
		if (clubFilter.trim()) parts.push(`club=${encodeURIComponent(clubFilter.trim())}`);
		if (modalitatFilter !== undefined) parts.push(`modalitat=${modalitatFilter}`);
		if (competicioFilter) parts.push(`competicio=${encodeURIComponent(competicioFilter)}`);
		if (seasonOnly) parts.push(`season_only=true`);
		parts.push(`limit=300`);
		return parts.join('&');
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') search();
	}

	onMount(async () => {
		try {
			modalitats = await api<Modalitat[]>('/api/modalitats');
		} catch {
			// non-fatal
		}
		await search();
	});

	const columns = [
		{ key: 'data', label: 'Data', muted: true, fmt: (v: any) => fmtDate(v) },
		{ key: 'modalitat', label: 'Modalitat' },
		{ key: 'competicio', label: 'Competició', muted: true, fmt: (v: any) => v ?? '' },
		{ key: 'local', label: 'Local' },
		{ key: 'cara1', label: 'C₁', numeric: true },
		{ key: '_wl', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'L') },
		{ key: 'visitant', label: 'Visitant' },
		{ key: 'cara2', label: 'C₂', numeric: true },
		{ key: '_wv', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'V') },
		{ key: 'entrades', label: 'E', numeric: true },
		{ key: 'm1', label: 'M₁', numeric: true, value: (r: any) => mitjana(r.cara1, r.entrades), fmt: fmtMitjana },
		{ key: 'm2', label: 'M₂', numeric: true, value: (r: any) => mitjana(r.cara2, r.entrades), fmt: fmtMitjana },
		{ key: 'club_local', label: 'Club local', muted: true, fmt: (v: any) => v ?? '' },
		{ key: 'club_visitant', label: 'Club visitant', muted: true, fmt: (v: any) => v ?? '' }
	];
</script>

<h1 class="text-2xl font-bold mb-4">Cerca de partides</h1>

<!-- Filter bar -->
<div class="flex flex-wrap gap-2 items-end mb-4">
	<div class="flex flex-col gap-1">
		<label class="text-xs text-slate-500 font-medium">Jugador</label>
		<input
			type="text"
			bind:value={playerFilter}
			on:keydown={handleKeydown}
			placeholder="Nom del jugador…"
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
		/>
	</div>

	<div class="flex flex-col gap-1">
		<label class="text-xs text-slate-500 font-medium">Club</label>
		<input
			type="text"
			bind:value={clubFilter}
			on:keydown={handleKeydown}
			placeholder="Nom del club…"
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
		/>
	</div>

	<div class="flex flex-col gap-1">
		<label class="text-xs text-slate-500 font-medium">Modalitat</label>
		<select
			bind:value={modalitatFilter}
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
		>
			<option value={undefined}>Totes</option>
			{#each modalitats as m}
				<option value={m.codi_fcb}>{m.nom}</option>
			{/each}
		</select>
	</div>

	<div class="flex flex-col gap-1">
		<label class="text-xs text-slate-500 font-medium">Competició</label>
		<select
			bind:value={competicioFilter}
			class="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
		>
			<option value="">Totes</option>
			<option value="LLIGA">Lliga</option>
			<option value="INDIVIDUAL">Individual</option>
			<option value="COPA">Copa</option>
		</select>
	</div>

	<label class="flex items-center gap-2 text-sm text-slate-600">
		<input type="checkbox" bind:checked={seasonOnly} />
		Només temporada actual
	</label>

	<button
		on:click={search}
		class="px-3 py-1.5 rounded-md bg-slate-900 text-white text-sm hover:bg-slate-700"
	>
		Cercar
	</button>
</div>

<!-- Results -->
{#if loading}
	<p class="text-slate-500">Carregant…</p>
{:else if error}
	<p class="text-red-500 text-sm">{error}</p>
{:else}
	<Collapsible title="Partides" open={true} count={games.length}>
		<SortableTable {columns} rows={games} emptyText="Cap partida trobada" />
	</Collapsible>
{/if}
