from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


BOARD_SIZE = 11
BOARD_CELLS = BOARD_SIZE * BOARD_SIZE


@dataclass(frozen=True)
class Card:
    direction: str
    distance: int

    def to_public(self) -> Dict[str, Any]:
        return {"dir": self.direction, "dist": self.distance}


_DIR_DELTAS = {
    "N": (0, -1),
    "NE": (1, -1),
    "E": (1, 0),
    "SE": (1, 1),
    "S": (0, 1),
    "SW": (-1, 1),
    "W": (-1, 0),
    "NW": (-1, -1),
}


def _idx(x: int, y: int) -> int:
    return y * BOARD_SIZE + x


def _in_bounds(x: int, y: int) -> bool:
    return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE


class RosenkoenigEngine:
    """Minimal, server-authoritative engine.

    This is intentionally in-memory and deterministic per-process. The backend
    uses this as the source of truth for validating client actions.
    """

    def __init__(self, *, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)

        self._board: List[int] = [0 for _ in range(BOARD_CELLS)]
        self._crown_pos: Tuple[int, int] = (BOARD_SIZE // 2, BOARD_SIZE // 2)

        self._players: List[str] = []
        self._hands: Dict[str, List[Card]] = {}
        self._knights: Dict[str, int] = {}
        self._scores: Dict[str, int] = {}
        self._current_turn: Optional[str] = None
        self._game_over: bool = False

        self._deck: List[Card] = self._make_deck()
        self._rng.shuffle(self._deck)

    def _make_deck(self) -> List[Card]:
        # Simple deck: 2 copies of each (dir, dist) to provide enough cards.
        deck: List[Card] = []
        for d in _DIR_DELTAS.keys():
            for dist in (1, 2, 3):
                deck.append(Card(direction=d, distance=dist))
                deck.append(Card(direction=d, distance=dist))
        return deck

    def add_player(self, player_name: str) -> None:
        player_name = player_name.strip()
        if not player_name:
            raise ValueError("player_name must be non-empty")

        if player_name in self._players:
            return

        if len(self._players) >= 2:
            raise ValueError("room already has two players")

        self._players.append(player_name)
        self._hands[player_name] = []
        self._knights[player_name] = 4
        self._scores[player_name] = 0

        if self._current_turn is None:
            self._current_turn = player_name

        # Initial hand (up to 5).
        self._deal_to_hand(player_name, target_size=5)

    def _deal_to_hand(self, player_name: str, *, target_size: int) -> None:
        hand = self._hands[player_name]
        while len(hand) < target_size and self._deck:
            hand.append(self._deck.pop())

    def public_state(self) -> Dict[str, Any]:
        players_public = []
        for name in self._players:
            players_public.append(
                {
                    "name": name,
                    "hand": [c.to_public() for c in self._hands.get(name, [])],
                    "knights": self._knights.get(name, 0),
                    "score": self._scores.get(name, 0),
                }
            )

        current_turn = self._current_turn or (self._players[0] if self._players else "")
        return {
            "board": list(self._board),
            "crown_pos": [self._crown_pos[0], self._crown_pos[1]],
            "players": players_public,
            "current_turn": current_turn,
            "game_over": self._game_over,
        }

    def draw_card(self, *, player_name: str) -> None:
        self._assert_can_act(player_name)

        hand = self._hands[player_name]
        if len(hand) >= 5:
            raise ValueError("hand is already full")
        if not self._deck:
            raise ValueError("deck is empty")

        hand.append(self._deck.pop())
        self._advance_turn()
        self._update_game_over()

    def make_move(self, *, player_name: str, card_index: int, use_knight: bool) -> None:
        self._assert_can_act(player_name)

        hand = self._hands[player_name]
        if not (0 <= card_index < len(hand)):
            raise ValueError("card_index out of range")

        card = hand[card_index]
        dx, dy = _DIR_DELTAS.get(card.direction, (0, 0))
        if (dx, dy) == (0, 0):
            raise ValueError("invalid card direction")

        cx, cy = self._crown_pos
        tx = cx + dx * card.distance
        ty = cy + dy * card.distance
        if not _in_bounds(tx, ty):
            raise ValueError("move out of bounds")

        mover_code = self._player_code(player_name)
        target = self._board[_idx(tx, ty)]
        if target == mover_code:
            raise ValueError("target cell already occupied by you")

        if target != 0:
            if not use_knight:
                raise ValueError("target occupied; set use_knight to true")
            if self._knights[player_name] <= 0:
                raise ValueError("no knights remaining")
            self._knights[player_name] -= 1
        else:
            if use_knight:
                raise ValueError("use_knight only allowed when flipping an opponent")

        # Apply move: consume card, place/flip crown, move token.
        hand.pop(card_index)
        self._board[_idx(tx, ty)] = mover_code
        self._crown_pos = (tx, ty)

        self._recompute_scores()
        self._advance_turn()
        self._deal_to_hand(player_name, target_size=5)
        self._update_game_over()

    def _assert_can_act(self, player_name: str) -> None:
        if self._game_over:
            raise ValueError("game is over")
        if player_name not in self._players:
            raise ValueError("unknown player")
        if self._current_turn != player_name:
            raise ValueError("not your turn")

    def _player_code(self, player_name: str) -> int:
        # 1 for first player, 2 for second player.
        try:
            return self._players.index(player_name) + 1
        except ValueError:
            return 0

    def _advance_turn(self) -> None:
        if len(self._players) < 2:
            return
        if self._current_turn is None:
            self._current_turn = self._players[0]
            return
        self._current_turn = (
            self._players[0]
            if self._current_turn == self._players[1]
            else self._players[1]
        )

    def _update_game_over(self) -> None:
        if all(v != 0 for v in self._board):
            self._game_over = True
            return
        if not self._deck and all(
            len(self._hands.get(p, [])) == 0 for p in self._players
        ):
            self._game_over = True

    def _recompute_scores(self) -> None:
        # Connectivity scoring: sum of (group_size^2) per color.
        visited = [False] * BOARD_CELLS
        scores = {1: 0, 2: 0}

        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                i = _idx(x, y)
                if visited[i]:
                    continue
                color = self._board[i]
                if color == 0:
                    visited[i] = True
                    continue

                # BFS over 4-neighborhood.
                q = [(x, y)]
                visited[i] = True
                size = 0

                while q:
                    qx, qy = q.pop()
                    size += 1
                    for nx, ny in (
                        (qx - 1, qy),
                        (qx + 1, qy),
                        (qx, qy - 1),
                        (qx, qy + 1),
                    ):
                        if not _in_bounds(nx, ny):
                            continue
                        ni = _idx(nx, ny)
                        if visited[ni]:
                            continue
                        if self._board[ni] != color:
                            continue
                        visited[ni] = True
                        q.append((nx, ny))

                scores[color] += size * size

        # Map scores back onto player names.
        for idx, name in enumerate(self._players):
            code = idx + 1
            self._scores[name] = scores.get(code, 0)
