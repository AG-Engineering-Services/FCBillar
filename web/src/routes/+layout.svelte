<script lang="ts">
	import '../app.css';
	import { page } from '$app/stores';
	let { children } = $props();

	const tabs = [
		{ href: '/', label: 'Rànquings', match: (p: string) => p === '/' || p.startsWith('/jugador') },
		{ href: '/lliga', label: 'Lliga', match: (p: string) => p.startsWith('/lliga') },
		{ href: '/copa', label: 'Copa', match: (p: string) => p.startsWith('/copa') },
		{ href: '/opens', label: 'Individual', match: (p: string) => p.startsWith('/opens') },
		{ href: '/cerca', label: 'Cerca', match: (p: string) => p.startsWith('/cerca') },
		{ href: '/seguiment', label: '★ Seguits', match: (p: string) => p.startsWith('/seguiment') }
	];
	const path = $derived($page.url.pathname);
</script>

<div class="mx-auto flex min-h-full max-w-screen-sm flex-col">
	<header class="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
		<div class="flex items-center gap-2 px-4 pt-3">
			<svg viewBox="0 0 40 40" class="h-7 w-7 shrink-0" aria-hidden="true">
				<rect width="40" height="40" rx="10" fill="#0b3d2e" />
				<circle cx="20" cy="13.5" r="7" fill="#e0322a" />
				<circle cx="13.5" cy="24.5" r="7" fill="#f7f7f5" />
				<circle cx="26.5" cy="24.5" r="7" fill="#f3c623" />
				<circle cx="17.6" cy="11" r="2" fill="#fff" opacity="0.55" />
				<circle cx="11.2" cy="22" r="1.8" fill="#fff" opacity="0.7" />
				<circle cx="24.2" cy="22" r="1.8" fill="#fff" opacity="0.5" />
			</svg>
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
