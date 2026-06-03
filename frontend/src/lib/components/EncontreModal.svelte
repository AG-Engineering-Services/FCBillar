<script lang="ts">
	import Modal from './Modal.svelte';
	import SortableTable from './SortableTable.svelte';
	import { api } from '$lib/api';
	import { fmtDate, mitjana, fmtMitjana, winnerBadge } from '$lib/format';

	export let encontreId: number | null = null;
	export let open = false;

	let detail: any = null;
	let loading = false;

	const cols = [
		{ key: 'modalitat', label: 'Modalitat' },
		{ key: 'local', label: 'Local' },
		{ key: 'cara1', label: 'C₁', numeric: true },
		{ key: '_wl', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'L') },
		{ key: 'visitant', label: 'Visitant' },
		{ key: 'cara2', label: 'C₂', numeric: true },
		{ key: '_wv', label: '', sortable: false, badge: (r: any) => winnerBadge(r, 'V') },
		{ key: 'entrades', label: 'E', numeric: true },
		{ key: 'm1', label: 'M₁', numeric: true, value: (r: any) => mitjana(r.cara1, r.entrades), fmt: fmtMitjana },
		{ key: 'm2', label: 'M₂', numeric: true, value: (r: any) => mitjana(r.cara2, r.entrades), fmt: fmtMitjana },
		{ key: 'serie1', label: 'S₁', numeric: true, muted: true, fmt: (v: any) => (v ?? '—') },
		{ key: 'serie2', label: 'S₂', numeric: true, muted: true, fmt: (v: any) => (v ?? '—') }
	];

	// Carrega quan s'obre amb un id; en tancar, oblida l'últim per recarregar.
	$: if (open && encontreId != null) load(encontreId);
	$: if (!open) lastLoaded = null;

	let lastLoaded: number | null = null;
	async function load(id: number) {
		if (id === lastLoaded) return;
		lastLoaded = id;
		loading = true;
		detail = null;
		try {
			detail = await api(`/api/results/encontre/${id}`);
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	}

	$: title = detail
		? `${detail.equip_local} ${detail.p_match_local ?? ''}–${detail.p_match_visitant ?? ''} ${detail.equip_visitant}`
		: 'Encontre';
</script>

<Modal {open} {title} on:close>
	<div class="p-2">
		{#if loading}
			<p class="text-slate-500 p-4">Carregant…</p>
		{:else if detail}
			<div class="px-2 pb-2 text-sm text-slate-500">
				{fmtDate(detail.data)}{#if detail.fase}
					<span class="ml-2 inline-block px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 text-xs"
						>{detail.fase}</span
					>
				{/if}
			</div>
			<SortableTable columns={cols} rows={detail.games ?? []} emptyText="Sense partides." />
		{:else}
			<p class="text-slate-400 p-4">Sense dades.</p>
		{/if}
	</div>
</Modal>
