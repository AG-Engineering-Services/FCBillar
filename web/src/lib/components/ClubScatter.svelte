<script lang="ts">
	// Mapa 2D de clubs: X = Profunditat (0..100, relativa) · Y = Potència (top-K).
	// La mida de la bombolla és el nombre de jugadors rankejats. SVG pur.
	import { theme } from '$lib/theme';
	import type { ClubIndex } from '$lib/clubs';

	let {
		clubs = [],
		selected = null,
		onselect
	}: {
		clubs?: ClubIndex[];
		selected?: string | null;
		onselect?: (club: string | null) => void;
	} = $props();

	const W = 640;
	const H = 440;
	const M = { l: 48, r: 18, t: 18, b: 44 };
	const iw = W - M.l - M.r;
	const ih = H - M.t - M.b;

	const cGrid = $derived($theme === 'dark' ? '#334155' : '#e2e8f0');
	const ACCENT = '#0b3d2e'; // verd del club (mateix de la marca)
	const ACCENT_D = '#34d399'; // emerald-400 per al mode fosc
	const cDot = $derived($theme === 'dark' ? ACCENT_D : ACCENT);

	// Dominis ajustats a les dades (amb marge) perquè les bombolles no s'apleguin
	// —sobretot en mode Global, on les potències es comprimeixen a dalt.
	const potVals = $derived(clubs.map((c) => c.potencia));
	const yMin = $derived(clubs.length ? Math.max(0, Math.min(...potVals) - 4) : 0);
	const yMax = $derived(clubs.length ? Math.min(100, Math.max(...potVals) + 4) : 100);
	const xMax = 100; // depthScore ja és 0..100

	const maxN = $derived(Math.max(1, ...clubs.map((c) => c.n)));

	function px(depthScore: number): number {
		return M.l + (Math.max(0, Math.min(xMax, depthScore)) / xMax) * iw;
	}
	function py(pot: number): number {
		const span = Math.max(1e-6, yMax - yMin);
		return M.t + ih - ((Math.max(yMin, Math.min(yMax, pot)) - yMin) / span) * ih;
	}
	function radius(n: number): number {
		return 5 + Math.sqrt(n / maxN) * 16;
	}
	function short(name: string): string {
		return name.replace(/^(C\.?B\.?|B\.?C\.?|S\.?B\.?)\s*/i, '').trim() || name;
	}

	// Etiquetem els clubs destacats (top per CQI) i el seleccionat, per no saturar.
	const labelled = $derived(
		new Set([
			...[...clubs].sort((a, b) => b.cqi - a.cqi).slice(0, 8).map((c) => c.club),
			...(selected ? [selected] : [])
		])
	);

	const yTicks = $derived.by(() => {
		const t: number[] = [];
		const lo = Math.ceil(yMin / 10) * 10;
		for (let v = lo; v <= yMax; v += 10) t.push(v);
		return t;
	});
	const xTicks = [0, 25, 50, 75, 100];
</script>

<div class="w-full">
	<svg viewBox="0 0 {W} {H}" class="w-full" role="img" aria-label="Mapa de clubs: profunditat contra potència">
		<!-- graella X -->
		{#each xTicks as t}
			<line x1={px(t)} y1={M.t} x2={px(t)} y2={M.t + ih} stroke={cGrid} stroke-width="1" />
			<text x={px(t)} y={M.t + ih + 16} text-anchor="middle" class="fill-slate-400 dark:fill-slate-500" style="font-size:10px">{t}</text>
		{/each}
		<!-- graella Y -->
		{#each yTicks as t}
			<line x1={M.l} y1={py(t)} x2={M.l + iw} y2={py(t)} stroke={cGrid} stroke-width="1" />
			<text x={M.l - 6} y={py(t)} text-anchor="end" dominant-baseline="middle" class="fill-slate-400 dark:fill-slate-500" style="font-size:10px">{t}</text>
		{/each}

		<!-- títols d'eixos -->
		<text x={M.l + iw / 2} y={H - 4} text-anchor="middle" class="fill-slate-500 dark:fill-slate-400" style="font-size:11px;font-weight:600">Profunditat →</text>
		<text x={14} y={M.t + ih / 2} text-anchor="middle" dominant-baseline="middle" transform="rotate(-90 14 {M.t + ih / 2})" class="fill-slate-500 dark:fill-slate-400" style="font-size:11px;font-weight:600">Potència (top-K) ↑</text>

		<!-- bombolles -->
		{#each clubs as c (c.club)}
			{@const sel = c.club === selected}
			<g
				role="button"
				tabindex="0"
				style="cursor:pointer"
				onclick={() => onselect?.(sel ? null : c.club)}
				onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onselect?.(sel ? null : c.club); } }}
			>
				<circle
					cx={px(c.depthScore)}
					cy={py(c.potencia)}
					r={radius(c.n)}
					fill={cDot}
					fill-opacity={sel ? 0.85 : 0.4}
					stroke={cDot}
					stroke-width={sel ? 2.5 : 1}
				/>
				{#if labelled.has(c.club)}
					<text
						x={px(c.depthScore)}
						y={py(c.potencia) - radius(c.n) - 3}
						text-anchor="middle"
						class="fill-slate-700 dark:fill-slate-200"
						style="font-size:10px;font-weight:{sel ? 700 : 600};pointer-events:none"
					>{short(c.club)}</text>
				{/if}
			</g>
		{/each}
	</svg>
</div>
