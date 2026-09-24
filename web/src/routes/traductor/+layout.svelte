<script lang="ts">
	import ApreNav from '$lib/components/ApreNav.svelte';
	let { children } = $props();
</script>

<ApreNav />
{@render children()}
