# Architecture

Online Rosenkönig follows a server-authoritative model. The backend manages all game logic and state, while the frontend acts as a thin client for rendering and user input.

## System Overview

The application is split into two main layers: a FastAPI backend and a Svelte frontend. Communication happens over WebSockets to ensure real-time updates.

```text
+-------------------+          +-------------------+
|      Browser      |          |      Server       |
|  (Svelte Client)  | <------> | (FastAPI Backend) |
+---------+---------+    WS    +---------+---------+
          |                              |
          |                              |
    +-----+-----+                  +-----+-----+
    | UI Layer  |                  | Game Engine|
    +-----------+                  +-----------+
    | State Sync|                  | Room Mgmt |
    +-----------+                  +-----------+
```

## Data Flow

1.  **User Action**: A player clicks a valid move on the board.
2.  **Client Request**: The frontend sends a JSON message via WebSocket.
3.  **Server Validation**: The backend checks if the move is legal based on the current state.
4.  **State Update**: If valid, the server updates the game board and player hands.
5.  **Broadcast**: The server sends the updated state to all players in the room.
6.  **UI Refresh**: The frontend receives the new state and re-renders the board.

## Server-Authoritative State

The server is the single source of truth. Clients do not calculate game logic or determine if a move is valid. This prevents cheating and ensures both players see the exact same state. If a client disconnects, they can reconnect and receive the current state from the server to resume play.

## Layer Separation

### Backend (Python/FastAPI)
- **API Layer**: Handles WebSocket connections and routing.
- **Room Manager**: Tracks active games and player assignments.
- **Game Engine**: Pure logic for board state, move validation, and scoring.

### Frontend (Svelte)
- **Store**: Manages the local copy of the game state.
- **Components**: Modular UI elements for the board, cards, and player info.
- **Socket Handler**: Manages the lifecycle of the WebSocket connection.
