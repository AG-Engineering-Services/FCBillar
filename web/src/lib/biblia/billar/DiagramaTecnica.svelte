<script lang="ts">
	/**
	 * Diagrames tècnics d'una tirada, a l'estil de les fitxes de billar:
	 *  - Efecte (당점): on picar la bola jugadora (posició horària + alçada).
	 *  - Quantitat de bola (두께): quina part de la bola objectiu s'ha de tocar.
	 *  - Velocitat (속도): força del cop.
	 */

	interface Props {
		/** Punt de contacte "x|y": x = hora del rellotge (0-12), y = radi (0-3). */
		puntContacte: string;
		/** Quantitat de bola: -8..+8 (0 = bola plena, ±8 = molt fina, signe = costat). */
		gruix: number;
		/** Velocitat / força: normalment 0-5. */
		velocitat: number;
	}

	let { puntContacte, gruix, velocitat }: Props = $props();

	const R_EF = 34;
	const R_GR = 24;
	// Quantitat de bola = 1 − |gruix|/8: gruix 0 = bola plena, gruix 8 = vora.
	const FRACCIONS: Record<number, string> = {
		0: '1/1',
		1: '7/8',
		2: '3/4',
		3: '5/8',
		4: '1/2',
		5: '3/8',
		6: '1/4',
		7: '1/8',
		8: 'vora'
	};
	const punts = [1, 2, 3, 4, 5];

	// --- Efecte (당점): x = hora 0-12, y = radi 0-3 ---
	const parts = $derived(puntContacte.split('|').map(Number));
	const efX = $derived(Number.isFinite(parts[0]) ? parts[0] : 0);
	const efY = $derived(Number.isFinite(parts[1]) ? parts[1] : 0);
	const angle = $derived((efX / 12) * 2 * Math.PI); // 0 = a dalt, sentit horari
	const radi = $derived((efY / 3) * (R_EF - 8));
	// Rellotge estàndard del 당점 (com billiard-bible): 12 a dalt, 3 a la dreta.
	const dotX = $derived(45 + radi * Math.sin(angle));
	const dotY = $derived(45 - radi * Math.cos(angle));

	// Etiqueta de l'efecte: hora del rellotge + descomposició numèrica (0-3).
	function horaText(x: number): string {
		let ent = Math.floor(x + 1e-6);
		const frac = x - ent;
		let fs = '';
		if (Math.abs(frac - 0.5) < 0.08) fs = '½';
		else if (Math.abs(frac - 0.25) < 0.08) fs = '¼';
		else if (Math.abs(frac - 0.75) < 0.08) fs = '¾';
		if (ent === 0) ent = 12;
		return `${ent}${fs} h`;
	}
	const horaTxt = $derived(horaText(efX));
	const hEnglish = $derived(efY * Math.sin(angle)); // + = dreta
	const vEnglish = $derived(efY * Math.cos(angle)); // + = amunt
	const numericTxt = $derived.by(() => {
		if (efY < 0.4) return 'centrat';
		const rh = Math.round(hEnglish);
		const rv = Math.round(vEnglish);
		const pv = rv > 0 ? `${rv} amunt` : rv < 0 ? `${-rv} avall` : '';
		const ph = rh > 0 ? `${rh} dreta` : rh < 0 ? `${-rh} esq.` : '';
		return [pv, ph].filter(Boolean).join(' · ') || 'centrat';
	});

	// Marques de les hores del rellotge.
	const hores = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
	function puntHora(h: number, r: number): [number, number] {
		const a = (h / 12) * 2 * Math.PI;
		return [45 + r * Math.sin(a), 45 - r * Math.cos(a)];
	}
	const numHores = [
		{ t: '12', p: puntHora(0, R_EF - 9) },
		{ t: '3', p: puntHora(3, R_EF - 9) },
		{ t: '6', p: puntHora(6, R_EF - 9) },
		{ t: '9', p: puntHora(9, R_EF - 9) }
	];

	// Fletxa del sentit de rotació (efecte lateral): horari = efecte a la dreta.
	const RA_ROT = R_EF + 4;
	const p10 = puntHora(10, RA_ROT);
	const p2 = puntHora(2, RA_ROT);
	const arcHorari = `M ${p10[0].toFixed(1)} ${p10[1].toFixed(1)} A ${RA_ROT} ${RA_ROT} 0 0 1 ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
	const arcAntihorari = `M ${p2[0].toFixed(1)} ${p2[1].toFixed(1)} A ${RA_ROT} ${RA_ROT} 0 0 0 ${p10[0].toFixed(1)} ${p10[1].toFixed(1)}`;
	const hEng = $derived(radi * Math.sin(angle)); // + = efecte a la dreta
	const mostraRotacio = $derived(Math.abs(hEng) > 3);
	const sentitHorari = $derived(hEng > 0); // dreta → sentit horari

	// --- Quantitat de bola (두께) ---
	const absG = $derived(Math.min(8, Math.abs(gruix)));
	const signe = $derived(gruix > 0 ? 1 : gruix < 0 ? -1 : 0);
	const desplacament = $derived((absG / 8) * 2 * R_GR);
	// Com billiard-bible: gruix>0 → bola objectiu a l'esquerra i jugadora a la
	// dreta (la jugadora cobreix el costat dret de l'objectiu).
	const cueCx = $derived(75 + signe * desplacament);
	const fraccio = $derived(FRACCIONS[absG] ?? `${absG}/8`);
	const costat = $derived(gruix < 0 ? 'esquerra' : gruix > 0 ? 'dreta' : 'centrada');
	const descripcio = $derived(absG === 0 ? 'bola plena' : absG === 8 ? 'molt fina' : `${fraccio} de bola`);
</script>

<div class="diagrames">
	<div class="bloc">
		<svg viewBox="0 0 90 90" role="img" aria-label="Efecte">
			<defs>
				<marker
					id="rot-cap"
					viewBox="0 0 10 10"
					refX="6"
					refY="5"
					markerWidth="4.5"
					markerHeight="4.5"
					orient="auto"
				>
					<path d="M0,0 L10,5 L0,10 z" class="rot-cap" />
				</marker>
			</defs>
			<circle cx="45" cy="45" r={R_EF} class="cara-bola" />
			<line x1={45 - R_EF + 3} y1="45" x2={45 + R_EF - 3} y2="45" class="creu" />
			<line x1="45" y1={45 - R_EF + 3} x2="45" y2={45 + R_EF - 3} class="creu" />
			{#each hores as h (h)}
				{@const a = (h / 12) * 2 * Math.PI}
				<line
					x1={45 + R_EF * Math.sin(a)}
					y1={45 - R_EF * Math.cos(a)}
					x2={45 + (R_EF - 3) * Math.sin(a)}
					y2={45 - (R_EF - 3) * Math.cos(a)}
					class="tick"
				/>
			{/each}
			{#each numHores as n (n.t)}
				<text x={n.p[0]} y={n.p[1]} class="hora">{n.t}</text>
			{/each}
			{#if mostraRotacio}
				<path
					d={sentitHorari ? arcHorari : arcAntihorari}
					class="arc-rot"
					marker-end="url(#rot-cap)"
				/>
			{/if}
			<circle cx="45" cy="45" r="1.6" class="centre" />
			<circle cx={dotX} cy={dotY} r="5.5" class="efecte-punt" />
		</svg>
		<div class="titol">Efecte</div>
		<div class="valor">{horaTxt}</div>
		<div class="subvalor">{numericTxt}</div>
	</div>

	<div class="bloc">
		<svg viewBox="0 0 150 90" role="img" aria-label="Quantitat de bola">
			<!-- bola objectiu -->
			<circle cx="75" cy="45" r={R_GR} class="bola-obj" />
			<!-- bola jugadora, desplaçada segons el gruix -->
			<circle cx={cueCx} cy="45" r={R_GR} class="bola-jug" />
		</svg>
		<div class="titol">Quantitat de bola</div>
		<div class="valor">{descripcio}{signe !== 0 ? ` · ${costat}` : ''}</div>
	</div>

	<div class="bloc">
		<div class="velocimetre">
			{#each punts as n (n)}
				<span class="punt" class:ple={n <= velocitat}></span>
			{/each}
		</div>
		<div class="titol">Velocitat</div>
		<div class="valor">{velocitat} / 5</div>
	</div>
</div>

<style>
	.diagrames {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.6rem;
		margin-top: 0.9rem;
	}
	.bloc {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		padding: 0.6rem 0.4rem;
		background: var(--fons-3);
		border-radius: 8px;
	}
	.bloc svg {
		width: 100%;
		max-width: 130px;
		height: auto;
	}
	.titol {
		font-size: 0.72rem;
		color: var(--text-suau);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.valor {
		font-size: 0.82rem;
		font-weight: 600;
		text-align: center;
	}
	.subvalor {
		font-size: 0.72rem;
		color: var(--text-suau);
		text-align: center;
	}

	.cara-bola {
		fill: #f3efe6;
		stroke: #14110c;
		stroke-width: 1.4;
	}
	.creu {
		stroke: #c4bcac;
		stroke-width: 0.7;
		stroke-dasharray: 2 2;
	}
	.centre {
		fill: #b9b0a0;
	}
	.tick {
		stroke: #8a8172;
		stroke-width: 0.8;
	}
	.hora {
		fill: #6f675a;
		font-size: 6px;
		font-family: system-ui, sans-serif;
		text-anchor: middle;
		dominant-baseline: middle;
	}
	.arc-rot {
		fill: none;
		stroke: #2563a8;
		stroke-width: 1.7;
	}
	.rot-cap {
		fill: #2563a8;
	}
	.efecte-punt {
		fill: #16233a;
		stroke: #ffffff;
		stroke-width: 1.2;
	}

	.bola-obj {
		fill: #e10000;
		stroke: #14110c;
		stroke-width: 1.4;
	}
	.bola-jug {
		fill: #f5f5f5;
		fill-opacity: 0.82;
		stroke: #14110c;
		stroke-width: 1.4;
	}

	.velocimetre {
		display: flex;
		gap: 0.28rem;
		height: 74px;
		align-items: center;
		justify-content: center;
	}
	.punt {
		width: 0.7rem;
		height: 0.7rem;
		border-radius: 50%;
		background: var(--fons);
		border: 1px solid var(--vora);
	}
	.punt.ple {
		background: var(--accent);
		border-color: var(--accent);
	}
</style>
