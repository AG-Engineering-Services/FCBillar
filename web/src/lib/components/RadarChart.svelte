<script lang="ts">
	// Radar (aranya) de rendiment: un eix per franja de nivell d'oponent.
	// mode='abs' → dos polígons (victòries / derrotes). mode='pct' → dos polígons
	// (% de victòries i % de derrotes per franja). SVG pur, sense dependències.
	// Amb `onselect`, cada branca és un botó (ratolí, dit o Tab + Enter).
	let {
		buckets = [],
		size = 360,
		mode = 'abs',
		onselect
	}: {
		buckets?: { label: string; wins: number; losses: number; draws?: number }[];
		size?: number;
		mode?: 'abs' | 'pct';
		onselect?: (i: number, ev: Event) => void;
	} = $props();

	import { theme } from '$lib/theme';

	const WIN = '#16a34a';
	const LOSS = '#dc2626';
	// Color de la graella (anells/radis) reactiu al tema.
	const cGrid = $derived($theme === 'dark' ? '#334155' : '#e2e8f0');
	// Branca assenyalada (hover o focus): el radi es pinta amb l'accent dels botons.
	const cActiu = $derived($theme === 'dark' ? '#38bdf8' : '#0284c7');
	let actiu = $state<number | null>(null);

	// Falca de la branca i: de mig camí cap a l'anterior a mig camí cap a la
	// següent, fins a fora de l'etiqueta. És la zona que es pot tocar.
	function falca(i: number): string {
		const r = R + 44;
		// Una sola branca: tot el cercle.
		if (n === 1) return `M${cx - r},${cy} a${r},${r} 0 1 0 ${2 * r},0 a${r},${r} 0 1 0 ${-2 * r},0 Z`;
		const mig = Math.PI / n;
		const a0 = angle(i) - mig;
		const a1 = angle(i) + mig;
		const p = (a: number) => `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
		return `M${cx},${cy} L${p(a0)} A${r},${r} 0 0 1 ${p(a1)} Z`;
	}
	function descripcio(b: { label: string; wins: number; losses: number }): string {
		const v = b.wins === 1 ? '1 victòria' : `${b.wins} victòries`;
		const d = b.losses === 1 ? '1 derrota' : `${b.losses} derrotes`;
		return `Rivals de ${b.label}: ${v} i ${d}. Obre les partides`;
	}

	const n = $derived(buckets.length);
	const cx = $derived(size / 2);
	const cy = $derived(size / 2);
	const R = $derived(size / 2 - 64);
	const PADX = 28;

	const dec = (b: { wins: number; losses: number }) => b.wins + b.losses;
	const winPct = (b: { wins: number; losses: number }) => (dec(b) > 0 ? (b.wins / dec(b)) * 100 : 0);
	const lossPct = (b: { wins: number; losses: number }) => (dec(b) > 0 ? (b.losses / dec(b)) * 100 : 0);

	function niceCeil(v: number): number {
		if (v <= 5) return 5;
		if (v <= 10) return 10;
		const step = v <= 50 ? 5 : v <= 100 ? 10 : 25;
		return Math.ceil(v / step) * step;
	}
	const maxAbs = $derived(Math.max(1, ...buckets.flatMap((b) => [b.wins, b.losses])));
	const scaleMax = $derived(mode === 'pct' ? 100 : niceCeil(maxAbs));

	function angle(i: number): number {
		return (-90 + (i * 360) / n) * (Math.PI / 180);
	}
	function pt(i: number, r: number): [number, number] {
		const a = angle(i);
		return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
	}
	function poly(values: number[]): string {
		return values
			.map((v, i) => {
				const [x, y] = pt(i, (v / scaleMax) * R);
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	}
	function anchor(i: number): string {
		const c = Math.cos(angle(i));
		if (c > 0.15) return 'start';
		if (c < -0.15) return 'end';
		return 'middle';
	}

	const rings = $derived(
		[0.25, 0.5, 0.75, 1].map((f) => ({
			f,
			points: Array.from({ length: n }, (_, i) => {
				const [x, y] = pt(i, f * R);
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			}).join(' ')
		}))
	);
	const pctVals = $derived(buckets.map(winPct));
	const lossPctVals = $derived(buckets.map(lossPct));
	const winPoly = $derived(poly(buckets.map((b) => b.wins)));
	const lossPoly = $derived(poly(buckets.map((b) => b.losses)));
	const pctPoly = $derived(poly(pctVals));
	const lossPctPoly = $derived(poly(lossPctVals));
	const hasData = $derived(buckets.some((b) => b.wins + b.losses > 0));
</script>

{#if !hasData}
	<p class="text-slate-500 dark:text-slate-400 text-sm">Sense partides classificades per nivell d'oponent.</p>
{:else}
	<div class="flex flex-col items-center">
		<!-- Marge lateral (PADX) perquè les etiquetes dels eixos de dreta i esquerra
		     («0,47-0,54», «≥ 0,82») no quedin tallades. -->
		<svg
			viewBox="{-PADX} 0 {size + 2 * PADX} {size}"
			width={size + 2 * PADX}
			height={size}
			class="h-auto max-w-full"
		>
			{#each rings as ring}
				<polygon points={ring.points} fill="none" stroke={cGrid} stroke-width="1" />
			{/each}
			{#each buckets as _b, i}
				{@const [x, y] = pt(i, R)}
				<line
					x1={cx}
					y1={cy}
					x2={x}
					y2={y}
					stroke={actiu === i ? cActiu : cGrid}
					stroke-width={actiu === i ? 2 : 1}
				/>
			{/each}

			{#if mode === 'pct'}
				<polygon points={lossPctPoly} fill={LOSS} fill-opacity="0.18" stroke={LOSS} stroke-width="2" />
				<polygon points={pctPoly} fill={WIN} fill-opacity="0.22" stroke={WIN} stroke-width="2" />
				{#each buckets as _b, i}
					{@const [wx, wy] = pt(i, (pctVals[i] / scaleMax) * R)}
					{@const [lx, ly] = pt(i, (lossPctVals[i] / scaleMax) * R)}
					<circle cx={lx} cy={ly} r="3" fill={LOSS} />
					<circle cx={wx} cy={wy} r="3" fill={WIN} />
				{/each}
			{:else}
				<polygon points={lossPoly} fill={LOSS} fill-opacity="0.18" stroke={LOSS} stroke-width="2" />
				<polygon points={winPoly} fill={WIN} fill-opacity="0.22" stroke={WIN} stroke-width="2" />
				{#each buckets as b, i}
					{@const [wx, wy] = pt(i, (b.wins / scaleMax) * R)}
					{@const [lx, ly] = pt(i, (b.losses / scaleMax) * R)}
					<circle cx={lx} cy={ly} r="3" fill={LOSS} />
					<circle cx={wx} cy={wy} r="3" fill={WIN} />
				{/each}
			{/if}

			{#each buckets as b, i}
				{@const [lxr, lyr] = pt(i, R + 14)}
				<text
					x={lxr}
					y={lyr}
					text-anchor={anchor(i)}
					dominant-baseline="middle"
					class="fill-slate-600 dark:fill-slate-300"
					style="font-size: 11px; font-weight: 600"
				>
					{b.label}
				</text>
				{#if mode === 'pct'}
					<text x={lxr} y={lyr + 13} text-anchor={anchor(i)} dominant-baseline="middle" style="font-size: 10px">
						{#if dec(b)}
							<tspan fill={WIN}>{Math.round(winPct(b))}%</tspan>
							<tspan fill="#94a3b8"> · </tspan>
							<tspan fill={LOSS}>{Math.round(lossPct(b))}%</tspan>
						{:else}<tspan fill="#94a3b8">—</tspan>{/if}
					</text>
				{:else}
					<text x={lxr} y={lyr + 13} text-anchor={anchor(i)} dominant-baseline="middle" style="font-size: 10px">
						<tspan fill={WIN}>{b.wins}V</tspan>
						<tspan fill="#94a3b8"> · </tspan>
						<tspan fill={LOSS}>{b.losses}D</tspan>
					</text>
				{/if}
			{/each}

			{#if onselect}
				{#each buckets as b, i}
					<path
						d={falca(i)}
						fill="transparent"
						role="button"
						tabindex="0"
						aria-label={descripcio(b)}
						class="falca cursor-pointer"
						onclick={(e) => onselect(i, e)}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault();
								onselect(i, e);
							}
						}}
						onpointerenter={() => (actiu = i)}
						onpointerleave={() => (actiu = null)}
						onfocus={() => (actiu = i)}
						onblur={() => (actiu = null)}
					/>
				{/each}
			{/if}
		</svg>
		<div class="mt-1 flex items-center gap-4 text-xs text-slate-600 dark:text-slate-300">
			{#if mode === 'pct'}
				<span class="flex items-center gap-1">
					<span class="inline-block h-3 w-3 rounded-sm" style="background:{WIN}"></span> % victòries
				</span>
				<span class="flex items-center gap-1">
					<span class="inline-block h-3 w-3 rounded-sm" style="background:{LOSS}"></span> % derrotes
				</span>
				<span class="text-slate-500 dark:text-slate-400">escala 0–100%</span>
			{:else}
				<span class="flex items-center gap-1">
					<span class="inline-block h-3 w-3 rounded-sm" style="background:{WIN}"></span> Victòries
				</span>
				<span class="flex items-center gap-1">
					<span class="inline-block h-3 w-3 rounded-sm" style="background:{LOSS}"></span> Derrotes
				</span>
				<span class="text-slate-500 dark:text-slate-400">escala 0–{scaleMax}</span>
			{/if}
		</div>
		{#if onselect}
			<p class="mt-1 text-2xs text-slate-500 dark:text-slate-400 print:hidden">Toca una branca per veure'n les partides.</p>
		{/if}
	</div>
{/if}

<style>
	/* La falca és invisible: el focus de teclat es marca amb el contorn de la
	   falca, a més del radi pintat. */
	.falca:focus {
		outline: none;
	}
	.falca:focus-visible {
		fill: rgb(14 165 233 / 0.08);
		stroke: #0284c7;
		stroke-width: 2;
		stroke-dasharray: 4 3;
	}
	:global(.dark) .falca:focus-visible {
		stroke: #38bdf8;
	}
</style>
