<script lang="ts">
  import { page } from '$app/stores';
  import GameUI from '$lib/components/GameUI.svelte';

  $: routeGameId = decodeURIComponent($page.params.gameId ?? '');
</script>

<GameUI routeGameId={routeGameId} />
