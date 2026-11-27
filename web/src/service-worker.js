/// <reference lib="webworker" />
// Service worker: força que les versions instal·lades (PWA) s'actualitzin.
// La `version` canvia a cada build → nou SW → skipWaiting + claim + neteja
// de caches velles. Network-first per a HTML; cache-first per als assets
// versionats. Les crides a orígens externs (la Data API de Neon) passen sense tocar.

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
	if (url.origin !== self.location.origin) return; // Neon i altres: sense tocar
	// Àudio i vídeo (el traductor, /traductor/fitxer): sense tocar. Safari a
	// l'iPhone els demana a trossos (Range → 206) i, quan passen pel service
	// worker, no els reprodueix; Chrome sí, i per això no es veia a l'ordinador.
	if (
		url.pathname.startsWith('/traductor/fitxer/') ||
		request.headers.has('range') ||
		request.destination === 'audio' ||
		request.destination === 'video'
	)
		return;

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

// Avisos de resultats (fcbillar avisa, des de GitHub Actions). El missatge ja
// porta el text sencer: el telèfon el pot ensenyar sense obrir l'app.
self.addEventListener('push', (event) => {
	let dades = {};
	try {
		dades = event.data ? event.data.json() : {};
	} catch {
		dades = { body: event.data ? event.data.text() : '' };
	}
	const title = dades.title || 'FCBillar';
	event.waitUntil(
		self.registration.showNotification(title, {
			body: dades.body || '',
			// La mateixa etiqueta substitueix l'avís anterior en lloc d'apilar-ne:
			// només la fan servir els resums que es reescriuen.
			tag: dades.tag || undefined,
			icon: '/icon-192.png',
			badge: '/icon-192.png',
			data: { url: dades.url || '/' }
		})
	);
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const desti = new URL(event.notification.data?.url || '/', self.location.origin).href;
	event.waitUntil(
		(async () => {
			const finestres = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
			for (const f of finestres) {
				if ('focus' in f) {
					await f.focus();
					if ('navigate' in f) await f.navigate(desti);
					return;
				}
			}
			await self.clients.openWindow(desti);
		})()
	);
});
