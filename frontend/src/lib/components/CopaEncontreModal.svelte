<script lang="ts">
	import Modal from './Modal.svelte';
	import SortableTable from './SortableTable.svelte';
	import { api } from '$lib/api';
	import { mitjana, fmtMitjana } from '$lib/format';

	export let encontreId: number | null = null;
	export let open = false;

	let detail: any = null;
	let loading = false;

	const cols = [
		{ key: 'local_nom', label: 'Local' },
		{ key: 'local_caramboles', label: 'C₁', numeric: true },
		{ key: 'local_serie', label: 'S₁', numeric: true, muted: true, fmt: (v: any) => (v ?? '—') },
		{ key: 'visitant_nom', label: 'Visitant' },
		{ key: 'visitant_caramboles', label: 'C₂', numeric: true },
		{ key: 'visitant_serie', label: 'S₂', numeric: true, muted: true, fmt: (v: any) => (v ?? '—') },
		{ key: 'entrades', label: 'E', numeric: true },
		{
			key: 'm1',
			label: 'M₁',
			numeric: true,
			value: (r: any) => mitjana(r.local_caramboles, r.entrades),
			fmt: fmtMitjana
		},
		{
			key: 'm2',
			label: 'M₂',
			numeric: true,
			value: (r: any) => mitjana(r.visitant_caramboles, r.entrades),
			fmt: fmtMitjana
		},
		{
			key: 'punts',
			label: 'Punts',
			numeric: true,
			value: (r: any) => r.punts_local + '-' + r.punts_visitant
		}
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
			detail = await api(`/api/results/copa/encontre/${id}`);
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
			<SortableTable columns={cols} rows={detail.partides ?? []} emptyText="Sense partides." />
		{:else}
			<p class="text-slate-400 p-4">Sense dades.</p>
		{/if}
	</div>
</Modal>
