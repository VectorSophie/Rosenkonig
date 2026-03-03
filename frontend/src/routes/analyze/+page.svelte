<script lang="ts">
  import { page } from '$app/stores';
  import AnalysisPanel from '$lib/components/AnalysisPanel.svelte';
  import { game } from '$lib/stores/game';

  $: roomId = $page.url.searchParams.get('room');
  $: state = $game.state;
  $: stateHistory = $game.state_history;
</script>

<main class="analyze-shell">
  <header class="top">
    <h1>Game Analysis</h1>
    <a class="btn ghost" href="/">Back to game</a>
  </header>

  {#if roomId}
    <AnalysisPanel roomId={roomId} state={state} stateHistory={stateHistory} />
  {:else}
    <div class="empty">Open analysis from a finished game or use `/analyze/&lt;roomId&gt;`.</div>
  {/if}
</main>

<style>
  .analyze-shell {
    width: min(1200px, 96vw);
    margin: 0 auto;
    padding: 20px 0 28px;
    display: grid;
    gap: 12px;
  }

  .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  h1 {
    margin: 0;
    font-size: clamp(1.2rem, 1rem + 1vw, 1.8rem);
  }

  .empty {
    border: 1px solid var(--stroke);
    border-radius: 12px;
    padding: 14px;
    background: rgba(0, 0, 0, 0.18);
  }
</style>
