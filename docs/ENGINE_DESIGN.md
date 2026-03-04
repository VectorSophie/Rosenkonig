# Engine Design

This document covers the competitive Rosenkonig engine, deterministic explainable-move pipeline, and analysis UI stretch features.

## Core Engine Model

The engine state is managed by `BoardState` (`backend/app/engine/board.py`) and move legality/application by `logic.py`.

- Board is an 11x11 grid with values: `0=empty`, `1=red`, `2=white`.
- Crown position (`king_position`) drives play targets from power cards.
- Player resources include hand cards, hero cards, and remaining stones.
- Move types are `play`, `draw`, and `pass`.

### Scoring Rule

`calculate_scores` in `logic.py` computes each player score as:

1. Find orthogonally connected regions of a player color.
2. For each region size `n`, add `n^2`.
3. Sum all region contributions.

This is the official connectivity objective and is the base term for competitive evaluation.

## Competitive Search

`find_best_move` in `backend/app/engine/competitive.py` uses determinization + alpha-beta.

1. Enumerate legal root moves.
2. Sample hidden-information worlds (`sample_opponent_hand`) with fixed RNG seed for determinism.
3. For each root move and sampled world:
   - Apply root move.
   - Run iterative deepening alpha-beta up to configured depth.
   - Record score and principal variation.
4. Average scores across completed determinizations.
5. Classify candidates (`best/good/inaccuracy/blunder/brilliant`) using numeric drop thresholds.

Determinism guarantees:

- Fixed `random_seed` in config.
- No non-deterministic text generation.
- Explanations are pure functions of measured deltas and search artifacts.

## Structured Evaluation Breakdown

Evaluation now returns `EvalBreakdown` instead of scalar-only output.

```python
class EvalBreakdown:
    total: float
    region_score_diff: float
    expansion_score: float
    mobility_score: float
    crown_centrality: float
    hero_threat_adjustment: float
    stone_scarcity_pressure: float
```

All candidate moves and the root position carry these breakdowns in `EngineResult`.

## Explainable Move Generation

### Data Contract

`MoveExplanation` is generated per candidate move and returned in engine/API payloads.

```python
class MoveExplanation:
    summary: str
    key_factors: list[str]  # max 4
    principal_variation: list
    risk_level: str         # low/medium/high
    robustness_score: float # 0..1
```

### Rule Sources

Explanations are derived from:

- Eval component deltas (`after - before`)
- Region topology metrics (region count, largest region size, isolated groups)
- Principal variation sequence from search
- Variance across determinizations

### Rule Mapping (Deterministic)

- Region term increases:
  - "Connects two regions" when own region count decreases while largest region grows.
  - "Expands largest region" when largest component size increases.
  - "Prevents opponent region growth" when opponent largest region drops or fragmentation rises.
- Expansion term increase/decrease:
  - Future expansion options improved or reduced.
- Mobility term increase/decrease:
  - Crown flexibility improved or crown committed to narrow lane.
- Hero threat adjustment increase/decrease:
  - Reduced vulnerability to hero flip or increased exposure.
- PV explanation (depth >= 3):
  - Emits forced-sequence statement using actual PV moves and measured region swing.
- Robustness from variance:
  - `robustness_score = 1 / (1 + variance)`
  - variance <= 0.15 -> low risk
  - 0.15 < variance <= 0.6 -> medium risk
  - variance > 0.6 -> high risk

### Anti-Hallucination Constraints

- No generic strategy phrases without numeric driver.
- No claims not backed by eval deltas or search/PV output.
- Maximum 4 key factors to keep every bullet meaningful and traceable.

## Engine Result and Analysis Output

`EngineResult` now includes:

- `move_explanations`: move-key -> `MoveExplanation`
- `evaluation_breakdowns`: move-key -> `EvalBreakdown`
- `root_evaluation`: `EvalBreakdown` for current state

`analyze_game` now stores per-ply:

- `chosen_explanation`
- `best_move_explanation`
- `blunder_explanation` (when applicable)

This keeps post-game analysis consistent with what the search actually computed at each position.

## Stretch UI Features

Implemented in `frontend/src/lib/components/AnalysisPanel.svelte` and `Board.svelte`.

### 1) Affected Region Highlight

- Board accepts `highlightedSquares`.
- Analysis view computes changed cells by diffing previous vs selected snapshot.
- Highlight region expands from changed stones through orthogonal flood-fill of same-color connected cells.
- Crown movement cells are also highlighted when crown position changes.

### 2) Swing Magnitude Visualization

- For selected analyzed move, UI shows:
  - absolute score swing `abs(best_score - chosen_score)`
  - normalized bar for quick severity reading

### 3) Side-by-Side Alternative Explanation

- When both explanations exist, analysis panel shows:
  - chosen move summary
  - best alternative summary

This makes the blunder/inaccuracy cause directly comparable without leaving the current move context.

## Validation

Added tests in `backend/tests/test_competitive.py` for:

- region-merge explanation mentioning connection
- mobility-drop explanation mentioning reduced flexibility
- high-variance explanation marked high risk

All tests and frontend checks/build must pass before shipping.
