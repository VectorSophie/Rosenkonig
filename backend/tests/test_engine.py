from backend.app.engine.board import (
    CellState,
    Direction,
    PlayerColor,
    PowerCard,
    create_initial_state,
)
from backend.app.engine.logic import (
    InvalidMoveError,
    apply_move,
    calculate_scores,
    is_game_over,
    validate_move,
)


def test_valid_move_places_rose_consumes_card_and_advances_turn() -> None:
    red_card = PowerCard(direction=Direction.E, distance=1)
    white_card = PowerCard(direction=Direction.W, distance=1)
    state = create_initial_state(
        red_power_cards=[red_card], white_power_cards=[white_card]
    )

    next_state = apply_move(state=state, card=red_card)

    assert state.king_position == (5, 5)
    assert next_state.king_position == (5, 6)
    assert next_state.grid[5][6] == CellState.RED
    assert red_card not in next_state.players[PlayerColor.RED].power_cards
    assert next_state.current_player == PlayerColor.WHITE
    assert next_state.game_over is False


def test_move_validation_rejects_out_of_bounds_and_missing_card() -> None:
    card = PowerCard(direction=Direction.N, distance=3)
    state = create_initial_state(red_power_cards=[card], white_power_cards=[])
    state.king_position = (1, 1)

    out_of_bounds = validate_move(state=state, card=card)
    assert out_of_bounds.is_valid is False
    assert out_of_bounds.reason == "Move goes out of bounds"

    missing_card = validate_move(
        state=state,
        card=PowerCard(direction=Direction.S, distance=1),
    )
    assert missing_card.is_valid is False
    assert missing_card.reason == "Player does not have this power card"


def test_hero_card_flips_opponent_rose_and_decrements_hero_cards() -> None:
    red_card = PowerCard(direction=Direction.E, distance=1)
    state = create_initial_state(
        red_power_cards=[red_card],
        white_power_cards=[PowerCard(direction=Direction.W, distance=1)],
    )
    state.grid[5][6] = CellState.WHITE

    without_hero = validate_move(state=state, card=red_card, use_hero=False)
    assert without_hero.is_valid is False
    assert without_hero.reason == "Landing on an opponent rose requires a hero card"

    next_state = apply_move(state=state, card=red_card, use_hero=True)

    assert next_state.grid[5][6] == CellState.RED
    assert next_state.players[state.current_player].hero_cards == 3


def test_apply_move_raises_for_invalid_move() -> None:
    state = create_initial_state(red_power_cards=[], white_power_cards=[])

    try:
        _ = apply_move(state=state, card=PowerCard(direction=Direction.N, distance=1))
        assert False
    except InvalidMoveError as error:
        assert str(error) == "Player does not have this power card"


def test_calculate_scores_sums_square_of_connected_group_sizes() -> None:
    state = create_initial_state(red_power_cards=[], white_power_cards=[])

    state.grid[1][1] = CellState.RED
    state.grid[1][2] = CellState.RED
    state.grid[2][2] = CellState.RED
    state.grid[8][8] = CellState.RED
    state.grid[9][9] = CellState.RED

    state.grid[0][10] = CellState.WHITE
    state.grid[5][5] = CellState.WHITE
    state.grid[5][6] = CellState.WHITE

    scores = calculate_scores(state)

    assert scores[PlayerColor.RED] == 11
    assert scores[PlayerColor.WHITE] == 5


def test_end_game_when_both_players_have_no_legal_moves() -> None:
    red_card = PowerCard(direction=Direction.E, distance=1)
    state = create_initial_state(red_power_cards=[red_card], white_power_cards=[])

    next_state = apply_move(state=state, card=red_card)

    assert is_game_over(next_state) is True
    assert next_state.game_over is True
