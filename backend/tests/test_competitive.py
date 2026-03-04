from backend.app.engine.board import (
    CellState,
    Direction,
    Move,
    PlayerColor,
    PowerCard,
    create_initial_state,
)
from backend.app.engine.competitive import (
    EngineConfig,
    EvalBreakdown,
    SearchContext,
    analyze_game,
    explain_move,
    find_best_move,
)
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


def test_region_merge_explanation_mentions_connection() -> None:
    state = create_initial_state(
        red_power_cards=[PowerCard(direction=Direction.E, distance=1)],
        white_power_cards=[PowerCard(direction=Direction.W, distance=1)],
        shuffled_deck=[],
    )
    state.king_position = (5, 4)
    state.grid[4][5] = CellState.RED
    state.grid[5][6] = CellState.RED

    result = find_best_move(state, EngineConfig(search_depth=1, num_determinizations=1))
    move_key = "play:0:0"
    explanation = result.move_explanations[move_key]

    assert "connects two regions" in explanation.summary.lower() or any(
        "connects two regions" in factor.lower() for factor in explanation.key_factors
    )


def test_mobility_drop_explanation_mentions_reduced_flexibility() -> None:
    state = create_initial_state(
        red_power_cards=[PowerCard(direction=Direction.NW, distance=1)],
        white_power_cards=[PowerCard(direction=Direction.S, distance=1)],
        shuffled_deck=[],
    )
    state.king_position = (1, 1)

    after_state = apply_move(state, Move(action="play", card_index=0, use_hero=False))
    explanation = explain_move(
        before_state=state,
        after_state=after_state,
        eval_before=EvalBreakdown(
            total=0.0,
            region_score_diff=0.0,
            expansion_score=0.0,
            mobility_score=1.0,
            crown_centrality=0.0,
            hero_threat_adjustment=0.0,
            stone_scarcity_pressure=0.0,
        ),
        eval_after=EvalBreakdown(
            total=-1.0,
            region_score_diff=0.0,
            expansion_score=0.0,
            mobility_score=-1.0,
            crown_centrality=0.0,
            hero_threat_adjustment=0.0,
            stone_scarcity_pressure=0.0,
        ),
        search_context=SearchContext(
            move_key="play:0:0",
            principal_variation=[Move(action="play", card_index=0, use_hero=False)],
            search_depth=1,
            score_variance=0.1,
            completed_trials=1,
            determinizations=1,
        ),
    )

    assert any(
        "narrow lane" in factor.lower() or "flexibility" in factor.lower()
        for factor in explanation.key_factors
    )


def test_high_variance_move_is_marked_high_risk() -> None:
    state = create_initial_state(
        red_power_cards=[PowerCard(direction=Direction.E, distance=1)],
        white_power_cards=[PowerCard(direction=Direction.W, distance=1)],
        shuffled_deck=[],
    )

    after_state = apply_move(state, Move(action="play", card_index=0, use_hero=False))
    explanation = explain_move(
        before_state=state,
        after_state=after_state,
        eval_before=EvalBreakdown(
            total=0.0,
            region_score_diff=0.0,
            expansion_score=0.0,
            mobility_score=0.0,
            crown_centrality=0.0,
            hero_threat_adjustment=0.0,
            stone_scarcity_pressure=0.0,
        ),
        eval_after=EvalBreakdown(
            total=0.2,
            region_score_diff=0.0,
            expansion_score=0.0,
            mobility_score=0.0,
            crown_centrality=0.0,
            hero_threat_adjustment=0.0,
            stone_scarcity_pressure=0.0,
        ),
        search_context=SearchContext(
            move_key="play:0:0",
            principal_variation=[Move(action="play", card_index=0, use_hero=False)],
            search_depth=2,
            score_variance=0.95,
            completed_trials=8,
            determinizations=8,
        ),
    )

    assert explanation.risk_level == "high"
