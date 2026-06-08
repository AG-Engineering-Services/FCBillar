/// <reference lib="webworker" />
// Service worker: força que les versions instal·lades (PWA) s'actualitzin.
// La `version` canvia a cada build → nou SW → skipWaiting + claim + neteja
// de caches velles. Network-first per a HTML; cache-first per als assets
// versionats. Les crides a orígens externs (Supabase) passen sense tocar.

import { build, files, version } from '$service-worker';

const CACHE = `fcbillar-${version}`;
const ASSETS = [...build, ...files];

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE)
			.then((cache) => cache.addAll(ASSETS))
			.then(() => self.skipWaiting())
	);
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		(async () => {
			for (const key of await caches.keys()) {
				if (key !== CACHE) await caches.delete(key);
			}
			await self.clients.claim();
		})()
	);
});

self.addEventListener('fetch', (event) => {
	const { request } = event;
	if (request.method !== 'GET') return;
	const url = new URL(request.url);
	if (url.origin !== self.location.origin) return; // Supabase i altres: sense tocar

	event.respondWith(
		(async () => {
			const cache = await caches.open(CACHE);
			// Assets versionats: cache-first.
			if (ASSETS.includes(url.pathname)) {
				const cached = await cache.match(request);
				if (cached) return cached;
			}
			// Resta (HTML, etc.): network-first amb fallback a cache si offline.
			try {
				return await fetch(request);
			} catch {
				const cached = await cache.match(request);
				if (cached) return cached;
				throw new Error('offline i sense cache');
			}
		})()
	);
});
