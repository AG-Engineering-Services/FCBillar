<script lang="ts">
	import Billar from '$lib/biblia/billar/Billar.svelte';

	// Diagrama d'un sistema: posicions de les tres boles i el/s traçat/s de
	// l'exemple, tot en coordenades de DIAMANTS (x 0..8 llarg, y 0..4 curt).
	// b1 = blanca (tiradora), b2 = groga, b3 = vermella.
	interface Diagrama {
		boles: { b1: [number, number]; b2: [number, number]; b3: [number, number] };
		traca?: [number, number][]; // recorregut de la bola tiradora (blanca)
		traca2?: [number, number][]; // recorregut secundari opcional (groga)
		nota?: string; // llegenda breu sota el diagrama
	}
	let { diagrama }: { diagrama: Diagrama } = $props();

	// Còpia de les boles (Billar té la prop bindable; aquí és només visor).
	const boles = $derived({
		b1: [...diagrama.boles.b1] as [number, number],
		b2: [...diagrama.boles.b2] as [number, number],
		b3: [...diagrama.boles.b3] as [number, number]
	});
	const traces = $derived([
		...(diagrama.traca?.length
			? [{ color: '#f5f5f5', punts: diagrama.traca.map(([x, y]) => ({ x, y })) }]
			: []),
		...(diagrama.traca2?.length
			? [{ color: '#ffbb00', punts: diagrama.traca2.map(([x, y]) => ({ x, y })) }]
			: [])
	]);
</script>

<figure class="m-0">
	<div class="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
		<Billar {boles} {traces} mostraNumeros mode="visor" />
	</div>
	{#if diagrama.nota}
		<figcaption class="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
			{diagrama.nota}
		</figcaption>
	{/if}
</figure>
