import { derived, get, writable } from 'svelte/store';

export type RoomMode = 'single' | 'multi';
export type PlayerColor = 'red' | 'white';
export type ColorPreference = 'random' | PlayerColor;

export type PowerCard = {
  direction: string;
  distance: number;
};

export type LegalMove = {
  action: string;
  card_index: number;
  target: [number, number] | null;
  use_hero: boolean;
};

export type LoggedMove = {
  action: string;
  card_index: number | null;
  use_hero: boolean;
};

export type PlayerView = {
  color: PlayerColor;
  name: string;
  hero_cards: number;
  power_cards: PowerCard[];
  score: number;
};

export type GameState = {
  room_id: string;
  board: number[][];
  crown_pos: [number, number];
  draw_pile_count: number;
  players: PlayerView[];
  current_turn: PlayerColor;
  game_over: boolean;
  legal_moves: LegalMove[];
  move_history: LoggedMove[];
};

type ServerPlayer = {
  name: string;
  hand: PowerCard[];
  knights: number;
  score: number;
};

type ServerStatePayload = {
  board: number[] | number[][];
  crown_pos: [number, number];
  draw_pile_count?: number;
  players: ServerPlayer[];
  current_turn: string;
  game_over: boolean;
  legal_moves?: Array<{
    action: string;
    card_index: number;
    target: [number, number] | null;
    use_hero: boolean;
  }>;
  move_history?: LoggedMove[];
};

type SocketEnvelope = { type: string; payload: any };

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed';

type GameStoreState = {
  status: ConnectionStatus;
  url: string;
  room_id: string | null;
  mode: RoomMode | null;
  player_name: string;
  player_color: PlayerColor | null;
  is_spectator: boolean;
  last_error: string | null;
  state: GameState | null;
  state_history: GameState[];
};

function toBoardMatrix(input: number[] | number[][]): number[][] {
  if (Array.isArray(input) && Array.isArray(input[0])) {
    return (input as number[][]).map((row) => row.slice(0, 11));
  }

  const flat = Array.isArray(input) ? (input as number[]) : [];
  if (flat.length !== 121) {
    return Array.from({ length: 11 }, () => Array.from({ length: 11 }, () => 0));
  }

  const board: number[][] = [];
  for (let r = 0; r < 11; r += 1) {
    board.push(flat.slice(r * 11, r * 11 + 11));
  }
  return board;
}

function normalizeStatePayload(
  payload: ServerStatePayload,
  roomId: string,
  localPlayerName: string,
  currentPlayerColor: PlayerColor | null
): { state: GameState; playerColor: PlayerColor | null } {
  const players: PlayerView[] = [
    {
      color: 'red',
      name: payload.players?.[0]?.name ?? 'Red',
      hero_cards: payload.players?.[0]?.knights ?? 0,
      power_cards: payload.players?.[0]?.hand ?? [],
      score: payload.players?.[0]?.score ?? 0
    },
    {
      color: 'white',
      name: payload.players?.[1]?.name ?? 'White',
      hero_cards: payload.players?.[1]?.knights ?? 0,
      power_cards: payload.players?.[1]?.hand ?? [],
      score: payload.players?.[1]?.score ?? 0
    }
  ];

  const turnName = (payload.current_turn ?? '').toLowerCase();
  const current_turn: PlayerColor =
    players[0].name.toLowerCase() === turnName || turnName === 'red' ? 'red' : 'white';

  const inferredColor =
    currentPlayerColor ??
    players.find((p) => p.name.toLowerCase() === localPlayerName.trim().toLowerCase())?.color ??
    null;

  const legal_moves = (payload.legal_moves ?? []).map((m) => ({
    action: m.action,
    card_index: m.card_index,
    use_hero: m.use_hero,
    target: m.target ? [m.target[1], m.target[0]] : null
  })) as LegalMove[];

  return {
    state: {
      room_id: roomId,
      board: toBoardMatrix(payload.board),
      crown_pos: [payload.crown_pos?.[1] ?? 5, payload.crown_pos?.[0] ?? 5],
      draw_pile_count: payload.draw_pile_count ?? 0,
      players,
      current_turn,
      game_over: Boolean(payload.game_over),
      legal_moves,
      move_history: payload.move_history ?? []
    },
    playerColor: inferredColor
  };
}

function makeWsUrl(base: string): string {
  if (base.startsWith('ws://') || base.startsWith('wss://')) return base;
  if (base.startsWith('http://')) return base.replace('http://', 'ws://');
  if (base.startsWith('https://')) return base.replace('https://', 'wss://');
  return base;
}

function createGameStore() {
  const initial: GameStoreState = {
    status: 'idle',
    url: makeWsUrl(import.meta.env.VITE_BACKEND_WS ?? 'ws://localhost:8000/ws'),
    room_id: null,
    mode: null,
    player_name: 'Player',
    player_color: null,
    is_spectator: false,
    last_error: null,
    state: null,
    state_history: []
  };

  const { subscribe, update, set } = writable<GameStoreState>(initial);

  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempt = 0;
  let intentionalClose = false;
  const outbox: SocketEnvelope[] = [];

  function makeRoomId(mode: RoomMode): string {
    const token = Math.random().toString(36).slice(2, 10);
    return mode === 'single' ? `ai-${token}` : token;
  }

  function scheduleReconnect() {
    const snapshot = get({ subscribe });
    if (!snapshot.room_id || !snapshot.player_name) return;
    if (intentionalClose) return;

    if (reconnectTimer) return;
    update((s) => ({ ...s, status: s.status === 'connected' ? 'reconnecting' : s.status }));

    const delay = Math.min(5000, 250 * Math.pow(1.6, reconnectAttempt));
    reconnectAttempt += 1;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      void connect().then(() => {
        const s = get({ subscribe });
        if (s.room_id) {
          send({
            type: 'JOIN_ROOM',
            payload: {
              room_id: s.room_id,
              player_name: s.player_name,
              spectator: s.is_spectator,
            }
          });
        }
      });
    }, delay);
  }

  function flushOutbox() {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    while (outbox.length) {
      const msg = outbox.shift();
      if (!msg) break;
      socket.send(JSON.stringify(msg));
    }
  }

  function send(message: SocketEnvelope) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      outbox.push(message);
      return;
    }
    socket.send(JSON.stringify(message));
  }

  function connect(): Promise<void> {
    const { url } = get({ subscribe });
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return new Promise((resolve) => {
        if (socket?.readyState === WebSocket.OPEN) return resolve();
        const onOpen = () => {
          socket?.removeEventListener('open', onOpen);
          resolve();
        };
        socket?.addEventListener('open', onOpen);
      });
    }

    intentionalClose = false;
    update((s) => ({ ...s, status: s.status === 'reconnecting' ? 'reconnecting' : 'connecting', last_error: null }));

    return new Promise((resolve) => {
      socket = new WebSocket(url);

      socket.addEventListener('open', () => {
        reconnectAttempt = 0;
        update((s) => ({ ...s, status: 'connected' }));
        flushOutbox();
        resolve();
      });

      socket.addEventListener('message', (ev) => {
        let msg: SocketEnvelope;
        try {
          msg = JSON.parse(String(ev.data));
        } catch {
          return;
        }

        if (msg.type === 'ERROR') {
          update((s) => ({ ...s, last_error: msg.payload?.message ?? 'Unknown error' }));
          return;
        }

        if (msg.type === 'ROOM_CREATED' || msg.type === 'ROOM_JOINED') {
          const hasPlayerColor = Object.prototype.hasOwnProperty.call(msg.payload ?? {}, 'player_color');
          update((s) => ({
            ...s,
            room_id: msg.payload.room_id ?? s.room_id,
            player_color: hasPlayerColor ? (msg.payload.player_color as PlayerColor | null) : s.player_color,
            is_spectator: Boolean(msg.payload.spectator),
            mode: msg.payload.mode ?? s.mode,
            last_error: null
          }));
          return;
        }

        if (msg.type === 'STATE_UPDATE') {
          update((s) => {
            const normalized = normalizeStatePayload(
              msg.payload as ServerStatePayload,
              s.room_id ?? '',
              s.player_name,
              s.player_color
            );
            const nextState = normalized.state;
            const previous = s.state;
            const changed =
              !previous ||
              JSON.stringify(previous.board) !== JSON.stringify(nextState.board) ||
              previous.current_turn !== nextState.current_turn ||
              previous.game_over !== nextState.game_over;
            const nextHistory = changed ? [...s.state_history, nextState] : s.state_history;
            return {
              ...s,
              state: nextState,
              state_history: nextHistory,
              player_color: s.is_spectator ? null : normalized.playerColor,
              last_error: null
            };
          });
          return;
        }
      });

      socket.addEventListener('close', () => {
        update((s) => ({ ...s, status: intentionalClose ? 'closed' : s.status }));
        if (!intentionalClose) scheduleReconnect();
      });

      socket.addEventListener('error', () => {
        update((s) => ({ ...s, last_error: 'WebSocket error' }));
      });
    });
  }

  async function createRoom(opts: {
    player_name: string;
    mode: RoomMode;
    color_preference?: ColorPreference;
  }) {
    const playerName = opts.player_name?.trim() || 'Player';
    const roomId = makeRoomId(opts.mode);
    const colorPreference = opts.color_preference ?? 'random';
    update((s) => ({ ...s, room_id: roomId, player_name: playerName, mode: opts.mode }));
    await connect();
    send({
      type: 'JOIN_ROOM',
      payload: {
        room_id: roomId,
        player_name: playerName,
        player_color: colorPreference,
        spectator: false,
      },
    });
  }

  async function joinRoom(opts: { room_id: string; player_name: string; spectator?: boolean }) {
    const playerName = opts.player_name?.trim() || 'Player';
    const joinAsSpectator = Boolean(opts.spectator);
    update((s) => ({ ...s, room_id: opts.room_id, player_name: playerName, is_spectator: joinAsSpectator }));
    await connect();
    send({
      type: 'JOIN_ROOM',
      payload: { room_id: opts.room_id, player_name: playerName, spectator: joinAsSpectator },
    });
  }

  function makeMove(opts: { card_index: number; use_knight: boolean }) {
    send({ type: 'MAKE_MOVE', payload: { card_index: opts.card_index, use_knight: opts.use_knight } });
  }

  function drawCard() {
    send({ type: 'DRAW_CARD', payload: {} });
  }

  function disconnect() {
    intentionalClose = true;
    reconnectAttempt = 0;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (socket) {
      try {
        socket.close();
      } catch {
      }
      socket = null;
    }
    update((s) => ({ ...s, status: 'closed' }));
  }

  const you = derived({ subscribe }, ($s) => {
    if (!$s.state || !$s.player_color) return null;
    return $s.state.players.find((p) => p.color === $s.player_color) ?? null;
  });

  const opponent = derived({ subscribe }, ($s) => {
    if (!$s.state || !$s.player_color) return null;
    return $s.state.players.find((p) => p.color !== $s.player_color) ?? null;
  });

  return {
    subscribe,
    connect,
    createRoom,
    joinRoom,
    makeMove,
    drawCard,
    disconnect,
    you,
    opponent,
    stateHistory: derived({ subscribe }, ($s) => $s.state_history)
  };
}

export const game = createGameStore();
