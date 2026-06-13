<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import { supabase } from '$lib/supabase';
	let { children } = $props();

	// Punt vermell llampegant al costat d'"Opens" si hi ha algun Open en curs.
	let liveCount = $state(0);
	onMount(async () => {
		const { count } = await supabase
			.from('open_live')
			.select('fcb_division_id', { count: 'exact', head: true });
		liveCount = count ?? 0;
	});

	// En canviar de pàgina, torna a dalt. EXCEPCIÓ: en navegacions enrere/endavant
	// (popstate) deixem que SvelteKit restauri la posició d'scroll on era l'usuari.
	afterNavigate((nav) => {
		if (nav.type === 'popstate') return;
		if (typeof window !== 'undefined') window.scrollTo({ top: 0, left: 0 });
	});

	const tabs = [
		{ href: '/', label: 'Rànquings', match: (p: string) => p === '/' || p.startsWith('/jugador') },
		{ href: '/lliga', label: 'Lliga', match: (p: string) => p.startsWith('/lliga') },
		{ href: '/copa', label: 'Copa', match: (p: string) => p.startsWith('/copa') },
		{ href: '/opens', label: 'Opens', match: (p: string) => p.startsWith('/opens') },
		{ href: '/campionats', label: 'Camp. Cat.', match: (p: string) => p.startsWith('/campionats') },
		{ href: '/cerca', label: 'Cerca', match: (p: string) => p.startsWith('/cerca') },
		{ href: '/comparar', label: 'Comparar', match: (p: string) => p.startsWith('/comparar') },
		{ href: '/records', label: 'Rècords', match: (p: string) => p.startsWith('/records') },
		{ href: '/seguiment', label: '★ Seguits', match: (p: string) => p.startsWith('/seguiment') }
	];
	const path = $derived($page.url.pathname);
</script>

<div class="mx-auto flex min-h-full max-w-screen-sm flex-col md:max-w-3xl lg:max-w-5xl">
	<header class="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
		<div class="flex items-center gap-2 px-4 pt-3 md:px-6 md:pt-4">
			<svg viewBox="0 0 40 40" class="h-7 w-7 shrink-0 md:h-9 md:w-9" aria-hidden="true">
				<rect width="40" height="40" rx="10" fill="#0b3d2e" />
				<circle cx="20" cy="13.5" r="7" fill="#e0322a" />
				<circle cx="13.5" cy="24.5" r="7" fill="#f7f7f5" />
				<circle cx="26.5" cy="24.5" r="7" fill="#f3c623" />
				<circle cx="17.6" cy="11" r="2" fill="#fff" opacity="0.55" />
				<circle cx="11.2" cy="22" r="1.8" fill="#fff" opacity="0.7" />
				<circle cx="24.2" cy="22" r="1.8" fill="#fff" opacity="0.5" />
			</svg>
			<span class="text-base font-bold tracking-tight md:text-xl">FCBillar</span>
		</div>
		<nav class="flex flex-wrap gap-x-1 gap-y-0 px-3 pt-2 md:px-5">
			{#each tabs as t}
				<a
					href={t.href}
					class="-mb-px rounded-t-lg px-3 py-2 text-sm font-medium md:px-4 md:text-base {t.match(path)
						? 'border-b-2 border-slate-900 text-slate-900'
						: 'text-slate-400'}"
					>{t.label}{#if t.href === '/opens' && liveCount > 0}<span
							class="relative ml-1 inline-flex h-2 w-2 align-middle"
							title="Opens en directe ara"
							><span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75"
							></span><span class="relative inline-flex h-2 w-2 rounded-full bg-red-500"></span></span>{/if}</a
					>
			{/each}
		</nav>
	</header>
	<main class="flex-1 px-3 py-3 md:px-6 md:py-5">
		{@render children()}
	</main>
	<footer class="flex flex-col items-center gap-2 px-4 py-6 text-center text-[11px] text-slate-400">
		<img src="/logo-ag.png" alt="Propietari de l'aplicació" class="h-7 w-auto opacity-80" />
		<p>No se'n permet la distribució no autoritzada.</p>
		<p class="text-slate-300">Dades de la Federació Catalana de Billar · ús personal</p>
	</footer>
</div>
