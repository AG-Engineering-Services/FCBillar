// Avisos de resultats. El servidor (`fcbillar avisa`, a GitHub Actions) envia
// a cada subscripció només els tipus que hi té marcats; aquests identificadors
// han de coincidir amb els de src/fcbillar/avisos.py.
export const TIPUS_AVIS = [
	{
		id: 'opens_3b',
		nom: 'Opens de 3 bandes',
		detall: 'Totes les partides acabades, agrupades cada pocs minuts.'
	},
	{
		id: 'banyoles_lliga',
		nom: 'Banyoles: lliga',
		detall: "El resultat de cada encontre d'un equip del Banyoles."
	},
	{
		id: 'banyoles_opens',
		nom: 'Banyoles: opens',
		detall: 'Partides de jugadors del Banyoles a opens de qualsevol modalitat.'
	},
	{
		id: 'banyoles_copa_camp',
		nom: 'Banyoles: Copa i Camp. de Catalunya',
		detall: 'Resultats del Banyoles i dels seus jugadors en aquestes competicions.'
	}
] as const;

export type TipusAvis = (typeof TIPUS_AVIS)[number]['id'];

// Clau pública VAPID: no és secreta, viatja al navegador per definició. La
// privada és el secret VAPID_PRIVATE_KEY del repositori.
export const VAPID_PUBLIC_KEY =
	'BNxq5HpCkKQk9zOLK4jLniUgUAxTZeeMGziwX4a3pzJXGLnUJRuSfvakDKXTpP5GICtA-7c6yf9zPvG3xRJFIRA';

export function base64UrlABytes(b64: string): Uint8Array<ArrayBuffer> {
	const pad = '='.repeat((4 - (b64.length % 4)) % 4);
	const bin = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
	const bytes = new Uint8Array(new ArrayBuffer(bin.length));
	for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
	return bytes;
}
