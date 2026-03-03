from backend.app.engine.board import (
    CellState,
    Direction,
    Move,
    PlayerColor,
    PowerCard,
    create_initial_state,
    official_power_deck,
)
from backend.app.engine.logic import (
    InvalidMoveError,
    apply_move,
    calculate_scores,
    get_legal_moves,
    undo_move,
    validate_move,
)


def test_official_power_deck_has_24_unique_cards() -> None:
    deck = official_power_deck()
    assert len(deck) == 24
    assert len({(card.direction, card.distance) for card in deck}) == 24


def test_play_move_places_stone_consumes_card_and_advances_turn() -> None:
    red_card = PowerCard(direction=Direction.E, distance=1)
    white_card = PowerCard(direction=Direction.W, distance=1)
    state = create_initial_state(
        red_power_cards=[red_card], white_power_cards=[white_card]
    )

    next_state = apply_move(state=state, move=Move(action="play", card_index=0))

    assert state.king_position == (5, 5)
    assert next_state.king_position == (5, 6)
    assert next_state.grid[5][6] == CellState.RED
    assert red_card not in next_state.players[PlayerColor.RED].power_cards
    assert next_state.players[PlayerColor.RED].stones_remaining == 25
    assert next_state.current_player == PlayerColor.WHITE


def test_hero_move_flips_opponent_and_consumes_hero_not_stone() -> None:
    red_card = PowerCard(direction=Direction.E, distance=1)
    state = create_initial_state(
        red_power_cards=[red_card],
        white_power_cards=[PowerCard(direction=Direction.W, distance=1)],
    )
    state.grid[5][6] = CellState.WHITE

    without_hero = validate_move(state=state, move=Move(action="play", card_index=0))
    assert without_hero.is_valid is False

    next_state = apply_move(
        state=state,
        move=Move(action="play", card_index=0, use_hero=True),
    )
    assert next_state.grid[5][6] == CellState.RED
    assert next_state.players[PlayerColor.RED].hero_cards == 3
    assert next_state.players[PlayerColor.RED].stones_remaining == 26


def test_draw_is_a_turn_and_requires_hand_below_five() -> None:
    deck = [PowerCard(direction=Direction.N, distance=1)]
    state = create_initial_state(shuffled_deck=deck)
    state.players[PlayerColor.RED].power_cards = [
        PowerCard(direction=Direction.E, distance=1),
        PowerCard(direction=Direction.W, distance=1),
    ]

    next_state = apply_move(state=state, move=Move(action="draw"))
    assert len(next_state.players[PlayerColor.RED].power_cards) == 3
    assert next_state.current_player == PlayerColor.WHITE


def test_pass_only_legal_when_no_draw_or_play_exists() -> None:
    state = create_initial_state(shuffled_deck=[])
    state.current_player = PlayerColor.RED
    state.players[PlayerColor.RED].power_cards = [
        PowerCard(direction=Direction.N, distance=1),
    ]
    state.king_position = (0, 0)
    state.players[PlayerColor.RED].hero_cards = 0

    legal = get_legal_moves(state)
    assert len(legal) == 1
    assert legal[0].move.action == "pass"


def test_game_ends_after_two_consecutive_passes() -> None:
    state = create_initial_state(shuffled_deck=[])
    state.players[PlayerColor.RED].power_cards = [
        PowerCard(direction=Direction.N, distance=1),
    ]
    state.players[PlayerColor.WHITE].power_cards = [
        PowerCard(direction=Direction.N, distance=1),
    ]
    state.players[PlayerColor.RED].hero_cards = 0
    state.players[PlayerColor.WHITE].hero_cards = 0
    state.king_position = (0, 0)

    after_red_pass = apply_move(state, Move(action="pass"))
    after_white_pass = apply_move(after_red_pass, Move(action="pass"))
    assert after_white_pass.game_over is True


def test_calculate_scores_sums_square_of_connected_group_sizes() -> None:
    state = create_initial_state(shuffled_deck=[])

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


def test_undo_move_restores_previous_state() -> None:
    red_card = PowerCard(direction=Direction.E, distance=1)
    state = create_initial_state(red_power_cards=[red_card], white_power_cards=[])
    moved = apply_move(state, Move(action="play", card_index=0))
    restored = undo_move(moved)

    assert restored.king_position == state.king_position
    assert restored.grid == state.grid
    assert len(restored.players[PlayerColor.RED].power_cards) == 1


def test_invalid_move_raises() -> None:
    state = create_initial_state(shuffled_deck=[])
    state.players[PlayerColor.RED].power_cards = []

    try:
        _ = apply_move(state=state, move=Move(action="play", card_index=0))
        assert False
    except InvalidMoveError as error:
        assert "card_index" in str(error)
