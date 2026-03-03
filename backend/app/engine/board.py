from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

BOARD_SIZE = 11
MIN_POWER_DISTANCE = 1
MAX_POWER_DISTANCE = 3
START_KING_POSITION = (BOARD_SIZE // 2, BOARD_SIZE // 2)
MAX_HAND_SIZE = 5
HERO_CARDS_PER_PLAYER = 4
TOTAL_POWER_STONES = 52
POWER_STONES_PER_PLAYER = TOTAL_POWER_STONES // 2


class PlayerColor(str, Enum):
    RED = "red"
    WHITE = "white"


class Direction(str, Enum):
    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"


DIRECTION_DELTAS: Mapping[Direction, tuple[int, int]] = {
    Direction.N: (-1, 0),
    Direction.NE: (-1, 1),
    Direction.E: (0, 1),
    Direction.SE: (1, 1),
    Direction.S: (1, 0),
    Direction.SW: (1, -1),
    Direction.W: (0, -1),
    Direction.NW: (-1, -1),
}


class CellState(int, Enum):
    EMPTY = 0
    RED = 1
    WHITE = 2


@dataclass(frozen=True, slots=True)
class PowerCard:
    direction: Direction
    distance: int

    def __post_init__(self) -> None:
        if self.distance < MIN_POWER_DISTANCE or self.distance > MAX_POWER_DISTANCE:
            raise ValueError("Power card distance must be between 1 and 3")


@dataclass(frozen=True, slots=True)
class Move:
    action: str
    card_index: int | None = None
    use_hero: bool = False


@dataclass(slots=True)
class PlayerResources:
    power_cards: list[PowerCard] = field(default_factory=list)
    hero_cards: int = HERO_CARDS_PER_PLAYER
    stones_remaining: int = POWER_STONES_PER_PLAYER

    def __post_init__(self) -> None:
        if self.hero_cards < 0:
            raise ValueError("Hero cards cannot be negative")
        if self.stones_remaining < 0:
            raise ValueError("Stones remaining cannot be negative")


@dataclass(slots=True)
class BoardState:
    grid: list[list[int]]
    king_position: tuple[int, int]
    players: dict[PlayerColor, PlayerResources]
    current_player: PlayerColor = PlayerColor.RED
    draw_pile: list[PowerCard] = field(default_factory=list)
    discard_pile: list[PowerCard] = field(default_factory=list)
    consecutive_passes: int = 0
    history: list[dict[str, object]] = field(default_factory=list)
    move_history: list[dict[str, object]] = field(default_factory=list)
    game_over: bool = False

    def __post_init__(self) -> None:
        if len(self.grid) != BOARD_SIZE:
            raise ValueError("Grid must have 11 rows")

        for row in self.grid:
            if len(row) != BOARD_SIZE:
                raise ValueError("Each grid row must have 11 columns")
            for value in row:
                if value not in (CellState.EMPTY, CellState.RED, CellState.WHITE):
                    raise ValueError("Grid values must be empty, red, or white")

        if not is_in_bounds(self.king_position):
            raise ValueError("King position is out of bounds")

        for color in PlayerColor:
            if color not in self.players:
                raise ValueError(f"Missing resources for player {color.value}")

        if self.current_player not in self.players:
            raise ValueError("Current player resources missing")

    def copy(self) -> BoardState:
        return BoardState(
            grid=clone_grid(self.grid),
            king_position=self.king_position,
            players=clone_players(self.players),
            current_player=self.current_player,
            draw_pile=self.draw_pile.copy(),
            discard_pile=self.discard_pile.copy(),
            consecutive_passes=self.consecutive_passes,
            history=[entry.copy() for entry in self.history],
            move_history=[entry.copy() for entry in self.move_history],
            game_over=self.game_over,
        )

    def to_dict(self) -> dict[str, object]:
        # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
        # "Shuffle the power cards well ... Place the rest of the cards face down ... as the draw pile."
        # Implementation: Preserve draw/discard piles in serialized state for deterministic replay.
        return {
            "grid": clone_grid(self.grid),
            "king_position": [self.king_position[0], self.king_position[1]],
            "players": {
                color.value: {
                    "power_cards": [
                        _power_card_to_dict(card) for card in resources.power_cards
                    ],
                    "hero_cards": resources.hero_cards,
                    "stones_remaining": resources.stones_remaining,
                }
                for color, resources in self.players.items()
            },
            "current_player": self.current_player.value,
            "draw_pile": [_power_card_to_dict(card) for card in self.draw_pile],
            "discard_pile": [_power_card_to_dict(card) for card in self.discard_pile],
            "consecutive_passes": self.consecutive_passes,
            "history": [entry.copy() for entry in self.history],
            "move_history": [entry.copy() for entry in self.move_history],
            "game_over": self.game_over,
        }


def power_card_from_dict(raw: Mapping[str, object]) -> PowerCard:
    direction = Direction(str(raw["direction"]))
    raw_distance = raw["distance"]
    if not isinstance(raw_distance, (int, str)):
        raise ValueError("distance must be int or numeric string")
    distance = int(raw_distance)
    return PowerCard(direction=direction, distance=distance)


def _power_card_to_dict(card: PowerCard) -> dict[str, object]:
    return {"direction": card.direction.value, "distance": card.distance}


def state_from_dict(raw: Mapping[str, object]) -> BoardState:
    def _to_int(value: object, *, field: str) -> int:
        if not isinstance(value, (int, str)):
            raise ValueError(f"{field} must be int or numeric string")
        return int(value)

    players_raw = raw["players"]
    if not isinstance(players_raw, Mapping):
        raise ValueError("players must be a mapping")

    players: dict[PlayerColor, PlayerResources] = {}
    for color in PlayerColor:
        payload = players_raw[color.value]
        if not isinstance(payload, Mapping):
            raise ValueError("player payload must be a mapping")
        cards_raw = payload.get("power_cards", [])
        if not isinstance(cards_raw, list):
            raise ValueError("power_cards must be a list")
        players[color] = PlayerResources(
            power_cards=[
                power_card_from_dict(item)
                for item in cards_raw
                if isinstance(item, Mapping)
            ],
            hero_cards=_to_int(
                payload.get("hero_cards", HERO_CARDS_PER_PLAYER), field="hero_cards"
            ),
            stones_remaining=_to_int(
                payload.get("stones_remaining", POWER_STONES_PER_PLAYER),
                field="stones_remaining",
            ),
        )

    def _cards_from(field: str) -> list[PowerCard]:
        cards = raw.get(field, [])
        if not isinstance(cards, list):
            raise ValueError(f"{field} must be a list")
        return [
            power_card_from_dict(item) for item in cards if isinstance(item, Mapping)
        ]

    king = raw.get("king_position", [START_KING_POSITION[0], START_KING_POSITION[1]])
    if not isinstance(king, list) or len(king) != 2:
        raise ValueError("king_position must be [row, col]")

    grid_raw = raw.get("grid")
    if not isinstance(grid_raw, list):
        raise ValueError("grid must be a list")

    history_raw = raw.get("history", [])
    if not isinstance(history_raw, list):
        raise ValueError("history must be a list")

    move_history_raw = raw.get("move_history", [])
    if not isinstance(move_history_raw, list):
        raise ValueError("move_history must be a list")

    raw_consecutive_passes = raw.get("consecutive_passes", 0)
    if not isinstance(raw_consecutive_passes, (int, str)):
        raise ValueError("consecutive_passes must be int or numeric string")

    return BoardState(
        grid=[
            [_to_int(value, field="grid cell") for value in row]
            for row in grid_raw
            if isinstance(row, list)
        ],
        king_position=(
            _to_int(king[0], field="king row"),
            _to_int(king[1], field="king column"),
        ),
        players=players,
        current_player=PlayerColor(
            str(raw.get("current_player", PlayerColor.RED.value))
        ),
        draw_pile=_cards_from("draw_pile"),
        discard_pile=_cards_from("discard_pile"),
        consecutive_passes=_to_int(raw_consecutive_passes, field="consecutive_passes"),
        history=[entry.copy() for entry in history_raw if isinstance(entry, dict)],
        move_history=[
            entry.copy() for entry in move_history_raw if isinstance(entry, dict)
        ],
        game_over=bool(raw.get("game_over", False)),
    )


def create_empty_grid() -> list[list[int]]:
    return [[CellState.EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]


def clone_grid(grid: list[list[int]]) -> list[list[int]]:
    return [row.copy() for row in grid]


def clone_players(
    players: dict[PlayerColor, PlayerResources],
) -> dict[PlayerColor, PlayerResources]:
    return {
        color: PlayerResources(
            power_cards=resources.power_cards.copy(),
            hero_cards=resources.hero_cards,
            stones_remaining=resources.stones_remaining,
        )
        for color, resources in players.items()
    }


def official_power_deck() -> list[PowerCard]:
    # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
    # "24 power cards" / "there are three cards for each of the 8 directions, one each of value I, II, III"
    # Implementation: Build a finite 24-card deck with each (direction, distance 1..3) exactly once.
    cards: list[PowerCard] = []
    for direction in Direction:
        for distance in range(MIN_POWER_DISTANCE, MAX_POWER_DISTANCE + 1):
            cards.append(PowerCard(direction=direction, distance=distance))
    return cards


def create_initial_state(
    *,
    shuffled_deck: Sequence[PowerCard] | None = None,
    red_power_cards: Sequence[PowerCard] | None = None,
    white_power_cards: Sequence[PowerCard] | None = None,
) -> BoardState:
    # Source: https://www.thamesandkosmos.com/manuals/full/691790_theroseking_manual.pdf
    # "Each player also gets four hero cards matching his or her rose color."
    # Implementation: Initialize each player with exactly 4 hero cards.
    draw_pile = list(shuffled_deck) if shuffled_deck is not None else []
    return BoardState(
        grid=create_empty_grid(),
        king_position=START_KING_POSITION,
        players={
            PlayerColor.RED: PlayerResources(
                power_cards=list(red_power_cards)
                if red_power_cards is not None
                else [],
                hero_cards=HERO_CARDS_PER_PLAYER,
                stones_remaining=POWER_STONES_PER_PLAYER,
            ),
            PlayerColor.WHITE: PlayerResources(
                power_cards=list(white_power_cards)
                if white_power_cards is not None
                else [],
                hero_cards=HERO_CARDS_PER_PLAYER,
                stones_remaining=POWER_STONES_PER_PLAYER,
            ),
        },
        draw_pile=draw_pile,
    )


def is_in_bounds(position: tuple[int, int]) -> bool:
    row, column = position
    return 0 <= row < BOARD_SIZE and 0 <= column < BOARD_SIZE


def opponent(player: PlayerColor) -> PlayerColor:
    if player is PlayerColor.RED:
        return PlayerColor.WHITE
    return PlayerColor.RED


def cell_for_player(player: PlayerColor) -> CellState:
    if player is PlayerColor.RED:
        return CellState.RED
    return CellState.WHITE


def player_for_cell(cell_value: int) -> PlayerColor | None:
    if cell_value == CellState.RED:
        return PlayerColor.RED
    if cell_value == CellState.WHITE:
        return PlayerColor.WHITE
    return None
