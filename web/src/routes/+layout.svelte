<script lang="ts">
	import '../app.css';
	import { page } from '$app/stores';
	let { children } = $props();

	const tabs = [
		{ href: '/', label: 'Rànquings', match: (p: string) => p === '/' || p.startsWith('/jugador') },
		{ href: '/lliga', label: 'Lliga', match: (p: string) => p.startsWith('/lliga') },
		{ href: '/copa', label: 'Copa', match: (p: string) => p.startsWith('/copa') },
		{ href: '/opens', label: 'Individual', match: (p: string) => p.startsWith('/opens') },
		{ href: '/cerca', label: 'Cerca', match: (p: string) => p.startsWith('/cerca') }
	];
	const path = $derived($page.url.pathname);
</script>

<div class="mx-auto flex min-h-full max-w-screen-sm flex-col">
	<header class="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
		<div class="flex items-center gap-2 px-4 pt-3">
			<span class="text-base font-bold tracking-tight">FCBillar</span>
		</div>
		<nav class="flex gap-1 overflow-x-auto px-3 pt-2 [scrollbar-width:none]">
			{#each tabs as t}
				<a
					href={t.href}
					class="-mb-px shrink-0 rounded-t-lg px-3 py-2 text-sm font-medium {t.match(path)
						? 'border-b-2 border-slate-900 text-slate-900'
						: 'text-slate-400'}">{t.label}</a>
			{/each}
		</nav>
	</header>
	<main class="flex-1 px-3 py-3">
		{@render children()}
	</main>
	<footer class="px-4 py-4 text-center text-[11px] text-slate-400">
		Dades de la Federació Catalana de Billar · ús personal
	</footer>
</div>
