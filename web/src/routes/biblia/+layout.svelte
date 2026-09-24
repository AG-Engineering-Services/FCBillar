<script lang="ts">
	import '$lib/biblia/biblia.css';
	import ApreNav from '$lib/components/ApreNav.svelte';
	let { children } = $props();
</script>

<ApreNav />
<div class="biblia">
	<nav class="biblia-nav">
		<a href="/biblia">🎱 Tirades</a>
		<a href="/biblia/quiz">🎯 Test</a>
		<span class="nota">reproducció en català · dades de billiard-bible.com</span>
	</nav>
	{@render children()}
</div>
