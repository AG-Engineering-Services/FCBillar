/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			fontFamily: {
				sans: ['ui-sans-serif', 'system-ui', 'sans-serif'],
				mono: ['ui-monospace', 'SFMono-Regular', 'monospace']
			}
		}
	},
	plugins: [require('@tailwindcss/forms')]
};
