<script lang="ts">
	import '../app.css';
	import { page } from '$app/stores';
	const nav = [
		{ href: '/', label: 'Dashboard' },
		{ href: '/rankings', label: 'Rànquings' },
		{ href: '/players', label: 'Jugadors' },
		{ href: '/compare', label: 'Comparar' },
		{ href: '/games', label: 'Partides' },
		{ href: '/results', label: 'Resultats' },
		{ href: '/opens', label: 'Opens' },
		{ href: '/clubs', label: 'Clubs' },
		{ href: '/focus', label: 'Focus club' },
		{ href: '/virtual-clubs', label: 'Clubs virtuals' },
		{ href: '/sync', label: 'Actualitzar dades' }
	];
	$: path = $page.url.pathname;
	function isActive(href: string): boolean {
		return href === '/' ? path === '/' : path.startsWith(href);
	}
</script>

<div class="min-h-screen flex flex-col">
	<header class="bg-white border-b border-slate-200 sticky top-0 z-10">
		<div class="max-w-7xl mx-auto px-4 flex items-center gap-6 h-14">
			<a href="/" class="font-bold text-lg text-slate-900">FCBillar</a>
			<nav class="flex items-center gap-1 text-sm overflow-x-auto">
				{#each nav as item}
					<a
						href={item.href}
						class="px-3 py-1.5 rounded-md transition-colors whitespace-nowrap {isActive(item.href)
							? 'bg-slate-900 text-white'
							: 'text-slate-600 hover:bg-slate-100'}">{item.label}</a
					>
				{/each}
			</nav>
		</div>
	</header>
	<main class="flex-1 max-w-7xl mx-auto px-4 py-6 w-full">
		<slot />
	</main>
	<footer class="border-t border-slate-200 text-center text-xs text-slate-400 py-4">
		FCBillar · dades de la Federació Catalana de Billar · ús personal
	</footer>
</div>
