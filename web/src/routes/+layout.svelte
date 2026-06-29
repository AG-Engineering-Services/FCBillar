<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import { supabase } from '$lib/supabase';
	import { theme, toggleTheme } from '$lib/theme';
	let { children } = $props();

	// Punt vermell llampegant al costat d'"Opens" NOMÉS quan hi ha competició
	// activa ara mateix. Ho lliguem a la frescor de open_live: el cron només
	// refresca l'estat durant les finestres de competició (dv/ds/dg), així que
	// si el snapshot més recent és d'aquesta darrera hora i mitja, s'està jugant.
	let liveCount = $state(0);
	// Avís de manteniment NOMÉS per a l'admin (qui ha usat el botó de reingesta,
	// marcat a localStorage): si la sessió de login de la federació ha caducat, la
	// reingesta del núvol no pot entrar dades noves fins fer `fcbillar login` al PC.
	let sessionExpired = $state(false);
	onMount(async () => {
		const since = new Date(Date.now() - 90 * 60 * 1000).toISOString();
		const { count } = await supabase
			.from('open_live')
			.select('fcb_division_id', { count: 'exact', head: true })
			.gte('captured_at', since);
		liveCount = count ?? 0;

		const isAdmin =
			typeof localStorage !== 'undefined' && localStorage.getItem('fcb_admin') === '1';
		if (isAdmin) {
			const { data } = await supabase
				.from('cloud_status')
				.select('session_ok')
				.eq('id', 1)
				.maybeSingle();
			sessionExpired = data?.session_ok === false;
		}
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
	// Vista aïllada (/fitxa/[id]): sense capçalera/navbar, perquè no es pugui accedir
	// a cap altra secció de la PWA des d'aquí. El peu (autoria + avís de no distribució)
	// SÍ que s'hi mostra: no conté navegació i l'avís ha de sortir a totes les pàgines.
	const embed = $derived(path.startsWith('/fitxa'));
</script>

<div class="mx-auto flex min-h-full max-w-screen-sm flex-col md:max-w-3xl lg:max-w-5xl">
	<!-- Marca d'aigua d'autoria: emblema "AG" + nom Albert Gómez, fixat al centre de la
	     finestra i sense capturar clics (pointer-events-none). Va a z-0: per sota de la
	     capçalera sticky (z-10) i per sobre del contingut, però amb opacitat molt baixa,
	     així es percep com una marca de fons a totes les pàgines —inclosa la vista
	     aïllada /fitxa— sense destorbar la lectura. -->
	<div
		class="pointer-events-none fixed inset-0 z-0 flex select-none flex-col items-center justify-center gap-3 opacity-[0.05] dark:opacity-[0.09]"
		aria-hidden="true"
	>
		<img src="/logo-ag.png" alt="" class="w-48 max-w-[55vw] grayscale md:w-64 lg:w-72" />
		<span
			class="text-2xl font-semibold uppercase tracking-[0.35em] text-slate-900 dark:text-slate-100 md:text-3xl lg:text-4xl"
			>Albert&nbsp;Gómez</span
		>
	</div>
	{#if !embed}
	<header
		class="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90"
	>
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
			<button
				type="button"
				onclick={toggleTheme}
				class="ml-auto grid h-9 w-9 shrink-0 place-items-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
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
		<nav class="flex flex-wrap gap-x-1 gap-y-0 px-3 pt-2 md:px-5">
			{#each tabs as t}
				<a
					href={t.href}
					class="-mb-px rounded-t-lg px-3 py-2 text-sm font-medium md:px-4 md:text-base {t.match(path)
						? 'border-b-2 border-slate-900 text-slate-900 dark:border-slate-100 dark:text-slate-100'
						: 'text-slate-400 dark:text-slate-500'}"
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
	{#if sessionExpired && !embed}
		<div
			class="mx-3 mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200 md:mx-6"
			role="status"
		>
			⚠ La sessió de la federació ha caducat: la reingesta del núvol no incorpora dades
			noves. Fes <code class="font-mono">fcbillar login</code> i
			<code class="font-mono">state push --session</code> al PC.
		</div>
	{/if}
	<main class="flex-1 px-3 py-3 md:px-6 md:py-5">
		{@render children()}
	</main>
	<footer
		class="flex flex-col items-center gap-2 px-4 py-6 text-center text-[11px] text-slate-400 dark:text-slate-500"
	>
		<div class="flex items-center gap-2">
			<img src="/logo-ag.png" alt="Albert Gómez" class="h-7 w-auto opacity-80" />
			<span class="text-xs font-semibold tracking-wide text-slate-500 dark:text-slate-400">Albert Gómez</span>
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
