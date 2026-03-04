<script lang="ts">
  import { goto } from '$app/navigation';
  import { onDestroy, onMount, tick } from 'svelte';
  import {
    game,
    type ColorPreference,
    type LegalMove,
    type PlayerView,
    type RoomMode,
  } from '$lib/stores/game';
  import Board from '$lib/components/Board.svelte';
  import { fade, fly } from 'svelte/transition';
  import { Copy, DoorOpen, Swords, User, WifiOff, Wifi } from 'lucide-svelte';

  type DisplayCard = {
    id: string;
    idx: number;
    direction: string;
    distance: number;
    label: string;
  };

  type Keybinds = {
    cards: [string, string, string, string, string];
    hero: string;
    draw: string;
  };

  const DEFAULT_KEYBINDS: Keybinds = {
    cards: ['1', '2', '3', '4', '5'],
    hero: 'h',
    draw: 'd'
  };

  let name = 'Player';
  let roomId = '';
  let mode: RoomMode = 'single';
  let colorPreference: ColorPreference = 'random';
  let joinAsSpectator = false;
  let showOnboarding = true;

  let selectedCardIndex: number | null = null;
  let hoveredCardIndex: number | null = null;
  let useHero = false;
  let myHandRevision = 0;
  let oppHandRevision = 0;
  let myHandFingerprint = '';
  let oppHandFingerprint = '';
  let myHandCount = 0;
  let oppHandCount = 0;
  type FlightCard = {
    id: number;
    target: 'you' | 'opp';
    label: string;
    direction: string;
    distance: number;
    startX: number;
    startY: number;
    endX: number;
    endY: number;
    rotation: number;
    scale: number;
    active: boolean;
  };

  let flightToken = 0;
  let flyingCards: FlightCard[] = [];
  let deckButtonEl: HTMLButtonElement | null = null;
  let youRailEl: HTMLDivElement | null = null;
  let oppRailEl: HTMLDivElement | null = null;
  let myCardEls = new Map<number, HTMLButtonElement>();
  let keybinds: Keybinds = { ...DEFAULT_KEYBINDS };
  let keybindSettingsOpen = false;
  let hasLoadedKeybinds = false;
  export let routeGameId: string | null = null;
  let attemptedRouteJoin = false;

  $: state = $game?.state ?? null;
  $: you =
    $game?.player_color && state
      ? state.players.find((p: PlayerView) => p.color === $game.player_color) ?? null
      : null;
  $: opp =
    $game?.player_color && state
      ? state.players.find((p: PlayerView) => p.color !== $game.player_color) ?? null
      : null;
  $: myTurn = !!(state && $game?.player_color && state.current_turn === $game.player_color);
  $: oppTurn = Boolean(state && !myTurn && !state?.game_over);
  $: isSpectator = Boolean($game?.is_spectator || ($game?.room_id && !$game?.player_color));
  $: canControlTurn = Boolean(myTurn && !isSpectator);

  $: legalMoves = (state?.legal_moves ?? []) as LegalMove[];
  $: drawPileCount = Number((state as { draw_pile_count?: number } | null)?.draw_pile_count ?? 0);
  $: hasServerLegalMoves = legalMoves.length > 0;

  $: selectedMove =
    !hasServerLegalMoves || selectedCardIndex === null
      ? null
      : legalMoves.find((m) => m.card_index === selectedCardIndex && m.use_hero === useHero) ?? null;
  $: selectedCard = selectedCardIndex === null ? null : (you?.power_cards?.[selectedCardIndex] ?? null);
  $: altMove =
    !hasServerLegalMoves || selectedCardIndex === null
      ? null
      : legalMoves.find((m) => m.card_index === selectedCardIndex && m.use_hero !== useHero) ?? null;

  function ensureReasonableHeroToggle() {
    if (!you) return;
    if (useHero && you.hero_cards <= 0) useHero = false;
  }

  $: ensureReasonableHeroToggle();

  function cardLabel(c: { direction: string; distance: number }) {
    return `${c.direction}${c.distance}`;
  }

  function directionGlyph(direction: string): string {
    const d = direction.toUpperCase();
    if (d === 'N') return '↑';
    if (d === 'NE') return '↗';
    if (d === 'E') return '→';
    if (d === 'SE') return '↘';
    if (d === 'S') return '↓';
    if (d === 'SW') return '↙';
    if (d === 'W') return '←';
    if (d === 'NW') return '↖';
    return '•';
  }

  function directionAngle(direction: string): number {
    const d = direction.toUpperCase();
    if (d === 'N') return -90;
    if (d === 'NE') return -45;
    if (d === 'E') return 0;
    if (d === 'SE') return 45;
    if (d === 'S') return 90;
    if (d === 'SW') return 135;
    if (d === 'W') return 180;
    if (d === 'NW') return -135;
    return 0;
  }

  function swordBladeLength(distance: number): number {
    const numericDistance = Number(distance);
    const normalized = Number.isFinite(numericDistance) ? Math.round(numericDistance) : 1;
    const clamped = Math.max(1, Math.min(8, normalized));
    return clamped * 7;
  }

  function directionDelta(direction: string): [number, number] {
    const d = direction.toUpperCase();
    if (d === 'N') return [-1, 0];
    if (d === 'NE') return [-1, 1];
    if (d === 'E') return [0, 1];
    if (d === 'SE') return [1, 1];
    if (d === 'S') return [1, 0];
    if (d === 'SW') return [1, -1];
    if (d === 'W') return [0, -1];
    if (d === 'NW') return [-1, -1];
    return [0, 0];
  }

  function handFingerprint(player: PlayerView | null) {
    if (!player) return '';
    return player.power_cards.map((c) => `${c.direction}:${c.distance}`).join('|');
  }

  $: {
    const next = handFingerprint(you);
    if (next !== myHandFingerprint) {
      myHandFingerprint = next;
      myHandRevision += 1;
    }
  }

  $: {
    const next = handFingerprint(opp);
    if (next !== oppHandFingerprint) {
      oppHandFingerprint = next;
      oppHandRevision += 1;
    }
  }

  $: myHandCards = (you?.power_cards ?? []).map((c, idx) => ({
    id: `my-${myHandRevision}-${idx}-${c.direction}-${c.distance}`,
    idx,
    direction: c.direction,
    distance: c.distance,
    label: cardLabel(c)
  })) as DisplayCard[];

  $: oppHandCards = (opp?.power_cards ?? []).map((_, idx) => ({
    id: `opp-${oppHandRevision}-${idx}`,
    idx,
    label: 'Hidden'
  })) as DisplayCard[];

  function setMyCardEl(idx: number, el: HTMLButtonElement | null) {
    if (el) {
      myCardEls.set(idx, el);
      return;
    }
    myCardEls.delete(idx);
  }

  function cardRef(node: HTMLButtonElement, idx: number) {
    setMyCardEl(idx, node);
    return {
      destroy() {
        setMyCardEl(idx, null);
      }
    };
  }

  function centerOf(rect: DOMRect): [number, number] {
    return [rect.left + rect.width / 2, rect.top + rect.height / 2];
  }

  async function triggerDeal(target: 'you' | 'opp', newIndex: number) {
    if (!deckButtonEl) return;
    const deckRect = deckButtonEl.getBoundingClientRect();
    const [startX, startY] = centerOf(deckRect);

    await tick();

    let endX = startX;
    let endY = startY;

    if (target === 'you') {
      const targetEl = myCardEls.get(newIndex);
      if (targetEl) {
        const rect = targetEl.getBoundingClientRect();
        [endX, endY] = centerOf(rect);
      } else if (youRailEl) {
        const rect = youRailEl.getBoundingClientRect();
        [endX, endY] = centerOf(rect);
      }
    } else if (oppRailEl) {
      const rect = oppRailEl.getBoundingClientRect();
      [endX, endY] = centerOf(rect);
    }

    const token = ++flightToken;
    const card =
      target === 'you' ? (you?.power_cards?.[newIndex] ?? null) : null;
    const direction = card?.direction ?? 'RK';
    const distance = card?.distance ?? 0;

    const flight: FlightCard = {
      id: token,
      target,
      label: target === 'you' ? `${direction}${distance}` : 'RK',
      direction,
      distance,
      startX,
      startY,
      endX,
      endY,
      rotation: target === 'you' ? 9 : -9,
      scale: 0.86,
      active: false
    };

    flyingCards = [...flyingCards, flight];

    requestAnimationFrame(() => {
      flyingCards = flyingCards.map((entry) =>
        entry.id === token
          ? {
              ...entry,
              active: true,
              rotation: 0,
              scale: 1
            }
          : entry
      );
    });

    setTimeout(() => {
      flyingCards = flyingCards.filter((entry) => entry.id !== token);
    }, 520);
  }

  $: {
    const nextCount = you?.power_cards.length ?? 0;
    if (nextCount > myHandCount) {
      const newIndex = Math.max(0, nextCount - 1);
      void triggerDeal('you', newIndex);
    }
    myHandCount = nextCount;
  }

  $: {
    const nextCount = opp?.power_cards.length ?? 0;
    if (nextCount > oppHandCount) {
      void triggerDeal('opp', Math.max(0, nextCount - 1));
    }
    oppHandCount = nextCount;
  }

  $: previewPos = (() => {
    if (!state) return null;
    const idx = hoveredCardIndex ?? selectedCardIndex;
    if (idx === null) return null;
    const card = you?.power_cards?.[idx];
    if (!card) return null;
    const [dr, dc] = directionDelta(card.direction);
    const row = state.crown_pos[0] + dr * card.distance;
    const col = state.crown_pos[1] + dc * card.distance;
    if (row < 0 || row > 10 || col < 0 || col > 10) return null;
    return [row, col] as [number, number];
  })();

  function pickCard(idx: number) {
    if (!canControlTurn) return;
    selectedCardIndex = idx;

    const normal = legalMoves.find((m) => m.card_index === idx && m.use_hero === false);
    const hero = legalMoves.find((m) => m.card_index === idx && m.use_hero === true);

    if (!normal && hero && (you?.hero_cards ?? 0) > 0) useHero = true;
    if (normal) useHero = false;
  }

  function toggleHeroForCard(idx: number | null) {
    if (!canControlTurn || idx === null) return;
    if ((you?.hero_cards ?? 0) <= 0) return;
    selectedCardIndex = idx;
    useHero = !useHero;
  }

  function toggleHero() {
    if (!canControlTurn || (you?.hero_cards ?? 0) <= 0) return;
    useHero = !useHero;
  }

  function onHotkey(e: KeyboardEvent) {
    const key = e.key.toLowerCase();
    const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

    const cardIdx = keybinds.cards.findIndex((k) => k && k === key);
    if (cardIdx >= 0) {
      e.preventDefault();
      pickCard(cardIdx);
      return;
    }

    if (keybinds.hero && key === keybinds.hero) {
      e.preventDefault();
      toggleHeroForCard(hoveredCardIndex ?? selectedCardIndex);
      return;
    }

    if (keybinds.draw && key === keybinds.draw) {
      e.preventDefault();
      draw();
      return;
    }

    if (key === 'enter') {
      e.preventDefault();
      submitSelectedMove();
    }
  }

  function normalizeBinding(raw: string): string {
    return raw.trim().toLowerCase().slice(0, 1);
  }

  function setCardBinding(index: number, value: string) {
    const next = normalizeBinding(value);
    keybinds = {
      ...keybinds,
      cards: keybinds.cards.map((k, i) => (i === index ? next : k)) as Keybinds['cards']
    };
  }

  function setHeroBinding(value: string) {
    keybinds = { ...keybinds, hero: normalizeBinding(value) };
  }

  function setDrawBinding(value: string) {
    keybinds = { ...keybinds, draw: normalizeBinding(value) };
  }

  function onCardBindingInput(index: number, e: Event) {
    setCardBinding(index, (e.currentTarget as HTMLInputElement).value);
  }

  function onHeroBindingInput(e: Event) {
    setHeroBinding((e.currentTarget as HTMLInputElement).value);
  }

  function onDrawBindingInput(e: Event) {
    setDrawBinding((e.currentTarget as HTMLInputElement).value);
  }

  function resetKeybinds() {
    keybinds = { ...DEFAULT_KEYBINDS };
  }

  $: duplicateBindings = (() => {
    const entries = [
      ...keybinds.cards.filter(Boolean),
      keybinds.hero,
      keybinds.draw
    ].filter(Boolean);
    return new Set(entries).size !== entries.length;
  })();

  onMount(() => {
    try {
      const raw = localStorage.getItem('rk.keybinds');
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<Keybinds>;
        const cards = Array.isArray(parsed.cards)
          ? parsed.cards.slice(0, 5).map((v) => normalizeBinding(String(v ?? '')))
          : DEFAULT_KEYBINDS.cards;
        while (cards.length < 5) cards.push(DEFAULT_KEYBINDS.cards[cards.length]);
        keybinds = {
          cards: cards as Keybinds['cards'],
          hero: normalizeBinding(String(parsed.hero ?? DEFAULT_KEYBINDS.hero)),
          draw: normalizeBinding(String(parsed.draw ?? DEFAULT_KEYBINDS.draw))
        };
      }
    } catch {
      keybinds = { ...DEFAULT_KEYBINDS };
    }
    hasLoadedKeybinds = true;
    window.addEventListener('keydown', onHotkey);
  });

  $: if (hasLoadedKeybinds) {
    try {
      localStorage.setItem('rk.keybinds', JSON.stringify(keybinds));
    } catch {
    }
  }

  onDestroy(() => {
    window.removeEventListener('keydown', onHotkey);
  });

  function onBoardCell(e: CustomEvent<{ row: number; col: number }>) {
    if (!canControlTurn) return;
    if (hasServerLegalMoves) {
      if (!selectedMove || !selectedMove.target) return;
      if (selectedMove.target[0] !== e.detail.row || selectedMove.target[1] !== e.detail.col) return;
      game.makeMove({ card_index: selectedMove.card_index, use_knight: selectedMove.use_hero });
    } else {
      submitSelectedMove();
      return;
    }
    selectedCardIndex = null;
    useHero = false;
  }

  function submitSelectedMove() {
    if (!canControlTurn) return;
    if (selectedCardIndex === null) return;
    game.makeMove({ card_index: selectedCardIndex, use_knight: useHero });
    selectedCardIndex = null;
    useHero = false;
  }

  function onCardHover(idx: number | null) {
    hoveredCardIndex = idx;
  }

  function draw() {
    if (!canControlTurn) return;
    game.drawCard();
  }

  function winnerLabel(players: PlayerView[]) {
    const [a, b] = players;
    if (!a || !b) return null;
    if (a.score === b.score) return 'Draw';
    return a.score > b.score ? `${a.name} wins` : `${b.name} wins`;
  }

  async function create() {
    selectedCardIndex = null;
    useHero = false;
    await game.createRoom({
      player_name: name,
      mode,
      color_preference: colorPreference,
    });
    const createdId = $game?.room_id;
    if (createdId) {
      await goto(`/games/${encodeURIComponent(createdId)}`);
    }
  }

  async function join() {
    selectedCardIndex = null;
    useHero = false;
    const targetRoom = roomId.trim();
    await game.joinRoom({ room_id: targetRoom, player_name: name, spectator: joinAsSpectator });
    await goto(`/games/${encodeURIComponent(targetRoom)}`);
  }

  async function joinSpectator() {
    selectedCardIndex = null;
    useHero = false;
    const targetRoom = roomId.trim();
    joinAsSpectator = true;
    await game.joinRoom({ room_id: targetRoom, player_name: name, spectator: true });
    await goto(`/games/${encodeURIComponent(targetRoom)}`);
  }

  async function copyRoom() {
    const id = $game?.room_id;
    if (!id) return;
    try {
      await navigator.clipboard.writeText(id);
    } catch {
    }
  }

  async function joinRouteRoomIfNeeded() {
    if (!routeGameId || attemptedRouteJoin) return;
    const trimmed = routeGameId.trim();
    if (!trimmed) return;
    attemptedRouteJoin = true;
    roomId = trimmed;
    const currentRoom = $game?.room_id;
    if (currentRoom === trimmed && $game?.status === 'connected') return;
    await game.joinRoom({ room_id: trimmed, player_name: name });
  }

  $: if (routeGameId) {
    void joinRouteRoomIfNeeded();
  }

  $: onboardingSteps = [
    {
      id: 'join',
      label: 'Join or create a room',
      done: Boolean($game?.room_id)
    },
    {
      id: 'turn',
      label: isSpectator ? 'Watch turns and crown movement' : 'Wait for your turn',
      done: isSpectator ? Boolean(state) : Boolean(myTurn)
    },
    {
      id: 'card',
      label: isSpectator ? 'Read card direction + distance' : 'Pick a card from your hand',
      done: isSpectator ? Boolean(state) : selectedCardIndex !== null
    },
    {
      id: 'target',
      label: isSpectator ? 'Track score swings in Players panel' : 'Click a highlighted square to play',
      done: isSpectator ? Boolean(state?.move_history?.length) : Boolean(selectedMove?.target)
    }
  ];

  $: onboardingTip = isSpectator
    ? 'You are in spectator mode. You can watch live turns and open analysis without taking actions.'
    : myTurn
      ? 'Your turn: choose a card, then click one of the highlighted board squares.'
      : 'Use number keys (1-5) to preselect cards before your turn starts.';
</script>

<div class="shell">
  <header class="top">
    <div class="brand">
      <div class="crest" aria-hidden="true">
        <div class="card-back-roses">
          <img src="/assets/red.png" alt="" class="rose red" draggable="false" />
          <img src="/assets/white.png" alt="" class="rose white" draggable="false" />
        </div>
      </div>
      <div>
        <div class="title">Rosenkonig</div>
        <div class="subtitle muted">Server-authoritative, real-time</div>
      </div>
    </div>
    <div class="status" title={$game?.status ?? 'idle'}>
      {#if $game?.status === 'connected'}
        <Wifi size={18} />
      {:else}
        <WifiOff size={18} />
      {/if}
      <span class="muted">{$game?.status ?? 'idle'}</span>
    </div>
  </header>

  <main class="main">
    <section class="board-area">
      <div class="panel board-panel">
        <div class="arena">
          <div class={['hand-rail', 'opp', oppTurn ? 'active' : ''].join(' ')} bind:this={oppRailEl}>
            <div class="rail-label">{opp?.name ?? 'Opponent'}</div>
            <div class="hand-stack">
              {#if oppHandCards.length === 0}
                <div class="muted tiny">No cards</div>
              {:else}
                {#each oppHandCards as c, idx (c.id)}
                  <div class="play-card back" in:fly={{ x: -24, duration: 260, delay: idx * 40 }} out:fade={{ duration: 120 }}>
                    <div class="card-back-roses" aria-hidden="true">
                      <img src="/assets/red.png" alt="" class="rose red" draggable="false" />
                      <img src="/assets/white.png" alt="" class="rose white" draggable="false" />
                    </div>
                  </div>
                {/each}
              {/if}
            </div>
          </div>

          <div class="board-frame">
            <Board
              board={state?.board ?? Array.from({ length: 11 }, () => Array.from({ length: 11 }, () => 0))}
              crownPos={state?.crown_pos ?? [5, 5]}
              previewPos={previewPos}
              legalMoves={legalMoves}
              selectedCardIndex={selectedCardIndex}
              selectedUseHero={useHero}
              interactive={myTurn}
              on:cellclick={onBoardCell}
            />

            <div class="deck-zone" aria-label="draw pile">
              <button
                class={['deck', myTurn ? 'ready' : ''].join(' ')}
                on:click={draw}
                disabled={!canControlTurn || !state || state.game_over}
                style={`--deck-depth:${Math.max(2, Math.min(14, Math.ceil(drawPileCount / 2)))}`}
                bind:this={deckButtonEl}
              >
                <span>Deck</span>
                <small>Draw ({drawPileCount})</small>
              </button>
            </div>
          </div>

          <div class={['hand-rail', 'you', myTurn ? 'active' : ''].join(' ')} bind:this={youRailEl}>
            <div class="rail-label">{you?.name ?? 'You'}</div>
            <div class="hand-stack interactive">
              {#if myHandCards.length === 0}
                <div class="muted tiny">No cards</div>
              {:else}
                {#each myHandCards as c, idx (c.id)}
                  <button
                    class={[
                      'play-card',
                      'face',
                      selectedCardIndex === c.idx ? 'sel' : '',
                      selectedCardIndex === c.idx && useHero ? 'hero-card' : '',
                      myTurn ? '' : 'off'
                    ].join(' ')}
                    style={`--stagger:${idx};--fan:${idx - (myHandCards.length - 1) / 2};--dir-angle:${directionAngle(c.direction)}deg;--blade-len:${swordBladeLength(c.distance)}px;`}
                    on:click={() => pickCard(c.idx)}
                    on:mouseenter={() => onCardHover(c.idx)}
                    on:mouseleave={() => onCardHover(null)}
                    on:focus={() => onCardHover(c.idx)}
                    on:blur={() => onCardHover(null)}
                    disabled={!canControlTurn}
                    title={`${c.label} [${keybinds.cards[c.idx] || '-'}]`}
                    in:fly={{ x: 28, y: 18, duration: 280, delay: idx * 45 }}
                    out:fade={{ duration: 120 }}
                    use:cardRef={c.idx}
                  >
                    {#if selectedCardIndex === c.idx && useHero}
                      <span class="hero-badge">HERO</span>
                    {/if}
                    <span class="dir-tag">{c.direction}</span>
                    <div class="card-art" aria-hidden="true">
                      <div class="crown-meter">
                        <img src="/assets/crown.png" alt="" class="crown-mini" draggable="false" />
                        <span class="move-num overlay">{c.distance}</span>
                      </div>
                      <div class="sword-meter">
                        <span class="hilt"></span>
                        <span class="blade"></span>
                        <span class="tip"></span>
                      </div>
                    </div>
                  </button>
                {/each}
              {/if}
            </div>
          </div>
        </div>

        <div class="below">
          {#if !state}
            <div class="muted">Create or join a room to start.</div>
          {:else if state.game_over}
            <div class="end">
              <span>{winnerLabel(state.players) ?? 'Game over'}</span>
              {#if $game?.room_id}
                <a class="btn" href={`/games/${encodeURIComponent($game.room_id)}/analyze`}>Open analysis</a>
              {/if}
            </div>
          {:else}
            <div class={['turn', myTurn ? 'my' : 'their'].join(' ')}>
              <span>{myTurn ? 'Your turn' : `${state.current_turn.toUpperCase()} to move`}</span>
              {#if selectedMove}
                <span class="muted">Selected: {selectedCard ? cardLabel(selectedCard) : 'Card'} {selectedMove.use_hero ? '(Hero)' : ''}</span>
              {:else if selectedCardIndex !== null}
                <span class="muted">Pick a highlighted square</span>
              {/if}
            </div>
          {/if}
          {#if $game?.last_error}
            <div class="error">{$game.last_error}</div>
          {/if}

          {#if state && you}
            <div class="keybind-panel compact">
              <div class="muted tiny">
                Hotkeys:
                {#each keybinds.cards as k, i}
                  <span class="kbd">{k || '-'}</span><span class="muted"> card {i + 1}</span>
                {/each}
                / Hero <span class="kbd">{keybinds.hero || '-'}</span>
                / Draw <span class="kbd">{keybinds.draw || '-'}</span>
                / Play <span class="kbd">Enter</span>
              </div>

              <button class="btn ghost" on:click={() => (keybindSettingsOpen = !keybindSettingsOpen)}>
                {keybindSettingsOpen ? 'Hide key settings' : 'Key settings'}
              </button>

              {#if keybindSettingsOpen}
                <div class="keybind-grid">
                  {#each [0, 1, 2, 3, 4] as i}
                    <label class="label tiny">
                      <span class="muted">Card {i + 1}</span>
                      <input
                        class="field key-field"
                        value={keybinds.cards[i]}
                        maxlength="1"
                        on:input={(e) => onCardBindingInput(i, e)}
                      />
                    </label>
                  {/each}

                  <label class="label tiny">
                    <span class="muted">Hero</span>
                    <input class="field key-field" value={keybinds.hero} maxlength="1" on:input={onHeroBindingInput} />
                  </label>

                  <label class="label tiny">
                    <span class="muted">Draw</span>
                    <input class="field key-field" value={keybinds.draw} maxlength="1" on:input={onDrawBindingInput} />
                  </label>
                </div>

                <div class="tools">
                  <button class="btn" on:click={resetKeybinds}>Reset defaults</button>
                </div>

                {#if duplicateBindings}
                  <div class="hint">Some key bindings overlap; first matching action will trigger.</div>
                {/if}
              {/if}
            </div>
          {/if}
        </div>

        {#if flyingCards.length > 0}
          <div class="flight-layer" aria-hidden="true">
            {#each flyingCards as card (card.id)}
              <div
                class={['draw-flight', card.target === 'you' ? 'to-you' : 'to-opp', card.active ? 'active' : ''].join(' ')}
                style={`--sx:${card.startX}px;--sy:${card.startY}px;--ex:${card.endX}px;--ey:${card.endY}px;--rot:${card.rotation}deg;--scale:${card.scale}`}
              >
                <div class={['flight-card', card.target === 'you' ? 'face' : 'back'].join(' ')}>
                  {#if card.target === 'you'}
                    <span class="dir-tag">{card.direction}</span>
                    <div class="card-art" aria-hidden="true" style={`--dir-angle:${directionAngle(card.direction)}deg;--blade-len:${swordBladeLength(card.distance)}px;`}>
                      <div class="crown-meter">
                        <img src="/assets/crown.png" alt="" class="crown-mini" draggable="false" />
                        <span class="move-num overlay">{card.distance}</span>
                      </div>
                      <div class="sword-meter">
                        <span class="hilt"></span>
                        <span class="blade"></span>
                        <span class="tip"></span>
                      </div>
                    </div>
                  {:else}
                    <div class="card-back-roses" aria-hidden="true">
                      <img src="/assets/red.png" alt="" class="rose red" draggable="false" />
                      <img src="/assets/white.png" alt="" class="rose white" draggable="false" />
                    </div>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </section>

    <aside class="side">
      <div class="panel side-panel">
        <div class="section">
          <div class="section-title">Lobby</div>
          <div class="grid2">
            <label class="label">
              <span class="muted">Name</span>
              <div class="with-icon">
                <User size={16} />
                <input class="field" bind:value={name} placeholder="Your name" />
              </div>
            </label>

            <label class="label">
              <span class="muted">Mode</span>
              <select class="field" bind:value={mode}>
                <option value="single">Single (vs AI)</option>
                <option value="multi">Multi (2 players)</option>
              </select>
            </label>

            <label class="label">
              <span class="muted">Color</span>
              <select class="field" bind:value={colorPreference}>
                <option value="random">Random</option>
                <option value="red">Red</option>
                <option value="white">White</option>
              </select>
            </label>

            <label class="label">
              <span class="muted">Join role</span>
              <select class="field" bind:value={joinAsSpectator}>
                <option value={false}>Player</option>
                <option value={true}>Spectator</option>
              </select>
            </label>
          </div>

          <div class="actions">
            <button class="btn" on:click={create}>
              <Swords size={16} />
              <span>Create</span>
            </button>

            <div class="join">
              <input class="field" bind:value={roomId} placeholder="Room id" />
              <button class="btn" on:click={join} disabled={!roomId.trim()}>
                <DoorOpen size={16} />
                <span>Join</span>
              </button>
            </div>
            <button class="btn ghost" on:click={joinSpectator} disabled={!roomId.trim()}>
              <DoorOpen size={16} />
              <span>Spectate</span>
            </button>
          </div>

          {#if $game?.room_id}
            <div class="roomline">
              <div>
                <div class="muted">Room</div>
                <div class="room">{$game.room_id}</div>
              </div>
              <button class="btn" on:click={copyRoom} title="Copy room id"><Copy size={16} /></button>
            </div>
          {/if}

          {#if isSpectator}
            <div class="hint">Watching as spectator. Moves and draws are disabled for this connection.</div>
          {/if}

          {#if $game?.last_error?.includes('room is full')}
            <button class="btn ghost" on:click={joinSpectator} disabled={!roomId.trim()}>
              <DoorOpen size={16} />
              <span>Room full - Join as spectator</span>
            </button>
          {/if}
        </div>

        {#if showOnboarding}
          <div class="section onboarding">
            <div class="section-title">Quick Start</div>
            <div class="hint">{onboardingTip}</div>
            <div class="steps">
              {#each onboardingSteps as step}
                <div class={['step', step.done ? 'done' : ''].join(' ')}>
                  <span class="dot" aria-hidden="true"></span>
                  <span>{step.label}</span>
                </div>
              {/each}
            </div>
            <button class="btn ghost" on:click={() => (showOnboarding = false)}>Hide guide</button>
          </div>
        {:else}
          <div class="section onboarding-collapsed">
            <button class="btn ghost" on:click={() => (showOnboarding = true)}>Show quick guide</button>
          </div>
        {/if}

        <div class="section">
          <div class="section-title">Players</div>
          <div class="players">
            {#each state?.players ?? [] as p (p.color)}
              <div class={['p', p.color, state?.current_turn === p.color ? 'active' : ''].join(' ')}>
                <div class="row">
                  <div class="name">{p.name}</div>
                  <div class="tag">{p.color.toUpperCase()}</div>
                </div>
                <div class="row muted">
                  <span>Score</span>
                  <span class="mono">{p.score}</span>
                </div>
                <div class="row muted">
                  <span>Hero</span>
                  <span class="mono">{p.hero_cards}</span>
                </div>
              </div>
            {/each}
            {#if state && (state.players?.length ?? 0) < 2}
              <div class="muted">Waiting for opponent...</div>
            {/if}
          </div>
        </div>

      </div>
    </aside>
  </main>
</div>

<style>
  .shell {
    padding: 18px;
    max-width: 1180px;
    margin: 0 auto;
  }

  .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 14px;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .crest {
    width: 42px;
    height: 42px;
    border-radius: 14px;
    display: grid;
    place-items: center;
    background:
      radial-gradient(circle at 24% 18%, rgba(255, 255, 255, 0.26), transparent 46%),
      linear-gradient(165deg, rgba(44, 94, 178, 0.95), rgba(17, 46, 105, 0.97));
    border: 1px solid rgba(255, 255, 255, 0.48);
    box-shadow: 0 14px 30px rgba(0, 0, 0, 0.35);
    overflow: hidden;
  }

  .crest .card-back-roses {
    width: 30px;
    height: 30px;
  }

  .title {
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 0.01em;
  }

  .subtitle {
    font-size: 12px;
    margin-top: 2px;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-radius: 14px;
    border: 1px solid var(--stroke);
    background: rgba(0, 0, 0, 0.18);
  }

  .main {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 360px;
    gap: 16px;
    align-items: start;
  }

  .board-area {
    min-width: 0;
  }

  .board-panel {
    padding: 16px;
    overflow: visible;
  }

  .arena {
    display: grid;
    grid-template-columns: 124px minmax(0, 1fr) 124px;
    gap: 16px;
    align-items: center;
  }

  .board-frame {
    display: grid;
    justify-items: center;
    gap: 10px;
    padding-inline: 6px;
    width: 100%;
    min-width: 0;
    position: relative;
    z-index: 1;
  }

  .board-frame :global(.board-wrap) {
    width: 100% !important;
    max-width: 720px;
    min-width: 0;
  }

  .side {
    min-width: 0;
  }

  .deck-zone {
    position: relative;
    min-height: 60px;
    display: grid;
    place-items: center;
  }

  .deck {
    --deck-depth: 8;
    width: 86px;
    height: 54px;
    border-radius: 12px;
    border: 1px solid rgba(242, 193, 78, 0.28);
    color: rgba(255, 255, 255, 0.9);
    background:
      linear-gradient(140deg, rgba(20, 30, 50, 0.95), rgba(8, 10, 16, 0.95)),
      repeating-linear-gradient(45deg, rgba(242, 193, 78, 0.16) 0 5px, transparent 5px 10px);
    display: grid;
    place-items: center;
    gap: 2px;
    cursor: pointer;
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.28);
    transition: transform 160ms ease, box-shadow 160ms ease, border-color 120ms ease;
  }

  .deck::before,
  .deck::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 12px;
    pointer-events: none;
  }

  .deck::before {
    transform: translateY(calc(var(--deck-depth) * 0.4px));
    border: 1px solid rgba(255, 255, 255, 0.14);
    opacity: 0.6;
  }

  .deck::after {
    transform: translateY(calc(var(--deck-depth) * 0.75px));
    box-shadow: 0 calc(var(--deck-depth) * 0.45px) 0 rgba(255, 255, 255, 0.08);
    opacity: 0.75;
  }

  .deck small {
    font-size: 10px;
    color: rgba(234, 240, 255, 0.72);
  }

  .deck.ready:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 22px rgba(0, 0, 0, 0.34);
    border-color: rgba(242, 193, 78, 0.46);
  }

  .deck:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .flight-layer {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 70;
  }

  .draw-flight {
    position: fixed;
    left: 0;
    top: 0;
    transform: translate(var(--sx), var(--sy)) rotate(var(--rot)) scale(var(--scale));
    transition: transform 460ms cubic-bezier(0.22, 0.9, 0.3, 1), opacity 180ms ease;
    opacity: 0.98;
    will-change: transform, opacity;
  }

  .draw-flight.active {
    transform: translate(var(--ex), var(--ey)) rotate(0deg) scale(1);
  }

  .flight-card {
    width: 72px;
    height: 104px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.72);
    box-shadow: 0 14px 30px rgba(0, 0, 0, 0.35);
    position: relative;
    display: grid;
    place-items: center;
  }

  .flight-card.back {
    background:
      radial-gradient(circle at 24% 18%, rgba(255, 255, 255, 0.26), transparent 46%),
      linear-gradient(165deg, rgba(44, 94, 178, 0.95), rgba(17, 46, 105, 0.97));
    color: rgba(242, 247, 255, 0.98);
  }

  .flight-card.face {
    background:
      radial-gradient(circle at 22% 18%, rgba(255, 255, 255, 0.34), transparent 46%),
      linear-gradient(180deg, rgba(53, 111, 210, 0.96), rgba(26, 66, 150, 0.97));
    color: rgba(242, 247, 255, 0.98);
  }

  .flight-card.face .dir-tag,
  .play-card.face .dir-tag {
    position: absolute;
    left: 8px;
    top: 5px;
    font-size: 9px;
    font-weight: 900;
    letter-spacing: 0.08em;
    color: rgba(246, 250, 255, 0.95);
    text-shadow: 0 1px 0 rgba(0, 0, 0, 0.26);
  }

  .card-art {
    width: 100%;
    height: 100%;
    display: grid;
    align-content: start;
    justify-items: center;
    gap: 12px;
    padding-top: 14px;
  }

  .crown-meter {
    position: relative;
    width: 24px;
    height: 24px;
  }

  .crown-mini {
    width: 100%;
    height: 100%;
    object-fit: contain;
    filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35));
    pointer-events: none;
  }

  .move-num {
    font-size: 10px;
    font-weight: 900;
    line-height: 1;
    color: rgba(248, 252, 255, 0.98);
    text-shadow: 0 1px 0 rgba(0, 0, 0, 0.22);
  }

  .move-num.overlay {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -52%);
    pointer-events: none;
  }

  .sword-meter {
    position: relative;
    width: 0;
    height: 0;
    transform: translateY(3px) rotate(var(--dir-angle, 0deg));
    transform-origin: center;
  }

  .sword-meter .hilt {
    position: absolute;
    left: -5px;
    top: -4px;
    width: 10px;
    height: 8px;
    border-radius: 3px;
    background: linear-gradient(180deg, rgba(245, 203, 107, 0.96), rgba(208, 154, 34, 0.95));
    border: 1px solid rgba(255, 255, 255, 0.72);
    box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.18);
  }

  .sword-meter .blade {
    position: absolute;
    left: 5px;
    top: -3px;
    width: var(--blade-len, 7px);
    height: 6px;
    background: linear-gradient(180deg, rgba(247, 251, 255, 0.98), rgba(210, 226, 248, 0.95));
    border-top: 1px solid rgba(255, 255, 255, 0.85);
    border-bottom: 1px solid rgba(180, 204, 234, 0.9);
    box-shadow: inset 0 0 0 1px rgba(17, 41, 82, 0.18);
  }

  .sword-meter .tip {
    position: absolute;
    left: calc(5px + var(--blade-len, 7px));
    top: -4px;
    width: 0;
    height: 0;
    border-top: 4px solid transparent;
    border-bottom: 4px solid transparent;
    border-left: calc(5px + var(--blade-len, 7px) * 0.28) solid rgba(228, 240, 255, 0.98);
  }

  .hand-rail {
    min-height: 560px;
    border-radius: 16px;
    border: 1px solid var(--stroke);
    background: linear-gradient(180deg, rgba(0, 0, 0, 0.20), rgba(0, 0, 0, 0.32));
    display: grid;
    grid-template-rows: auto 1fr;
    padding: 10px;
    gap: 10px;
    overflow: hidden;
    position: relative;
    z-index: 2;
  }

  .hand-rail.active {
    box-shadow: inset 0 0 0 1px rgba(242, 193, 78, 0.2);
  }

  .rail-label {
    font-size: 11px;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    text-align: center;
    color: rgba(234, 240, 255, 0.78);
    font-weight: 700;
  }

  .hand-stack {
    display: grid;
    align-content: center;
    justify-content: center;
    gap: 8px;
    isolation: isolate;
  }

  .hand-stack.interactive {
    gap: 6px;
  }

  .play-card {
    width: 76px;
    height: 108px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.72);
    transform-origin: center bottom;
    box-shadow: 0 12px 20px rgba(0, 0, 0, 0.30);
    transition:
      transform 180ms cubic-bezier(0.22, 0.9, 0.3, 1),
      box-shadow 180ms ease,
      border-color 140ms ease,
      background 180ms ease;
  }

  .play-card.back {
    display: grid;
    place-items: center;
    background:
      radial-gradient(circle at 24% 18%, rgba(255, 255, 255, 0.26), transparent 46%),
      linear-gradient(165deg, rgba(44, 94, 178, 0.95), rgba(17, 46, 105, 0.97));
    color: rgba(242, 247, 255, 0.98);
  }

  .play-card.face {
    position: relative;
    display: grid;
    place-items: center;
    cursor: pointer;
    background:
      radial-gradient(circle at 22% 18%, rgba(255, 255, 255, 0.34), transparent 46%),
      linear-gradient(180deg, rgba(53, 111, 210, 0.96), rgba(26, 66, 150, 0.97));
    color: rgba(242, 247, 255, 0.98);
    transform: translateY(calc(var(--fan, 0) * 1px)) rotate(calc(var(--fan, 0) * 3.5deg));
  }

  .card-back-roses {
    position: relative;
    width: 44px;
    height: 44px;
  }

  .card-back-roses .rose {
    position: absolute;
    width: 24px;
    height: 24px;
    object-fit: contain;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.35));
    pointer-events: none;
  }

  .card-back-roses .rose.red {
    top: 1px;
    left: 1px;
    transform: rotate(-16deg);
  }

  .card-back-roses .rose.white {
    right: 1px;
    bottom: 1px;
    transform: rotate(16deg);
  }

  .play-card.face.hero-card {
    position: relative;
    border-color: rgba(242, 193, 78, 0.75);
    box-shadow:
      0 18px 30px rgba(0, 0, 0, 0.34),
      0 0 0 2px rgba(242, 193, 78, 0.32),
      inset 0 0 18px rgba(242, 193, 78, 0.16);
    background:
      radial-gradient(circle at 22% 18%, rgba(255, 255, 255, 0.45), transparent 48%),
      linear-gradient(180deg, rgba(250, 246, 220, 0.98), rgba(230, 220, 176, 0.96));
  }

  .play-card.face.hero-card::after {
    content: '';
    position: absolute;
    inset: -8px;
    border-radius: 14px;
    border: 2px solid rgba(242, 193, 78, 0.72);
    box-shadow: 0 0 16px rgba(242, 193, 78, 0.4);
    animation: hero-spark 420ms cubic-bezier(0.2, 0.8, 0.2, 1);
    pointer-events: none;
  }

  @keyframes hero-spark {
    0% {
      opacity: 0;
      transform: scale(0.86);
    }
    25% {
      opacity: 1;
      transform: scale(1);
    }
    100% {
      opacity: 0;
      transform: scale(1.1);
    }
  }

  .hero-badge {
    position: absolute;
    top: -8px;
    right: -4px;
    padding: 3px 7px;
    border-radius: 999px;
    border: 1px solid rgba(242, 193, 78, 0.75);
    background: linear-gradient(180deg, rgba(242, 193, 78, 0.98), rgba(206, 154, 38, 0.96));
    color: rgba(25, 20, 8, 0.95);
    font-size: 9px;
    font-weight: 900;
    letter-spacing: 0.08em;
  }

  .play-card.face:hover:not(.off),
  .play-card.face:focus-visible:not(.off) {
    transform: translateY(-12px) rotate(calc(var(--fan, 0) * 2deg)) scale(1.03);
    box-shadow: 0 18px 30px rgba(0, 0, 0, 0.34);
    border-color: rgba(242, 193, 78, 0.45);
  }

  .play-card.face.sel {
    transform: translateY(-16px) rotate(calc(var(--fan, 0) * 1.5deg)) scale(1.04);
    border-color: rgba(242, 193, 78, 0.6);
    box-shadow:
      0 22px 36px rgba(0, 0, 0, 0.4),
      0 0 0 2px rgba(242, 193, 78, 0.24);
  }

  .play-card.off {
    cursor: default;
    opacity: 0.58;
  }

  .below {
    margin-top: 12px;
    display: grid;
    gap: 8px;
  }

  .turn {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    border-radius: 14px;
    padding: 10px 12px;
    border: 1px solid var(--stroke);
    background: rgba(0, 0, 0, 0.18);
  }

  .turn.my {
    box-shadow: inset 0 0 0 1px rgba(242, 193, 78, 0.18);
  }

  .turn.their {
    opacity: 0.95;
  }

  .end {
    padding: 10px 12px;
    border-radius: 14px;
    border: 1px solid rgba(242, 193, 78, 0.35);
    background: rgba(242, 193, 78, 0.10);
    font-weight: 700;
  }

  .error {
    padding: 10px 12px;
    border-radius: 14px;
    border: 1px solid rgba(255, 107, 107, 0.35);
    background: rgba(255, 107, 107, 0.10);
    color: rgba(255, 255, 255, 0.92);
  }

  .side-panel {
    padding: 14px;
    display: grid;
    gap: 14px;
  }

  .section {
    display: grid;
    gap: 10px;
  }

  .section-title {
    font-weight: 800;
    letter-spacing: 0.01em;
    font-size: 12px;
    text-transform: uppercase;
    color: rgba(234, 240, 255, 0.78);
  }

  .grid2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .label {
    display: grid;
    gap: 6px;
  }

  .with-icon {
    display: grid;
    grid-template-columns: 22px 1fr;
    align-items: center;
    gap: 8px;
    padding-left: 10px;
    border-radius: 12px;
    border: 1px solid var(--stroke);
    background: rgba(0, 0, 0, 0.25);
  }

  .with-icon :global(input.field) {
    border: none;
    background: transparent;
    padding-left: 0;
  }

  .actions {
    display: grid;
    gap: 10px;
  }

  .onboarding {
    border: 1px solid rgba(242, 193, 78, 0.2);
    border-radius: 12px;
    padding: 10px;
    background: linear-gradient(180deg, rgba(242, 193, 78, 0.08), rgba(0, 0, 0, 0.06));
  }

  .steps {
    display: grid;
    gap: 8px;
  }

  .step {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: rgba(234, 240, 255, 0.9);
  }

  .step.done {
    color: rgba(168, 234, 168, 0.92);
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.38);
    background: rgba(255, 255, 255, 0.22);
  }

  .step.done .dot {
    border-color: rgba(122, 226, 122, 0.95);
    background: rgba(122, 226, 122, 0.95);
  }

  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .btn.ghost {
    background: rgba(255, 255, 255, 0.03);
    border-color: rgba(255, 255, 255, 0.2);
  }

  .join {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
    align-items: center;
  }

  .roomline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 14px;
    border: 1px solid var(--stroke);
    background: rgba(0, 0, 0, 0.18);
  }

  .room {
    font-weight: 800;
    letter-spacing: 0.02em;
  }

  .players {
    display: grid;
    gap: 10px;
  }

  .p {
    padding: 12px;
    border-radius: 14px;
    border: 1px solid var(--stroke);
    background: rgba(0, 0, 0, 0.18);
  }

  .p.active {
    box-shadow: inset 0 0 0 1px rgba(242, 193, 78, 0.22);
  }

  .p.red {
    border-color: rgba(226, 85, 85, 0.25);
  }

  .p.white {
    border-color: rgba(243, 244, 246, 0.18);
  }

  .row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
  }

  .name {
    font-weight: 800;
  }

  .tag {
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 999px;
    border: 1px solid var(--stroke);
    background: rgba(255, 255, 255, 0.06);
  }

  .mono {
    font-variant-numeric: tabular-nums;
  }

  .tools {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  .btn.on {
    border-color: rgba(242, 193, 78, 0.38);
    box-shadow: inset 0 0 0 1px rgba(242, 193, 78, 0.18);
  }

  .hint {
    padding: 8px 10px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.05);
    color: rgba(234, 240, 255, 0.82);
  }

  .keybind-panel {
    display: grid;
    gap: 10px;
    padding: 10px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    background: rgba(255, 255, 255, 0.04);
  }

  .keybind-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
  }

  .key-field {
    text-transform: lowercase;
    text-align: center;
    font-weight: 800;
    font-size: 14px;
    padding: 8px;
  }

  .tiny {
    font-size: 11px;
  }

  .kbd {
    display: inline-grid;
    place-items: center;
    min-width: 18px;
    height: 18px;
    padding: 0 4px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.22);
    background: rgba(0, 0, 0, 0.22);
    font-size: 11px;
    font-weight: 800;
    color: rgba(242, 193, 78, 0.95);
  }

  @media (max-width: 1220px) {
    .main {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 1000px) {
    .main {
      grid-template-columns: 1fr;
    }
    .arena {
      grid-template-columns: 1fr;
      gap: 10px;
    }
    .hand-rail {
      min-height: 0;
      grid-template-rows: auto auto;
    }
    .hand-stack {
      display: flex;
      flex-direction: row;
      justify-content: center;
      flex-wrap: wrap;
    }
    .play-card {
      width: 68px;
      height: 98px;
    }
    .opp {
      order: 1;
    }
    .board-frame {
      order: 2;
    }
    .you {
      order: 3;
    }
  }

  @media (max-width: 640px) {
    .shell {
      padding: 12px;
    }
    .grid2 {
      grid-template-columns: 1fr;
    }
    .keybind-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .play-card {
      width: 62px;
      height: 88px;
    }
    .play-card.face .center-dir {
      font-size: 22px;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .play-card {
      transition: none;
    }
    .play-card.face.hero-card::after {
      animation: none;
    }
  }
</style>
