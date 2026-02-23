"""FastAPI entry point for the Rosenkonig backend.

The backend hosts server-authoritative Rosenkonig games over WebSockets.
Communication follows `docs/PROTOCOL.md` (JSON messages over a single WS).

WebSocket
---------

- URL: `/ws`

Client -> Server:

- `JOIN_ROOM`: `{ "room_id": "string", "player_name": "string" }`
- `MAKE_MOVE`: `{ "card_index": number, "use_knight": boolean }`
- `DRAW_CARD`: `{}`

Server -> Client:

- `STATE_UPDATE`: `{ "board": [121 ints], "crown_pos": [x, y], "players": [...], "current_turn": "name", "game_over": bool }`
- `ERROR`: `{ "message": "string" }`

Rooms and game state are kept entirely in memory for this version.
Reconnection is supported by re-sending `JOIN_ROOM` with the same `room_id`
and `player_name` on a new WebSocket connection.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.rooms import router as rooms_router
from .api.websocket import router as websocket_router


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    if raw.strip():
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Rosenkonig Backend",
        version="0.1.0",
        description="Server-authoritative Rosenkonig backend. Protocol: docs/PROTOCOL.md.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(rooms_router)
    app.include_router(websocket_router)

    @app.get("/health")
    async def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    return app


app = create_app()
