<script lang="ts">
	export let title: string | null = null;
</script>

<div class="bg-white rounded-lg border border-slate-200 overflow-hidden">
	{#if title}
		<div class="px-4 py-3 border-b border-slate-200 font-semibold">{title}</div>
	{/if}
	<slot />
</div>
