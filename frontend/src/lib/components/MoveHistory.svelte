<script lang="ts">
  type MoveLine = {
    player: 'red' | 'white';
    label: string;
    use_hero: boolean;
  };

  export let moves: MoveLine[] = [];
</script>

<div class="hist">
  {#if moves.length === 0}
    <div class="muted">No moves yet.</div>
  {:else}
    {#each moves as move, i}
      <div class={['line', i % 2 === 0 ? 'even' : ''].join(' ')}>
        <span class="idx">{i + 1}.</span>
        <span class="txt">{move.label}</span>
        {#if move.use_hero}
          <span class="chip">Hero</span>
        {/if}
      </div>
    {/each}
  {/if}
</div>

<style>
  .hist {
    display: grid;
    gap: 6px;
  }
  .line {
    display: grid;
    grid-template-columns: 32px 1fr auto;
    gap: 10px;
    align-items: center;
    padding: 8px 10px;
    border-radius: 12px;
    border: 1px solid var(--stroke);
    background: rgba(0, 0, 0, 0.18);
  }
  .line.even {
    background: rgba(0, 0, 0, 0.25);
  }
  .idx {
    color: rgba(234, 240, 255, 0.55);
    font-variant-numeric: tabular-nums;
  }
  .txt {
    color: rgba(234, 240, 255, 0.92);
  }
  .chip {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid rgba(242, 193, 78, 0.35);
    background: rgba(242, 193, 78, 0.10);
  }
</style>
