<script lang="ts">
	import { tick } from 'svelte';
	import { ADMIN_EMAIL, marcaAdmin } from '$lib/admin';

	// Marca d'administració des de dins la PWA. A l'iPhone, l'app instal·lada no té
	// barra d'adreces (no s'hi pot posar `?admin`) i no comparteix l'emmagatzematge
	// amb Safari: sense això, la campana i la resta d'eines d'admin no hi surten mai.
	// S'hi arriba tocant cinc cops seguits el nom de la capçalera.
	let { onAdmin }: { onAdmin: () => void } = $props();

	let obert = $state(false);
	let correu = $state('');
	let error = $state('');
	let camp: HTMLInputElement | undefined = $state();
	let tocs: number[] = [];

	export async function toc() {
		const ara = Date.now();
		tocs = [...tocs.filter((t) => ara - t < 3000), ara];
		if (tocs.length < 5) return;
		tocs = [];
		obert = true;
		error = '';
		await tick();
		camp?.focus();
	}

	function confirma(e: SubmitEvent) {
		e.preventDefault();
		if (correu.trim().toLowerCase() !== ADMIN_EMAIL) {
			error = 'Aquest correu no té accés d’administració.';
			return;
		}
		marcaAdmin();
		obert = false;
		correu = '';
		onAdmin();
	}

	function alTeclat(e: KeyboardEvent) {
		if (e.key === 'Escape' && obert) obert = false;
	}
</script>

<svelte:window onkeydown={alTeclat} />

{#if obert}
	<form
		onsubmit={confirma}
		role="dialog"
		aria-labelledby="titol-admin"
		class="fixed inset-x-4 top-14 z-30 rounded-md border border-slate-200 bg-white p-4 text-sm shadow-lg sm:left-auto sm:right-4 sm:w-80 dark:border-slate-700 dark:bg-slate-900"
	>
		<h2 id="titol-admin" class="text-base font-semibold">Mode administració</h2>
		<label for="correu-admin" class="mt-2 block text-slate-600 dark:text-slate-300"
			>Correu autoritzat</label
		>
		<input
			bind:this={camp}
			bind:value={correu}
			id="correu-admin"
			type="email"
			autocomplete="email"
			placeholder="correu@exemple.cat"
			class="mt-1 min-h-11 w-full rounded-sm border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
		/>
		<p class="mt-1 min-h-5 text-xs text-red-700 dark:text-red-400" role="status">{error}</p>
		<div class="mt-1 flex gap-2">
			<button
				type="submit"
				class="min-h-11 rounded-sm bg-sky-700 px-4 font-medium text-white hover:bg-sky-800 dark:bg-sky-600 dark:hover:bg-sky-500"
				>Activa'l en aquest dispositiu</button
			>
			<button
				type="button"
				onclick={() => (obert = false)}
				class="min-h-11 rounded-sm px-3 text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
				>Tanca</button
			>
		</div>
	</form>
{/if}
