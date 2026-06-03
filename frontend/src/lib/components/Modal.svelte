<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	export let title = '';
	export let open = false;
	const dispatch = createEventDispatcher();

	function close() {
		dispatch('close');
	}
	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') close();
	}
</script>

<svelte:window on:keydown={onKey} />

{#if open}
	<!-- Overlay -->
	<div
		class="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 p-4 overflow-y-auto"
		on:click={close}
		role="presentation"
	>
		<!-- Diàleg: aturem la propagació perquè un clic dins no tanqui -->
		<div
			class="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-5xl mt-10"
			on:click|stopPropagation
			role="dialog"
			aria-modal="true"
		>
			<div class="flex items-center justify-between px-4 py-3 border-b border-slate-200">
				<h3 class="font-semibold">{title}</h3>
				<button
					type="button"
					class="text-slate-400 hover:text-slate-700 text-xl leading-none px-2"
					on:click={close}
					aria-label="Tanca">×</button
				>
			</div>
			<div class="max-h-[70vh] overflow-y-auto">
				<slot />
			</div>
		</div>
	</div>
{/if}
