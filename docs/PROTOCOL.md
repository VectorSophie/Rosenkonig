# Protocol

Communication between the client and server uses JSON messages over WebSockets.

## Message Structure

All messages follow a standard format with a `type` field and a `payload`.

```json
{
  "type": "MESSAGE_TYPE",
  "payload": { ... }
}
```

## Client to Server Messages

### JoinRoom
Sent when a player wants to join a specific game room.
- `type`: `JOIN_ROOM`
- `payload`: `{ "room_id": "string", "player_name": "string" }`

### Move
Sent when a player attempts to make a move.
- `type`: `MAKE_MOVE`
- `payload`: `{ "card_index": number, "use_knight": boolean }`

### DrawCard
Sent when a player chooses to draw a card instead of moving.
- `type`: `DRAW_CARD`
- `payload`: `{}`

## Server to Client Messages

### StateUpdate
Sent whenever the game state changes. This is the primary way the client stays in sync.
- `type`: `STATE_UPDATE`
- `payload`:
  ```json
  {
    "board": [121 integers],
    "crown_pos": [x, y],
    "players": [
      { "name": "Red", "hand": [...], "knights": 4, "score": 0 },
      { "name": "White", "hand": [...], "knights": 4, "score": 0 }
    ],
    "current_turn": "Red",
    "game_over": false
  }
  ```

### Error
Sent when a client action is invalid or a server error occurs.
- `type`: `ERROR`
- `payload`: `{ "message": "string" }`

## Reconnection Flow

1.  **Disconnect**: The WebSocket connection is lost.
2.  **Reconnect**: The client attempts to re-establish the connection.
3.  **Identify**: The client sends a `JOIN_ROOM` message with the same `room_id` and `player_name`.
4.  **Sync**: The server recognizes the player and sends the current `STATE_UPDATE` to bring the client up to speed.
