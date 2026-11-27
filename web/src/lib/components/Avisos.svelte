<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { db } from '$lib/db';
	import { follows } from '$lib/follows';
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
		const sub = await subscripcioActual();
		estat = sub ? 'actiu' : 'inactiu';
		// La torna a desar en silenci: si l'alta al núvol havia fallat, o el
		// navegador ha renovat les claus, el servidor ho sap sense que calgui fer res.
		if (sub) desaAlNuvol(sub, [...triats]).catch(() => {});
	});

	// Seguir o deixar de seguir un jugador (★ a la fitxa) actualitza els avisos
	// d'aquest dispositiu sense haver de tornar a la campana.
	let nSeguits = $state(0);
	onMount(() => {
		let primer = true;
		return follows.subscribe(async (llista) => {
			nSeguits = llista.length;
			if (primer) {
				primer = false;
				return;
			}
			if (estat !== 'actiu' || !triats.has('jugadors_seguits')) return;
			const actual = await subscripcioActual();
			if (actual) desaAlNuvol(actual, [...triats]).catch(() => {});
		});
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
	// Clic fora del panell i de la campana: tanca. No és una capa a pantalla
	// completa perquè el `backdrop-blur` de la capçalera la confinaria a la
	// capçalera mateixa.
	function alPremer(e: PointerEvent) {
		if (!obert) return;
		const on = e.target as Node;
		if (panell?.contains(on) || boto?.contains(on)) return;
		obert = false;
	}

	function commuta(id: TipusAvis) {
		const s = new Set(triats);
		if (s.has(id)) s.delete(id);
		else s.add(id);
		triats = s;
	}

	async function desaAlNuvol(sub: PushSubscription, tipus: TipusAvis[]) {
		const j = sub.toJSON();
		const base = {
			p_endpoint: sub.endpoint,
			p_p256dh: j.keys?.p256dh,
			p_auth: j.keys?.auth,
			p_tipus: tipus,
			p_dispositiu: navigator.userAgent.slice(0, 200)
		};
		let { error: e } = await db.rpc('desa_subscripcio', { ...base, p_jugadors: get(follows) });
		// PGRST202: el servidor encara no té la funció amb `p_jugadors` (migració
		// 0046 sense aplicar, o el Data API encara no la veu). Es desa la resta.
		if (e?.code === 'PGRST202') {
			const sense = tipus.filter((t) => t !== 'jugadors_seguits');
			({ error: e } = await db.rpc('desa_subscripcio', { ...base, p_tipus: sense }));
		}
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

<svelte:window onkeydown={alTeclat} onpointerdown={alPremer} />

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
		<!-- Al mòbil, fix amb marges a tots dos costats: penjat de la campana, que
		     no és a la vora, sortia tallat per l'esquerra. -->
		<div
			bind:this={panell}
			id="panell-avisos"
			role="dialog"
			aria-labelledby="titol-avisos"
			class="fixed inset-x-4 top-14 z-30 rounded-md sm:absolute sm:inset-x-auto sm:right-0 sm:top-12 sm:w-80 border border-slate-200 bg-white p-4 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
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
								<span class="block text-xs text-slate-600 dark:text-slate-400"
									>{t.id === 'jugadors_seguits'
										? nSeguits === 0
											? 'Encara no en segueixes cap: marca’ls amb ★ a la seva fitxa.'
											: nSeguits === 1
												? 'Les partides del jugador de ★ Seguits, de qualsevol competició.'
												: `Les partides dels ${nSeguits} jugadors de ★ Seguits, de qualsevol competició.`
										: t.detall}</span
								>
							</span>
						</label>
						{#if t.id === 'jugadors_seguits'}
							<a
								href="/seguiment"
								onclick={() => (obert = false)}
								class="ml-9 inline-flex min-h-11 items-center text-xs font-medium text-sky-700 underline underline-offset-2 dark:text-sky-400"
								>Tria'ls a ★ Seguits</a
							>
						{/if}
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
