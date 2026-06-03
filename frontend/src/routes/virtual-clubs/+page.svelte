<script lang="ts">
	import { onMount } from 'svelte';
	import { api, apiSend } from '$lib/api';
	import type { VirtualClub, PlayerKpi } from '$lib/types';
	import Card from '$lib/components/Card.svelte';
	import Collapsible from '$lib/components/Collapsible.svelte';

	// ── List state ─────────────────────────────────────────────────────────────
	let clubs: VirtualClub[] = [];
	let loading = true;
	let selectedId: number | null = null;
	let newNom = '';

	// ── Rename inline state ────────────────────────────────────────────────────
	let renaming = false;
	let renameNom = '';

	// ── Members state ──────────────────────────────────────────────────────────
	let members: PlayerKpi[] = [];
	let membersLoading = false;

	// ── Search state ───────────────────────────────────────────────────────────
	let searchQ = '';
	let searchResults: PlayerKpi[] = [];
	let searching = false;

	// ── Derived: selected club ─────────────────────────────────────────────────
	$: selectedClub = clubs.find((c) => c.id === selectedId) ?? null;

	// ── Init ────────────────────────────────────────────────────────────────────
	onMount(async () => {
		await loadClubs();
	});

	async function loadClubs() {
		loading = true;
		try {
			clubs = await api<VirtualClub[]>('/api/virtual-clubs');
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	}

	async function loadMembers(id: number) {
		membersLoading = true;
		members = [];
		try {
			members = await api<PlayerKpi[]>(`/api/virtual-clubs/${id}/members`);
		} catch (e) {
			console.error(e);
		} finally {
			membersLoading = false;
		}
	}

	async function selectClub(id: number) {
		selectedId = id;
		renaming = false;
		searchResults = [];
		searchQ = '';
		await loadMembers(id);
	}

	// ── Create ─────────────────────────────────────────────────────────────────
	async function createClub() {
		if (!newNom.trim()) return;
		try {
			await apiSend('/api/virtual-clubs', 'POST', { nom: newNom.trim() });
			newNom = '';
			await loadClubs();
		} catch (e) {
			console.error(e);
		}
	}

	// ── Rename ─────────────────────────────────────────────────────────────────
	function startRename() {
		if (!selectedClub) return;
		renameNom = selectedClub.nom;
		renaming = true;
	}

	async function confirmRename() {
		if (!selectedId || !renameNom.trim()) return;
		try {
			await apiSend(`/api/virtual-clubs/${selectedId}`, 'PUT', { nom: renameNom.trim() });
			renaming = false;
			await loadClubs();
		} catch (e) {
			console.error(e);
		}
	}

	function cancelRename() {
		renaming = false;
	}

	// ── Delete ─────────────────────────────────────────────────────────────────
	async function deleteClub() {
		if (!selectedId || !selectedClub) return;
		if (!window.confirm(`Esborrar "${selectedClub.nom}"? Aquesta acció no es pot desfer.`)) return;
		try {
			await apiSend(`/api/virtual-clubs/${selectedId}`, 'DELETE');
			selectedId = null;
			members = [];
			searchResults = [];
			await loadClubs();
		} catch (e) {
			console.error(e);
		}
	}

	// ── Remove member ──────────────────────────────────────────────────────────
	async function removeMember(fcb_id: string) {
		if (!selectedId) return;
		try {
			await apiSend(`/api/virtual-clubs/${selectedId}/members/${fcb_id}`, 'DELETE');
			await Promise.all([loadMembers(selectedId), loadClubs()]);
		} catch (e) {
			console.error(e);
		}
	}

	// ── Search players ─────────────────────────────────────────────────────────
	async function searchPlayers() {
		if (!searchQ.trim()) return;
		searching = true;
		try {
			searchResults = await api<PlayerKpi[]>(
				`/api/players?q=${encodeURIComponent(searchQ.trim())}&limit=50`
			);
		} catch (e) {
			console.error(e);
		} finally {
			searching = false;
		}
	}

	function onSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') searchPlayers();
	}

	// ── Add member ─────────────────────────────────────────────────────────────
	async function addMember(fcb_id: string) {
		if (!selectedId) return;
		try {
			await apiSend(`/api/virtual-clubs/${selectedId}/members`, 'POST', {
				player_fcb_id: fcb_id
			});
			await Promise.all([loadMembers(selectedId), loadClubs()]);
		} catch (e) {
			console.error(e);
		}
	}
</script>

<h1 class="text-2xl font-bold mb-4">Clubs virtuals</h1>

<div class="grid md:grid-cols-2 gap-6">
	<!-- LEFT: list + create -->
	<div class="flex flex-col gap-4">
		<Collapsible title="Clubs virtuals" open={true} count={clubs.length}>
			{#if loading}
				<p class="text-slate-500 px-4 py-3">Carregant…</p>
			{:else}
				<table class="w-full text-sm">
					<thead class="bg-slate-50 text-slate-500 text-left">
						<tr>
							<th class="px-4 py-2 font-medium">Club</th>
							<th class="px-4 py-2 font-medium text-right">Membres</th>
						</tr>
					</thead>
					<tbody>
						{#each clubs as c}
							<tr
								class="border-t border-slate-100 hover:bg-slate-50 cursor-pointer {selectedId === c.id
									? 'bg-slate-100'
									: ''}"
								on:click={() => selectClub(c.id)}
							>
								<td class="px-4 py-2">{c.nom}</td>
								<td class="px-4 py-2 text-right">{c.num_membres}</td>
							</tr>
						{/each}
					</tbody>
				</table>

				<!-- Create row -->
				<div class="flex items-center gap-2 px-4 py-3 border-t border-slate-100">
					<input
						class="border border-slate-300 rounded-md px-3 py-1.5 text-sm flex-1 min-w-0"
						type="text"
						placeholder="Nom del nou club…"
						bind:value={newNom}
						on:keydown={(e) => e.key === 'Enter' && createClub()}
					/>
					<button
						class="px-3 py-1.5 rounded-md bg-slate-900 text-white text-sm hover:bg-slate-700 whitespace-nowrap"
						on:click={createClub}
					>
						Crea
					</button>
				</div>
			{/if}
		</Collapsible>

		<!-- Actions for selected club -->
		{#if selectedClub}
			<Card title="Accions — {selectedClub.nom}">
				<div class="px-4 py-3 flex flex-col gap-3">
					{#if renaming}
						<div class="flex items-center gap-2">
							<input
								class="border border-slate-300 rounded-md px-3 py-1.5 text-sm flex-1 min-w-0"
								type="text"
								bind:value={renameNom}
								on:keydown={(e) => e.key === 'Enter' && confirmRename()}
							/>
							<button
								class="px-3 py-1.5 rounded-md bg-slate-900 text-white text-sm hover:bg-slate-700"
								on:click={confirmRename}
							>
								Desa
							</button>
							<button
								class="px-3 py-1.5 rounded-md bg-white border border-slate-300 text-sm hover:bg-slate-100"
								on:click={cancelRename}
							>
								Cancel·la
							</button>
						</div>
					{:else}
						<div class="flex gap-2 flex-wrap">
							<button
								class="px-3 py-1.5 rounded-md bg-white border border-slate-300 text-sm hover:bg-slate-100"
								on:click={startRename}
							>
								Reanomena
							</button>
							<button
								class="px-3 py-1.5 rounded-md bg-red-600 text-white text-sm hover:bg-red-700"
								on:click={deleteClub}
							>
								Esborra
							</button>
						</div>
					{/if}
				</div>
			</Card>
		{/if}
	</div>

	<!-- RIGHT: members + search -->
	<div class="flex flex-col gap-4">
		{#if selectedClub}
			<!-- Members table -->
			<Collapsible title="Membres — {selectedClub.nom}" open={true} count={members.length}>
				{#if membersLoading}
					<p class="text-slate-500 px-4 py-3">Carregant…</p>
				{:else}
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-slate-500 text-left">
							<tr>
								<th class="px-4 py-2 font-medium">ID FCB</th>
								<th class="px-4 py-2 font-medium">Jugador</th>
								<th class="px-4 py-2 font-medium">Club real</th>
								<th class="px-4 py-2 font-medium text-right">Partides</th>
								<th class="px-4 py-2 font-medium"></th>
							</tr>
						</thead>
						<tbody>
							{#each members as m}
								<tr class="border-t border-slate-100 hover:bg-slate-50">
									<td class="px-4 py-2 text-slate-500 text-xs">{m.fcb_id}</td>
									<td class="px-4 py-2">
										<a class="hover:underline" href="/players/{m.fcb_id}">{m.nom}</a>
									</td>
									<td class="px-4 py-2 text-slate-600">{m.club ?? '—'}</td>
									<td class="px-4 py-2 text-right">{m.num_partides}</td>
									<td class="px-4 py-2">
										<button
											class="px-3 py-1.5 rounded-md bg-white border border-slate-300 text-sm hover:bg-slate-100"
											on:click={() => removeMember(m.fcb_id)}
										>
											Treu
										</button>
									</td>
								</tr>
							{/each}
							{#if members.length === 0}
								<tr>
									<td colspan="5" class="px-4 py-3 text-slate-500 text-center"
										>Cap membre</td
									>
								</tr>
							{/if}
						</tbody>
					</table>
				{/if}
			</Collapsible>

			<!-- Add player search -->
			<Collapsible title="Afegir jugador" open={true}>
				<div class="px-4 py-3 flex items-center gap-2">
					<input
						class="border border-slate-300 rounded-md px-3 py-1.5 text-sm flex-1 min-w-0"
						type="text"
						placeholder="Cerca per nom o ID…"
						bind:value={searchQ}
						on:keydown={onSearchKeydown}
					/>
					<button
						class="px-3 py-1.5 rounded-md bg-slate-900 text-white text-sm hover:bg-slate-700 whitespace-nowrap"
						on:click={searchPlayers}
					>
						Cerca
					</button>
				</div>

				{#if searching}
					<p class="text-slate-500 px-4 pb-3">Carregant…</p>
				{:else if searchResults.length > 0}
					<table class="w-full text-sm">
						<thead class="bg-slate-50 text-slate-500 text-left">
							<tr>
								<th class="px-4 py-2 font-medium">ID FCB</th>
								<th class="px-4 py-2 font-medium">Jugador</th>
								<th class="px-4 py-2 font-medium">Club</th>
								<th class="px-4 py-2 font-medium text-right">Partides</th>
								<th class="px-4 py-2 font-medium"></th>
							</tr>
						</thead>
						<tbody>
							{#each searchResults as p}
								<tr class="border-t border-slate-100 hover:bg-slate-50">
									<td class="px-4 py-2 text-slate-500 text-xs">{p.fcb_id}</td>
									<td class="px-4 py-2">{p.nom}</td>
									<td class="px-4 py-2 text-slate-600">{p.club ?? '—'}</td>
									<td class="px-4 py-2 text-right">{p.num_partides}</td>
									<td class="px-4 py-2">
										<button
											class="px-3 py-1.5 rounded-md bg-slate-900 text-white text-sm hover:bg-slate-700"
											on:click={() => addMember(p.fcb_id)}
										>
											Afegeix
										</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</Collapsible>
		{:else}
			<div class="flex items-center justify-center h-32 text-slate-400 text-sm">
				Selecciona un club per gestionar-ne els membres.
			</div>
		{/if}
	</div>
</div>
