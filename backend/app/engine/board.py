from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

BOARD_SIZE = 11
MIN_POWER_DISTANCE = 1
MAX_POWER_DISTANCE = 3
START_KING_POSITION = (BOARD_SIZE // 2, BOARD_SIZE // 2)


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


@dataclass(slots=True)
class PlayerResources:
    power_cards: list[PowerCard] = field(default_factory=list)
    hero_cards: int = 4

    def __post_init__(self) -> None:
        if self.hero_cards < 0:
            raise ValueError("Hero cards cannot be negative")


@dataclass(slots=True)
class BoardState:
    grid: list[list[int]]
    king_position: tuple[int, int]
    players: dict[PlayerColor, PlayerResources]
    current_player: PlayerColor = PlayerColor.RED
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
            game_over=self.game_over,
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
        )
        for color, resources in players.items()
    }


def default_power_cards() -> list[PowerCard]:
    cards: list[PowerCard] = []
    for direction in Direction:
        for distance in range(MIN_POWER_DISTANCE, MAX_POWER_DISTANCE + 1):
            cards.append(PowerCard(direction=direction, distance=distance))
    return cards


def create_initial_state(
    red_power_cards: Sequence[PowerCard] | None = None,
    white_power_cards: Sequence[PowerCard] | None = None,
) -> BoardState:
    return BoardState(
        grid=create_empty_grid(),
        king_position=START_KING_POSITION,
        players={
            PlayerColor.RED: PlayerResources(
                power_cards=list(red_power_cards)
                if red_power_cards is not None
                else default_power_cards(),
                hero_cards=4,
            ),
            PlayerColor.WHITE: PlayerResources(
                power_cards=list(white_power_cards)
                if white_power_cards is not None
                else default_power_cards(),
                hero_cards=4,
            ),
        },
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
