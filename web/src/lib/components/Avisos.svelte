<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { db } from '$lib/db';
	import {
		TIPUS_AVIS,
		type TipusAvis,
		VAPID_PUBLIC_KEY,
		base64UrlABytes
	} from '$lib/avisos';

	// Estat del dispositiu, en l'ordre en què es comprova.
	type Estat = 'carregant' | 'no-suportat' | 'cal-instal·lar' | 'bloquejat' | 'inactiu' | 'actiu';
	let estat = $state<Estat>('carregant');
	let obert = $state(false);
	let triats = $state<Set<TipusAvis>>(new Set(TIPUS_AVIS.map((t) => t.id)));
	let enviant = $state(false);
	let missatge = $state('');
	let error = $state('');
	let panell: HTMLDivElement | undefined = $state();
	let boto: HTMLButtonElement | undefined = $state();

	const DESAT = 'fcb_avisos_tipus';

	function esIos(): boolean {
		return /iphone|ipad|ipod/i.test(navigator.userAgent);
	}
	function esInstal·lada(): boolean {
		return (
			window.matchMedia('(display-mode: standalone)').matches ||
			(navigator as any).standalone === true
		);
	}

	async function subscripcioActual(): Promise<PushSubscription | null> {
		const reg = await navigator.serviceWorker.ready;
		return reg.pushManager.getSubscription();
	}

	onMount(async () => {
		try {
			const desat = JSON.parse(localStorage.getItem(DESAT) ?? 'null');
			if (Array.isArray(desat)) triats = new Set(desat);
		} catch {
			/* sense preferència desada: tots marcats */
		}
		if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
			// A l'iPhone, Safari només en dona fora de la pantalla d'inici.
			estat = esIos() && !esInstal·lada() ? 'cal-instal·lar' : 'no-suportat';
			return;
		}
		if (Notification.permission === 'denied') {
			estat = 'bloquejat';
			return;
		}
		estat = (await subscripcioActual()) ? 'actiu' : 'inactiu';
	});

	async function obre() {
		obert = !obert;
		missatge = '';
		error = '';
		if (obert) {
			await tick();
			panell?.querySelector<HTMLElement>('input, button')?.focus();
		}
	}
	function tanca() {
		obert = false;
		boto?.focus();
	}
	function alTeclat(e: KeyboardEvent) {
		if (e.key === 'Escape' && obert) tanca();
	}

	function commuta(id: TipusAvis) {
		const s = new Set(triats);
		if (s.has(id)) s.delete(id);
		else s.add(id);
		triats = s;
	}

	async function desaAlNuvol(sub: PushSubscription, tipus: TipusAvis[]) {
		const j = sub.toJSON();
		const { error: e } = await db.rpc('desa_subscripcio', {
			p_endpoint: sub.endpoint,
			p_p256dh: j.keys?.p256dh,
			p_auth: j.keys?.auth,
			p_tipus: tipus,
			p_dispositiu: navigator.userAgent.slice(0, 200)
		});
		if (e) throw new Error(`No s'ha pogut desar al núvol: ${e.message}`);
	}

	async function activa() {
		enviant = true;
		missatge = '';
		error = '';
		try {
			if (!triats.size) throw new Error('Marca almenys un tipus de resultat.');
			const permis = await Notification.requestPermission();
			if (permis !== 'granted') {
				estat = permis === 'denied' ? 'bloquejat' : 'inactiu';
				throw new Error("El telèfon no ha donat permís per als avisos.");
			}
			const reg = await navigator.serviceWorker.ready;
			const sub =
				(await reg.pushManager.getSubscription()) ??
				(await reg.pushManager.subscribe({
					userVisibleOnly: true,
					applicationServerKey: base64UrlABytes(VAPID_PUBLIC_KEY)
				}));
			const tipus = [...triats];
			await desaAlNuvol(sub, tipus);
			try {
				localStorage.setItem(DESAT, JSON.stringify(tipus));
			} catch {
				/* no és crític */
			}
			const eraActiu = estat === 'actiu';
			estat = 'actiu';
			if (!eraActiu) {
				// Avís local: prova que el telèfon els ensenya, sense esperar cap resultat.
				await reg.showNotification('Avisos activats', {
					body: 'Rebràs els resultats que has triat en aquest dispositiu.',
					icon: '/icon-192.png'
				});
			}
			missatge = eraActiu ? 'Preferències desades.' : 'Avisos activats en aquest dispositiu.';
		} catch (e) {
			error = (e as Error).message;
		} finally {
			enviant = false;
		}
	}

	async function desactiva() {
		enviant = true;
		missatge = '';
		error = '';
		try {
			const sub = await subscripcioActual();
			if (sub) {
				// Sense tipus el servidor ja no hi envia res, encara que la baixa local falli.
				await desaAlNuvol(sub, []);
				await sub.unsubscribe();
			}
			estat = 'inactiu';
			missatge = 'Avisos desactivats en aquest dispositiu.';
		} catch (e) {
			error = (e as Error).message;
		} finally {
			enviant = false;
		}
	}
</script>

<svelte:window onkeydown={alTeclat} />

<div class="relative">
	<button
		bind:this={boto}
		type="button"
		onclick={obre}
		aria-expanded={obert}
		aria-controls="panell-avisos"
		class="grid h-11 w-11 shrink-0 place-items-center rounded-sm text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
		aria-label={estat === 'actiu' ? 'Avisos de resultats (activats)' : 'Avisos de resultats'}
		title="Avisos de resultats"
	>
		<!-- campana: plena quan aquest dispositiu rep avisos -->
		<svg
			viewBox="0 0 24 24"
			class="h-5 w-5"
			fill={estat === 'actiu' ? 'currentColor' : 'none'}
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
			<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
		</svg>
	</button>

	{#if obert}
		<!-- Clic fora: tanca. És un botó a pantalla completa perquè també hi arribi el teclat. -->
		<button
			type="button"
			class="fixed inset-0 z-20 cursor-default"
			aria-label="Tanca els avisos"
			tabindex="-1"
			onclick={tanca}
		></button>
		<div
			bind:this={panell}
			id="panell-avisos"
			role="dialog"
			aria-labelledby="titol-avisos"
			class="absolute right-0 top-12 z-30 w-[min(20rem,calc(100vw-2rem))] rounded-md border border-slate-200 bg-white p-4 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
		>
			<h2 id="titol-avisos" class="text-base font-semibold">Avisos de resultats</h2>

			{#if estat === 'carregant'}
				<p class="mt-2 text-slate-600 dark:text-slate-300">Comprovant aquest dispositiu…</p>
			{:else if estat === 'cal-instal·lar'}
				<p class="mt-2 text-slate-600 dark:text-slate-300">
					A l'iPhone, els avisos només funcionen des de l'app instal·lada. A Safari, toca
					<strong>Comparteix</strong> → <strong>Afegeix a la pantalla d'inici</strong>, obre FCBillar
					des d'allà i torna a prémer la campana.
				</p>
			{:else if estat === 'no-suportat'}
				<p class="mt-2 text-slate-600 dark:text-slate-300">
					Aquest navegador no admet avisos web. Prova-ho des de l'app instal·lada al telèfon.
				</p>
			{:else if estat === 'bloquejat'}
				<p class="mt-2 text-slate-600 dark:text-slate-300">
					Els avisos de FCBillar estan bloquejats en aquest dispositiu. Activa'ls a la configuració
					de notificacions del telèfon (o del navegador) i torna-ho a provar.
				</p>
			{:else}
				<p class="mt-1 text-slate-600 dark:text-slate-300">
					{estat === 'actiu'
						? 'Aquest dispositiu rep avisos. Tria quins:'
						: 'Tria quins resultats vols rebre en aquest dispositiu:'}
				</p>
				<fieldset class="mt-3 space-y-1">
					<legend class="sr-only">Tipus de resultats</legend>
					{#each TIPUS_AVIS as t (t.id)}
						<label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-sm px-1 py-2 hover:bg-slate-50 dark:hover:bg-slate-800">
							<input
								type="checkbox"
								class="mt-0.5 h-5 w-5 shrink-0 accent-sky-700"
								checked={triats.has(t.id)}
								onchange={() => commuta(t.id)}
							/>
							<span>
								<span class="block font-medium">{t.nom}</span>
								<span class="block text-xs text-slate-600 dark:text-slate-400">{t.detall}</span>
							</span>
						</label>
					{/each}
				</fieldset>
				<div class="mt-3 flex flex-wrap gap-2">
					<button
						type="button"
						onclick={activa}
						disabled={enviant}
						class="min-h-11 rounded-sm bg-sky-700 px-4 font-medium text-white hover:bg-sky-800 disabled:opacity-60 dark:bg-sky-600 dark:hover:bg-sky-500"
					>
						{enviant ? 'Desant…' : estat === 'actiu' ? 'Desa' : 'Activa els avisos'}
					</button>
					{#if estat === 'actiu'}
						<button
							type="button"
							onclick={desactiva}
							disabled={enviant}
							class="min-h-11 rounded-sm px-3 text-slate-700 hover:bg-slate-100 disabled:opacity-60 dark:text-slate-300 dark:hover:bg-slate-800"
						>
							Desactiva
						</button>
					{/if}
				</div>
			{/if}

			<p class="mt-2 min-h-5 text-xs" role="status">
				{#if error}<span class="text-red-700 dark:text-red-400">{error}</span>{:else if missatge}<span class="text-emerald-700 dark:text-emerald-400">{missatge}</span>{/if}
			</p>
		</div>
	{/if}
</div>
