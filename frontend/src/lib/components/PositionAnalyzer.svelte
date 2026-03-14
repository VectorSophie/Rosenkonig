<script lang="ts">
  import { onMount } from 'svelte';
  import Board from '$lib/components/Board.svelte';

  type Card = { direction: string; distance: number };

  type EngineConfig = {
    search_depth: number;
    num_determinizations: number;
    time_limit_seconds: number | null;
    max_nodes: number | null;
    use_transposition_table: boolean;
    use_quiescence: boolean;
    random_seed: number;
    eval_weights: Record<string, number>;
    risk_profile: 'balanced' | 'aggressive' | 'defensive';
    assume_known_opponent_hand: boolean;
  };

  type MoveExplanation = {
    summary: string;
    key_factors: string[];
    principal_variation: Array<{ action: string; card_index: number | null; use_hero: boolean }>;
    risk_level: 'low' | 'medium' | 'high';
    robustness_score: number;
  };

  type BestMoveResponse = {
    best_move: { action: string; card_index: number | null; use_hero: boolean } | null;
    expected_score: number;
    principal_variation: Array<{ action: string; card_index: number | null; use_hero: boolean }>;
    move_evaluations: Record<string, number>;
    move_classifications: Record<string, string>;
    move_explanations: Record<string, MoveExplanation>;
    diagnostics: Record<string, unknown>;
  };

  type ShareState = {
    board: number[][];
    crownPos: [number, number];
    currentTurn: Turn;
    redHeroCards: number;
    whiteHeroCards: number;
    redStonesRemaining: number;
    whiteStonesRemaining: number;
    myCardsInput: string;
    opponentCardsInput: string;
    opponentUnknownHandSize: number;
    assumeKnownOpponentHand: boolean;
    cycleCellMode: boolean;
    config: EngineConfig;
  };

  type Turn = 'red' | 'white';
  type Tool = 'red' | 'white' | 'erase' | 'crown';

  const BACKEND_HTTP = import.meta.env.VITE_BACKEND_HTTP ?? 'http://localhost:8000';
  const DIRECTIONS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

  let board = Array.from({ length: 11 }, () => Array.from({ length: 11 }, () => 0));
  let crownPos: [number, number] = [5, 5];
  let currentTurn: Turn = 'red';
  let tool: Tool = 'red';

  let redHeroCards = 4;
  let whiteHeroCards = 4;
  let redStonesRemaining = 26;
  let whiteStonesRemaining = 26;
  let cycleCellMode = true;

  let myCardsInput = 'N1, E1, SE2, S3, W2';
  let opponentCardsInput = '';
  let opponentUnknownHandSize = 5;
  let assumeKnownOpponentHand = true;

  let config: EngineConfig = {
    search_depth: 5,
    num_determinizations: 20,
    time_limit_seconds: 1.8,
    max_nodes: 50000,
    use_transposition_table: true,
    use_quiescence: true,
    random_seed: 7,
    eval_weights: {
      region_score: 1.0,
      mobility: 0.4,
      expansion_potential: 0.6,
      crown_centrality: 0.2,
      hero_threat_discount: 0.5,
      stone_scarcity_pressure: 0.5
    },
    risk_profile: 'balanced',
    assume_known_opponent_hand: false
  };

  let loading = false;
  let error = '';
  let result: BestMoveResponse | null = null;
  let shareStatus = '';

  $: myColor = currentTurn;
  $: opponentColor = currentTurn === 'red' ? 'white' : 'red';

  function updateCell(row: number, col: number, value: number) {
    board = board.map((line, r) => (r === row ? line.map((cell, c) => (c === col ? value : cell)) : line));
  }

  function onBoardClick(event: CustomEvent<{ row: number; col: number }>) {
    const { row, col } = event.detail;
    if (tool === 'crown') {
      crownPos = [row, col];
      return;
    }
    if (cycleCellMode) {
      const current = board?.[row]?.[col] ?? 0;
      const next = (current + 1) % 3;
      updateCell(row, col, next);
      return;
    }
    if (tool === 'erase') {
      updateCell(row, col, 0);
      return;
    }
    updateCell(row, col, tool === 'red' ? 1 : 2);
  }

  function encodeState(data: ShareState): string {
    const json = JSON.stringify(data);
    const bytes = new TextEncoder().encode(json);
    let binary = '';
    for (const b of bytes) {
      binary += String.fromCharCode(b);
    }
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  }

  function decodeState(raw: string): ShareState {
    const padded = raw + '='.repeat((4 - (raw.length % 4 || 4)) % 4);
    const binary = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    const json = new TextDecoder().decode(bytes);
    return JSON.parse(json) as ShareState;
  }

  function isTurn(value: string): value is Turn {
    return value === 'red' || value === 'white';
  }

  function normalizeBoard(raw: number[][]): number[][] {
    const fallback = Array.from({ length: 11 }, () => Array.from({ length: 11 }, () => 0));
    if (!Array.isArray(raw) || raw.length !== 11) return fallback;
    const normalized = raw.map((row) => {
      if (!Array.isArray(row) || row.length !== 11) return Array.from({ length: 11 }, () => 0);
      return row.map((cell) => (cell === 1 ? 1 : cell === 2 ? 2 : 0));
    });
    if (normalized.length !== 11) return fallback;
    return normalized;
  }

  function captureState(): ShareState {
    return {
      board,
      crownPos,
      currentTurn,
      redHeroCards,
      whiteHeroCards,
      redStonesRemaining,
      whiteStonesRemaining,
      myCardsInput,
      opponentCardsInput,
      opponentUnknownHandSize,
      assumeKnownOpponentHand,
      cycleCellMode,
      config
    };
  }

  function applyState(state: ShareState) {
    board = normalizeBoard(state.board);
    crownPos = [clamp(state.crownPos?.[0] ?? 5, 0, 10), clamp(state.crownPos?.[1] ?? 5, 0, 10)];
    currentTurn = isTurn(state.currentTurn) ? state.currentTurn : 'red';
    redHeroCards = clamp(Number(state.redHeroCards ?? 4), 0, 8);
    whiteHeroCards = clamp(Number(state.whiteHeroCards ?? 4), 0, 8);
    redStonesRemaining = clamp(Number(state.redStonesRemaining ?? 26), 0, 26);
    whiteStonesRemaining = clamp(Number(state.whiteStonesRemaining ?? 26), 0, 26);
    myCardsInput = String(state.myCardsInput ?? '');
    opponentCardsInput = String(state.opponentCardsInput ?? '');
    opponentUnknownHandSize = clamp(Number(state.opponentUnknownHandSize ?? 5), 0, 8);
    assumeKnownOpponentHand = Boolean(state.assumeKnownOpponentHand);
    cycleCellMode = Boolean(state.cycleCellMode);

    config = {
      ...config,
      ...state.config,
      search_depth: clamp(Number(state.config?.search_depth ?? config.search_depth), 1, 8),
      num_determinizations: clamp(Number(state.config?.num_determinizations ?? config.num_determinizations), 1, 200),
      time_limit_seconds:
        state.config?.time_limit_seconds === null
          ? null
          : Number(state.config?.time_limit_seconds ?? config.time_limit_seconds ?? 1.8),
      max_nodes:
        state.config?.max_nodes === null
          ? null
          : clamp(Number(state.config?.max_nodes ?? config.max_nodes ?? 50000), 100, 2_000_000),
      risk_profile:
        state.config?.risk_profile === 'aggressive' || state.config?.risk_profile === 'defensive'
          ? state.config.risk_profile
          : 'balanced',
      assume_known_opponent_hand: Boolean(state.config?.assume_known_opponent_hand),
      eval_weights: {
        ...config.eval_weights,
        ...(state.config?.eval_weights ?? {})
      }
    };
  }

  function buildShareUrl(): string {
    const encoded = encodeState(captureState());
    const url = new URL(window.location.href);
    url.searchParams.set('state', encoded);
    return url.toString();
  }

  function updateUrlWithCurrentState() {
    const url = buildShareUrl();
    window.history.replaceState({}, '', url);
    shareStatus = 'URL updated with current position.';
  }

  async function copyShareLink() {
    try {
      const url = buildShareUrl();
      await navigator.clipboard.writeText(url);
      shareStatus = 'Share link copied.';
    } catch {
      shareStatus = 'Could not copy automatically. Use Update URL and copy from address bar.';
    }
  }

  function loadStateFromUrl() {
    const raw = new URL(window.location.href).searchParams.get('state');
    if (!raw) {
      shareStatus = 'No shared state found in URL.';
      return;
    }
    try {
      const decoded = decodeState(raw);
      applyState(decoded);
      shareStatus = 'Loaded state from URL.';
    } catch {
      shareStatus = 'Invalid shared state in URL.';
    }
  }

  function parseCards(raw: string): Card[] {
    const tokens = raw
      .split(/[\s,;]+/)
      .map((token) => token.trim().toUpperCase())
      .filter(Boolean);

    const parsed: Card[] = [];
    for (const token of tokens) {
      const match = token.match(/^(N|NE|E|SE|S|SW|W|NW)([123])$/);
      if (!match) {
        throw new Error(`Invalid card token: ${token}. Use format like N1, SE2, W3.`);
      }
      parsed.push({ direction: match[1], distance: Number(match[2]) });
    }
    return parsed;
  }

  function notation(move: { action: string; card_index: number | null; use_hero: boolean }, hand: Card[]): string {
    if (move.action === 'draw') return 'Draw';
    if (move.action === 'pass') return 'Pass';
    const idx = move.card_index ?? -1;
    const card = idx >= 0 && idx < hand.length ? `${hand[idx].direction}${hand[idx].distance}` : `C${idx + 1}`;
    return `${move.use_hero ? 'H-' : ''}${card}`;
  }

  function clamp(v: number, lo: number, hi: number): number {
    return Math.max(lo, Math.min(hi, v));
  }

  function countCells(value: number): number {
    let count = 0;
    for (const row of board) {
      for (const cell of row) {
        if (cell === value) count += 1;
      }
    }
    return count;
  }

  function autoFillStonesRemaining() {
    redStonesRemaining = clamp(26 - countCells(1), 0, 26);
    whiteStonesRemaining = clamp(26 - countCells(2), 0, 26);
  }

  function resetPosition() {
    board = Array.from({ length: 11 }, () => Array.from({ length: 11 }, () => 0));
    crownPos = [5, 5];
    redHeroCards = 4;
    whiteHeroCards = 4;
    redStonesRemaining = 26;
    whiteStonesRemaining = 26;
    cycleCellMode = true;
    result = null;
    error = '';
    shareStatus = '';
  }

  function makeUnknownOpponentCards(size: number): Card[] {
    const cards: Card[] = [];
    const clamped = clamp(size, 0, 8);
    for (let i = 0; i < clamped; i += 1) {
      cards.push({ direction: DIRECTIONS[i % DIRECTIONS.length], distance: (i % 3) + 1 });
    }
    return cards;
  }

  async function analyze() {
    loading = true;
    error = '';
    result = null;

    try {
      const myCards = parseCards(myCardsInput);
      const opponentCards = opponentCardsInput.trim().length > 0 ? parseCards(opponentCardsInput) : [];
      const useKnownOpponent = opponentCards.length > 0 && assumeKnownOpponentHand;
      const syntheticOpponentCards = opponentCards.length > 0 ? opponentCards : makeUnknownOpponentCards(opponentUnknownHandSize);

      const redCards = myColor === 'red' ? myCards : syntheticOpponentCards;
      const whiteCards = myColor === 'white' ? myCards : syntheticOpponentCards;

      const payload = {
        state: {
          grid: board,
          king_position: [crownPos[0], crownPos[1]],
          players: {
            red: {
              power_cards: redCards,
              hero_cards: clamp(redHeroCards, 0, 8),
              stones_remaining: clamp(redStonesRemaining, 0, 26)
            },
            white: {
              power_cards: whiteCards,
              hero_cards: clamp(whiteHeroCards, 0, 8),
              stones_remaining: clamp(whiteStonesRemaining, 0, 26)
            }
          },
          current_player: currentTurn,
          draw_pile: [],
          discard_pile: [],
          consecutive_passes: 0,
          history: [],
          move_history: [],
          game_over: false
        },
        config: {
          ...config,
          assume_known_opponent_hand: useKnownOpponent
        }
      };

      const res = await fetch(`${BACKEND_HTTP}/best-move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        error = await res.text();
        return;
      }

      result = (await res.json()) as BestMoveResponse;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  $: myCardsParsed = (() => {
    try {
      return parseCards(myCardsInput);
    } catch {
      return [] as Card[];
    }
  })();

  $: bestMoveKey =
    result?.best_move
      ? `${result.best_move.action}:${result.best_move.card_index}:${result.best_move.use_hero ? 1 : 0}`
      : null;
  $: bestExplanation = bestMoveKey ? result?.move_explanations?.[bestMoveKey] ?? null : null;

  onMount(() => {
    loadStateFromUrl();
  });
</script>

<section class="freeform-wrap">
  <div class="top">
    <h2>Free-Form Position Analyzer</h2>
    <div class="tools-row">
      <button class="btn ghost" on:click={autoFillStonesRemaining}>Auto stones from board</button>
      <button class="btn ghost" on:click={copyShareLink}>Copy share link</button>
      <button class="btn ghost" on:click={updateUrlWithCurrentState}>Update URL</button>
      <button class="btn ghost" on:click={loadStateFromUrl}>Load URL</button>
      <button class="btn ghost" on:click={resetPosition}>Reset</button>
      <button class="btn" on:click={analyze} disabled={loading}>{loading ? 'Analyzing...' : 'Recommend Move'}</button>
    </div>
  </div>
  {#if shareStatus}
    <div class="muted tiny">{shareStatus}</div>
  {/if}

  <div class="grid">
    <div class="panel board-panel">
      <Board
        board={board}
        crownPos={crownPos}
        previewPos={null}
        legalMoves={[]}
        highlightedSquares={[]}
        selectedCardIndex={null}
        selectedUseHero={false}
        interactive={true}
        on:cellclick={onBoardClick}
      />
      <div class="muted tiny">{cycleCellMode ? 'Cycle mode: empty -> red -> white per click.' : 'Tool mode: use selected tool for each click.'}</div>

      <label class="row compact">
        <input type="checkbox" bind:checked={cycleCellMode} disabled={tool === 'crown'} />
        <span>Click-to-cycle cells</span>
      </label>

      <div class="tool-grid">
        <button class={['tool', tool === 'red' ? 'active red' : ''].join(' ')} on:click={() => (tool = 'red')}>Red stone</button>
        <button class={['tool', tool === 'white' ? 'active white' : ''].join(' ')} on:click={() => (tool = 'white')}>White stone</button>
        <button class={['tool', tool === 'erase' ? 'active' : ''].join(' ')} on:click={() => (tool = 'erase')}>Erase</button>
        <button class={['tool', tool === 'crown' ? 'active crown' : ''].join(' ')} on:click={() => (tool = 'crown')}>Move crown</button>
      </div>
    </div>

    <div class="panel form-panel">
      <div class="section">
        <label>
          Side to move
          <select bind:value={currentTurn}>
            <option value="red">Red</option>
            <option value="white">White</option>
          </select>
        </label>
      </div>

      <div class="section two-col">
        <label>
          Red hero
          <input type="number" min="0" max="8" bind:value={redHeroCards} />
        </label>
        <label>
          White hero
          <input type="number" min="0" max="8" bind:value={whiteHeroCards} />
        </label>
        <label>
          Red stones left
          <input type="number" min="0" max="26" bind:value={redStonesRemaining} />
        </label>
        <label>
          White stones left
          <input type="number" min="0" max="26" bind:value={whiteStonesRemaining} />
        </label>
      </div>

      <div class="section">
        <label>
          Your cards ({myColor})
          <input bind:value={myCardsInput} placeholder="N1, E2, SW3" />
        </label>
      </div>

      <div class="section">
        <label>
          Opponent cards ({opponentColor}, optional)
          <input bind:value={opponentCardsInput} placeholder="Leave blank to treat as unknown" />
        </label>
        <label class="row">
          <input type="checkbox" bind:checked={assumeKnownOpponentHand} disabled={opponentCardsInput.trim().length === 0} />
          <span>Use provided opponent cards exactly</span>
        </label>
        <label>
          Unknown opponent hand size
          <input type="number" min="0" max="8" bind:value={opponentUnknownHandSize} disabled={opponentCardsInput.trim().length > 0} />
        </label>
      </div>

      <div class="section two-col">
        <label>
          Depth
          <input type="number" min="1" max="8" bind:value={config.search_depth} />
        </label>
        <label>
          Determinizations
          <input type="number" min="1" max="200" bind:value={config.num_determinizations} />
        </label>
        <label>
          Time (s)
          <input type="number" min="0.05" step="0.05" bind:value={config.time_limit_seconds} />
        </label>
        <label>
          Risk
          <select bind:value={config.risk_profile}>
            <option value="balanced">balanced</option>
            <option value="aggressive">aggressive</option>
            <option value="defensive">defensive</option>
          </select>
        </label>
      </div>
    </div>
  </div>

  {#if result}
    <div class="panel result-panel">
      <div class="section-title">Recommendation</div>
      {#if result.best_move}
        <div class="best-row">
          <span class="chip">Best: {notation(result.best_move, myCardsParsed)}</span>
          <span class="chip">Expected score: {result.expected_score.toFixed(2)}</span>
        </div>
      {:else}
        <div class="muted tiny">No legal move found for this position.</div>
      {/if}

      {#if bestExplanation}
        <div class="summary">{bestExplanation.summary}</div>
        <ul class="factors">
          {#each bestExplanation.key_factors.slice(0, 4) as factor}
            <li>{factor}</li>
          {/each}
        </ul>
      {/if}

      <div class="section-title">Move evaluations</div>
      <div class="eval-list">
        {#each Object.entries(result.move_evaluations).sort((a, b) => b[1] - a[1]) as [key, score]}
          <div class="eval-item">
            <span>{key}</span>
            <span>{score.toFixed(2)}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  {#if error}
    <div class="error">{error}</div>
  {/if}
</section>

<style>
  .freeform-wrap { display: grid; gap: 12px; }
  .top { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
  h2 { margin: 0; font-size: clamp(1.1rem, 1rem + 0.9vw, 1.5rem); }
  .tools-row { display: flex; gap: 8px; flex-wrap: wrap; }
  .grid { display: grid; grid-template-columns: 1.1fr 1fr; gap: 12px; }
  .panel { border: 1px solid var(--stroke); border-radius: 14px; padding: 10px; background: rgba(0, 0, 0, 0.18); display: grid; gap: 10px; }
  .board-panel :global(.board-wrap) { width: min(62vmin, 520px); }
  .tool-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
  .tool { border: 1px solid var(--stroke); border-radius: 10px; padding: 8px; background: rgba(0, 0, 0, 0.2); color: inherit; }
  .tool.active { box-shadow: inset 0 0 0 1px rgba(242, 193, 78, 0.45); }
  .tool.active.red { box-shadow: inset 0 0 0 1px rgba(226, 85, 85, 0.65); }
  .tool.active.white { box-shadow: inset 0 0 0 1px rgba(244, 244, 244, 0.55); }
  .tool.active.crown { box-shadow: inset 0 0 0 1px rgba(242, 193, 78, 0.75); }
  .section { display: grid; gap: 8px; }
  .two-col { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  label { display: grid; gap: 4px; font-size: 12px; }
  input, select { border-radius: 8px; border: 1px solid var(--stroke); background: rgba(0, 0, 0, 0.26); color: inherit; padding: 6px; }
  .row { display: flex; align-items: center; gap: 8px; }
  .row.compact { font-size: 12px; }
  .section-title { font-size: 12px; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 800; color: rgba(234, 240, 255, 0.75); }
  .best-row { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip { border-radius: 999px; border: 1px solid var(--stroke); padding: 4px 10px; font-size: 12px; }
  .summary { font-size: 13px; line-height: 1.35; }
  .factors { margin: 0; padding-left: 18px; display: grid; gap: 4px; font-size: 12px; }
  .eval-list { display: grid; gap: 6px; max-height: 220px; overflow: auto; }
  .eval-item { display: flex; justify-content: space-between; border: 1px solid var(--stroke); border-radius: 8px; padding: 6px 8px; font-size: 12px; font-variant-numeric: tabular-nums; }
  .error { padding: 8px 10px; border-radius: 10px; border: 1px solid rgba(226, 85, 85, 0.5); background: rgba(226, 85, 85, 0.12); }
  @media (max-width: 1000px) {
    .grid { grid-template-columns: 1fr; }
  }
</style>
