<script lang="ts">
	import '../app.css';
	let { children } = $props();
</script>

<div class="mx-auto flex min-h-full max-w-screen-sm flex-col">
	<header class="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
		<div class="flex items-center gap-2 px-4 py-3">
			<span class="text-base font-bold tracking-tight">FCBillar</span>
			<span class="text-sm text-slate-400">· Rànquings</span>
		</div>
	</header>
	<main class="flex-1 px-3 py-3">
		{@render children()}
	</main>
	<footer class="px-4 py-4 text-center text-[11px] text-slate-400">
		Dades de la Federació Catalana de Billar · ús personal
	</footer>
</div>
