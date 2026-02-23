<script lang="ts">
  import { createEventDispatcher, onDestroy, onMount } from 'svelte';
  import type { LegalMove } from '$lib/stores/game';

  export let board: number[][] = [];
  export let crownPos: [number, number] = [5, 5];
  export let previewPos: [number, number] | null = null;
  export let legalMoves: LegalMove[] = [];
  export let selectedCardIndex: number | null = null;
  export let selectedUseHero = false;
  export let interactive = true;

  const dispatch = createEventDispatcher<{ cellclick: { row: number; col: number } }>();

  let rootEl: HTMLDivElement | null = null;
  let cellPx = 48;
  let resizeObs: ResizeObserver | null = null;

  function measure() {
    if (!rootEl) return;
    const w = rootEl.clientWidth;
    cellPx = Math.max(18, Math.floor(w / 11));
  }

  onMount(() => {
    measure();
    if (rootEl && typeof ResizeObserver !== 'undefined') {
      resizeObs = new ResizeObserver(() => measure());
      resizeObs.observe(rootEl);
    }
  });

  onDestroy(() => {
    resizeObs?.disconnect();
  });

  function keyOf(r: number, c: number) {
    return `${r},${c}`;
  }

  $: selectedMove =
    selectedCardIndex === null
      ? null
      : legalMoves.find((m) => m.card_index === selectedCardIndex && m.use_hero === selectedUseHero) ?? null;

  $: allTargets = new Map<string, LegalMove>();
  $: {
    allTargets.clear();
    for (const m of legalMoves) {
      allTargets.set(keyOf(m.target[0], m.target[1]) + `|${m.card_index}|${m.use_hero ? 1 : 0}`, m);
    }
  }

  $: selectedTargetKey = selectedMove ? keyOf(selectedMove.target[0], selectedMove.target[1]) : null;

  function isSelectableTarget(r: number, c: number) {
    if (!selectedMove) return false;
    return selectedMove.target[0] === r && selectedMove.target[1] === c;
  }

  function isAnyLegalTarget(r: number, c: number) {
    for (const m of legalMoves) {
      if (m.target[0] === r && m.target[1] === c) return true;
    }
    return false;
  }

  function onCellClick(row: number, col: number) {
    if (!interactive) return;
    dispatch('cellclick', { row, col });
  }

  $: crownStyle = `--crown-x:${(crownPos?.[1] ?? 5) * cellPx}px;--crown-y:${(crownPos?.[0] ?? 5) * cellPx}px;`;
</script>

<div class="board-wrap" bind:this={rootEl}>
  <div class="board" style={`--cell:${cellPx}px`}>
    {#each Array(11) as _, r}
      {#each Array(11) as __, c}
        {@const v = board?.[r]?.[c] ?? 0}
        {@const dark = (r + c) % 2 === 1}
        {@const isCrown = crownPos?.[0] === r && crownPos?.[1] === c}
        {@const isPreview = !isCrown && previewPos?.[0] === r && previewPos?.[1] === c}
        {@const anyLegal = isAnyLegalTarget(r, c)}
        {@const selected = selectedTargetKey === keyOf(r, c)}
        {@const selectable = isSelectableTarget(r, c)}

        <button
          type="button"
          class={['cell', dark ? 'dark' : 'light', anyLegal ? 'legal' : '', selected ? 'selected' : '', selectable ? 'selectable' : ''].join(' ')}
          on:click={() => onCellClick(r, c)}
          aria-label={`cell ${r},${c}`}
        >
          {#if v === 1}
            <div class="piece red" />
          {:else if v === 2}
            <div class="piece white" />
          {/if}

          {#if anyLegal}
            <div class="dot" />
          {/if}

          {#if isPreview}
            <div class="king preview" aria-hidden="true">
              <img src="/assets/crown.png" alt="" class="crown-icon" draggable="false" />
            </div>
          {/if}
        </button>
      {/each}
    {/each}

    <div class="crown-layer" style={crownStyle} aria-hidden="true">
      <div class="king live">
        <img src="/assets/crown.png" alt="" class="crown-icon" draggable="false" />
      </div>
    </div>
  </div>
</div>

<style>
  .board-wrap {
    width: min(86vmin, 720px);
    margin: 0 auto;
  }

  .board {
    position: relative;
    display: grid;
    grid-template-columns: repeat(11, var(--cell));
    grid-template-rows: repeat(11, var(--cell));
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid var(--board-border);
    box-shadow: var(--shadow);
  }

  .cell {
    position: relative;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    outline: none;
    display: grid;
    place-items: center;
  }

  .cell.light {
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.06), transparent), var(--board-light);
  }

  .cell.dark {
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), transparent), var(--board-dark);
  }

  .cell.legal {
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14);
  }

  .cell.selected {
    box-shadow:
      inset 0 0 0 2px rgba(242, 193, 78, 0.85),
      inset 0 0 0 1px rgba(0, 0, 0, 0.25);
  }

  .cell.selectable:hover {
    filter: saturate(1.05) brightness(1.04);
  }

  .piece {
    width: calc(var(--cell) * 0.62);
    height: calc(var(--cell) * 0.62);
    border-radius: 999px;
    position: relative;
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    box-shadow:
      0 10px 18px rgba(0, 0, 0, 0.32),
      inset 0 0 0 1px rgba(255, 255, 255, 0.22);
    overflow: hidden;
  }

  .piece.red {
    background-image: url('/assets/red.png');
  }

  .piece.white {
    background-image: url('/assets/white.png');
  }

  .king {
    position: absolute;
    width: calc(var(--cell) * 0.70);
    height: calc(var(--cell) * 0.70);
    border-radius: 14px;
    display: grid;
    place-items: center;
    background: linear-gradient(180deg, rgba(242, 193, 78, 0.22), rgba(242, 193, 78, 0.08));
    border: 1px solid rgba(242, 193, 78, 0.45);
    box-shadow:
      0 12px 22px rgba(0, 0, 0, 0.32),
      0 0 0 2px rgba(242, 193, 78, 0.12);
    color: rgba(255, 255, 255, 0.95);
  }

  .crown-layer {
    position: absolute;
    left: 0;
    top: 0;
    width: var(--cell);
    height: var(--cell);
    display: grid;
    place-items: center;
    transform: translate(var(--crown-x), var(--crown-y));
    transition: transform 340ms cubic-bezier(0.22, 0.9, 0.3, 1);
    pointer-events: none;
    z-index: 4;
  }

  .king.live {
    width: calc(var(--cell) * 0.72);
    height: calc(var(--cell) * 0.72);
    overflow: hidden;
  }

  .crown-icon {
    width: 100%;
    height: 100%;
    object-fit: contain;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.28));
    pointer-events: none;
  }

  .king.preview {
    opacity: 0.58;
    background: linear-gradient(180deg, rgba(242, 193, 78, 0.14), rgba(242, 193, 78, 0.04));
    border-style: dashed;
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
  }

  .dot {
    position: absolute;
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.38);
    box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.16);
  }

  @media (max-width: 700px) {
    .board-wrap {
      width: min(92vmin, 560px);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .crown-layer {
      transition: none;
    }
  }
</style>
