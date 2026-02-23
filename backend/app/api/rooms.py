from __future__ import annotations

import asyncio
import random
import secrets
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel

from ..engine.board import (
    BOARD_SIZE,
    BoardState,
    PlayerColor,
    PowerCard,
    create_initial_state,
    default_power_cards,
    opponent,
)
from ..engine.logic import apply_move, calculate_scores, list_legal_moves


HAND_SIZE = 5
DECK_COPIES = 2


class RoomInfo(BaseModel):
    room_id: str
    players: dict[str, str]
    created_at: float


class CreateRoomResponse(BaseModel):
    room_id: str


class GameEngine:
    """Server-authoritative game logic wrapper.

    Uses the pure engine functions (`app.engine.*`) for validation/apply.
    Deck/hand management is kept in-memory here to match `docs/PROTOCOL.md`.
    """

    def __init__(self) -> None:
        # Start with empty hands; we deal when a player joins.
        self.state: BoardState = create_initial_state(
            red_power_cards=[],
            white_power_cards=[],
        )

        deck: list[PowerCard] = []
        for _ in range(DECK_COPIES):
            deck.extend(default_power_cards())
        random.shuffle(deck)
        self._draw_pile: list[PowerCard] = deck

    def ensure_hand(self, player: PlayerColor) -> None:
        hand = self.state.players[player].power_cards
        while len(hand) < HAND_SIZE and self._draw_pile:
            hand.append(self._draw_pile.pop())

    def _can_draw(self, player: PlayerColor) -> bool:
        hand = self.state.players[player].power_cards
        return len(hand) < HAND_SIZE and bool(self._draw_pile)

    def _has_legal_move(self, player: PlayerColor) -> bool:
        probe = self.state.copy()
        probe.current_player = player
        return bool(list_legal_moves(probe))

    def refresh_game_over(self) -> None:
        player = self.state.current_player
        self.state.game_over = not (
            self._has_legal_move(player) or self._can_draw(player)
        )

    def draw_card(self, *, player: PlayerColor) -> None:
        if self.state.game_over:
            raise ValueError("game is over")
        if player != self.state.current_player:
            raise ValueError("not your turn")

        hand = self.state.players[player].power_cards
        if len(hand) >= HAND_SIZE:
            raise ValueError("hand is already full")
        if not self._draw_pile:
            raise ValueError("draw pile is empty")

        hand.append(self._draw_pile.pop())
        self.state.current_player = opponent(player)
        self.refresh_game_over()

    def make_move(
        self, *, player: PlayerColor, card_index: int, use_knight: bool
    ) -> None:
        if self.state.game_over:
            raise ValueError("game is over")
        if player != self.state.current_player:
            raise ValueError("not your turn")

        resources = self.state.players[player]
        if card_index < 0 or card_index >= len(resources.power_cards):
            raise ValueError("invalid card_index")

        card = resources.power_cards[card_index]
        # Engine uses "hero" terminology; protocol uses "knight".
        next_state = apply_move(state=self.state, card=card, use_hero=use_knight)
        self.state = next_state
        self.refresh_game_over()

    def to_public_payload(
        self, *, players: dict[PlayerColor, str]
    ) -> dict[str, object]:
        scores = calculate_scores(self.state)

        flat_board: list[int] = []
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                flat_board.append(int(self.state.grid[row][col]))

        king_row, king_col = self.state.king_position
        current_name = players.get(
            self.state.current_player, self.state.current_player.value
        )

        def _player_payload(color: PlayerColor) -> dict[str, object]:
            resources = self.state.players[color]
            hand = [
                {"direction": c.direction.value, "distance": c.distance}
                for c in resources.power_cards
            ]
            return {
                "name": players.get(color, color.value.title()),
                "hand": hand,
                "knights": int(resources.hero_cards),
                "score": int(scores[color]),
            }

        return {
            "board": flat_board,
            "crown_pos": [int(king_col), int(king_row)],
            "players": [
                _player_payload(PlayerColor.RED),
                _player_payload(PlayerColor.WHITE),
            ],
            "current_turn": current_name,
            "game_over": bool(self.state.game_over),
        }


@dataclass(slots=True)
class Room:
    room_id: str
    engine: GameEngine = field(default_factory=GameEngine)
    created_at: float = field(default_factory=lambda: time.time())
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # Stable across reconnects.
    name_to_color: dict[str, PlayerColor] = field(default_factory=dict)
    players: dict[PlayerColor, str] = field(default_factory=dict)

    # Connected websockets (for broadcast).
    connections: set[WebSocket] = field(default_factory=set)


class RoomManager:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def create_room(self) -> Room:
        async with self._lock:
            room_id = secrets.token_urlsafe(6)
            while room_id in self._rooms:
                room_id = secrets.token_urlsafe(6)
            room = Room(room_id=room_id)
            self._rooms[room_id] = room
            return room

    async def get_room(self, room_id: str) -> Room:
        async with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                raise KeyError(room_id)
            return room

    async def get_or_create_room(self, room_id: str) -> Room:
        async with self._lock:
            existing = self._rooms.get(room_id)
            if existing is not None:
                return existing
            room = Room(room_id=room_id)
            self._rooms[room_id] = room
            return room

    async def list_rooms(self) -> list[Room]:
        async with self._lock:
            return list(self._rooms.values())

    def assign_player(self, room: Room, *, player_name: str) -> PlayerColor:
        normalized = player_name.strip() or "Player"
        if normalized in room.name_to_color:
            return room.name_to_color[normalized]

        if PlayerColor.RED not in room.players:
            room.players[PlayerColor.RED] = normalized
            room.name_to_color[normalized] = PlayerColor.RED
            return PlayerColor.RED
        if PlayerColor.WHITE not in room.players:
            room.players[PlayerColor.WHITE] = normalized
            room.name_to_color[normalized] = PlayerColor.WHITE
            return PlayerColor.WHITE

        raise ValueError("room is full")


room_manager = RoomManager()


router = APIRouter(tags=["rooms"])


@router.get("/rooms", response_model=list[RoomInfo])
async def http_list_rooms() -> list[RoomInfo]:
    rooms = await room_manager.list_rooms()
    payload: list[RoomInfo] = []
    for room in rooms:
        payload.append(
            RoomInfo(
                room_id=room.room_id,
                players={c.value: n for c, n in room.players.items()},
                created_at=room.created_at,
            )
        )
    return payload


@router.post("/rooms", response_model=CreateRoomResponse)
async def http_create_room() -> CreateRoomResponse:
    room = await room_manager.create_room()
    return CreateRoomResponse(room_id=room.room_id)


@router.get("/rooms/{room_id}")
async def http_get_room_state(room_id: str) -> dict[str, object]:
    try:
        room = await room_manager.get_room(room_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="room not found") from exc
    async with room.lock:
        return room.engine.to_public_payload(players=room.players)
