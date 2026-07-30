<script lang="ts">
	import { goto } from '$app/navigation';
	import Billar from '$lib/biblia/billar/Billar.svelte';
	import { FAMILIES, familiaCat, TEXT } from '$lib/biblia/api/vocabulari';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const nomsJugadors = $derived(new Map(data.jugadors.map((j) => [j.id, j.nom])));
	const nPagines = $derived(Math.max(1, Math.ceil(data.total / data.mida)));

	function nomJugador(id: number): string {
		return nomsJugadors.get(id) ?? '—';
	}

	type Canvis = Partial<typeof data.filtres> & { pagina?: number };

	function vesA(canvis: Canvis) {
		const f = { ...data.filtres, ...canvis };
		const sp = new URLSearchParams();
		sp.set('tipus', f.esAnalisi ? 'analisi' : 'pro');
		if (f.jugador !== -1) sp.set('jugador', String(f.jugador));
		if (f.familia !== 0) sp.set('familia', String(f.familia));
		if (f.posicio) sp.set('pos', '1');
		if (f.defensa) sp.set('def', '1');
		if (f.evitarKiss) sp.set('kiss', '1');
		if (canvis.pagina && canvis.pagina > 1) sp.set('pagina', String(canvis.pagina));
		goto(`/biblia?${sp}`, { keepFocus: true });
	}

	function enllacDetall(id: number, teAnalisi: boolean): string {
		return `/biblia/${id}${teAnalisi ? '?a=1' : ''}`;
	}
</script>

<div class="contenidor">
	<header class="capsalera">
		<div>
			<h1>{TEXT.subtitol}</h1>
			<p class="compte">
				{data.total.toLocaleString('ca')}
				{TEXT.tiradesTrobades}
			</p>
		</div>
		<div class="tipus">
			<button class:actiu={!data.filtres.esAnalisi} onclick={() => vesA({ esAnalisi: false })}>
				{TEXT.tirsPro} <span class="compte-tag">{data.comptadors.pro.toLocaleString('ca')}</span>
			</button>
			<button class:actiu={data.filtres.esAnalisi} onclick={() => vesA({ esAnalisi: true })}>
				{TEXT.tirsAnalitzats}
				<span class="compte-tag">{data.comptadors.analisi.toLocaleString('ca')}</span>
			</button>
		</div>
	</header>

	<div class="filtres">
		<label>
			{TEXT.jugador}
			<select value={data.filtres.jugador} onchange={(e) => vesA({ jugador: +e.currentTarget.value })}>
				<option value={-1}>{TEXT.totsJugadors}</option>
				{#each data.jugadors as j (j.id)}
					<option value={j.id}>{j.nom}</option>
				{/each}
			</select>
		</label>

		<label>
			{TEXT.familia}
			<select value={data.filtres.familia} onchange={(e) => vesA({ familia: +e.currentTarget.value })}>
				{#each FAMILIES as f (f.idx)}
					<option value={f.idx}>{f.ca}</option>
				{/each}
			</select>
		</label>

		<div class="flags">
			<label class="chk">
				<input
					type="checkbox"
					checked={data.filtres.posicio}
					onchange={(e) => vesA({ posicio: e.currentTarget.checked })}
				/> Posició
			</label>
			<label class="chk">
				<input
					type="checkbox"
					checked={data.filtres.defensa}
					onchange={(e) => vesA({ defensa: e.currentTarget.checked })}
				/> Defensa
			</label>
			<label class="chk">
				<input
					type="checkbox"
					checked={data.filtres.evitarKiss}
					onchange={(e) => vesA({ evitarKiss: e.currentTarget.checked })}
				/> Evitar retruc
			</label>
		</div>
	</div>

	{#if data.tirades.length === 0}
		<p class="buit">{TEXT.capResultat}</p>
	{:else}
		<div class="graella">
			{#each data.tirades as t (t.id)}
				<a class="carta" href={enllacDetall(t.id, t.teAnalisi)}>
					<div class="mini">
						<Billar boles={t.boles} mode="visor" />
					</div>
					<div class="peu">
						<span class="jugador">{nomJugador(t.jugadorId)}</span>
						<span class="etiquetes">
							<span class="tag">{familiaCat(t.familia)}</span>
							{#if t.teAnalisi}<span class="tag analisi">anàlisi</span>{/if}
							{#if t.teVideo}<span class="tag video">▶</span>{/if}
							{#if t.esPosicio}<span class="tag">pos</span>{/if}
							{#if t.esDefensa}<span class="tag">def</span>{/if}
							{#if t.esEvitarKiss}<span class="tag">retruc</span>{/if}
						</span>
					</div>
				</a>
			{/each}
		</div>

		<nav class="paginacio">
			<button disabled={data.pagina <= 1} onclick={() => vesA({ pagina: data.pagina - 1 })}>
				← {TEXT.anterior}
			</button>
			<span>{TEXT.pagina} {data.pagina} {TEXT.de} {nPagines.toLocaleString('ca')}</span>
			<button disabled={data.pagina >= nPagines} onclick={() => vesA({ pagina: data.pagina + 1 })}>
				{TEXT.seguent} →
			</button>
		</nav>
	{/if}
</div>

<style>
	.capsalera {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		align-items: flex-end;
		justify-content: space-between;
		margin-bottom: 1rem;
	}
	.capsalera h1 {
		margin: 0;
		font-size: 1.5rem;
	}
	.compte {
		margin: 0.15rem 0 0;
		color: var(--text-suau);
		font-size: 0.9rem;
	}
	.tipus {
		display: flex;
		gap: 0.4rem;
	}
	.compte-tag {
		display: inline-block;
		font-size: 0.72rem;
		padding: 0.02rem 0.35rem;
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.14);
		margin-left: 0.15rem;
	}
	.filtres {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem 1.25rem;
		align-items: end;
		padding: 0.85rem 1rem;
		margin-bottom: 1.25rem;
		background: var(--fons-2);
		border: 1px solid var(--vora);
		border-radius: var(--radi);
	}
	.filtres label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.8rem;
		color: var(--text-suau);
	}
	.flags {
		display: flex;
		gap: 1rem;
		align-items: center;
		padding-bottom: 0.35rem;
	}
	.chk {
		flex-direction: row !important;
		align-items: center;
		gap: 0.35rem !important;
		color: var(--text) !important;
		font-size: 0.9rem !important;
		cursor: pointer;
	}
	.graella {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
		gap: 1rem;
	}
	.carta {
		display: block;
		background: var(--fons-2);
		border: 1px solid var(--vora);
		border-radius: var(--radi);
		overflow: hidden;
		color: var(--text);
		transition: border-color 0.12s ease, transform 0.12s ease;
	}
	.carta:hover {
		border-color: var(--accent);
		transform: translateY(-2px);
		text-decoration: none;
	}
	.mini {
		padding: 0.5rem 0.5rem 0;
	}
	.peu {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		padding: 0.5rem 0.6rem 0.6rem;
	}
	.jugador {
		font-size: 0.85rem;
		font-weight: 600;
	}
	.etiquetes {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}
	.tag {
		font-size: 0.68rem;
		padding: 0.05rem 0.35rem;
		border-radius: 5px;
		background: var(--fons-3);
		color: var(--text-suau);
		border: 1px solid var(--vora);
	}
	.tag.analisi {
		background: #123;
		color: var(--accent);
		border-color: #235;
	}
	.tag.video {
		color: #ff6b6b;
	}
	.buit {
		color: var(--text-suau);
		padding: 2rem 0;
	}
	.paginacio {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		margin: 1.75rem 0 0;
		color: var(--text-suau);
		font-size: 0.9rem;
	}
	.paginacio button:disabled {
		opacity: 0.4;
		cursor: default;
	}
</style>
