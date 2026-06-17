<script lang="ts">
	import { page } from '$app/stores';
	import PlayerProfile from '$lib/components/PlayerProfile.svelte';
</script>

<PlayerProfile fcbId={$page.params.fcb_id!} />
