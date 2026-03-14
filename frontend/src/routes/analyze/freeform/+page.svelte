<script lang="ts">
  import PositionAnalyzer from '$lib/components/PositionAnalyzer.svelte';
</script>

<main class="analyze-shell">
  <header class="top">
    <h1>Position Lab</h1>
    <div class="actions">
      <a class="btn ghost" href="/analyze">Game analysis</a>
      <a class="btn ghost" href="/">Back to game</a>
    </div>
  </header>

  <PositionAnalyzer />
</main>

<style>
  .analyze-shell {
    width: min(1240px, 96vw);
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
    flex-wrap: wrap;
  }

  .actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  h1 {
    margin: 0;
    font-size: clamp(1.2rem, 1rem + 1vw, 1.8rem);
  }
</style>
