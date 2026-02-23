from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .board import (
    BOARD_SIZE,
    CellState,
    DIRECTION_DELTAS,
    BoardState,
    PlayerColor,
    PowerCard,
    cell_for_player,
    is_in_bounds,
    opponent,
)


ORTHOGONAL_DELTAS: tuple[tuple[int, int], ...] = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
)


class InvalidMoveError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MoveValidation:
    is_valid: bool
    target: tuple[int, int] | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class LegalMove:
    card: PowerCard
    target: tuple[int, int]
    use_hero: bool


def compute_target_position(
    king_position: tuple[int, int],
    card: PowerCard,
) -> tuple[int, int]:
    delta_row, delta_column = DIRECTION_DELTAS[card.direction]
    row, column = king_position
    return row + delta_row * card.distance, column + delta_column * card.distance


def validate_move(
    state: BoardState,
    card: PowerCard,
    use_hero: bool = False,
    player: PlayerColor | None = None,
) -> MoveValidation:
    if state.game_over:
        return MoveValidation(is_valid=False, reason="Game is already over")

    active_player = state.current_player if player is None else player

    if active_player != state.current_player:
        return MoveValidation(is_valid=False, reason="It is not this player's turn")

    player_resources = state.players[active_player]
    if card not in player_resources.power_cards:
        return MoveValidation(
            is_valid=False, reason="Player does not have this power card"
        )

    target = compute_target_position(state.king_position, card)
    if not is_in_bounds(target):
        return MoveValidation(
            is_valid=False, target=target, reason="Move goes out of bounds"
        )

    row, column = target
    target_cell = state.grid[row][column]
    player_cell = cell_for_player(active_player)
    opponent_cell = cell_for_player(opponent(active_player))

    if target_cell == CellState.EMPTY:
        if use_hero:
            return MoveValidation(
                is_valid=False,
                target=target,
                reason="Hero card can only be used to flip an opponent rose",
            )
        return MoveValidation(is_valid=True, target=target)

    if target_cell == player_cell:
        return MoveValidation(
            is_valid=False,
            target=target,
            reason="Cannot land on your own rose",
        )

    if target_cell == opponent_cell:
        if not use_hero:
            return MoveValidation(
                is_valid=False,
                target=target,
                reason="Landing on an opponent rose requires a hero card",
            )
        if player_resources.hero_cards <= 0:
            return MoveValidation(
                is_valid=False,
                target=target,
                reason="No hero cards remaining",
            )
        return MoveValidation(is_valid=True, target=target)

    return MoveValidation(is_valid=False, target=target, reason="Invalid target cell")


def list_legal_moves(
    state: BoardState,
    player: PlayerColor | None = None,
) -> list[LegalMove]:
    active_player = state.current_player if player is None else player
    if state.game_over:
        return []
    if active_player != state.current_player:
        return []

    legal_moves: list[LegalMove] = []
    for card in state.players[active_player].power_cards:
        normal_validation = validate_move(
            state=state, card=card, use_hero=False, player=active_player
        )
        if normal_validation.is_valid and normal_validation.target is not None:
            legal_moves.append(
                LegalMove(card=card, target=normal_validation.target, use_hero=False)
            )
            continue

        hero_validation = validate_move(
            state=state, card=card, use_hero=True, player=active_player
        )
        if hero_validation.is_valid and hero_validation.target is not None:
            legal_moves.append(
                LegalMove(card=card, target=hero_validation.target, use_hero=True)
            )

    return legal_moves


def apply_move(
    state: BoardState, card: PowerCard, use_hero: bool = False
) -> BoardState:
    validation = validate_move(state=state, card=card, use_hero=use_hero)
    if not validation.is_valid or validation.target is None:
        reason = validation.reason if validation.reason is not None else "Invalid move"
        raise InvalidMoveError(reason)

    next_state = state.copy()
    active_player = next_state.current_player
    player_resources = next_state.players[active_player]

    player_resources.power_cards.remove(card)

    row, column = validation.target
    target_cell = next_state.grid[row][column]
    if target_cell != CellState.EMPTY:
        player_resources.hero_cards -= 1

    next_state.grid[row][column] = cell_for_player(active_player)
    next_state.king_position = validation.target
    next_state.current_player = opponent(active_player)
    next_state.game_over = is_game_over(next_state)

    return next_state


def is_game_over(state: BoardState) -> bool:
    if state.game_over:
        return True

    red_turn = state.copy()
    red_turn.current_player = PlayerColor.RED
    if list_legal_moves(red_turn):
        return False

    white_turn = state.copy()
    white_turn.current_player = PlayerColor.WHITE
    return len(list_legal_moves(white_turn)) == 0


def calculate_scores(state: BoardState) -> dict[PlayerColor, int]:
    return {
        PlayerColor.RED: _calculate_player_score(state.grid, CellState.RED),
        PlayerColor.WHITE: _calculate_player_score(state.grid, CellState.WHITE),
    }


def _calculate_player_score(grid: list[list[int]], player_cell: CellState) -> int:
    visited: set[tuple[int, int]] = set()
    score = 0

    for row in range(BOARD_SIZE):
        for column in range(BOARD_SIZE):
            if grid[row][column] != player_cell or (row, column) in visited:
                continue
            group_size = _group_size(grid, row, column, player_cell, visited)
            score += group_size * group_size

    return score


def _group_size(
    grid: list[list[int]],
    start_row: int,
    start_column: int,
    player_cell: CellState,
    visited: set[tuple[int, int]],
) -> int:
    queue: deque[tuple[int, int]] = deque([(start_row, start_column)])
    visited.add((start_row, start_column))
    size = 0

    while queue:
        row, column = queue.popleft()
        size += 1

        for delta_row, delta_column in ORTHOGONAL_DELTAS:
            next_row = row + delta_row
            next_column = column + delta_column
            neighbor = (next_row, next_column)

            if not is_in_bounds(neighbor):
                continue
            if neighbor in visited:
                continue
            if grid[next_row][next_column] != player_cell:
                continue

            visited.add(neighbor)
            queue.append(neighbor)

    return size
