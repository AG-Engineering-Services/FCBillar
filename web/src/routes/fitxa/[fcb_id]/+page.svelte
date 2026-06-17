<script lang="ts">
	import { page } from '$app/stores';
	import PlayerProfile from '$lib/components/PlayerProfile.svelte';
</script>

<!-- Vista aïllada de la fitxa: sense navbar (vegeu +layout.svelte) ni botons/enllaços
     que surtin a la resta de la PWA. /fitxa/716 (Ricardo García), /fitxa/995 (F. Segura). -->
<PlayerProfile fcbId={$page.params.fcb_id!} kiosk />
