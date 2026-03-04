<script lang="ts">
  import { onMount } from 'svelte';
  import type { GameState } from '$lib/stores/game';
  import Board from '$lib/components/Board.svelte';

  export let roomId: string | null = null;
  export let state: GameState | null = null;
  export let stateHistory: GameState[] = [];

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
  };

  type AnalysisMove = {
    ply: number;
    side_to_move: string;
    chosen_move: { action: string; card_index: number | null; use_hero: boolean };
    best_move: { action: string; card_index: number | null; use_hero: boolean } | null;
    chosen_score: number;
    best_score: number;
    classification: string;
    best_line: Array<{ action: string; card_index: number | null; use_hero: boolean }>;
    chosen_explanation?: MoveExplanation | null;
    best_move_explanation?: MoveExplanation | null;
    blunder_explanation?: string | null;
  };

  type EvalBreakdown = {
    total: number;
    region_score_diff: number;
    expansion_score: number;
    mobility_score: number;
    crown_centrality: number;
    hero_threat_adjustment: number;
    stone_scarcity_pressure: number;
  };

  type MoveExplanation = {
    summary: string;
    key_factors: string[];
    principal_variation: Array<{ action: string; card_index: number | null; use_hero: boolean }>;
    risk_level: 'low' | 'medium' | 'high';
    robustness_score: number;
  };

  type AnalysisResponse = {
    moves: AnalysisMove[];
    initial_position?: {
      board: number[][];
      crown_pos: [number, number];
      current_turn: string;
      game_over: boolean;
    };
    positions?: Array<{
      board: number[][];
      crown_pos: [number, number];
      current_turn: string;
      game_over: boolean;
    }>;
    score_timeline: number[];
    classifications: string[];
    alternatives: Array<Array<{ action: string; card_index: number | null; use_hero: boolean }>>;
    accuracy_by_player: Record<string, number>;
    largest_blunder: { ply: number; side: string; move: unknown; drop: number } | null;
    most_brilliant_move: { ply: number; side: string; move: unknown } | null;
  };

  type BestMoveResponse = {
    best_move: { action: string; card_index: number | null; use_hero: boolean } | null;
    expected_score: number;
    principal_variation: Array<{ action: string; card_index: number | null; use_hero: boolean }>;
    move_evaluations: Record<string, number>;
    move_classifications: Record<string, string>;
    move_explanations: Record<string, MoveExplanation>;
    evaluation_breakdowns: Record<string, EvalBreakdown>;
    root_evaluation: EvalBreakdown;
    diagnostics: Record<string, unknown>;
  };

  type BoardSnapshot = {
    board: number[][];
    crown_pos: [number, number];
    legal_moves: Array<{ action: string; card_index: number; target: [number, number] | null; use_hero: boolean }>;
  };

  const BACKEND_HTTP = import.meta.env.VITE_BACKEND_HTTP ?? 'http://localhost:8000';

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
    risk_profile: 'balanced'
  };

  let analyzing = false;
  let analysisError = '';
  let report: AnalysisResponse | null = null;
  let bestMoveResult: BestMoveResponse | null = null;
  let selectedMoveIndex = -1;
  let roomState: GameState | null = null;

  $: timeline = report?.score_timeline ?? [];
  $: reportInitial = report?.initial_position
    ? {
        board: report.initial_position.board,
        crown_pos: [report.initial_position.crown_pos[1], report.initial_position.crown_pos[0]] as [number, number],
        legal_moves: []
      }
    : null;

  $: reportSnapshots = (report?.positions ?? []).map((p) => ({
    board: p.board,
    crown_pos: [p.crown_pos[1], p.crown_pos[0]] as [number, number],
    legal_moves: []
  })) as BoardSnapshot[];

  $: baselineState = (state ?? roomState ?? reportInitial) as BoardSnapshot | null;
  $: selectedSnapshot =
    selectedMoveIndex < 0
      ? baselineState
      : reportSnapshots[selectedMoveIndex] ?? stateHistory[selectedMoveIndex] ?? baselineState;
  $: selectedMove = selectedMoveIndex >= 0 ? report?.moves?.[selectedMoveIndex] ?? null : null;
  $: chosenExplanation = selectedMove?.chosen_explanation ?? null;
  $: bestAlternativeExplanation = selectedMove?.best_move_explanation ?? null;
  $: selectedExplanation = selectedMove
    ? chosenExplanation ?? bestAlternativeExplanation ?? null
    : bestMoveResult && bestMoveResult.best_move
      ? bestMoveResult.move_explanations?.[
          `${bestMoveResult.best_move.action}:${bestMoveResult.best_move.card_index}:${bestMoveResult.best_move.use_hero ? 1 : 0}`
        ] ?? null
      : null;
  $: selectedPv = selectedExplanation?.principal_variation ?? (selectedMove ? selectedMove.best_line : bestMoveResult?.principal_variation ?? []);

  $: firstPvMove = selectedPv.length > 0 ? selectedPv[0] : null;
  $: firstMoveTarget =
    firstPvMove && selectedSnapshot?.legal_moves
      ? selectedSnapshot.legal_moves.find(
          (lm) =>
            lm.card_index === firstPvMove.card_index &&
            lm.use_hero === firstPvMove.use_hero &&
            lm.action === firstPvMove.action
        )?.target ?? null
      : null;

  $: evalValue = selectedMove
    ? selectedMove.chosen_score
    : bestMoveResult?.expected_score ?? (timeline.length ? timeline[timeline.length - 1] : 0);
  $: previousSnapshot =
    selectedMoveIndex <= 0
      ? baselineState
      : reportSnapshots[selectedMoveIndex - 1] ?? stateHistory[selectedMoveIndex - 1] ?? baselineState;
  $: affectedSquares = deriveAffectedSquares(previousSnapshot, selectedSnapshot);
  $: scoreSwing = selectedMove ? Math.abs(selectedMove.best_score - selectedMove.chosen_score) : 0;
  $: scoreSwingPercent = Math.max(0, Math.min(100, (scoreSwing / 3) * 100));

  function clampEval(v: number): number {
    return Math.max(-20, Math.min(20, v));
  }

  function graphPoints(values: number[]): string {
    if (!values.length) return '';
    const width = 520;
    const height = 180;
    const denom = Math.max(1, values.length - 1);
    return values
      .map((v, i) => {
        const x = (i / denom) * width;
        const y = ((20 - clampEval(v)) / 40) * height;
        return `${x},${y}`;
      })
      .join(' ');
  }

  function badgeClass(label: string): string {
    if (label === 'blunder') return 'b-blunder';
    if (label === 'inaccuracy') return 'b-inaccuracy';
    if (label === 'best') return 'b-best';
    if (label === 'brilliant') return 'b-brilliant';
    return 'b-good';
  }

  function notation(m: { action: string; card_index: number | null; use_hero: boolean }): string {
    if (m.action === 'draw') return 'Draw';
    if (m.action === 'pass') return 'Pass';
    const idx = m.card_index === null ? '-' : m.card_index + 1;
    return `${m.use_hero ? 'H-' : ''}C${idx}`;
  }

  function riskBadgeClass(risk: 'low' | 'medium' | 'high'): string {
    if (risk === 'low') return 'risk-low';
    if (risk === 'high') return 'risk-high';
    return 'risk-medium';
  }

  function sameCell(a: [number, number], b: [number, number]): boolean {
    return a[0] === b[0] && a[1] === b[1];
  }

  function keyOf(r: number, c: number): string {
    return `${r},${c}`;
  }

  function deriveAffectedSquares(
    before: BoardSnapshot | null,
    after: BoardSnapshot | null
  ): Array<[number, number]> {
    if (!before || !after) return [];
    const changed: Array<[number, number]> = [];
    const changedKeys = new Set<string>();
    for (let r = 0; r < 11; r += 1) {
      for (let c = 0; c < 11; c += 1) {
        if ((before.board?.[r]?.[c] ?? 0) !== (after.board?.[r]?.[c] ?? 0)) {
          changed.push([r, c]);
          changedKeys.add(keyOf(r, c));
        }
      }
    }

    if (!sameCell(before.crown_pos, after.crown_pos)) {
      changedKeys.add(keyOf(before.crown_pos[0], before.crown_pos[1]));
      changedKeys.add(keyOf(after.crown_pos[0], after.crown_pos[1]));
      changed.push(before.crown_pos);
      changed.push(after.crown_pos);
    }

    const expandedKeys = new Set<string>(changedKeys);
    for (const [r, c] of changed) {
      const color = after.board?.[r]?.[c] ?? 0;
      if (color === 0) continue;
      const stack: Array<[number, number]> = [[r, c]];
      const seen = new Set<string>();
      while (stack.length > 0) {
        const current = stack.pop();
        if (!current) break;
        const [rr, cc] = current;
        const k = keyOf(rr, cc);
        if (seen.has(k)) continue;
        seen.add(k);
        if ((after.board?.[rr]?.[cc] ?? 0) !== color) continue;
        expandedKeys.add(k);
        for (const [dr, dc] of [
          [-1, 0],
          [1, 0],
          [0, -1],
          [0, 1]
        ]) {
          const nr = rr + dr;
          const nc = cc + dc;
          if (nr < 0 || nr >= 11 || nc < 0 || nc >= 11) continue;
          stack.push([nr, nc]);
        }
      }
    }

    return Array.from(expandedKeys).map((entry) => {
      const [r, c] = entry.split(',').map(Number);
      return [r, c] as [number, number];
    });
  }

  async function loadConfig() {
    try {
      const res = await fetch(`${BACKEND_HTTP}/engine-config`);
      if (!res.ok) return;
      config = (await res.json()) as EngineConfig;
    } catch {
    }
  }

  async function loadRoomState() {
    if (!roomId) return;
    try {
      const res = await fetch(`${BACKEND_HTTP}/rooms/${roomId}`);
      if (!res.ok) return;
      const payload = (await res.json()) as {
        board: number[];
        crown_pos: [number, number];
        draw_pile_count?: number;
        players: Array<{ name: string; hand: Array<{ direction: string; distance: number }>; knights: number; score: number }>;
        current_turn: string;
        game_over: boolean;
        legal_moves?: Array<{ action: string; card_index: number; target: [number, number] | null; use_hero: boolean }>;
        move_history?: Array<{ action: string; card_index: number | null; use_hero: boolean }>;
      };

      const board = Array.from({ length: 11 }, (_, r) => payload.board.slice(r * 11, r * 11 + 11));
      const currentTurnName = payload.current_turn.toLowerCase();
      const players = [
        {
          color: 'red' as const,
          name: payload.players?.[0]?.name ?? 'Red',
          hero_cards: payload.players?.[0]?.knights ?? 0,
          power_cards: payload.players?.[0]?.hand ?? [],
          score: payload.players?.[0]?.score ?? 0
        },
        {
          color: 'white' as const,
          name: payload.players?.[1]?.name ?? 'White',
          hero_cards: payload.players?.[1]?.knights ?? 0,
          power_cards: payload.players?.[1]?.hand ?? [],
          score: payload.players?.[1]?.score ?? 0
        }
      ];
      const currentTurn =
        players[0].name.toLowerCase() === currentTurnName || currentTurnName === 'red' ? 'red' : 'white';

      roomState = {
        room_id: roomId,
        board,
        crown_pos: [payload.crown_pos[1], payload.crown_pos[0]],
        draw_pile_count: payload.draw_pile_count ?? 0,
        players,
        current_turn: currentTurn,
        game_over: payload.game_over,
        legal_moves: (payload.legal_moves ?? []).map((m) => ({
          action: m.action,
          card_index: m.card_index,
          target: m.target ? [m.target[1], m.target[0]] : null,
          use_hero: m.use_hero
        })),
        move_history: payload.move_history ?? []
      };
    } catch {
    }
  }

  async function saveConfig() {
    try {
      await fetch(`${BACKEND_HTTP}/engine-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
    } catch {
    }
  }

  async function reanalyzeGame() {
    if (!roomId) return;
    analyzing = true;
    analysisError = '';
    bestMoveResult = null;
    try {
      await saveConfig();
      const res = await fetch(`${BACKEND_HTTP}/analyze-game`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: roomId, config })
      });
      if (!res.ok) {
        analysisError = await res.text();
        return;
      }
      report = (await res.json()) as AnalysisResponse;
      selectedMoveIndex = report.moves.length > 0 ? report.moves.length - 1 : -1;
    } catch (e) {
      analysisError = String(e);
    } finally {
      analyzing = false;
    }
  }

  async function analyzePosition() {
    if (!roomId) return;
    analyzing = true;
    analysisError = '';
    try {
      await saveConfig();
      const res = await fetch(`${BACKEND_HTTP}/best-move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_id: roomId, config })
      });
      if (!res.ok) {
        analysisError = await res.text();
        return;
      }
      bestMoveResult = (await res.json()) as BestMoveResponse;
      selectedMoveIndex = -1;
    } catch (e) {
      analysisError = String(e);
    } finally {
      analyzing = false;
    }
  }

  function goStart() {
    selectedMoveIndex = -1;
  }
  function goPrev() {
    if (selectedMoveIndex <= -1) return;
    selectedMoveIndex -= 1;
  }
  function goNext() {
    if (!report) return;
    if (selectedMoveIndex >= report.moves.length - 1) return;
    selectedMoveIndex += 1;
  }
  function goEnd() {
    if (!report || report.moves.length === 0) return;
    selectedMoveIndex = report.moves.length - 1;
  }

  onMount(() => {
    void loadConfig();
    void loadRoomState();
  });
</script>

<section class="analysis-wrap">
  <div class="analysis-grid">
    <div class="left-pane">
      <div class="mini-board">
        <Board
          board={selectedSnapshot?.board ?? Array.from({ length: 11 }, () => Array.from({ length: 11 }, () => 0))}
          crownPos={selectedSnapshot?.crown_pos ?? [5, 5]}
          previewPos={firstMoveTarget}
          legalMoves={selectedSnapshot?.legal_moves ?? []}
          highlightedSquares={affectedSquares}
          selectedCardIndex={null}
          selectedUseHero={false}
          interactive={false}
        />
      </div>
      {#if selectedMoveIndex >= 0}
        <div class="swing-box">
          <div class="section-title">Swing Magnitude</div>
          <div class="muted tiny">Best - chosen: {scoreSwing.toFixed(2)}</div>
          <div class="swing-track"><div class="swing-fill" style={`width:${scoreSwingPercent}%`}></div></div>
        </div>
      {/if}
      <div class="nav-row">
        <button class="btn ghost" on:click={goStart}>{'<<'}</button>
        <button class="btn ghost" on:click={goPrev}>{'<'}</button>
        <button class="btn ghost" on:click={goNext}>{'>'}</button>
        <button class="btn ghost" on:click={goEnd}>{'>>'}</button>
        <span class="muted tiny">
          {selectedMoveIndex < 0 ? 'Initial position' : `Move ${selectedMoveIndex + 1}`}
        </span>
      </div>

      <div class="pv-box">
        <div class="section-title">Principal Variation</div>
        {#if selectedPv.length === 0}
          <div class="muted tiny">No line available.</div>
        {:else}
          <div class="pv-line">
            {#each selectedPv as mv}
              <span class="pv-chip">{notation(mv)}</span>
            {/each}
          </div>
        {/if}
      </div>

      <div class="settings">
        <div class="section-title">Engine Settings</div>
        <div class="settings-grid">
          <label>Depth <input type="number" min="1" max="8" bind:value={config.search_depth} /></label>
          <label>Determinization <input type="number" min="1" max="200" bind:value={config.num_determinizations} /></label>
          <label>Time (s) <input type="number" min="0.05" step="0.05" bind:value={config.time_limit_seconds} /></label>
          <label>Nodes <input type="number" min="100" step="100" bind:value={config.max_nodes} /></label>
          <label>
            Risk
            <select bind:value={config.risk_profile}>
              <option value="balanced">balanced</option>
              <option value="aggressive">aggressive</option>
              <option value="defensive">defensive</option>
            </select>
          </label>
        </div>
        <div class="tools">
          <button class="btn" on:click={reanalyzeGame} disabled={analyzing || !roomId}>
            {analyzing ? 'Analyzing...' : 'Reanalyze Game'}
          </button>
          <button class="btn ghost" on:click={analyzePosition} disabled={analyzing || !roomId}>
            {analyzing ? 'Analyzing...' : 'Analyze Position'}
          </button>
        </div>
        {#if analyzing}
          <div class="muted tiny">Engine is running. High depth and many determinizations can take a few seconds.</div>
        {/if}
      </div>
    </div>

    <div class="right-pane">
      <div class="eval-area">
        <div class="eval-bar">
          <div class="mid"></div>
          <div class="fill" style={`height:${((clampEval(evalValue) + 20) / 40) * 100}%`}></div>
        </div>
        <div class="eval-num">{evalValue.toFixed(2)}</div>
      </div>

      <div class="graph-box">
        <svg viewBox="0 0 520 180" class="graph">
          <line x1="0" y1="90" x2="520" y2="90" class="axis" />
          <polyline points={graphPoints(timeline)} class="score-line" />
          {#if selectedMoveIndex >= 0 && timeline[selectedMoveIndex] !== undefined}
            <circle
              cx={(selectedMoveIndex / Math.max(1, timeline.length - 1)) * 520}
              cy={((20 - clampEval(timeline[selectedMoveIndex])) / 40) * 180}
              r="4"
              class="sel-dot"
            />
          {/if}
        </svg>
      </div>

      <div class="move-list">
        <div class="section-title">Move Classification</div>
        {#if !report || report.moves.length === 0}
          <div class="muted tiny">Run game analysis to see classifications.</div>
        {:else}
          {#each report.moves as move, i}
            <button
              class={['line', i === selectedMoveIndex ? 'active' : ''].join(' ')}
              on:click={() => (selectedMoveIndex = i)}
              title={move.chosen_explanation?.summary ?? move.best_move_explanation?.summary ?? 'No explanation available'}
            >
              <span class="idx">{move.ply}.</span>
              <span>{notation(move.chosen_move)}</span>
              <span class={['badge', badgeClass(move.classification)].join(' ')}>{move.classification}</span>
            </button>
          {/each}
        {/if}
      </div>

      <div class="explain-box">
        <div class="section-title">Move Reasoning</div>
        {#if !selectedExplanation}
          <div class="muted tiny">Select a move or run position analysis to view deterministic reasoning.</div>
        {:else}
          <div class="summary">{selectedExplanation.summary}</div>
          <ul class="factors">
            {#each selectedExplanation.key_factors.slice(0, 4) as factor}
              <li>{factor}</li>
            {/each}
          </ul>
          <div class="risk-row">
            <span class="muted tiny">Risk</span>
            <span class={['risk-pill', riskBadgeClass(selectedExplanation.risk_level)].join(' ')}>{selectedExplanation.risk_level}</span>
          </div>
          <div class="robustness">
            <div class="muted tiny">Robustness {(selectedExplanation.robustness_score * 100).toFixed(0)}%</div>
            <div class="bar"><div class="fill" style={`width:${Math.max(0, Math.min(100, selectedExplanation.robustness_score * 100))}%`}></div></div>
          </div>
          {#if selectedMove?.blunder_explanation}
            <div class="blunder-note">{selectedMove.blunder_explanation}</div>
          {/if}
          {#if selectedMove && chosenExplanation && bestAlternativeExplanation}
            <div class="compare-grid">
              <div class="compare-col">
                <div class="muted tiny">Chosen move</div>
                <div>{chosenExplanation.summary}</div>
              </div>
              <div class="compare-col">
                <div class="muted tiny">Best alternative</div>
                <div>{bestAlternativeExplanation.summary}</div>
              </div>
            </div>
          {/if}
        {/if}
      </div>

      {#if report}
        <div class="stats">
          <div class="section-title">Accuracy</div>
          <div class="row"><span>Red</span><span>{report.accuracy_by_player.red ?? 0}%</span></div>
          <div class="row"><span>White</span><span>{report.accuracy_by_player.white ?? 0}%</span></div>
        </div>
      {/if}
    </div>
  </div>
  {#if analysisError}
    <div class="error">{analysisError}</div>
  {/if}
</section>

<style>
  .analysis-wrap { margin-top: 14px; display: grid; gap: 10px; }
  .analysis-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 12px; }
  .left-pane, .right-pane { border: 1px solid var(--stroke); border-radius: 14px; padding: 10px; background: rgba(0,0,0,0.15); }
  .nav-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .mini-board :global(.board-wrap) { width: min(48vmin, 360px); margin-bottom: 10px; }
  .section-title { font-size: 12px; text-transform: uppercase; letter-spacing: 0.03em; font-weight: 800; color: rgba(234,240,255,0.75); margin-bottom: 6px; }
  .pv-box { margin-bottom: 10px; }
  .swing-box { border: 1px solid var(--stroke); border-radius: 12px; padding: 8px; margin-bottom: 10px; display: grid; gap: 6px; }
  .swing-track { height: 9px; border-radius: 999px; background: rgba(255,255,255,0.12); overflow: hidden; }
  .swing-fill { height: 100%; background: linear-gradient(90deg, rgba(72,187,120,0.85), rgba(242,193,78,0.95), rgba(226,85,85,0.95)); }
  .pv-line { display: flex; gap: 6px; flex-wrap: wrap; }
  .pv-chip { border: 1px solid var(--stroke); border-radius: 999px; padding: 4px 8px; font-size: 12px; }
  .settings-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .settings-grid label { display: grid; gap: 4px; font-size: 12px; }
  .settings-grid input, .settings-grid select { border-radius: 8px; border: 1px solid var(--stroke); background: rgba(0,0,0,0.25); color: inherit; padding: 6px; }
  .tools { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
  .eval-area { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .eval-bar { width: 24px; height: 160px; border: 1px solid var(--stroke); border-radius: 12px; position: relative; overflow: hidden; background: rgba(0,0,0,0.3); }
  .eval-bar .mid { position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: rgba(255,255,255,0.25); }
  .eval-bar .fill { position: absolute; left: 0; right: 0; bottom: 0; background: linear-gradient(180deg, rgba(226,85,85,0.8), rgba(242,193,78,0.95)); }
  .eval-num { font-weight: 900; font-variant-numeric: tabular-nums; }
  .graph-box { border: 1px solid var(--stroke); border-radius: 12px; padding: 8px; margin-bottom: 10px; }
  .graph { width: 100%; height: 180px; }
  .axis { stroke: rgba(255,255,255,0.2); stroke-width: 1; }
  .score-line { fill: none; stroke: rgba(242,193,78,0.9); stroke-width: 2; }
  .sel-dot { fill: rgba(255,255,255,0.95); }
  .move-list { max-height: 230px; overflow: auto; display: grid; gap: 6px; margin-bottom: 10px; }
  .line { display: grid; grid-template-columns: 36px 1fr auto; gap: 8px; align-items: center; width: 100%; text-align: left; border: 1px solid var(--stroke); border-radius: 10px; background: rgba(0,0,0,0.2); padding: 6px 8px; color: inherit; }
  .line.active { box-shadow: inset 0 0 0 1px rgba(242,193,78,0.35); }
  .idx { font-variant-numeric: tabular-nums; color: rgba(234,240,255,0.65); }
  .badge { border-radius: 999px; padding: 2px 8px; font-size: 11px; text-transform: uppercase; }
  .b-blunder { background: rgba(226,85,85,0.2); border: 1px solid rgba(226,85,85,0.5); }
  .b-inaccuracy { background: rgba(242,193,78,0.2); border: 1px solid rgba(242,193,78,0.5); }
  .b-good { background: rgba(72,187,120,0.2); border: 1px solid rgba(72,187,120,0.5); }
  .b-best { background: rgba(76,128,255,0.2); border: 1px solid rgba(76,128,255,0.5); }
  .b-brilliant { background: rgba(143,91,255,0.2); border: 1px solid rgba(143,91,255,0.5); }
  .stats { border: 1px solid var(--stroke); border-radius: 12px; padding: 8px; }
  .stats .row { display: flex; justify-content: space-between; font-variant-numeric: tabular-nums; }
  .explain-box { border: 1px solid var(--stroke); border-radius: 12px; padding: 8px; display: grid; gap: 8px; margin-bottom: 10px; }
  .summary { font-size: 13px; line-height: 1.35; }
  .factors { margin: 0; padding-left: 18px; display: grid; gap: 4px; font-size: 12px; }
  .risk-row { display: flex; justify-content: space-between; align-items: center; }
  .risk-pill { border-radius: 999px; font-size: 11px; text-transform: uppercase; padding: 2px 8px; border: 1px solid var(--stroke); }
  .risk-low { background: rgba(72,187,120,0.18); border-color: rgba(72,187,120,0.55); }
  .risk-medium { background: rgba(242,193,78,0.18); border-color: rgba(242,193,78,0.55); }
  .risk-high { background: rgba(226,85,85,0.18); border-color: rgba(226,85,85,0.55); }
  .robustness { display: grid; gap: 4px; }
  .robustness .bar { height: 8px; border-radius: 999px; background: rgba(255,255,255,0.12); overflow: hidden; }
  .robustness .bar .fill { height: 100%; background: linear-gradient(90deg, rgba(226,85,85,0.8), rgba(242,193,78,0.95), rgba(72,187,120,0.95)); }
  .blunder-note { font-size: 12px; border: 1px solid rgba(226,85,85,0.5); background: rgba(226,85,85,0.12); border-radius: 8px; padding: 6px; }
  .compare-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .compare-col { border: 1px solid var(--stroke); border-radius: 8px; padding: 6px; font-size: 12px; display: grid; gap: 4px; }
  .error { padding: 8px 10px; border-radius: 10px; border: 1px solid rgba(226,85,85,0.5); background: rgba(226,85,85,0.12); }
  @media (max-width: 1000px) {
    .analysis-grid { grid-template-columns: 1fr; }
    .compare-grid { grid-template-columns: 1fr; }
  }
</style>
