/* Vesteix Tailwind amb els tokens d'AGenginyeria.
 *
 * El marcatge de l'aplicació fa servir les rampes de Tailwind de la manera
 * habitual —`text-emerald-700 dark:text-emerald-400`—, o sigui que la manera de
 * portar tota l'aplicació al sistema de casa d'una tirada és redefinir les
 * rampes, no reescriure 1.600 classes. Dins de cada rampa:
 *
 *   50-200    fons suaus del mode clar
 *   300-400   tinta del mode fosc      (on viuen les variants `dark:`)
 *   500-700   tinta i acció del mode clar
 *   800-950   fons del mode fosc i tintes pregones
 *
 * Els valors surten de `src/lib/styles/ag-tokens.css`, que es copia dels
 * estàndards amb `scripts/sync_tokens_ag.py`. Aquí es repeteixen perquè
 * Tailwind compila a hex i no pot llegir una variable CSS en temps de build;
 * si en canvies cap, canvia'l primer als estàndards.
 *
 * La paleta és més curta que la de Tailwind a posta: quan un pas no existeix a
 * casa nostra s'apunta al més proper que sí que hi és, en comptes d'inventar-ne
 * un de nou. El resultat és una aplicació més silenciosa, que és el que busca
 * el sistema: si no és una acció, no porta accent.
 */

/** Neutres: betum. Cap gris pur — tots amb biaix verd-terrós. */
const bitum = {
	50: '#F4F6F3',
	100: '#E8EBE8',
	200: '#D6DAD6',
	300: '#B8BEB9',
	400: '#939A94',
	500: '#6E756F',
	600: '#4E544F',
	700: '#333833',
	800: '#212523',
	900: '#161917',
	950: '#101211'
};

/** Accent d'acció: família `gestio`. L'únic color d'acció de l'aplicació. */
const accent = {
	50: '#EDF3F8',
	100: '#DEEAF2',
	200: '#AFCDE2',
	300: '#6BA9D6',
	400: '#4A90C4',
	500: '#2E7BB0',
	600: '#1A5C8A',
	700: '#123F61',
	800: '#0D2E48',
	900: '#0B2438',
	950: '#172935'
};

/** Estat «bo». També és el verd de la sèrie 1 dels gràfics. */
const bo = {
	50: '#DCEFE4',
	100: '#DCEFE4',
	200: '#A6DCBE',
	300: '#4FC088',
	400: '#2FA96C',
	500: '#1F9A5F',
	600: '#157A4A',
	700: '#0E5533',
	800: '#0A3F26',
	900: '#0A3F26',
	950: '#12261B'
};

/** Estat «avís». */
const avis = {
	50: '#F7EDD9',
	100: '#F7EDD9',
	200: '#EBD5A6',
	300: '#D2A050',
	400: '#B8811F',
	500: '#C08018',
	600: '#C08018',
	700: '#A16900',
	800: '#7A5000',
	900: '#7A5000',
	950: '#2A2113'
};

/** Estats «greu» i «crític». El vermell de l'escut de la FCB viu a part: és
 *  marca d'identitat, no un estat ni una acció. */
const greu = {
	50: '#F7E4DE',
	100: '#F7E4DE',
	200: '#DFA08E',
	300: '#D86749',
	400: '#CB5C3E',
	500: '#B0432A',
	600: '#B0432A',
	700: '#A81E12',
	800: '#7C1A10',
	900: '#7C1A10',
	950: '#2B1A15'
};

/** Sèrie 5 dels gràfics. Aquí hi cauen els indigos i violetes del marcatge. */
const cat5 = {
	50: '#EFEAF6',
	100: '#E3DBF0',
	200: '#C9BCE0',
	300: '#A98CD0',
	400: '#8F68BE',
	500: '#7A4FA8',
	600: '#7A4FA8',
	700: '#5E3B83',
	800: '#452B60',
	900: '#452B60',
	950: '#1F1630'
};

/** @type {import('tailwindcss').Config} */
export default {
	// Tres estats, com mana el sistema: elecció explícita a `data-theme`, i si no
	// n'hi ha, la del sistema. La classe `dark` la posa el script d'app.html
	// abans del primer pintat perquè no hi hagi flaix.
	darkMode: 'class',
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			fontFamily: {
				// Verdana és la més llegible en pantalla i la que té les xifres més
				// clares. Consolas per a dades, codis i identificadors.
				sans: ['Verdana', 'Tahoma', 'DejaVu Sans', 'Geneva', 'sans-serif'],
				mono: ['Consolas', 'Cascadia Mono', 'DejaVu Sans Mono', 'monospace']
			},
			fontSize: {
				// Verdana és ampla: la base va a 15px i no a 16.
				base: ['0.9375rem', { lineHeight: '1.5' }]
			},
			borderRadius: {
				// Convencions de plànol: cantonades vives. 2px és el màxim.
				none: '0',
				sm: '2px',
				DEFAULT: '2px',
				md: '2px',
				lg: '2px',
				xl: '2px',
				'2xl': '2px',
				'3xl': '2px',
				full: '9999px' // només per a punts i pastilles rodones de debò
			},
			boxShadow: {
				// Cap ombra. Si cal separar plans, un filet.
				none: 'none',
				sm: 'none',
				DEFAULT: 'none',
				md: 'none',
				lg: 'none',
				xl: 'none',
				'2xl': 'none',
				inner: 'none'
			},
			colors: {
				slate: bitum,
				gray: bitum,
				zinc: bitum,
				neutral: bitum,
				stone: bitum,
				sky: accent,
				blue: accent,
				cyan: accent,
				teal: bo,
				emerald: bo,
				green: bo,
				lime: bo,
				amber: avis,
				yellow: avis,
				orange: avis,
				red: greu,
				rose: greu,
				indigo: cat5,
				violet: cat5,
				purple: cat5,
				fuchsia: cat5,
				pink: cat5,
				// Marca d'identitat de la federació. NO és un accent: no es fa
				// servir per a accions, només per al filet de capçalera i el
				// distintiu. L'escut, quan hi sigui, va tal com és.
				fcb: '#E41824'
			}
		}
	},
	plugins: [require('@tailwindcss/forms')]
};
