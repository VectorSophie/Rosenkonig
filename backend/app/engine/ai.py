from __future__ import annotations

import random
from collections import deque

from .board import BOARD_SIZE, BoardState, CellState, Move, PlayerColor, opponent
from .logic import apply_move, calculate_scores, get_legal_moves


def _largest_group_size(grid: list[list[int]], cell: CellState) -> int:
    visited: set[tuple[int, int]] = set()
    best = 0

    deltas = (
        (-1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
        (1, 0),
        (1, -1),
        (0, -1),
        (-1, -1),
    )

    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if grid[r][c] != cell or (r, c) in visited:
                continue

            queue: deque[tuple[int, int]] = deque([(r, c)])
            visited.add((r, c))
            size = 0

            while queue:
                cr, cc = queue.popleft()
                size += 1
                for dr, dc in deltas:
                    nr, nc = cr + dr, cc + dc
                    if nr < 0 or nr >= BOARD_SIZE or nc < 0 or nc >= BOARD_SIZE:
                        continue
                    if (nr, nc) in visited:
                        continue
                    if grid[nr][nc] != cell:
                        continue
                    visited.add((nr, nc))
                    queue.append((nr, nc))

            best = max(best, size)

    return best


def _center_control(
    grid: list[list[int]], my_cell: CellState, opp_cell: CellState
) -> int:
    score = 0
    for r in range(4, 7):
        for c in range(4, 7):
            if grid[r][c] == my_cell:
                score += 2
            elif grid[r][c] == opp_cell:
                score -= 2
    return score


def _piece_count(grid: list[list[int]]) -> int:
    return sum(
        1 for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if grid[r][c] != 0
    )


def evaluate_state(state: BoardState, player: PlayerColor) -> float:
    scores = calculate_scores(state)
    opp = opponent(player)
    score_diff = scores[player] - scores[opp]

    my_cell = CellState.RED if player is PlayerColor.RED else CellState.WHITE
    opp_cell = CellState.WHITE if player is PlayerColor.RED else CellState.RED
    my_max_group = _largest_group_size(state.grid, my_cell)

    total_pieces = _piece_count(state.grid)
    center_score = (
        _center_control(state.grid, my_cell, opp_cell) if total_pieces < 20 else 0
    )

    opp_turn: BoardState = state.copy()
    opp_turn.current_player = opp
    opp_mobility = len(get_legal_moves(opp_turn))

    return (
        (score_diff * 1.0)
        + (my_max_group * 5.0)
        + (center_score * 1.5)
        - (opp_mobility * 0.25)
    )


def choose_ai_move(state: BoardState) -> Move | None:
    """Pick a move for the *current* player using a 1-ply heuristic."""
    legal = get_legal_moves(state)
    if not legal:
        return None

    player = state.current_player
    best_score = float("-inf")
    best: list[Move] = []

    for legal_move in legal:
        if legal_move.move.action != "play":
            continue
        try:
            next_state = apply_move(state=state, move=legal_move.move)
        except Exception:
            continue
        score = evaluate_state(next_state, player)
        if score > best_score:
            best_score = score
            best = [legal_move.move]
        elif score == best_score:
            best.append(legal_move.move)

    return random.choice(best) if best else None
