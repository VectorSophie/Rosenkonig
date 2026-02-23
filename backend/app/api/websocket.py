from __future__ import annotations

import asyncio
import json
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .rooms import Room, room_manager
from ..engine.ai import choose_ai_move
from ..engine.board import PlayerColor


router = APIRouter(tags=["websocket"])


def _error(message: str) -> dict[str, object]:
    return {"type": "ERROR", "payload": {"message": message}}


def _state_update(room: Room) -> dict[str, object]:
    return {
        "type": "STATE_UPDATE",
        "payload": room.engine.to_public_payload(players=room.players),
    }


async def _safe_send(websocket: WebSocket, message: dict[str, object]) -> None:
    try:
        await websocket.send_json(message)
    except Exception:
        # Best-effort (connection is likely gone).
        return


async def _broadcast(room: Room, message: dict[str, object]) -> None:
    _ = await asyncio.gather(
        *[_safe_send(ws, message) for ws in list(room.connections)]
    )


async def _broadcast_state(room: Room) -> None:
    async with room.lock:
        message = _state_update(room)
    await _broadcast(room, message)


async def _ai_step(room: Room) -> None:
    """Check if it's the AI's turn and perform it."""
    # In this implementation, Player WHITE is always AI in "AI" mode.
    if room.players.get(PlayerColor.WHITE) != "AI":
        return

    while (
        not room.engine.state.game_over
        and room.engine.state.current_player == PlayerColor.WHITE
    ):
        async with room.lock:
            move = choose_ai_move(room.engine.state)
            if move:
                card, use_knight = move
                try:
                    # Find index of the card in hand.
                    hand = room.engine.state.players[PlayerColor.WHITE].power_cards
                    idx = hand.index(card)
                    room.engine.make_move(
                        player=PlayerColor.WHITE,
                        card_index=idx,
                        use_knight=use_knight,
                    )
                except (ValueError, IndexError):
                    # AI couldn't move, maybe draw?
                    try:
                        room.engine.draw_card(player=PlayerColor.WHITE)
                    except Exception:
                        break
            else:
                # No legal move, try drawing.
                try:
                    room.engine.draw_card(player=PlayerColor.WHITE)
                except Exception:
                    break

        await _broadcast_state(room)
        await asyncio.sleep(0.5)  # Slight delay for realism.


def _parse_message(obj: object) -> tuple[str, dict[str, object]] | None:
    if not isinstance(obj, dict):
        return None

    typed = cast(dict[str, object], obj)
    msg_type_obj = typed.get("type")
    if not isinstance(msg_type_obj, str):
        return None

    payload = typed.get("payload")
    if payload is None:
        payload_dict: dict[str, object] = {}
    elif isinstance(payload, dict):
        payload_dict = cast(dict[str, object], payload)
    else:
        return None
    return msg_type_obj, payload_dict


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    room: Room | None = None
    player_name: str | None = None
    player_color: PlayerColor | None = None

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                raw_obj = cast(object, json.loads(raw_text))
            except json.JSONDecodeError:
                await _safe_send(websocket, _error("invalid JSON"))
                continue

            parsed = _parse_message(raw_obj)
            if parsed is None:
                await _safe_send(websocket, _error("invalid message format"))
                continue

            msg_type, payload = parsed
            msg_type_norm = msg_type.strip().upper()

            if msg_type_norm == "PING":
                await _safe_send(websocket, {"type": "PONG", "payload": {}})
                continue

            if msg_type_norm in {"JOIN_ROOM", "JOINROOM"}:
                room_id_obj = payload.get("room_id")
                name_obj = payload.get("player_name")
                if not isinstance(room_id_obj, str) or not room_id_obj.strip():
                    await _safe_send(websocket, _error("room_id is required"))
                    continue
                if not isinstance(name_obj, str) or not name_obj.strip():
                    await _safe_send(websocket, _error("player_name is required"))
                    continue

                room_id = room_id_obj.strip()
                player_name = name_obj.strip()

                # Auto-create rooms on first join (no DB).
                room = await room_manager.get_or_create_room(room_id)
                async with room.lock:
                    try:
                        player_color = room_manager.assign_player(
                            room, player_name=player_name
                        )
                    except ValueError as exc:
                        await _safe_send(websocket, _error(str(exc)))
                        continue

                    room.engine.ensure_hand(player_color)
                    room.connections.add(websocket)

                    # If room id has "ai" or user requested it, add AI.
                    if (
                        "ai" in room_id.lower()
                        and PlayerColor.WHITE not in room.players
                    ):
                        room.players[PlayerColor.WHITE] = "AI"
                        room.name_to_color["AI"] = PlayerColor.WHITE
                        room.engine.ensure_hand(PlayerColor.WHITE)

                await _broadcast_state(room)
                if room.players.get(PlayerColor.WHITE) == "AI":
                    asyncio.create_task(_ai_step(room))
                continue

            # All other messages require being in a room.
            if room is None or player_name is None or player_color is None:
                await _safe_send(websocket, _error("Must JOIN_ROOM first"))
                continue

            if msg_type_norm in {"MAKE_MOVE", "PLAYER_MOVE", "PLAYERMOVE"}:
                raw_idx = payload.get("card_index")
                raw_knight = payload.get("use_knight")
                if not isinstance(raw_idx, int):
                    await _safe_send(websocket, _error("card_index must be an integer"))
                    continue
                if not isinstance(raw_knight, bool):
                    await _safe_send(websocket, _error("use_knight must be a boolean"))
                    continue

                async with room.lock:
                    try:
                        room.engine.make_move(
                            player=player_color,
                            card_index=raw_idx,
                            use_knight=raw_knight,
                        )
                    except Exception as exc:
                        await _safe_send(websocket, _error(str(exc)))
                        continue

                await _broadcast_state(room)
                if room.players.get(PlayerColor.WHITE) == "AI":
                    asyncio.create_task(_ai_step(room))
                continue

            if msg_type_norm in {"DRAW_CARD", "DRAWCARD"}:
                async with room.lock:
                    try:
                        room.engine.draw_card(player=player_color)
                    except Exception as exc:
                        await _safe_send(websocket, _error(str(exc)))
                        continue

                await _broadcast_state(room)
                if room.players.get(PlayerColor.WHITE) == "AI":
                    asyncio.create_task(_ai_step(room))
                continue

            if msg_type_norm in {
                "REQUEST_STATE",
                "SYNC_STATE",
                "GAME_STATE",
                "GAMESTATE",
            }:
                async with room.lock:
                    message = _state_update(room)
                await _safe_send(websocket, message)
                continue

            await _safe_send(websocket, _error("unknown message type"))

    except WebSocketDisconnect:
        pass
    finally:
        if room is not None:
            room.connections.discard(websocket)
