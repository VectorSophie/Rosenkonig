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
    ai_color = room.name_to_color.get("AI")
    if ai_color is None:
        return

    while (
        not room.engine.state.game_over and room.engine.state.current_player == ai_color
    ):
        async with room.lock:
            move = choose_ai_move(room.engine.state)
            if move:
                try:
                    room.engine.make_move(
                        player=ai_color,
                        card_index=move.card_index
                        if move.card_index is not None
                        else -1,
                        use_knight=move.use_hero,
                    )
                except (ValueError, IndexError):
                    # AI couldn't move, maybe draw?
                    try:
                        room.engine.draw_card(player=ai_color)
                    except Exception:
                        break
            else:
                # No legal move, try drawing.
                try:
                    room.engine.draw_card(player=ai_color)
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
                preferred_color_obj = payload.get("player_color")
                spectator_obj = payload.get("spectator")
                if not isinstance(room_id_obj, str) or not room_id_obj.strip():
                    await _safe_send(websocket, _error("room_id is required"))
                    continue
                if not isinstance(name_obj, str) or not name_obj.strip():
                    await _safe_send(websocket, _error("player_name is required"))
                    continue
                if spectator_obj is not None and not isinstance(spectator_obj, bool):
                    await _safe_send(websocket, _error("spectator must be a boolean"))
                    continue

                preferred_color: PlayerColor | None = None
                if isinstance(preferred_color_obj, str):
                    color_norm = preferred_color_obj.strip().lower()
                    if color_norm == "red":
                        preferred_color = PlayerColor.RED
                    elif color_norm == "white":
                        preferred_color = PlayerColor.WHITE
                    elif color_norm in {"", "random"}:
                        preferred_color = None
                    else:
                        await _safe_send(
                            websocket,
                            _error("player_color must be red, white, or random"),
                        )
                        continue

                room_id = room_id_obj.strip()
                player_name = name_obj.strip()
                join_as_spectator = bool(spectator_obj)

                # Auto-create rooms on first join (no DB).
                room = await room_manager.get_or_create_room(room_id)
                async with room.lock:
                    room.connections.add(websocket)
                    if join_as_spectator:
                        player_color = None
                        room.spectator_names.add(player_name)
                    else:
                        try:
                            player_color = room_manager.assign_player(
                                room,
                                player_name=player_name,
                                preferred_color=preferred_color,
                            )
                        except ValueError:
                            await _safe_send(
                                websocket,
                                _error(
                                    "room is full (join as spectator to watch this game)"
                                ),
                            )
                            continue

                        room.engine.ensure_hand(player_color)

                    # If room id has "ai" or user requested it, add AI.
                    if "ai" in room_id.lower() and "AI" not in room.name_to_color:
                        ai_color = (
                            PlayerColor.WHITE
                            if player_color == PlayerColor.RED
                            else PlayerColor.RED
                        )
                        if ai_color not in room.players:
                            room.players[ai_color] = "AI"
                            room.name_to_color["AI"] = ai_color
                            room.engine.ensure_hand(ai_color)

                await _safe_send(
                    websocket,
                    {
                        "type": "ROOM_JOINED",
                        "payload": {
                            "room_id": room_id,
                            "player_color": player_color.value
                            if player_color is not None
                            else None,
                            "spectator": player_color is None,
                        },
                    },
                )

                await _broadcast_state(room)
                if "AI" in room.name_to_color:
                    _ = asyncio.create_task(_ai_step(room))
                continue

            # All other messages require being in a room.
            if room is None or player_name is None:
                await _safe_send(websocket, _error("Must JOIN_ROOM first"))
                continue

            if msg_type_norm in {"MAKE_MOVE", "PLAYER_MOVE", "PLAYERMOVE"}:
                if player_color is None:
                    await _safe_send(websocket, _error("spectators cannot make moves"))
                    continue
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
                if "AI" in room.name_to_color:
                    _ = asyncio.create_task(_ai_step(room))
                continue

            if msg_type_norm in {"DRAW_CARD", "DRAWCARD"}:
                if player_color is None:
                    await _safe_send(websocket, _error("spectators cannot draw cards"))
                    continue
                async with room.lock:
                    try:
                        room.engine.draw_card(player=player_color)
                    except Exception as exc:
                        await _safe_send(websocket, _error(str(exc)))
                        continue

                await _broadcast_state(room)
                if "AI" in room.name_to_color:
                    _ = asyncio.create_task(_ai_step(room))
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
            if player_color is None and player_name is not None:
                room.spectator_names.discard(player_name)
