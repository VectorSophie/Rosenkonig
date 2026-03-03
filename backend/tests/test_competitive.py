from backend.app.engine.board import (
    Direction,
    Move,
    PlayerColor,
    PowerCard,
    create_initial_state,
)
from backend.app.engine.competitive import EngineConfig, analyze_game, find_best_move
from backend.app.engine.logic import apply_move


def test_find_best_move_returns_ranked_moves() -> None:
    state = create_initial_state(
        red_power_cards=[
            PowerCard(direction=Direction.E, distance=1),
            PowerCard(direction=Direction.S, distance=1),
        ],
        white_power_cards=[PowerCard(direction=Direction.W, distance=1)],
        shuffled_deck=[PowerCard(direction=Direction.N, distance=1)],
    )

    result = find_best_move(state, EngineConfig(search_depth=2, num_determinizations=4))

    assert result.best_move is not None
    assert len(result.move_evaluations) > 0
    assert len(result.move_classifications) == len(result.move_evaluations)
    assert result.diagnostics["nodes"] >= 1


def test_analyze_game_produces_timeline_and_accuracy() -> None:
    initial = create_initial_state(
        red_power_cards=[PowerCard(direction=Direction.E, distance=1)],
        white_power_cards=[PowerCard(direction=Direction.W, distance=1)],
        shuffled_deck=[],
    )
    state = apply_move(initial, Move(action="play", card_index=0))
    state = apply_move(state, Move(action="play", card_index=0))

    report = analyze_game(
        initial,
        move_history=[
            {"action": "play", "card_index": 0, "use_hero": False},
            {"action": "play", "card_index": 0, "use_hero": False},
        ],
        config=EngineConfig(search_depth=1, num_determinizations=2),
    )

    assert len(report.moves) >= 1
    assert len(report.score_timeline) == len(report.moves)
    assert PlayerColor.RED.value in report.accuracy_by_player
    assert PlayerColor.WHITE.value in report.accuracy_by_player
