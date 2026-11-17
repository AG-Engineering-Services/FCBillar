<script lang="ts">
	// Combobox «Partides contra…»: suggereix rivals de les partides del jugador a
	// partir de la tercera lletra. Escollir-ne un filtra la llista de partides.
	import { MIN_LLETRES, lletres, suggereixRivals, type Rival } from '$lib/rivals';

	let {
		rivals,
		selected = $bindable(null),
		label = 'Partides contra'
	}: { rivals: Rival[]; selected?: Rival | null; label?: string } = $props();

	const uid = $props.id();
	let q = $state(selected?.nom ?? '');
	let obert = $state(false);
	let actiu = $state(-1);
	let input: HTMLInputElement;

	const suggeriments = $derived(selected ? [] : suggereixRivals(rivals, q));
	const pocs = $derived(!selected && q.trim() !== '' && lletres(q) < MIN_LLETRES);
	const capNom = $derived(!selected && lletres(q) >= MIN_LLETRES && suggeriments.length === 0);

	function tria(r: Rival) {
		selected = r;
		q = r.nom;
		obert = false;
		actiu = -1;
	}

	function neteja() {
		selected = null;
		q = '';
		obert = false;
		actiu = -1;
		input?.focus();
	}

	function onInput() {
		if (selected) selected = null;
		obert = true;
		actiu = -1;
	}

	function onKeydown(ev: KeyboardEvent) {
		if (ev.key === 'ArrowDown' && suggeriments.length) {
			ev.preventDefault();
			obert = true;
			actiu = (actiu + 1) % suggeriments.length;
		} else if (ev.key === 'ArrowUp' && suggeriments.length) {
			ev.preventDefault();
			obert = true;
			actiu = actiu <= 0 ? suggeriments.length - 1 : actiu - 1;
		} else if (ev.key === 'Enter' && obert && suggeriments.length) {
			ev.preventDefault();
			tria(suggeriments[Math.max(actiu, 0)]!);
		} else if (ev.key === 'Escape') {
			if (obert && suggeriments.length) obert = false;
			else if (q) neteja();
		}
	}
</script>

<div class="relative print:hidden">
	<label for="{uid}-q" class="mb-1 block text-2xs font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</label>
	<div class="relative">
		<input
			bind:this={input}
			id="{uid}-q"
			type="text"
			role="combobox"
			autocomplete="off"
			spellcheck="false"
			placeholder="Nom del rival"
			aria-autocomplete="list"
			aria-expanded={obert && suggeriments.length > 0}
			aria-controls="{uid}-llista"
			aria-activedescendant={actiu >= 0 ? `${uid}-op-${actiu}` : undefined}
			aria-describedby="{uid}-ajuda"
			bind:value={q}
			oninput={onInput}
			onkeydown={onKeydown}
			onfocus={() => (obert = true)}
			onblur={() => setTimeout(() => (obert = false), 120)}
			class="min-h-11 w-full rounded-lg bg-white py-2 pl-3 pr-11 text-base text-slate-900 ring-1 ring-slate-300 placeholder:text-slate-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 dark:bg-slate-900 dark:text-slate-100 dark:ring-slate-600 dark:placeholder:text-slate-400 dark:focus-visible:ring-blue-400 sm:text-sm"
		/>
		{#if q}
			<button
				type="button"
				onclick={neteja}
				aria-label="Treu el filtre"
				class="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-lg text-lg leading-none text-slate-500 hover:text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 dark:text-slate-400 dark:hover:text-slate-100 dark:focus-visible:outline-blue-400"
				>×</button>
		{/if}
	</div>
	<p id="{uid}-ajuda" class="mt-1 min-h-4 text-[11px] text-slate-500 dark:text-slate-400" aria-live="polite">
		{#if pocs}Escriu almenys {MIN_LLETRES} lletres.{:else if capNom}Cap rival amb aquest nom a les seves partides.{/if}
	</p>
	{#if obert && suggeriments.length}
		<ul
			id="{uid}-llista"
			role="listbox"
			aria-label="Rivals"
			class="absolute left-0 right-0 top-[4.25rem] z-20 max-h-72 overflow-auto rounded-lg bg-white py-1 shadow-lg ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-700"
		>
			{#each suggeriments as r, i (r.key)}
				<li
					id="{uid}-op-{i}"
					role="option"
					aria-selected={i === actiu}
					onmousedown={(e) => {
						e.preventDefault();
						tria(r);
					}}
					onmouseenter={() => (actiu = i)}
					class="flex min-h-11 cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm {i === actiu
						? 'bg-slate-100 dark:bg-slate-800'
						: ''}"
				>
					<span class="min-w-0 truncate">{r.nom}</span>
					<span class="shrink-0 text-[11px] tabular-nums text-slate-500 dark:text-slate-400">{r.partides} {r.partides === 1 ? 'partida' : 'partides'}</span>
				</li>
			{/each}
		</ul>
	{/if}
</div>
