<script lang="ts">
	import '$lib/biblia/biblia.css';
	import { page } from '$app/stores';
	import ApreNav from '$lib/components/ApreNav.svelte';
	let { children } = $props();
	const path = $derived($page.url.pathname);
</script>

<ApreNav />
<div class="biblia">
	<nav class="biblia-nav" aria-label="Bíblia del billar">
		<a href="/biblia" aria-current={path.startsWith('/biblia/quiz') ? undefined : 'page'}>Tirades</a>
		<a href="/biblia/quiz" aria-current={path.startsWith('/biblia/quiz') ? 'page' : undefined}>Test</a>
		<span class="nota">reproducció en català · dades de billiard-bible.com</span>
	</nav>
	{@render children()}
</div>
