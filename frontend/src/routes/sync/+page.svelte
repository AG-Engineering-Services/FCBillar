<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api, apiSend } from '$lib/api';

	type Task = { key: string; label: string; needs_login: boolean };
	type Session = { exists: boolean; mtime: string | null };
	type Status = {
		running: boolean;
		task: string | null;
		label: string | null;
		exit_code: number | null;
		finished_at: string | null;
		log: string[];
	};

	let tasks: Task[] = [];
	let status: Status | null = null;
	let session: Session | null = null;
	let error = '';
	let poll: ReturnType<typeof setInterval> | null = null;

	async function refresh() {
		try {
			status = await api<Status>('/api/sync/status');
			// Quan acaba, atura el polling ràpid.
			if (status && !status.running && poll) {
				clearInterval(poll);
				poll = null;
			}
		} catch (e) {
			error = (e as Error).message;
		}
	}

	function startPolling() {
		if (poll) return;
		poll = setInterval(refresh, 1500);
	}

	async function run(task: string) {
		error = '';
		try {
			const r = await apiSend<{ accepted: boolean; message: string }>('/api/sync/run', 'POST', {
				task
			});
			if (!r.accepted) error = r.message;
			await refresh();
			startPolling();
		} catch (e) {
			error = (e as Error).message;
		}
	}

	onMount(async () => {
		try {
			tasks = await api<Task[]>('/api/sync/tasks');
			session = await api<Session>('/api/sync/session');
		} catch (e) {
			error = (e as Error).message;
		}
		await refresh();
		if (status?.running) startPolling();
	});

	onDestroy(() => {
		if (poll) clearInterval(poll);
	});
</script>

<h1 class="text-2xl font-bold mb-2">Actualitzar dades</h1>
<p class="text-sm text-slate-500 mb-4">
	Executa les tasques d'scraping/ingest contra el portal de la Federació. Només una alhora. Les
	tasques marcades amb 🔒 necessiten sessió iniciada; el <span class="font-medium">login</span> (amb
	captcha) s'ha de fer des del terminal:
	<code class="bg-slate-100 px-1 rounded">uv run fcbillar login</code>.
</p>

<!-- Avís de sessió -->
<div class="mb-4 rounded-md border border-amber-200 bg-amber-50 text-amber-900 text-sm px-3 py-2">
	{#if session?.exists}
		Sessió desada: <span class="font-medium">{session.mtime}</span>. Si les tasques 🔒 donen
		<code class="bg-amber-100 px-1 rounded">Error HTTP 404</code>, la sessió ha caducat — torna a
		executar <code class="bg-amber-100 px-1 rounded">uv run fcbillar login</code> al terminal.
	{:else}
		No hi ha cap sessió desada. Per a les tasques 🔒, executa primer
		<code class="bg-amber-100 px-1 rounded">uv run fcbillar login</code> al terminal.
	{/if}
</div>

{#if error}
	<div class="mb-4 rounded-md border border-red-200 bg-red-50 text-red-800 text-sm px-3 py-2">
		{error}
	</div>
{/if}

<div class="flex flex-wrap gap-2 mb-6">
	{#each tasks as t}
		<button
			class="px-3 py-2 rounded-md text-sm bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
			disabled={status?.running}
			on:click={() => run(t.key)}
		>
			{t.needs_login ? '🔒 ' : ''}{t.label}
		</button>
	{/each}
</div>

<!-- Estat -->
<div class="mb-3 flex items-center gap-3 text-sm">
	{#if status?.running}
		<span class="inline-flex items-center gap-2 text-amber-700">
			<span class="h-2 w-2 rounded-full bg-amber-500 animate-pulse"></span>
			En curs: {status.label}
		</span>
	{:else if status?.finished_at}
		<span class={status.exit_code === 0 ? 'text-emerald-700' : 'text-red-700'}>
			{status.exit_code === 0 ? '✓ Completat' : '✗ Error'}
			{status.label ? '· ' + status.label : ''}
			· {status.finished_at}
		</span>
	{:else}
		<span class="text-slate-400">Cap tasca executada encara.</span>
	{/if}
	<button class="text-xs text-slate-500 hover:underline" on:click={refresh}>Refresca</button>
</div>

<!-- Log -->
<div
	class="bg-slate-900 text-slate-100 rounded-lg p-4 font-mono text-xs leading-relaxed overflow-x-auto"
	style="min-height: 240px; max-height: 480px; overflow-y: auto;"
>
	{#if status && status.log.length}
		{#each status.log as line}
			<div class="whitespace-pre-wrap">{line}</div>
		{/each}
	{:else}
		<div class="text-slate-500">El log apareixerà aquí…</div>
	{/if}
</div>
