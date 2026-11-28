<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { hiHaNous, llegeix, recents, type AvisRebut } from '$lib/avisosRebuts';

	// En obrir l'app, els resultats arribats per avís a l'última hora, sencers.
	// Surt sol només si n'ha arribat algun des de l'últim cop que es va tancar.
	const CLAU_VISTOS = 'avisos-vistos-fins';

	let dialeg: HTMLDialogElement | undefined = $state();
	let avisos: AvisRebut[] = $state([]);
	let ara = $state(Date.now());

	function vistosFins(): number {
		try {
			return Number(localStorage.getItem(CLAU_VISTOS)) || 0;
		} catch {
			return 0;
		}
	}

	async function comprova() {
		if (typeof indexedDB === 'undefined' || document.visibilityState !== 'visible') return;
		let tots: AvisRebut[];
		try {
			tots = await llegeix();
		} catch {
			return;
		}
		ara = Date.now();
		avisos = recents(tots, ara);
		if (!dialeg?.open && hiHaNous(avisos, vistosFins())) dialeg?.showModal();
	}

	function marcaVistos() {
		try {
			localStorage.setItem(CLAU_VISTOS, String(Math.max(Date.now(), ...avisos.map((a) => a.rebut))));
		} catch {
			// Sense emmagatzematge el modal tornarà a sortir: millor que perdre resultats.
		}
	}

	function tanca() {
		dialeg?.close();
	}

	async function obreOpen(url: string) {
		dialeg?.close();
		await goto(url);
	}

	function quan(rebut: number): string {
		const min = Math.round((ara - rebut) / 60000);
		const hora = new Date(rebut).toLocaleTimeString('ca-ES', { hour: '2-digit', minute: '2-digit' });
		return min < 1 ? `ara mateix · ${hora}` : `fa ${min} min · ${hora}`;
	}

	onMount(() => {
		comprova();
		const visible = () => comprova();
		const missatge = (e: MessageEvent) => {
			if (e.data?.tipus === 'avis-rebut') comprova();
		};
		document.addEventListener('visibilitychange', visible);
		navigator.serviceWorker?.addEventListener('message', missatge);
		return () => {
			document.removeEventListener('visibilitychange', visible);
			navigator.serviceWorker?.removeEventListener('message', missatge);
		};
	});
</script>

<dialog
	bind:this={dialeg}
	onclose={marcaVistos}
	aria-labelledby="titol-recents"
	class="m-auto w-[calc(100%-2rem)] max-w-lg rounded-md border border-slate-200 bg-white p-0 text-sm text-slate-900 shadow-lg backdrop:bg-slate-900/50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
>
	<div class="flex max-h-[80dvh] flex-col">
		<header class="border-b border-slate-200 px-4 py-3 dark:border-slate-700">
			<h2 id="titol-recents" class="text-base font-semibold">Resultats de l'última hora</h2>
			<p class="text-xs text-slate-600 dark:text-slate-400">
				{avisos.length === 1 ? '1 avís rebut' : `${avisos.length} avisos rebuts`} en aquest dispositiu
			</p>
		</header>

		<ol class="flex-1 divide-y divide-slate-200 overflow-y-auto overscroll-contain px-4 dark:divide-slate-700">
			{#each avisos as a (a.id)}
				<li class="py-3">
					<div class="flex items-baseline justify-between gap-3">
						<h3 class="font-medium">{a.titol}</h3>
						<span class="shrink-0 text-xs text-slate-600 tabular-nums dark:text-slate-400"
							>{quan(a.rebut)}</span
						>
					</div>
					<ul class="mt-1 space-y-0.5">
						{#each a.linies as l, i (i)}
							<li class={l.startsWith('★') ? 'font-semibold' : ''}>{l}</li>
						{/each}
					</ul>
					{#if a.url !== '/'}
						<button
							type="button"
							onclick={() => obreOpen(a.url)}
							class="mt-1 inline-flex min-h-11 items-center text-xs font-medium text-sky-700 underline underline-offset-2 dark:text-sky-400"
							>Obre la competició</button
						>
					{/if}
				</li>
			{/each}
		</ol>

		<footer class="border-t border-slate-200 px-4 py-3 dark:border-slate-700">
			<button
				type="button"
				onclick={tanca}
				class="min-h-11 w-full rounded-sm bg-sky-700 px-4 font-medium text-white hover:bg-sky-800 dark:bg-sky-600 dark:hover:bg-sky-500"
				>Tanca</button
			>
		</footer>
	</div>
</dialog>
