<script lang="ts">
	// Botó "← Enrere". Si hi ha història de navegació torna enrere; si no
	// (p.ex. s'ha obert l'enllaç directament), navega a un fallback.
	export let fallback = '/';

	function back() {
		if (typeof history !== 'undefined' && history.length > 1) {
			history.back();
		} else {
			location.href = fallback;
		}
	}
</script>

<button
	type="button"
	class="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800 mb-3"
	on:click={back}
>
	<span aria-hidden="true">←</span> Enrere
</button>
