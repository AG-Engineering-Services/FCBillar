<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { get } from 'svelte/store';
	import { db } from '$lib/db';
	import {
		follows,
		toggleFollow,
		clubFollows,
		toggleClubFollow,
		equipFollows,
		toggleEquipFollow,
		openFollows,
		toggleOpenFollow
	} from '$lib/follows';
	import { arreglaCodificacio } from '$lib/codificacio';
	import {
		TIPUS_AVIS,
		type TipusAvis,
		VAPID_PUBLIC_KEY,
		base64UrlABytes,
		seguiments
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
	const CONEGUTS = new Set<string>(TIPUS_AVIS.map((t) => t.id));

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
			// Els tipus antics del Banyoles ja no existeixen: només es recuperen els d'ara.
			const desat = JSON.parse(localStorage.getItem(DESAT) ?? 'null');
			if (Array.isArray(desat)) {
				const bons = desat.filter((t) => CONEGUTS.has(t)) as TipusAvis[];
				if (bons.length) triats = new Set(bons);
			}
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

	// Seguir o deixar de seguir (★ a les fitxes, als clubs o als opens) actualitza
	// els avisos d'aquest dispositiu sense haver de tornar a la campana. S'espera
	// mig segon per no desar cinc cops si se'n marquen cinc seguits.
	let espera: ReturnType<typeof setTimeout> | undefined;
	function programaDesa() {
		clearTimeout(espera);
		espera = setTimeout(async () => {
			if (estat !== 'actiu') return;
			const actual = await subscripcioActual();
			if (actual) desaAlNuvol(actual, [...triats]).catch(() => {});
		}, 500);
	}
	onMount(() => {
		const baixes = [follows, clubFollows, equipFollows, openFollows].map((s) => {
			let primer = true;
			return s.subscribe(() => {
				if (primer) primer = false;
				else programaDesa();
			});
		});
		return () => baixes.forEach((b) => b());
	});

	// Què se segueix, amb noms, per ensenyar-ho al panell. Es demana en obrir-lo:
	// el dispositiu només guarda identificadors.
	type Seguit = { id: string; nom: string; detall?: string | null; href: string };
	let nomsJugadors = $state<Map<string, Seguit>>(new Map());
	let nomsClubs = $state<Map<string, string>>(new Map());
	let nomsOpens = $state<Map<string, string>>(new Map());
	let errorNoms = $state(false);
	async function carregaNoms() {
		errorNoms = false;
		const [jug, clubs, opens] = await Promise.all([
			get(follows).length
				? db.from('players').select('fcb_id, nom, club_fcb_id').in('fcb_id', get(follows))
				: Promise.resolve({ data: [], error: null }),
			get(clubFollows).length
				? db.from('clubs').select('fcb_id, nom').in('fcb_id', get(clubFollows))
				: Promise.resolve({ data: [], error: null }),
			get(openFollows).length
				? db.from('open_live').select('fcb_division_id, name').in('fcb_division_id', get(openFollows))
				: Promise.resolve({ data: [], error: null })
		]);
		if (jug.error || clubs.error || opens.error) errorNoms = true;
		nomsJugadors = new Map(
			(jug.data ?? []).map((p: any) => [
				String(p.fcb_id),
				{
					id: String(p.fcb_id),
					nom: arreglaCodificacio(p.nom),
					detall: p.club_fcb_id,
					href: `/jugador/${p.fcb_id}`
				}
			])
		);
		nomsClubs = new Map((clubs.data ?? []).map((c: any) => [c.fcb_id, arreglaCodificacio(c.nom)]));
		nomsOpens = new Map((opens.data ?? []).map((o: any) => [String(o.fcb_division_id), o.name]));
	}
	const perNom = (a: Seguit, b: Seguit) => a.nom.localeCompare(b.nom);
	const llistaJugadors = $derived(
		$follows
			.map((id) => nomsJugadors.get(id) ?? { id, nom: `Fitxa ${id}`, href: `/jugador/${id}` })
			.sort(perNom)
	);
	const llistaClubsEquips = $derived([
		...$clubFollows
			.map((id) => ({ id: `c:${id}`, nom: nomsClubs.get(id) ?? id, detall: 'Tots els equips', href: '/seguiment' }))
			.sort(perNom),
		...$equipFollows.map((e) => ({ id: `e:${e}`, nom: e, detall: 'Equip', href: '/seguiment' })).sort(perNom)
	]);
	const llistaOpens = $derived(
		$openFollows
			.map((id) => ({
				id,
				nom: nomsOpens.get(id) ?? `Open ${id}`,
				detall: nomsOpens.has(id) ? 'En directe' : 'Ja no és en directe',
				href: `/opens/directe/${id}`
			}))
			.sort(perNom)
	);
	function treu(tipus: TipusAvis, id: string) {
		if (tipus === 'jugadors_seguits') toggleFollow(id);
		else if (tipus === 'opens_seguits') toggleOpenFollow(id);
		else if (id.startsWith('c:')) toggleClubFollow(id.slice(2));
		else toggleEquipFollow(id.slice(2));
	}
	function llistaDe(tipus: TipusAvis): Seguit[] {
		if (tipus === 'jugadors_seguits') return llistaJugadors;
		if (tipus === 'clubs_seguits') return llistaClubsEquips;
		if (tipus === 'opens_seguits') return llistaOpens;
		return [];
	}
	// On es trien, per a l'enllaç de sota de cada llista.
	const ON_ES_TRIEN: Partial<Record<TipusAvis, { href: string; text: string; buit: string }>> = {
		jugadors_seguits: {
			href: '/seguiment',
			text: "Tria'ls a ★ Seguits",
			buit: 'Encara no en segueixes cap.'
		},
		clubs_seguits: {
			href: '/seguiment',
			text: "Tria'ls a ★ Seguits",
			buit: 'Encara no en segueixes cap.'
		},
		opens_seguits: {
			href: '/opens',
			text: 'Tria’ls a Opens, a la pàgina de cada open en directe',
			buit: 'Encara no en segueixes cap.'
		}
	};

	async function obre() {
		obert = !obert;
		missatge = '';
		error = '';
		if (obert) {
			carregaNoms();
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
		const { error: e } = await db.rpc('desa_subscripcio', {
			p_endpoint: sub.endpoint,
			p_p256dh: j.keys?.p256dh,
			p_auth: j.keys?.auth,
			p_tipus: tipus,
			p_dispositiu: navigator.userAgent.slice(0, 200),
			p_seguiments: seguiments(get(follows), get(clubFollows), get(equipFollows), get(openFollows))
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
				throw new Error('El telèfon no ha donat permís per als avisos.');
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
		     no és a la vora, sortia tallat per l'esquerra. Amb les llistes de
		     seguits pot passar de l'alçada de la pantalla: llavors llisca. -->
		<div
			bind:this={panell}
			id="panell-avisos"
			role="dialog"
			aria-labelledby="titol-avisos"
			class="fixed inset-x-4 top-14 z-30 max-h-[calc(100dvh-4.5rem)] overflow-y-auto rounded-md border border-slate-200 bg-white p-4 text-sm shadow-lg sm:absolute sm:inset-x-auto sm:right-0 sm:top-12 sm:w-80 dark:border-slate-700 dark:bg-slate-900"
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
						{@const llista = llistaDe(t.id)}
						{@const on = ON_ES_TRIEN[t.id]}
						<label
							class="flex min-h-11 cursor-pointer items-start gap-3 rounded-sm px-1 py-2 hover:bg-slate-50 dark:hover:bg-slate-800"
						>
							<input
								type="checkbox"
								class="mt-0.5 h-5 w-5 shrink-0 accent-sky-700"
								checked={triats.has(t.id)}
								onchange={() => commuta(t.id)}
							/>
							<span>
								<span class="block font-medium"
									>{t.nom}{#if on}<span class="font-normal text-slate-600 dark:text-slate-400"
											>{` · ${llista.length}`}</span
										>{/if}</span
								>
								<span class="block text-xs text-slate-600 dark:text-slate-400">{t.detall}</span>
							</span>
						</label>
						{#if on}
							{#if errorNoms && llista.length}
								<p class="ml-9 text-xs text-red-700 dark:text-red-400">
									No s'han pogut carregar els noms; hi surten els números.
								</p>
							{/if}
							{#if llista.length}
								<ul
									aria-label={t.nom}
									class="ml-9 max-h-44 overflow-y-auto rounded-sm border border-slate-200 dark:border-slate-700"
								>
									{#each llista as s (s.id)}
										<li
											class="flex items-center border-b border-slate-100 last:border-0 dark:border-slate-800"
										>
											<a
												href={s.href}
												onclick={() => (obert = false)}
												class="flex min-h-11 min-w-0 flex-1 flex-col justify-center px-2 hover:bg-slate-50 dark:hover:bg-slate-800"
											>
												<span class="truncate text-xs font-medium">{s.nom}</span>
												{#if s.detall}<span
														class="truncate text-[11px] text-slate-600 dark:text-slate-400"
														>{s.detall}</span
													>{/if}
											</a>
											<button
												type="button"
												onclick={() => treu(t.id, s.id)}
												aria-label="Deixa de seguir {s.nom}"
												title="Deixa de seguir"
												class="grid min-h-11 min-w-11 shrink-0 place-items-center text-amber-600 hover:bg-slate-50 dark:text-amber-400 dark:hover:bg-slate-800"
												>★</button
											>
										</li>
									{/each}
								</ul>
							{:else}
								<p class="ml-9 text-xs text-slate-600 dark:text-slate-400">{on.buit}</p>
							{/if}
							<a
								href={on.href}
								onclick={() => (obert = false)}
								class="ml-9 inline-flex min-h-11 items-center text-xs font-medium text-sky-700 underline underline-offset-2 dark:text-sky-400"
								>{on.text}</a
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
				{#if error}<span class="text-red-700 dark:text-red-400">{error}</span>{:else if missatge}<span
						class="text-emerald-700 dark:text-emerald-400">{missatge}</span
					>{/if}
			</p>
		</div>
	{/if}
</div>
