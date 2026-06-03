<script lang="ts">
	import type { LivePhase, LiveMatch } from '$lib/opens/types';

	interface Props {
		koPhases: LivePhase[];
		highlightName?: string;
		favorites?: Set<string>;
	}

	let { koPhases, highlightName = '', favorites = new Set() }: Props = $props();

	// Standard Catalan KO round labels → expected match counts. Each round
	// halves the previous, so knowing any one round's size determines the rest.
	const LABEL_TO_MATCHES: Record<string, number> = {
		TRENTADOSENS: 32,
		SETZENS: 16,
		VUITENS: 8,
		QUARTS: 4,
		SEMIFINALS: 2,
		FINAL: 1
	};

	function expectedMatchCount(p: LivePhase, fallbackFirst: number, roundIdx: number): number {
		const fromLabel = LABEL_TO_MATCHES[p.label.toUpperCase()];
		if (fromLabel !== undefined) return fromLabel;
		if (p.ko_matches.length > 0) return p.ko_matches.length;
		return Math.max(1, Math.floor(fallbackFirst / Math.pow(2, roundIdx)));
	}

	const PLACEHOLDER: LiveMatch = {
		player_a: '—',
		player_b: '—',
		punts_a: 0,
		punts_b: 0,
		caramboles_a: 0,
		caramboles_b: 0,
		serie_major_a: 0,
		serie_major_b: 0,
		entrades: null,
		arbitre: null,
		is_played: false
	};

	/** Returns the matches to render for a phase AND whether they're
	 * provisional (computed by us) rather than FCB-official. If the FCB has
	 * published ko_matches, always prefer those. Otherwise, fall back to
	 * provisional_matches (only populated for the first KO round). */
	function phaseMatches(p: LivePhase): { matches: LiveMatch[]; provisional: boolean } {
		if (p.ko_matches.length > 0) return { matches: p.ko_matches, provisional: false };
		if (p.provisional_matches.length > 0)
			return { matches: p.provisional_matches, provisional: true };
		return { matches: [], provisional: false };
	}

	function padMatches(source: LiveMatch[], expected: number): LiveMatch[] {
		const out: LiveMatch[] = [...source];
		while (out.length < expected) out.push(PLACEHOLDER);
		return out;
	}

	function winner(m: LiveMatch): 'a' | 'b' | null {
		if (!m.is_played) return null;
		if (m.punts_a > m.punts_b) return 'a';
		if (m.punts_b > m.punts_a) return 'b';
		return null;
	}

	function hit(name: string): boolean {
		if (!highlightName.trim() || name === '—') return false;
		return name.toUpperCase().includes(highlightName.trim().toUpperCase());
	}

	function isFav(name: string): boolean {
		if (name === '—') return false;
		return favorites.has(name.trim().toUpperCase());
	}

	const firstSize = $derived.by(() => {
		for (let i = 0; i < koPhases.length; i++) {
			const c = expectedMatchCount(koPhases[i], 16, i);
			if (c > 0) return c * Math.pow(2, i);
		}
		return 16;
	});

	const MATCH_BOX_H = 58;
	const MATCH_BOX_W = 200;
	const MIN_GAP = 10;
	const columnHeight = $derived(firstSize * (MATCH_BOX_H + MIN_GAP));
</script>

<div class="overflow-x-auto">
	<div class="flex items-start gap-6 py-4" style="min-width: max-content">
		{#each koPhases as phase, roundIdx (phase.label)}
			{@const expected = expectedMatchCount(phase, firstSize, roundIdx)}
			{@const source = phaseMatches(phase)}
			{@const roundMatches = padMatches(source.matches, expected)}
			<div style="width: {MATCH_BOX_W}px">
				<h4 class="mb-2 flex items-center justify-center gap-1 text-center text-xs font-semibold uppercase tracking-wider text-slate-500">
					{phase.label}
					{#if source.provisional}
						<span
							class="rounded bg-slate-200 px-1 text-[10px] normal-case text-slate-700"
							title="Emparellament calculat internament — la FCB encara no l'ha publicat"
						>
							calc
						</span>
					{/if}
				</h4>
				<div
					class="flex flex-col justify-around"
					style="height: {columnHeight}px"
				>
					{#each roundMatches as m}
						{@const win = winner(m)}
						{@const favA = isFav(m.player_a)}
						{@const favB = isFav(m.player_b)}
						<div
							class="rounded-md border bg-white shadow-sm"
							class:border-dashed={source.provisional}
							class:border-slate-200={!m.is_played}
							class:border-slate-400={m.is_played}
							class:bg-slate-50={!m.is_played && m.player_a === '—'}
							class:ring-2={favA || favB}
							class:ring-amber-300={favA || favB}
						>
							<div
								class="flex items-center justify-between border-b border-slate-100 px-2 py-1 text-sm"
								class:font-semibold={win === 'a'}
								class:text-slate-400={m.player_a === '—'}
								class:bg-amber-50={hit(m.player_a) || favA}
							>
								<span class="truncate">
									{#if favA}<span class="mr-0.5 text-amber-500">★</span>{/if}
									{m.player_a}
								</span>
								<span class="ml-2 font-mono text-xs">
									{m.is_played ? m.punts_a : ''}
								</span>
							</div>
							<div
								class="flex items-center justify-between px-2 py-1 text-sm"
								class:font-semibold={win === 'b'}
								class:text-slate-400={m.player_b === '—'}
								class:bg-amber-50={hit(m.player_b) || favB}
							>
								<span class="truncate">
									{#if favB}<span class="mr-0.5 text-amber-500">★</span>{/if}
									{m.player_b}
								</span>
								<span class="ml-2 font-mono text-xs">
									{m.is_played ? m.punts_b : ''}
								</span>
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/each}
	</div>
	{#if koPhases.every((p) => p.ko_matches.length === 0 && p.provisional_matches.length === 0)}
		<p class="mt-2 text-center text-sm text-slate-500 italic">
			El bracket es completarà a mesura que es disputin les partides.
		</p>
	{:else if koPhases.some((p) => p.provisional_matches.length > 0)}
		<p class="mt-3 text-center text-xs text-slate-500 italic">
			Els emparellaments amb etiqueta <span class="rounded bg-slate-200 px-1 text-slate-700">calc</span>
			són projecció interna (reservat #N vs guanyador #{'{'}17−N{'}'}), no publicats encara per la FCB.
		</p>
	{/if}
</div>
