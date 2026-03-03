from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Any

from .board import (
    BOARD_SIZE,
    DIRECTION_DELTAS,
    BoardState,
    Move,
    PlayerColor,
    PowerCard,
    cell_for_player,
    official_power_deck,
    opponent,
)
from .logic import (
    InvalidMoveError,
    apply_move,
    calculate_scores,
    get_legal_moves,
)


DEFAULT_EVAL_WEIGHTS = {
    "region_score": 1.0,
    "mobility": 0.4,
    "expansion_potential": 0.6,
    "crown_centrality": 0.2,
    "hero_threat_discount": 0.5,
    "stone_scarcity_pressure": 0.5,
}


@dataclass(slots=True)
class EngineConfig:
    search_depth: int = 5
    num_determinizations: int = 20
    time_limit_seconds: float | None = 1.8
    max_nodes: int | None = 50000
    use_transposition_table: bool = True
    use_quiescence: bool = False
    random_seed: int = 7
    eval_weights: dict[str, float] | None = None
    risk_profile: str = "balanced"

    def resolved_weights(self) -> dict[str, float]:
        weights = dict(DEFAULT_EVAL_WEIGHTS)
        if self.eval_weights is not None:
            weights.update(self.eval_weights)
        return weights


@dataclass(slots=True)
class EngineResult:
    best_move: dict[str, Any] | None
    expected_score: float
    principal_variation: list[dict[str, Any]]
    move_evaluations: dict[str, float]
    move_classifications: dict[str, str]
    diagnostics: dict[str, Any]


@dataclass(slots=True)
class AnalysisMove:
    ply: int
    side_to_move: str
    chosen_move: dict[str, Any]
    best_move: dict[str, Any] | None
    chosen_score: float
    best_score: float
    classification: str
    best_line: list[dict[str, Any]]


@dataclass(slots=True)
class AnalysisReport:
    moves: list[AnalysisMove]
    initial_position: dict[str, object]
    positions: list[dict[str, object]]
    score_timeline: list[float]
    classifications: list[str]
    alternatives: list[list[dict[str, Any]]]
    accuracy_by_player: dict[str, float]
    largest_blunder: dict[str, Any] | None
    most_brilliant_move: dict[str, Any] | None


def _move_key(move: Move) -> str:
    return f"{move.action}:{move.card_index}:{1 if move.use_hero else 0}"


def _move_to_dict(move: Move) -> dict[str, Any]:
    return {
        "action": move.action,
        "card_index": move.card_index,
        "use_hero": move.use_hero,
    }


def _is_capture(state: BoardState, move: Move) -> bool:
    if move.action != "play" or move.card_index is None:
        return False
    card = state.players[state.current_player].power_cards[move.card_index]
    row_delta, col_delta = DIRECTION_DELTAS[card.direction]
    row, col = state.king_position
    target = (row + row_delta * card.distance, col + col_delta * card.distance)
    target_cell = state.grid[target[0]][target[1]]
    return target_cell == cell_for_player(opponent(state.current_player))


def _cards_key(cards: list[PowerCard]) -> str:
    return ",".join(f"{card.direction.value}{card.distance}" for card in cards)


def _state_hash(state: BoardState, maximizing_for: PlayerColor) -> str:
    board_flat = "".join(str(int(v)) for row in state.grid for v in row)
    parts = [
        board_flat,
        str(state.king_position[0]),
        str(state.king_position[1]),
        state.current_player.value,
        maximizing_for.value,
        str(state.players[PlayerColor.RED].hero_cards),
        str(state.players[PlayerColor.WHITE].hero_cards),
        str(state.players[PlayerColor.RED].stones_remaining),
        str(state.players[PlayerColor.WHITE].stones_remaining),
        _cards_key(state.players[PlayerColor.RED].power_cards),
        _cards_key(state.players[PlayerColor.WHITE].power_cards),
        _cards_key(state.draw_pile),
        _cards_key(state.discard_pile),
        str(state.consecutive_passes),
    ]
    return "|".join(parts)


def sample_opponent_hand(public_state: BoardState, *, rng: random.Random) -> BoardState:
    sampled = public_state.copy()
    me = sampled.current_player
    opp = opponent(me)

    my_hand = sampled.players[me].power_cards.copy()
    opp_hand_size = len(sampled.players[opp].power_cards)
    known_removed = my_hand + sampled.discard_pile

    all_cards = official_power_deck()
    pool: list[PowerCard] = []
    removed = known_removed.copy()
    for card in all_cards:
        matched_idx = next(
            (
                i
                for i, removed_card in enumerate(removed)
                if removed_card.direction == card.direction
                and removed_card.distance == card.distance
            ),
            None,
        )
        if matched_idx is None:
            pool.append(card)
        else:
            removed.pop(matched_idx)

    rng.shuffle(pool)
    opp_cards = pool[:opp_hand_size]
    draw_cards = pool[opp_hand_size:]

    sampled.players[opp].power_cards = opp_cards
    sampled.draw_pile = draw_cards
    return sampled


def _expansion_potential(state: BoardState, player: PlayerColor) -> float:
    target = cell_for_player(player)
    seen: set[tuple[int, int]] = set()
    empty_adj = 0
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            if state.grid[row][col] != target:
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = row + dr, col + dc
                if nr < 0 or nr >= BOARD_SIZE or nc < 0 or nc >= BOARD_SIZE:
                    continue
                if state.grid[nr][nc] != 0:
                    continue
                if (nr, nc) in seen:
                    continue
                seen.add((nr, nc))
                empty_adj += 1
    return float(empty_adj)


def _crown_centrality(state: BoardState, player: PlayerColor) -> float:
    row, col = state.king_position
    center = (BOARD_SIZE - 1) / 2
    dist = abs(row - center) + abs(col - center)
    me_turn = 1.0 if state.current_player == player else -1.0
    return me_turn * (10.0 - dist)


def _mobility(state: BoardState, player: PlayerColor) -> float:
    probe = state.copy()
    probe.current_player = player
    legal = [entry for entry in get_legal_moves(probe) if entry.move.action == "play"]
    return float(len(legal))


def _hero_threat_exposure(state: BoardState, player: PlayerColor) -> float:
    opp = opponent(player)
    probe = state.copy()
    probe.current_player = opp
    opp_hero = state.players[opp].hero_cards
    if opp_hero <= 0:
        return 0.0

    tactical = 0
    for entry in get_legal_moves(probe):
        if entry.move.action == "play" and entry.move.use_hero:
            tactical += 1
    return float(tactical)


def _stone_scarcity_pressure(state: BoardState, player: PlayerColor) -> float:
    me = state.players[player].stones_remaining
    opp = state.players[opponent(player)].stones_remaining
    total_left = me + opp
    late_factor = 1.0 - (total_left / 52.0)
    return (float(opp - me)) * max(0.0, late_factor)


def evaluate_position(
    state: BoardState, player: PlayerColor, weights: dict[str, float]
) -> float:
    scores = calculate_scores(state)
    region_delta = float(scores[player] - scores[opponent(player)])
    mobility_delta = _mobility(state, player) - _mobility(state, opponent(player))
    expansion_delta = _expansion_potential(state, player) - _expansion_potential(
        state, opponent(player)
    )
    centrality = _crown_centrality(state, player)
    threat = _hero_threat_exposure(state, player)
    scarcity = _stone_scarcity_pressure(state, player)

    return (
        weights["region_score"] * region_delta
        + weights["mobility"] * mobility_delta
        + weights["expansion_potential"] * expansion_delta
        + weights["crown_centrality"] * centrality
        - weights["hero_threat_discount"] * threat
        + weights["stone_scarcity_pressure"] * scarcity
    )


def _ordered_moves(state: BoardState) -> list[Move]:
    legal = get_legal_moves(state)
    captures: list[Move] = []
    plays: list[Move] = []
    others: list[Move] = []
    for entry in legal:
        move = entry.move
        if move.action == "play":
            if _is_capture(state, move):
                captures.append(move)
            else:
                plays.append(move)
        else:
            others.append(move)
    return captures + plays + others


def _alpha_beta(
    state: BoardState,
    depth: int,
    alpha: float,
    beta: float,
    maximizing_for: PlayerColor,
    weights: dict[str, float],
    transposition: dict[str, tuple[int, float]] | None,
    node_counter: dict[str, int],
    cfg: EngineConfig,
    start_time: float,
) -> tuple[float, list[Move]]:
    if cfg.max_nodes is not None and node_counter["count"] >= cfg.max_nodes:
        return evaluate_position(state, maximizing_for, weights), []
    if (
        cfg.time_limit_seconds is not None
        and (time.perf_counter() - start_time) >= cfg.time_limit_seconds
    ):
        return evaluate_position(state, maximizing_for, weights), []

    node_counter["count"] += 1

    if state.game_over or depth <= 0:
        if depth <= 0 and cfg.use_quiescence:
            tactical_moves = [
                move
                for move in _ordered_moves(state)
                if move.action == "play" and move.use_hero
            ]
            if tactical_moves:
                best_q = -math.inf
                best_line_q: list[Move] = []
                for move in tactical_moves[:3]:
                    try:
                        child = apply_move(state, move)
                    except InvalidMoveError:
                        continue
                    score, line = _alpha_beta(
                        child,
                        0,
                        alpha,
                        beta,
                        maximizing_for,
                        weights,
                        transposition,
                        node_counter,
                        EngineConfig(
                            search_depth=0,
                            num_determinizations=cfg.num_determinizations,
                            time_limit_seconds=cfg.time_limit_seconds,
                            max_nodes=cfg.max_nodes,
                            use_transposition_table=cfg.use_transposition_table,
                            use_quiescence=False,
                            random_seed=cfg.random_seed,
                            eval_weights=cfg.eval_weights,
                            risk_profile=cfg.risk_profile,
                        ),
                        start_time,
                    )
                    if state.current_player == maximizing_for:
                        if score > best_q:
                            best_q = score
                            best_line_q = [move] + line
                        alpha = max(alpha, best_q)
                    else:
                        if -score > best_q:
                            best_q = -score
                            best_line_q = [move] + line
                        beta = min(beta, -best_q)
                    if beta <= alpha:
                        break
                if best_line_q:
                    return best_q, best_line_q
        return evaluate_position(state, maximizing_for, weights), []

    key = _state_hash(state, maximizing_for)
    if transposition is not None and key in transposition:
        cached_depth, cached_score = transposition[key]
        if cached_depth >= depth:
            return cached_score, []

    is_max = state.current_player == maximizing_for
    best_score = -math.inf if is_max else math.inf
    best_line: list[Move] = []

    for move in _ordered_moves(state):
        try:
            child = apply_move(state, move)
        except InvalidMoveError:
            continue
        child_score, child_line = _alpha_beta(
            child,
            depth - 1,
            alpha,
            beta,
            maximizing_for,
            weights,
            transposition,
            node_counter,
            cfg,
            start_time,
        )
        if is_max:
            if child_score > best_score:
                best_score = child_score
                best_line = [move] + child_line
            alpha = max(alpha, best_score)
        else:
            if child_score < best_score:
                best_score = child_score
                best_line = [move] + child_line
            beta = min(beta, best_score)
        if beta <= alpha:
            break

    if transposition is not None:
        transposition[key] = (depth, best_score)
    return best_score, best_line


def _classify_moves(
    move_scores: dict[str, float],
    best_key: str,
    *,
    blunder_drop: float,
    inaccuracy_drop: float,
) -> dict[str, str]:
    if not move_scores:
        return {}
    best_score = move_scores[best_key]
    sorted_scores = sorted(move_scores.values(), reverse=True)
    second = sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]
    classifications: dict[str, str] = {}
    for key, score in move_scores.items():
        drop = best_score - score
        if key == best_key:
            if best_score - second >= 1.2 and best_score > 0.8:
                classifications[key] = "brilliant"
            else:
                classifications[key] = "best"
            continue
        if drop > blunder_drop:
            classifications[key] = "blunder"
        elif drop > inaccuracy_drop:
            classifications[key] = "inaccuracy"
        elif drop <= inaccuracy_drop / 2:
            classifications[key] = "good"
        else:
            classifications[key] = "good"
    return classifications


def _risk_adjust(score: float, config: EngineConfig) -> float:
    if config.risk_profile == "aggressive":
        return score * 1.05
    if config.risk_profile == "defensive":
        return score * 0.95
    return score


def find_best_move(state: BoardState, config: EngineConfig) -> EngineResult:
    start = time.perf_counter()
    rng = random.Random(config.random_seed)
    weights = config.resolved_weights()
    legal_entries = get_legal_moves(state)
    root_moves = [entry.move for entry in legal_entries]
    move_scores: dict[str, float] = {}
    pv_by_move: dict[str, list[Move]] = {}

    if not root_moves:
        return EngineResult(
            best_move=None,
            expected_score=0.0,
            principal_variation=[],
            move_evaluations={},
            move_classifications={},
            diagnostics={"nodes": 0, "elapsed_ms": 0, "determinizations": 0},
        )

    sampled_worlds: list[BoardState] = []
    trials = max(1, config.num_determinizations)
    for _ in range(trials):
        if config.time_limit_seconds is not None:
            if (time.perf_counter() - start) >= config.time_limit_seconds:
                break
        sampled_worlds.append(sample_opponent_hand(state, rng=rng))

    total_nodes = 0
    completed_trials_by_move: dict[str, int] = {}
    for move in root_moves:
        key = _move_key(move)
        acc = 0.0
        line_acc: list[Move] = []
        completed_trials = 0
        for sampled_world in sampled_worlds:
            sampled = sampled_world.copy()
            try:
                child = apply_move(sampled, move)
            except InvalidMoveError:
                continue

            transposition: dict[str, tuple[int, float]] | None
            if config.use_transposition_table:
                transposition = {}
            else:
                transposition = None

            node_counter = {"count": 0}
            best_local_score = -math.inf
            best_local_line: list[Move] = []
            for depth in range(1, max(1, config.search_depth) + 1):
                score, line = _alpha_beta(
                    child,
                    depth - 1,
                    -math.inf,
                    math.inf,
                    state.current_player,
                    weights,
                    transposition,
                    node_counter,
                    config,
                    start,
                )
                best_local_score = score
                best_local_line = line
                if config.time_limit_seconds is not None:
                    if (time.perf_counter() - start) >= config.time_limit_seconds:
                        break
                if (
                    config.max_nodes is not None
                    and node_counter["count"] >= config.max_nodes
                ):
                    break

            acc += _risk_adjust(best_local_score, config)
            completed_trials += 1
            if len(best_local_line) > len(line_acc):
                line_acc = best_local_line
            total_nodes += node_counter["count"]

            if config.time_limit_seconds is not None:
                if (time.perf_counter() - start) >= config.time_limit_seconds:
                    break

        completed_trials_by_move[key] = completed_trials
        if completed_trials == 0:
            move_scores[key] = float("-inf")
        else:
            move_scores[key] = acc / float(completed_trials)
        pv_by_move[key] = [move] + line_acc

    best_key = max(move_scores.items(), key=lambda item: item[1])[0]
    best_move = next(move for move in root_moves if _move_key(move) == best_key)
    move_classifications = _classify_moves(
        move_scores,
        best_key,
        blunder_drop=1.5,
        inaccuracy_drop=0.6,
    )
    pv = [_move_to_dict(move) for move in pv_by_move.get(best_key, [best_move])]

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return EngineResult(
        best_move=_move_to_dict(best_move),
        expected_score=move_scores[best_key],
        principal_variation=pv,
        move_evaluations={k: float(v) for k, v in move_scores.items()},
        move_classifications=move_classifications,
        diagnostics={
            "nodes": total_nodes,
            "elapsed_ms": elapsed_ms,
            "determinizations": len(sampled_worlds),
            "completed_trials_by_move": completed_trials_by_move,
            "depth": config.search_depth,
            "risk_profile": config.risk_profile,
        },
    )


def _move_from_dict(payload: dict[str, Any]) -> Move:
    return Move(
        action=str(payload.get("action", "play")),
        card_index=(
            int(payload["card_index"])
            if payload.get("card_index") is not None
            else None
        ),
        use_hero=bool(payload.get("use_hero", False)),
    )


def _position_snapshot(state: BoardState) -> dict[str, object]:
    return {
        "board": [[int(cell) for cell in row] for row in state.grid],
        "crown_pos": [int(state.king_position[1]), int(state.king_position[0])],
        "current_turn": state.current_player.value,
        "game_over": bool(state.game_over),
    }


def analyze_game(
    initial_state: BoardState,
    move_history: list[dict[str, Any]],
    config: EngineConfig,
) -> AnalysisReport:
    state = initial_state.copy()
    initial_position = _position_snapshot(state)
    positions: list[dict[str, object]] = []
    timeline: list[float] = []
    moves: list[AnalysisMove] = []
    alternatives: list[list[dict[str, Any]]] = []
    largest_blunder: dict[str, Any] | None = None
    most_brilliant: dict[str, Any] | None = None

    accuracy_penalty: dict[PlayerColor, float] = {
        PlayerColor.RED: 0.0,
        PlayerColor.WHITE: 0.0,
    }
    move_counts: dict[PlayerColor, int] = {
        PlayerColor.RED: 0,
        PlayerColor.WHITE: 0,
    }

    for ply, raw_move in enumerate(move_history, start=1):
        side = state.current_player
        result = find_best_move(state, config)
        chosen = _move_from_dict(raw_move)
        chosen_key = _move_key(chosen)
        chosen_eval = result.move_evaluations.get(
            chosen_key, result.expected_score - 2.0
        )
        best_eval = result.expected_score
        drop = max(0.0, best_eval - chosen_eval)

        best_key = None
        if result.best_move is not None:
            best_key = _move_key(_move_from_dict(result.best_move))
        label = result.move_classifications.get(chosen_key, "good")
        if best_key is not None and chosen_key == best_key and label != "brilliant":
            label = "best"

        loss_points = min(100.0, drop * 16.0)
        accuracy_penalty[side] += loss_points
        move_counts[side] += 1

        move_record = AnalysisMove(
            ply=ply,
            side_to_move=side.value,
            chosen_move=_move_to_dict(chosen),
            best_move=result.best_move,
            chosen_score=chosen_eval,
            best_score=best_eval,
            classification=label,
            best_line=result.principal_variation,
        )
        moves.append(move_record)
        alternatives.append(result.principal_variation)
        timeline.append(chosen_eval)

        if label == "blunder":
            if largest_blunder is None or drop > float(largest_blunder["drop"]):
                largest_blunder = {
                    "ply": ply,
                    "side": side.value,
                    "move": _move_to_dict(chosen),
                    "drop": drop,
                }
        if label == "brilliant":
            most_brilliant = {
                "ply": ply,
                "side": side.value,
                "move": _move_to_dict(chosen),
            }

        try:
            state = apply_move(state, chosen)
            positions.append(_position_snapshot(state))
        except InvalidMoveError:
            break

    accuracy_by_player = {}
    for color in (PlayerColor.RED, PlayerColor.WHITE):
        count = max(1, move_counts[color])
        accuracy = max(0.0, 100.0 - (accuracy_penalty[color] / float(count)))
        accuracy_by_player[color.value] = round(accuracy, 2)

    return AnalysisReport(
        moves=moves,
        initial_position=initial_position,
        positions=positions,
        score_timeline=timeline,
        classifications=[move.classification for move in moves],
        alternatives=alternatives,
        accuracy_by_player=accuracy_by_player,
        largest_blunder=largest_blunder,
        most_brilliant_move=most_brilliant,
    )
