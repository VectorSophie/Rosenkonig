from typing import List, Tuple, Optional
from pydantic import BaseModel


class Card(BaseModel):
    direction: str  # N, NE, E, SE, S, SW, W, NW
    distance: int  # 1, 2, 3


class Move(BaseModel):
    card_index: Optional[int] = (
        None  # Index of the card in player's hand, None for draw
    )
    is_knight: bool = False
    target_pos: Optional[Tuple[int, int]] = None  # (row, col)


class PlayerState(BaseModel):
    hand: List[Card]
    knights: int
    score: int = 0


class GameState(BaseModel):
    board: List[List[int]]  # 0: empty, 1: Player 1 (Red), 2: Player 2 (White)
    crown_pos: Tuple[int, int]
    players: List[PlayerState]
    current_player: int  # 0 or 1
    draw_pile_size: int
