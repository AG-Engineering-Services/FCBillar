<script lang="ts">
	// Error de càrrega: què ha fallat, en català; el text de la base de dades
	// queda plegat per si algú l'ha de passar a qui manté el web.
	let {
		missatge,
		detall = null,
		onretry
	}: { missatge: string; detall?: string | null; onretry?: () => void } = $props();
</script>

<div
	role="alert"
	class="rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300"
>
	<p>{missatge}</p>
	{#if onretry}
		<button type="button" onclick={onretry} class="min-h-11 font-semibold underline">
			Torna-ho a provar
		</button>
	{/if}
	{#if detall}
		<details class="text-xs">
			<summary class="min-h-11 cursor-pointer py-3">Detall tècnic</summary>
			<p class="break-words pb-1 font-mono">{detall}</p>
		</details>
	{/if}
</div>
