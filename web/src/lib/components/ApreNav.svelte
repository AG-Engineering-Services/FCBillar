<script lang="ts">
	import { page } from '$app/stores';

	// Subpestanyes de la secció «Aprèn». Els URL antics es mantenen perquè hi ha
	// enllaços compartits a /sistemes-coreans/[id] i /biblia/[id].
	const seccions = [
		{ href: '/sistemes-coreans', label: 'Sistemes', match: (p: string) => p.startsWith('/sistemes') },
		{ href: '/biblia', label: 'Bíblia', match: (p: string) => p.startsWith('/biblia') },
		{ href: '/traductor', label: 'Traductor', match: (p: string) => p.startsWith('/traductor') }
	];
	const path = $derived($page.url.pathname);
</script>

<nav class="mb-4 flex flex-wrap gap-2">
	{#each seccions as s (s.href)}
		<a
			href={s.href}
			class="rounded-sm px-3 py-1 text-sm {s.match(path)
				? 'bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-900'
				: 'bg-slate-100 text-slate-600 hover:text-slate-900 dark:bg-slate-800 dark:text-slate-300 dark:hover:text-white'}"
			>{s.label}</a
		>
	{/each}
</nav>
