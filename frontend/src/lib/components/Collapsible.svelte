<script lang="ts">
	// Secció col·lapsable amb capçalera clicable. Estil consistent amb Card.
	export let title: string;
	export let open = true;
	export let count: number | string | null = null;
	export let subtitle: string | null = null;
</script>

<div class="bg-white rounded-lg border border-slate-200 overflow-hidden">
	<button
		type="button"
		class="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50 transition-colors"
		on:click={() => (open = !open)}
	>
		<span class="font-semibold flex items-center gap-2">
			<span class="text-slate-400 text-xs w-3">{open ? '▼' : '▶'}</span>
			{title}
			{#if count !== null}
				<span class="text-xs font-normal text-slate-400">({count})</span>
			{/if}
			{#if subtitle}
				<span class="text-xs font-normal text-slate-400">· {subtitle}</span>
			{/if}
		</span>
	</button>
	{#if open}
		<div class="border-t border-slate-200">
			<slot />
		</div>
	{/if}
</div>
