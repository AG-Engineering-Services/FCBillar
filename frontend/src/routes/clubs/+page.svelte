<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import type { ClubKpi } from '$lib/types';
	import Collapsible from '$lib/components/Collapsible.svelte';
	import SortableTable from '$lib/components/SortableTable.svelte';

	const columns = [
		{
			key: 'nom',
			label: 'Club',
			link: (r: ClubKpi) => `/focus?kind=real&key=${encodeURIComponent(r.fcb_id)}`
		},
		{ key: 'num_jugadors', label: 'Jugadors', numeric: true },
		{ key: 'num_equips', label: 'Equips', numeric: true },
		{ key: 'num_partides', label: 'Partides', numeric: true }
	];

	let clubs: ClubKpi[] = [];
	let loading = true;

	onMount(async () => {
		try {
			clubs = await api<ClubKpi[]>('/api/clubs');
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	});
</script>

<h1 class="text-2xl font-bold mb-4">Clubs</h1>

{#if loading}
	<p class="text-slate-500">Carregant…</p>
{:else}
	<Collapsible title="Clubs" open={true} count={clubs.length}>
		<SortableTable
			{columns}
			rows={clubs}
			initialSortKey="num_partides"
			initialSortDir="desc"
			emptyText="Cap club"
		/>
	</Collapsible>
{/if}
