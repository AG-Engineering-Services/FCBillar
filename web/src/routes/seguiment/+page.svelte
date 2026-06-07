<script lang="ts">
	import { supabase } from '$lib/supabase';
	import { follows, toggleFollow } from '$lib/follows';

	interface Pt {
		seq: number;
		mitjana: number | null;
		posicio: number | null;
	}
	interface Serie {
		fcb_id: string;
		nom: string;
		club: string | null;
		color: string;
		pts: Pt[];
		posicio: number | null;
		mitjana: number | null;
	}

	const COLORS = ['#0f172a', '#e0322a', '#2563eb', '#16a34a', '#f59e0b', '#7c3aed', '#db2777', '#0891b2'];
	let series = $state<Serie[]>([]);
	let loading = $state(true);

	$effect(() => {
		loadFollowed($follows);
	});

	async function loadFollowed(ids: string[]) {
		loading = true;
		if (!ids.length) {
			series = [];
			loading = false;
			return;
		}
		const [{ data: pl }, { data: cl }, { data: re }] = await Promise.all([
			supabase.from('players').select('fcb_id, nom, club_fcb_id').in('fcb_id', ids),
			supabase.from('clubs').select('fcb_id, nom'),
			supabase
				.from('ranking_entries')
				.select('player_fcb_id, num_seq, posicio, mitjana_general')
				.eq('modalitat_codi', 1)
				.in('player_fcb_id', ids)
				.order('num_seq')
		]);
		const clubs = new Map((cl ?? []).map((c) => [c.fcb_id, c.nom]));
		const byPlayer = new Map<string, Pt[]>();
		for (const r of re ?? []) {
			if (!byPlayer.has(r.player_fcb_id)) byPlayer.set(r.player_fcb_id, []);
			byPlayer.get(r.player_fcb_id)!.push({ seq: r.num_seq, mitjana: r.mitjana_general, posicio: r.posicio });
		}
		series = (pl ?? [])
			.map((p, i) => {
				const pts = byPlayer.get(p.fcb_id) ?? [];
				const last = pts.at(-1);
				return {
					fcb_id: p.fcb_id,
					nom: p.nom,
					club: clubs.get(p.club_fcb_id) ?? null,
					color: COLORS[i % COLORS.length],
					pts,
					posicio: last?.posicio ?? null,
					mitjana: last?.mitjana ?? null
				};
			})
			.sort((a, b) => (a.posicio ?? 9999) - (b.posicio ?? 9999));
		loading = false;
	}

	// Eixos compartits
	const VBW = 320,
		VBH = 90,
		PAD = 8;
	const seqRange = $derived.by(() => {
		const all = series.flatMap((s) => s.pts.map((p) => p.seq));
		return all.length ? [Math.min(...all), Math.max(...all)] : [0, 1];
	});
	function range(getter: (p: Pt) => number | null): [number, number] {
		const vs = series.flatMap((s) => s.pts.map(getter)).filter((v): v is number => v != null);
		if (!vs.length) return [0, 1];
		let lo = Math.min(...vs),
			hi = Math.max(...vs);
		if (lo === hi) {
			lo -= 0.5;
			hi += 0.5;
		}
		return [lo, hi];
	}
	function lineFor(s: Serie, getter: (p: Pt) => number | null, invert: boolean): string {
		const [smin, smax] = seqRange;
		const [vmin, vmax] = range(getter);
		const sw = smax - smin || 1;
		return s.pts
			.map((p) => {
				const v = getter(p);
				if (v == null) return null;
				const x = PAD + ((p.seq - smin) / sw) * (VBW - 2 * PAD);
				let t = (v - vmin) / (vmax - vmin);
				if (invert) t = 1 - t;
				return `${x.toFixed(1)},${(VBH - PAD - t * (VBH - 2 * PAD)).toFixed(1)}`;
			})
			.filter(Boolean)
			.join(' ');
	}
	const hasHist = $derived(series.some((s) => s.pts.length >= 2));
</script>

<h1 class="mb-1 text-base font-bold">★ Jugadors seguits</h1>
<p class="mb-3 text-[11px] text-slate-400">
	Es guarda en aquest dispositiu. Evolució del rànquing de 3 bandes.
</p>

{#if loading}
	<p class="py-6 text-center text-sm text-slate-400">Carregant…</p>
{:else if series.length === 0}
	<div class="rounded-xl bg-white p-6 text-center text-sm text-slate-400 ring-1 ring-slate-200">
		Encara no segueixes ningú.<br />Entra a la fitxa d'un jugador i toca <b>☆ Seguir</b>.
	</div>
{:else}
	{#if hasHist}
		<div class="mb-4 space-y-3">
			<div class="rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Evolució mitjana</div>
				<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" class="h-24 w-full">
					{#each series as s}
						<polyline points={lineFor(s, (p) => p.mitjana, false)} fill="none" stroke={s.color} stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
					{/each}
				</svg>
			</div>
			<div class="rounded-xl bg-white p-3 ring-1 ring-slate-200">
				<div class="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
					Evolució posició <span class="text-slate-300">(amunt = millor)</span>
				</div>
				<svg viewBox="0 0 {VBW} {VBH}" preserveAspectRatio="none" class="h-24 w-full">
					{#each series as s}
						<polyline points={lineFor(s, (p) => p.posicio, true)} fill="none" stroke={s.color} stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
					{/each}
				</svg>
			</div>
		</div>
	{/if}

	<ul class="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
		{#each series as s (s.fcb_id)}
			<li class="flex items-center gap-2 border-b border-slate-100 px-3 py-2.5 last:border-0">
				<span class="h-3 w-3 shrink-0 rounded-full" style:background-color={s.color}></span>
				<a href="/jugador/{s.fcb_id}" class="min-w-0 flex-1">
					<div class="truncate text-sm font-medium leading-tight">{s.nom}</div>
					{#if s.club}<div class="truncate text-xs text-slate-400">{s.club}</div>{/if}
				</a>
				{#if s.posicio != null}
					<div class="shrink-0 text-right">
						<div class="font-mono text-sm font-bold tabular-nums">#{s.posicio}</div>
						<div class="text-[10px] text-slate-400">{s.mitjana != null ? s.mitjana.toFixed(3) : ''}</div>
					</div>
				{/if}
				<button onclick={() => toggleFollow(s.fcb_id)} class="shrink-0 rounded-full px-2 py-1 text-xs text-amber-600" aria-label="deixar de seguir">★</button>
			</li>
		{/each}
	</ul>
{/if}
