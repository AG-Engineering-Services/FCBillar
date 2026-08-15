<script lang="ts">
	import { db } from '$lib/db';
	import sistemes from '$lib/sistemes/sistemes.json';
	import { onMount } from 'svelte';

	// Explorador (admin): enganxa un enllaç → va a una cua a Supabase que el
	// processador local (explora.mjs) tradueix i afegeix a Sistemes Coreans.
	const catIds = new Set((sistemes as { id: string }[]).map((s) => s.id));

	interface Peticio {
		id: number;
		url: string;
		video_id: string | null;
		plataforma: string | null;
		estat: string;
		validar: boolean;
		nom: string | null;
		missatge: string | null;
		creat: string;
	}

	let url = $state('');
	let validar = $state(false);
	let enviant = $state(false);
	let msg = $state('');
	let historial = $state<Peticio[]>([]);

	function extreu(u: string): { video_id: string | null; plataforma: string } {
		const s = u.trim();
		let m: RegExpMatchArray | null;
		if ((m = s.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|shorts\/|embed\/|live\/))([\w-]{11})/)))
			return { video_id: m[1], plataforma: 'youtube' };
		if ((m = s.match(/instagram\.com\/(?:reel|reels|p|tv)\/([\w-]+)/)))
			return { video_id: m[1], plataforma: 'instagram' };
		if ((m = s.match(/(?:facebook\.com\/reel\/|facebook\.com\/[^/]+\/videos\/|facebook\.com\/watch\/?\?v=|fb\.watch\/)(\w+)/)))
			return { video_id: m[1], plataforma: 'facebook' };
		if ((m = s.match(/tiktok\.com\/@[\w.]+\/video\/(\d+)/))) return { video_id: m[1], plataforma: 'tiktok' };
		if ((m = s.match(/vimeo\.com\/(\d+)/))) return { video_id: m[1], plataforma: 'vimeo' };
		return { video_id: null, plataforma: 'altre' };
	}

	async function carregaHistorial() {
		try {
			const { data } = await db
				.from('sistema_peticio')
				.select('*')
				.order('creat', { ascending: false })
				.limit(40);
			historial = (data as Peticio[]) ?? [];
		} catch {
			historial = [];
		}
	}
	onMount(carregaHistorial);

	async function envia() {
		const u = url.trim();
		if (!u) return;
		const { video_id, plataforma } = extreu(u);
		if (video_id && plataforma === 'youtube' && catIds.has(video_id)) {
			msg = '⚠ Aquest vídeo ja és al catàleg.';
			return;
		}
		if (historial.some((h) => h.url === u || (video_id && h.video_id === video_id))) {
			msg = '⚠ Aquest enllaç ja s’ha explorat abans.';
			return;
		}
		enviant = true;
		msg = '';
		try {
			const { error } = await db
				.from('sistema_peticio')
				.insert({ url: u, video_id, plataforma, validar, estat: 'pendent' });
			if (error) throw error;
			url = '';
			validar = false;
			msg = '✓ Afegit a la cua. Es processarà i apareixerà a Sistemes Coreans.';
			await carregaHistorial();
		} catch {
			msg = '✗ Error desant la petició.';
		}
		enviant = false;
	}

	const BADGE: Record<string, string> = {
		pendent: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
		processant: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
		fet: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
		duplicat: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
		error: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300'
	};
	const curt = (u: string) => u.replace(/^https?:\/\/(www\.)?/, '').slice(0, 42);
</script>

<details class="mb-5 rounded-xl border border-indigo-200 bg-indigo-50/50 p-3 dark:border-indigo-900 dark:bg-indigo-950/20">
	<summary class="cursor-pointer text-sm font-semibold text-indigo-700 dark:text-indigo-300">
		➕ Explora un vídeo nou (enganxa un enllaç)
	</summary>
	<div class="mt-3">
		<p class="mb-2 text-xs text-slate-500 dark:text-slate-400">
			YouTube, Instagram, Facebook, TikTok, Vimeo… S’afegeix a una cua; el processador del PC
			el tradueix i l’afegeix a Sistemes Coreans amb l’explicació. Es guarda l’historial per no repetir.
		</p>
		<div class="flex flex-col gap-2 sm:flex-row">
			<input
				type="url"
				bind:value={url}
				placeholder="https://…"
				class="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
			/>
			<button
				onclick={envia}
				disabled={enviant || !url.trim()}
				class="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
				>{enviant ? 'Enviant…' : 'Explora'}</button
			>
		</div>
		<label class="mt-2 flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300">
			<input type="checkbox" bind:checked={validar} class="accent-emerald-500" />
			Ja el valido com que funciona (anirà directe a Validats)
		</label>
		{#if msg}<p class="mt-2 text-sm text-slate-600 dark:text-slate-300">{msg}</p>{/if}

		{#if historial.length}
			<div class="mt-4">
				<h3 class="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
					Historial ({historial.length})
				</h3>
				<ul class="max-h-60 space-y-1 overflow-y-auto text-sm">
					{#each historial as h (h.id)}
						<li class="flex items-center gap-2">
							<span class="rounded px-1.5 py-0.5 text-xs font-medium {BADGE[h.estat] ?? BADGE.pendent}"
								>{h.estat}</span
							>
							<span class="text-slate-400">{h.plataforma}</span>
							{#if h.estat === 'fet' && h.video_id}
								<a href={`/sistemes-coreans/${h.video_id}`} class="truncate font-medium text-indigo-600 hover:underline dark:text-indigo-400"
									>{h.nom || curt(h.url)} →</a
								>
							{:else}
								<a href={h.url} target="_blank" rel="noopener" class="truncate text-slate-600 hover:underline dark:text-slate-300"
									>{h.nom || curt(h.url)}</a
								>
							{/if}
							{#if h.missatge}<span class="truncate text-xs text-slate-400" title={h.missatge}>· {h.missatge}</span>{/if}
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	</div>
</details>
