from backend.app.api.rooms import GameEngine
from backend.app.engine.board import Direction, PlayerColor, PowerCard


def test_game_not_over_if_current_player_can_still_draw() -> None:
    engine = GameEngine()

    engine.state.current_player = PlayerColor.RED
    engine.state.players[PlayerColor.RED].power_cards = [
        PowerCard(direction=Direction.N, distance=1),
        PowerCard(direction=Direction.N, distance=2),
    ]
    engine.state.king_position = (0, 0)
    engine._draw_pile = [PowerCard(direction=Direction.E, distance=1)]

    engine.refresh_game_over()

    assert engine.state.game_over is False


def test_game_over_when_current_player_has_full_hand_and_no_legal_move() -> None:
    engine = GameEngine()

    engine.state.current_player = PlayerColor.RED
    engine.state.players[PlayerColor.RED].power_cards = [
        PowerCard(direction=Direction.N, distance=1),
        PowerCard(direction=Direction.N, distance=2),
        PowerCard(direction=Direction.NW, distance=1),
        PowerCard(direction=Direction.W, distance=1),
        PowerCard(direction=Direction.W, distance=2),
    ]
    engine.state.king_position = (0, 0)
    engine._draw_pile = [PowerCard(direction=Direction.E, distance=1)]

    engine.refresh_game_over()

    assert engine.state.game_over is True
