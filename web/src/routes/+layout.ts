// Web Analytics de Vercel: quantes visites té cada pàgina. Es va afegir
// l'octubre de 2026 per saber quant consum de Neon és de la web i quant de la
// reingesta. No envia res fins que el projecte no la té activada al panell de
// Vercel, i en desenvolupament només ho escriu a la consola.
import { dev } from '$app/environment';
import { injectAnalytics } from '@vercel/analytics/sveltekit';

injectAnalytics({ mode: dev ? 'development' : 'production' });
