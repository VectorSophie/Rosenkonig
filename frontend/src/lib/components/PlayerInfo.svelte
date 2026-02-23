<script lang="ts">
  export let name: string;
  export let color: 'red' | 'white';
  export let score: number;
  export let heroCards: number;
  export let active = false;
</script>

<div class={['wrap', color, active ? 'active' : ''].join(' ')}>
  <div class="left">
    <div class="badge">{name?.[0] ?? '?'}</div>
    <div>
      <div class="nm">{name}</div>
      <div class="meta muted">Hero: {heroCards}</div>
    </div>
  </div>
  <div class="score">{score}</div>
</div>

<style>
  .wrap {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px;
    border-radius: 14px;
    border: 1px solid var(--stroke);
    background: rgba(0, 0, 0, 0.18);
  }
  .wrap.active {
    box-shadow: inset 0 0 0 1px rgba(242, 193, 78, 0.22);
  }
  .wrap.red {
    border-color: rgba(226, 85, 85, 0.25);
  }
  .wrap.white {
    border-color: rgba(243, 244, 246, 0.18);
  }
  .left {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .badge {
    width: 40px;
    height: 40px;
    border-radius: 14px;
    display: grid;
    place-items: center;
    font-weight: 800;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid var(--stroke);
  }
  .nm {
    font-weight: 800;
  }
  .meta {
    font-size: 12px;
  }
  .score {
    font-weight: 900;
    font-variant-numeric: tabular-nums;
    padding: 6px 10px;
    border-radius: 12px;
    border: 1px solid var(--stroke);
    background: rgba(255, 255, 255, 0.06);
  }
</style>
