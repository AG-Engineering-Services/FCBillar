<script lang="ts">
	/**
	 * Reproductor de YouTube (IFrame Player API) que emet el fotograma de
	 * l'animació segons el temps del vídeo: fotograma = (temps − inici) × fps.
	 * Així la taula es pot sincronitzar amb el clip real.
	 *
	 * Nota: només funciona en navegadors que reprodueixen YouTube (Chrome/Edge);
	 * al navegador de VS Code o DuckDuckGo el vídeo queda bloquejat.
	 */
	import { onMount } from 'svelte';

	interface Props {
		videoId: string;
		inici: number;
		fi?: number | null;
		maxFrame: number;
		fps?: number;
		/** Cert mentre el vídeo s'està reproduint (per reflectir-ho al control). */
		reproduint?: boolean;
		/** Opcional: emet el fotograma actual segons el temps del vídeo. */
		onframe?: (f: number | null) => void;
	}

	let {
		videoId,
		inici,
		fi = null,
		maxFrame,
		fps = 30,
		reproduint = $bindable(false),
		onframe
	}: Props = $props();

	// fps de sincronització: l'animació omple el clip (fotograma 0 a `inici`, últim
	// a `fi`), que és el mínim avançament possible amb el vídeo mestre.
	const fpsUsat = $derived(
		fi != null && fi > inici && maxFrame > 0 ? maxFrame / (fi - inici) : fps
	);

	let el: HTMLDivElement;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	let player: any = null;
	let raf = 0;

	// Controls imperatius perquè l'animació i el vídeo vagin junts i sincronitzats.
	export function reprodueix() {
		try {
			player?.playVideo?.();
		} catch {
			/* el reproductor encara no és a punt */
		}
	}
	export function pausa() {
		try {
			player?.pauseVideo?.();
		} catch {
			/* ignora */
		}
	}
	export function reinicia() {
		try {
			player?.seekTo?.(inici, true);
			player?.playVideo?.();
		} catch {
			/* ignora */
		}
	}
	export function vesA(frame: number) {
		try {
			player?.seekTo?.(inici + frame / fpsUsat, true);
		} catch {
			/* ignora */
		}
	}

	function actualitza() {
		if (!player?.getCurrentTime || !onframe) return;
		const t = player.getCurrentTime() as number;
		onframe(Math.max(0, Math.min(maxFrame, (t - inici) * fpsUsat)));
	}
	function bucle() {
		actualitza();
		raf = requestAnimationFrame(bucle);
	}

	onMount(() => {
		let destruit = false;
		const w = window as unknown as {
			YT?: { Player: new (...a: unknown[]) => unknown; PlayerState: { PLAYING: number } };
			onYouTubeIframeAPIReady?: () => void;
		};

		function crea() {
			if (destruit || !el || !w.YT) return;
			const YT = w.YT;
			player = new YT.Player(el, {
				videoId,
				host: 'https://www.youtube-nocookie.com',
				playerVars: { start: inici, ...(fi ? { end: fi } : {}), rel: 0, playsinline: 1 },
				events: {
					onStateChange: (e: { data: number }) => {
						if (e.data === YT.PlayerState.PLAYING) {
							reproduint = true;
							cancelAnimationFrame(raf);
							bucle();
						} else {
							reproduint = false;
							cancelAnimationFrame(raf);
							actualitza(); // congela al fotograma actual
						}
					}
				}
			});
		}

		if (w.YT?.Player) {
			crea();
		} else {
			const anterior = w.onYouTubeIframeAPIReady;
			w.onYouTubeIframeAPIReady = () => {
				anterior?.();
				crea();
			};
			if (!document.querySelector('script[src*="iframe_api"]')) {
				const s = document.createElement('script');
				s.src = 'https://www.youtube.com/iframe_api';
				document.head.appendChild(s);
			}
		}

		return () => {
			destruit = true;
			cancelAnimationFrame(raf);
			try {
				(player as { destroy?: () => void } | null)?.destroy?.();
			} catch {
				// ignora
			}
			onframe?.(null);
		};
	});
</script>

<div class="video">
	<div bind:this={el}></div>
</div>

<style>
	.video {
		position: relative;
		width: 100%;
		aspect-ratio: 16 / 9;
		border-radius: var(--radi);
		overflow: hidden;
		background: #000;
		border: 1px solid var(--vora);
	}
	.video :global(iframe) {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		border: 0;
	}
</style>
