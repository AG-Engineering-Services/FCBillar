import adapter from '@sveltejs/adapter-vercel';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter(),
		// Cada 5 minuts mira si hi ha una versió nova desplegada (store `updated`).
		version: { pollInterval: 5 * 60 * 1000 }
	}
};

export default config;
