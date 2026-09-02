<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import { db } from '$lib/db';
	import { theme, toggleTheme } from '$lib/theme';
	let { children } = $props();

	// Punt vermell llampegant al costat d'"Opens" NOMÉS quan hi ha competició
	// activa ara mateix. Ho lliguem a la frescor de open_live: el cron només
	// refresca l'estat durant les finestres de competició (dv/ds/dg), així que
	// si el snapshot més recent és d'aquesta darrera hora i mitja, s'està jugant.
	let liveCount = $state(0);
	onMount(async () => {
		const since = new Date(Date.now() - 90 * 60 * 1000).toISOString();
		const { count } = await db
			.from('open_live')
			.select('fcb_division_id', { count: 'exact', head: true })
			.gte('captured_at', since);
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
		{ href: '/lliga', label: 'Lliga', match: (p: string) => p === '/lliga' || p.startsWith('/lliga/') },
		{ href: '/copa', label: 'Copa', match: (p: string) => p.startsWith('/copa') },
		{ href: '/opens', label: 'Opens', match: (p: string) => p.startsWith('/opens') },
		{ href: '/campionats', label: 'Camp. Cat.', match: (p: string) => p.startsWith('/campionats') },
		{ href: '/calendari', label: 'Calendari', match: (p: string) => p.startsWith('/calendari') },
		{ href: '/clubs', label: 'Clubs', match: (p: string) => p.startsWith('/clubs') },
		{ href: '/cerca', label: 'Cerca', match: (p: string) => p.startsWith('/cerca') },
		{ href: '/comparar', label: 'Comparar', match: (p: string) => p.startsWith('/comparar') },
		{ href: '/records', label: 'Rècords', match: (p: string) => p.startsWith('/records') },
		{ href: '/seguiment', label: '★ Seguits', match: (p: string) => p.startsWith('/seguiment') },
		{ href: '/biblia', label: 'Bíblia', match: (p: string) => p.startsWith('/biblia') },
		{
			href: '/sistemes-coreans',
			label: 'Sistemes Coreans',
			match: (p: string) => p.startsWith('/sistemes-coreans')
		},
		{
			href: '/sistemes-validats',
			label: 'Sistemes Validats',
			match: (p: string) => p.startsWith('/sistemes-validats')
		}
	];
	const path = $derived($page.url.pathname);
	// Vista aïllada (/fitxa/[id]): sense capçalera/navbar, perquè no es pugui accedir
	// a cap altra secció de la PWA des d'aquí. El peu (autoria + avís de no distribució)
	// SÍ que s'hi mostra: no conté navegació i l'avís ha de sortir a totes les pàgines.
	const embed = $derived(path.startsWith('/fitxa'));
</script>

<div class="mx-auto flex min-h-full max-w-screen-sm flex-col md:max-w-3xl lg:max-w-6xl">
	<!-- Marca d'autoria. Surt a qualsevol captura de pantalla, que és per al que
	     serveix, però a la cantonada: al mig de la pàgina es barallava amb les
	     xifres, i aquí les files es llegeixen abans que la marca. No captura
	     clics i queda per sota de la capçalera enganxada. -->
	<div
		class="pointer-events-none fixed bottom-3 right-3 z-0 flex select-none items-center gap-2 opacity-[0.16] dark:opacity-[0.2]"
		aria-hidden="true"
	>
		<img src="/logo-ag.png" alt="" class="h-6 w-auto grayscale" />
		<span class="ag-et text-slate-900 dark:text-slate-100">Albert Gómez</span>
	</div>
	{#if !embed}
	<header
		class="ag-marca sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95"
	>
		<div class="flex items-center gap-2 px-4 pt-2 md:px-6 md:pt-3">
			<svg viewBox="0 0 40 40" class="h-7 w-7 shrink-0 md:h-9 md:w-9" aria-hidden="true">
				<rect width="40" height="40" rx="10" fill="#0b3d2e" />
				<circle cx="20" cy="13.5" r="7" fill="#e0322a" />
				<circle cx="13.5" cy="24.5" r="7" fill="#f7f7f5" />
				<circle cx="26.5" cy="24.5" r="7" fill="#f3c623" />
				<circle cx="17.6" cy="11" r="2" fill="#fff" opacity="0.55" />
				<circle cx="11.2" cy="22" r="1.8" fill="#fff" opacity="0.7" />
				<circle cx="24.2" cy="22" r="1.8" fill="#fff" opacity="0.5" />
			</svg>
			<span class="text-base font-bold tracking-tight md:text-lg">FCBillar</span>
			<span class="ag-et hidden sm:inline" title="Font de les dades"
				>Federació Catalana de Billar</span
			>
			<button
				type="button"
				onclick={toggleTheme}
				class="ml-auto grid h-8 w-8 shrink-0 place-items-center rounded-sm text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
				aria-label={$theme === 'dark' ? 'Mode clar' : 'Mode fosc'}
				title={$theme === 'dark' ? 'Mode clar' : 'Mode fosc'}
			>
				{#if $theme === 'dark'}
					<!-- sol: prem per passar a clar -->
					<svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<circle cx="12" cy="12" r="4" />
						<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
					</svg>
				{:else}
					<!-- lluna: prem per passar a fosc -->
					<svg viewBox="0 0 24 24" class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
					</svg>
				{/if}
			</button>
		</div>
		<nav class="flex flex-wrap gap-x-0 gap-y-0 px-3 pt-1 md:px-5">
			{#each tabs as t}
				<a
					href={t.href}
					class="ag-et -mb-px px-2.5 py-1.5 md:px-3 {t.match(path)
						? 'border-b-2 border-sky-600 text-sky-700 dark:border-sky-400 dark:text-sky-300'
						: 'border-b-2 border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'}"
					>{t.label}{#if t.href === '/opens' && liveCount > 0}<span
							class="relative ml-1 inline-flex h-2 w-2 align-middle"
							title="Opens en directe ara"
							><span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75"
							></span><span class="relative inline-flex h-2 w-2 rounded-full bg-red-500"></span></span>{/if}</a
					>
			{/each}
		</nav>
	</header>
	{/if}
	<main class="flex-1 px-3 py-3 md:px-6 md:py-5">
		{@render children()}
	</main>
	<footer
		class="flex flex-col items-center gap-2 px-4 py-6 text-center text-[11px] text-slate-500 dark:text-slate-400"
	>
		<div class="flex items-center gap-2">
			<img src="/logo-ag.png" alt="Albert Gómez" class="h-5 w-auto opacity-70" />
			<span class="ag-et text-slate-500 dark:text-slate-400">Albert Gómez</span>
		</div>
		<p>© Albert Gómez. No se'n permet la distribució no autoritzada.</p>
		<p class="text-slate-300 dark:text-slate-600">Dades de la Federació Catalana de Billar · ús personal</p>
	</footer>
</div>

<style>
	@page {
		size: A4 portrait;
		margin: 8mm;
	}
	@media print {
		:global(header),
		:global(footer),
		:global(.pointer-events-none.fixed) {
			display: none !important;
		}
		:global(main) {
			padding: 0 !important;
		}
		:global(html) {
			font-size: 10pt;
		}
	}
</style>
