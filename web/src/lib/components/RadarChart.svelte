<script lang="ts">
	// Radar (aranya) de rendiment: un eix per franja de nivell d'oponent.
	// mode='abs' → dos polígons (victòries / derrotes). mode='pct' → un polígon
	// (% de victòries per franja). SVG pur, sense dependències.
	let {
		buckets = [],
		size = 360,
		mode = 'abs'
	}: {
		buckets?: { label: string; wins: number; losses: number; draws?: number }[];
		size?: number;
		mode?: 'abs' | 'pct';
	} = $props();

	const WIN = '#16a34a';
	const LOSS = '#dc2626';

	const n = $derived(buckets.length);
	const cx = $derived(size / 2);
	const cy = $derived(size / 2);
	const R = $derived(size / 2 - 64);

	const dec = (b: { wins: number; losses: number }) => b.wins + b.losses;
	const winPct = (b: { wins: number; losses: number }) => (dec(b) > 0 ? (b.wins / dec(b)) * 100 : 0);

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
	const winPoly = $derived(poly(buckets.map((b) => b.wins)));
	const lossPoly = $derived(poly(buckets.map((b) => b.losses)));
	const pctPoly = $derived(poly(pctVals));
	const hasData = $derived(buckets.some((b) => b.wins + b.losses > 0));
</script>

{#if !hasData}
	<p class="text-slate-500 text-sm">Sense partides classificades per nivell d'oponent.</p>
{:else}
	<div class="flex flex-col items-center">
		<svg viewBox="0 0 {size} {size}" width={size} height={size} class="max-w-full">
			{#each rings as ring}
				<polygon points={ring.points} fill="none" stroke="#e2e8f0" stroke-width="1" />
			{/each}
			{#each buckets as _b, i}
				{@const [x, y] = pt(i, R)}
				<line x1={cx} y1={cy} x2={x} y2={y} stroke="#e2e8f0" stroke-width="1" />
			{/each}

			{#if mode === 'pct'}
				<polygon points={pctPoly} fill={WIN} fill-opacity="0.2" stroke={WIN} stroke-width="2" />
				{#each buckets as _b, i}
					{@const [x, y] = pt(i, (pctVals[i] / scaleMax) * R)}
					<circle cx={x} cy={y} r="3" fill={WIN} />
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
					class="fill-slate-600"
					style="font-size: 11px; font-weight: 600"
				>
					{b.label}
				</text>
				{#if mode === 'pct'}
					<text x={lxr} y={lyr + 13} text-anchor={anchor(i)} dominant-baseline="middle" style="font-size: 10px">
						<tspan fill={dec(b) ? WIN : '#94a3b8'}>{dec(b) ? Math.round(winPct(b)) + '%' : '—'}</tspan>
						<tspan fill="#94a3b8"> ({dec(b)})</tspan>
					</text>
				{:else}
					<text x={lxr} y={lyr + 13} text-anchor={anchor(i)} dominant-baseline="middle" style="font-size: 10px">
						<tspan fill={WIN}>{b.wins}V</tspan>
						<tspan fill="#94a3b8"> · </tspan>
						<tspan fill={LOSS}>{b.losses}D</tspan>
					</text>
				{/if}
			{/each}
		</svg>
		<div class="mt-1 flex items-center gap-4 text-xs text-slate-600">
			{#if mode === 'pct'}
				<span class="flex items-center gap-1">
					<span class="inline-block h-3 w-3 rounded-sm" style="background:{WIN}"></span> % victòries
				</span>
				<span class="text-slate-400">escala 0–100% · (n)</span>
			{:else}
				<span class="flex items-center gap-1">
					<span class="inline-block h-3 w-3 rounded-sm" style="background:{WIN}"></span> Victòries
				</span>
				<span class="flex items-center gap-1">
					<span class="inline-block h-3 w-3 rounded-sm" style="background:{LOSS}"></span> Derrotes
				</span>
				<span class="text-slate-400">escala 0–{scaleMax}</span>
			{/if}
		</div>
	</div>
{/if}
