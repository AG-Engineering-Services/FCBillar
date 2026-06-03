<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Tooltip,
		Legend
	} from 'chart.js';

	Chart.register(
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Tooltip,
		Legend
	);

	export let labels: string[] = [];
	// series: { label, data:(number|null)[] }[]
	export let series: { label: string; data: (number | null)[] }[] = [];
	export let invertY = false;
	export let integerY = false;
	export let yTitle = '';
	export let height = 320;
	// Si highlight no és null, només es ressalta aquesta sèrie (per label);
	// la resta es dibuixa en gris clar de fons. Simplifica gràfics amb moltes línies.
	export let highlight: string | null = null;

	const PALETTE = [
		'#2563eb', '#dc2626', '#16a34a', '#d97706', '#7c3aed', '#0891b2',
		'#db2777', '#ca8a04', '#65a30d', '#ea580c', '#0ea5e9', '#9333ea'
	];

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	function build() {
		if (!canvas) return;
		if (chart) chart.destroy();
		const hasHighlight = highlight !== null && highlight !== undefined;
		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels,
				datasets: series.map((s, i) => {
					const isHi = hasHighlight && s.label === highlight;
					const dim = hasHighlight && !isHi;
					const color = PALETTE[i % PALETTE.length];
					return {
						label: s.label,
						data: s.data as number[],
						borderColor: dim ? '#e2e8f0' : color,
						backgroundColor: dim ? '#e2e8f0' : color,
						borderWidth: isHi ? 3 : dim ? 1 : 2,
						pointRadius: dim ? 0 : isHi ? 3 : 2,
						tension: 0.25,
						spanGaps: true,
						order: isHi ? 0 : 1
					};
				})
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: { mode: 'nearest', intersect: false },
				plugins: {
					legend: {
						// Amb molts jugadors la llegenda és sorollosa; amaga-la si hi ha
						// ressalt o massa sèries.
						display: !hasHighlight && series.length > 1 && series.length <= 6,
						position: 'bottom',
						labels: { boxWidth: 12, font: { size: 11 } }
					},
					tooltip: {
						// Només la sèrie ressaltada al tooltip quan n'hi ha una.
						filter: (item: any) =>
							!hasHighlight || series[item.datasetIndex]?.label === highlight
					}
				},
				scales: {
					y: {
						reverse: invertY,
						title: { display: !!yTitle, text: yTitle },
						ticks: integerY ? { precision: 0, stepSize: 1 } : {}
					}
				}
			}
		});
	}

	onMount(build);
	onDestroy(() => chart?.destroy());

	// Reconstrueix quan canvien les dades o el ressalt.
	$: labels, series, invertY, highlight, chart && build();
</script>

<div style="height: {height}px">
	<canvas bind:this={canvas}></canvas>
</div>
