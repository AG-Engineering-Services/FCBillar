<script lang="ts">
	export let label: string;
	export let value: string | number | null | undefined;
	// Si es passa onClick, la targeta esdevé clicable (cursor + hover + fletxa).
	export let onClick: (() => void) | null = null;
</script>

{#if onClick}
	<button
		type="button"
		class="text-left w-full bg-white rounded-lg border border-slate-200 p-4 transition-colors hover:border-slate-400 hover:bg-slate-50 cursor-pointer"
		on:click={onClick}
	>
		<div class="text-xs uppercase tracking-wide text-slate-500 flex items-center justify-between">
			<span>{label}</span>
			<span class="text-slate-300">›</span>
		</div>
		<div class="text-2xl font-bold">{value ?? '—'}</div>
	</button>
{:else}
	<div class="bg-white rounded-lg border border-slate-200 p-4">
		<div class="text-xs uppercase tracking-wide text-slate-500">{label}</div>
		<div class="text-2xl font-bold">{value ?? '—'}</div>
	</div>
{/if}
