from backend.app.api.rooms import GameEngine
from backend.app.engine.board import Direction, PlayerColor, PowerCard


def test_forced_pass_advances_turn_not_immediate_game_over() -> None:
    engine = GameEngine(seed=1)
    engine.state.current_player = PlayerColor.RED
    engine.state.draw_pile = [PowerCard(direction=Direction.E, distance=1)]
    engine.state.players[PlayerColor.RED].power_cards = [
        PowerCard(direction=Direction.N, distance=1),
        PowerCard(direction=Direction.N, distance=2),
        PowerCard(direction=Direction.N, distance=3),
        PowerCard(direction=Direction.NW, distance=1),
        PowerCard(direction=Direction.W, distance=1),
    ]
    engine.state.players[PlayerColor.RED].hero_cards = 0
    engine.state.players[PlayerColor.WHITE].power_cards = [
        PowerCard(direction=Direction.N, distance=1),
    ]
    engine.state.players[PlayerColor.WHITE].hero_cards = 0
    engine.state.king_position = (0, 0)

    engine.refresh_game_over()

    assert engine.state.current_player == PlayerColor.WHITE
    assert engine.state.game_over is False


def test_game_over_after_both_players_forced_to_pass() -> None:
    engine = GameEngine(seed=1)
    engine.state.current_player = PlayerColor.RED
    engine.state.draw_pile = []
    engine.state.players[PlayerColor.RED].power_cards = [
        PowerCard(direction=Direction.N, distance=1),
    ]
    engine.state.players[PlayerColor.WHITE].power_cards = [
        PowerCard(direction=Direction.N, distance=1),
    ]
    engine.state.players[PlayerColor.RED].hero_cards = 0
    engine.state.players[PlayerColor.WHITE].hero_cards = 0
    engine.state.king_position = (0, 0)

    engine.refresh_game_over()
    engine.refresh_game_over()

    assert engine.state.game_over is True
