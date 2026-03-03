from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .board import (
    BOARD_SIZE,
    MAX_HAND_SIZE,
    POWER_STONES_PER_PLAYER,
    CellState,
    DIRECTION_DELTAS,
    BoardState,
    Move,
    PlayerColor,
    PowerCard,
    cell_for_player,
    is_in_bounds,
    opponent,
    state_from_dict,
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
    move: Move
    target: tuple[int, int] | None = None


def compute_target_position(
    king_position: tuple[int, int],
    card: PowerCard,
) -> tuple[int, int]:
    # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
    # "The crown token is moved from its current space in the direction and by the number of spaces (1, 2, or 3) indicated on the card."
    # Implementation: Translate king position by card direction delta multiplied by card distance.
    delta_row, delta_column = DIRECTION_DELTAS[card.direction]
    row, column = king_position
    return row + delta_row * card.distance, column + delta_column * card.distance


def can_draw(state: BoardState, player: PlayerColor) -> bool:
    # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
    # "Draw a power card ... This is only possible if the player has fewer than five cards."
    # Implementation: Drawing is legal only when hand size is below 5 and draw pile is non-empty.
    hand = state.players[player].power_cards
    return len(hand) < MAX_HAND_SIZE and bool(state.draw_pile)


def _validate_play_move(
    state: BoardState, move: Move, player: PlayerColor
) -> MoveValidation:
    if move.card_index is None:
        return MoveValidation(is_valid=False, reason="card_index is required for play")

    player_resources = state.players[player]
    if move.card_index < 0 or move.card_index >= len(player_resources.power_cards):
        return MoveValidation(is_valid=False, reason="card_index out of range")

    if player_resources.stones_remaining <= 0:
        # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
        # "52 double-sided markers" (finite component inventory)
        # Implementation: Empty-square placement is blocked when the player has no stones left.
        return MoveValidation(is_valid=False, reason="no stones remaining")

    card = player_resources.power_cards[move.card_index]
    target = compute_target_position(state.king_position, card)
    if not is_in_bounds(target):
        return MoveValidation(
            is_valid=False, target=target, reason="move goes out of bounds"
        )

    row, column = target
    target_cell = state.grid[row][column]
    player_cell = cell_for_player(player)
    opponent_cell = cell_for_player(opponent(player))

    if target_cell == CellState.EMPTY:
        if move.use_hero:
            return MoveValidation(
                is_valid=False,
                target=target,
                reason="hero card can only be used to flip an opponent stone",
            )
        return MoveValidation(is_valid=True, target=target)

    if target_cell == player_cell:
        return MoveValidation(
            is_valid=False,
            target=target,
            reason="cannot land on your own stone",
        )

    if target_cell == opponent_cell:
        # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
        # "A player can play a hero card together with a power card... [to] a space already occupied by an opponent's power token."
        # Implementation: Occupied-opponent targets are legal only with use_hero and available hero cards.
        if not move.use_hero:
            return MoveValidation(
                is_valid=False,
                target=target,
                reason="landing on an opponent stone requires a hero card",
            )
        if player_resources.hero_cards <= 0:
            return MoveValidation(
                is_valid=False,
                target=target,
                reason="no hero cards remaining",
            )
        return MoveValidation(is_valid=True, target=target)

    return MoveValidation(is_valid=False, target=target, reason="invalid target cell")


def validate_move(
    state: BoardState,
    move: Move,
    player: PlayerColor | None = None,
) -> MoveValidation:
    if state.game_over:
        return MoveValidation(is_valid=False, reason="game is already over")

    active_player = state.current_player if player is None else player
    if active_player != state.current_player:
        return MoveValidation(is_valid=False, reason="it is not this player's turn")

    if move.action == "play":
        return _validate_play_move(state, move, active_player)

    if move.action == "draw":
        if can_draw(state, active_player):
            return MoveValidation(is_valid=True)
        return MoveValidation(is_valid=False, reason="draw is not legal")

    if move.action == "pass":
        # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
        # "If a player cannot perform any of the three options, he or she must pass."
        # Implementation: Pass is legal only when no play move and no draw option exists.
        any_play = _has_any_play_move(state, active_player)
        if any_play or can_draw(state, active_player):
            return MoveValidation(
                is_valid=False, reason="pass is only legal when no action is available"
            )
        return MoveValidation(is_valid=True)

    return MoveValidation(is_valid=False, reason="unknown action")


def _has_any_play_move(state: BoardState, player: PlayerColor) -> bool:
    cards = state.players[player].power_cards
    for card_index in range(len(cards)):
        if _validate_play_move(
            state=state,
            move=Move(action="play", card_index=card_index, use_hero=False),
            player=player,
        ).is_valid:
            return True
        if _validate_play_move(
            state=state,
            move=Move(action="play", card_index=card_index, use_hero=True),
            player=player,
        ).is_valid:
            return True
    return False


def get_legal_moves(
    state: BoardState,
    player: PlayerColor | None = None,
) -> list[LegalMove]:
    active_player = state.current_player if player is None else player
    if state.game_over:
        return []
    if active_player != state.current_player:
        return []

    legal_moves: list[LegalMove] = []
    cards = state.players[active_player].power_cards
    for card_index in range(len(cards)):
        normal_move = Move(action="play", card_index=card_index, use_hero=False)
        normal_validation = validate_move(
            state=state, move=normal_move, player=active_player
        )
        if normal_validation.is_valid:
            legal_moves.append(
                LegalMove(move=normal_move, target=normal_validation.target)
            )

        hero_move = Move(action="play", card_index=card_index, use_hero=True)
        hero_validation = validate_move(
            state=state, move=hero_move, player=active_player
        )
        if hero_validation.is_valid:
            legal_moves.append(LegalMove(move=hero_move, target=hero_validation.target))

    draw_move = Move(action="draw")
    if validate_move(state=state, move=draw_move, player=active_player).is_valid:
        legal_moves.append(LegalMove(move=draw_move))

    if not legal_moves and not can_draw(state, active_player):
        legal_moves.append(LegalMove(move=Move(action="pass")))

    return legal_moves


def list_legal_moves(
    state: BoardState,
    player: PlayerColor | None = None,
) -> list[LegalMove]:
    return get_legal_moves(state=state, player=player)


def _apply_play(next_state: BoardState, move: Move, active_player: PlayerColor) -> None:
    if move.card_index is None:
        raise InvalidMoveError("card_index is required")

    player_resources = next_state.players[active_player]
    card = player_resources.power_cards.pop(move.card_index)
    next_state.discard_pile.append(card)

    target = compute_target_position(next_state.king_position, card)
    row, column = target
    target_cell = next_state.grid[row][column]

    if target_cell != CellState.EMPTY:
        player_resources.hero_cards -= 1
    else:
        # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
        # "The target space must be empty ... the player places one of his or her power tokens on the target space."
        # Implementation: Empty-target placement consumes one finite stone from player inventory.
        player_resources.stones_remaining -= 1

    next_state.grid[row][column] = cell_for_player(active_player)
    next_state.king_position = target
    next_state.consecutive_passes = 0


def _apply_draw(next_state: BoardState, active_player: PlayerColor) -> None:
    card = next_state.draw_pile.pop()
    next_state.players[active_player].power_cards.append(card)
    next_state.consecutive_passes = 0


def _apply_pass(next_state: BoardState) -> None:
    next_state.consecutive_passes += 1


def _update_game_over(next_state: BoardState) -> None:
    stones_used = sum(
        POWER_STONES_PER_PLAYER - next_state.players[color].stones_remaining
        for color in PlayerColor
    )
    # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
    # "The game ends when: All 52 power tokens have been placed OR neither player can make a move."
    # Implementation: End game at 52 placements, or after both players are forced to pass consecutively.
    if stones_used >= 52:
        next_state.game_over = True
        return
    if next_state.consecutive_passes >= 2:
        next_state.game_over = True


def apply_move(state: BoardState, move: Move) -> BoardState:
    validation = validate_move(state=state, move=move)
    if not validation.is_valid:
        reason = validation.reason if validation.reason is not None else "invalid move"
        raise InvalidMoveError(reason)

    next_state = state.copy()
    next_state.history.append(state.to_dict())
    next_state.move_history.append(
        {
            "action": move.action,
            "card_index": move.card_index,
            "use_hero": move.use_hero,
        }
    )
    active_player = next_state.current_player

    if move.action == "play":
        _apply_play(next_state, move, active_player)
    elif move.action == "draw":
        _apply_draw(next_state, active_player)
    elif move.action == "pass":
        _apply_pass(next_state)
    else:
        raise InvalidMoveError("unknown action")

    next_state.current_player = opponent(active_player)
    _update_game_over(next_state)
    return next_state


def undo_move(state: BoardState, _move: Move | None = None) -> BoardState:
    if not state.history:
        raise InvalidMoveError("no move to undo")
    previous_raw = state.history[-1]
    restored = state_from_dict(previous_raw)
    restored.history = state.history[:-1]
    return restored


def is_game_over(state: BoardState) -> bool:
    return state.game_over


def calculate_scores(state: BoardState) -> dict[PlayerColor, int]:
    # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
    # "The number of tokens in each area is multiplied by itself (squared)."
    # Implementation: Score equals sum of n^2 for all orthogonally-connected regions per player.
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


def evaluate_position(_state: BoardState) -> float:
    # Source: 691790_theroseking_manual.pdf (no AI heuristic section)
    # "The winner ... [is] player with the largest contiguous areas..."
    # Implementation: Stub kept intentionally neutral until an official AI evaluation spec exists.
    return 0.0


def determine_winner(state: BoardState) -> PlayerColor | None:
    # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
    # "The winner of the game is the player with the largest contiguous areas marked with his color of Rose."
    # Implementation: Return higher score color; return None on equal scores because no official tie-breaker is specified.
    scores = calculate_scores(state)
    if scores[PlayerColor.RED] > scores[PlayerColor.WHITE]:
        return PlayerColor.RED
    if scores[PlayerColor.WHITE] > scores[PlayerColor.RED]:
        return PlayerColor.WHITE
    return None
