<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { game, type LegalMove, type PlayerView, type RoomMode } from '$lib/stores/game';
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

  let selectedCardIndex: number | null = null;
  let hoveredCardIndex: number | null = null;
  let useHero = false;
  let myHandRevision = 0;
  let oppHandRevision = 0;
  let myHandFingerprint = '';
  let oppHandFingerprint = '';
  let myHandCount = 0;
  let oppHandCount = 0;
  let dealToken = 0;
  let dealTarget: 'you' | 'opp' | null = null;
  let keybinds: Keybinds = { ...DEFAULT_KEYBINDS };
  let keybindSettingsOpen = false;
  let hasLoadedKeybinds = false;

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

  $: legalMoves = (state?.legal_moves ?? []) as LegalMove[];
  $: hasServerLegalMoves = legalMoves.length > 0;

  $: selectedMove =
    !hasServerLegalMoves || selectedCardIndex === null
      ? null
      : legalMoves.find((m) => m.card_index === selectedCardIndex && m.use_hero === useHero) ?? null;
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

  function triggerDeal(target: 'you' | 'opp') {
    dealTarget = target;
    dealToken += 1;
    const token = dealToken;
    setTimeout(() => {
      if (token === dealToken) dealTarget = null;
    }, 340);
  }

  $: {
    const nextCount = you?.power_cards.length ?? 0;
    if (nextCount > myHandCount) triggerDeal('you');
    myHandCount = nextCount;
  }

  $: {
    const nextCount = opp?.power_cards.length ?? 0;
    if (nextCount > oppHandCount) triggerDeal('opp');
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
    if (!myTurn) return;
    selectedCardIndex = idx;

    const normal = legalMoves.find((m) => m.card_index === idx && m.use_hero === false);
    const hero = legalMoves.find((m) => m.card_index === idx && m.use_hero === true);

    if (!normal && hero && (you?.hero_cards ?? 0) > 0) useHero = true;
    if (normal) useHero = false;
  }

  function toggleHeroForCard(idx: number | null) {
    if (!myTurn || idx === null) return;
    if ((you?.hero_cards ?? 0) <= 0) return;
    selectedCardIndex = idx;
    useHero = !useHero;
  }

  function toggleHero() {
    if (!myTurn || (you?.hero_cards ?? 0) <= 0) return;
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
    if (!myTurn) return;
    if (hasServerLegalMoves) {
      if (!selectedMove) return;
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
    if (!myTurn) return;
    if (selectedCardIndex === null) return;
    game.makeMove({ card_index: selectedCardIndex, use_knight: useHero });
    selectedCardIndex = null;
    useHero = false;
  }

  function onCardHover(idx: number | null) {
    hoveredCardIndex = idx;
  }

  function draw() {
    if (!myTurn) return;
    game.drawCard();
    triggerDeal('you');
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
    await game.createRoom({ player_name: name, mode });
  }

  async function join() {
    selectedCardIndex = null;
    useHero = false;
    await game.joinRoom({ room_id: roomId.trim(), player_name: name });
  }

  async function copyRoom() {
    const id = $game?.room_id;
    if (!id) return;
    try {
      await navigator.clipboard.writeText(id);
    } catch {
    }
  }
</script>

<div class="shell">
  <header class="top">
    <div class="brand">
      <div class="crest">RK</div>
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
          <div class={['hand-rail', 'opp', oppTurn ? 'active' : ''].join(' ')}>
            <div class="rail-label">{opp?.name ?? 'Opponent'}</div>
            <div class="hand-stack">
              {#if oppHandCards.length === 0}
                <div class="muted tiny">No cards</div>
              {:else}
                {#each oppHandCards as c, idx (c.id)}
                  <div class="play-card back" in:fly={{ x: -24, duration: 260, delay: idx * 40 }} out:fade={{ duration: 120 }}>
                    <span>RK</span>
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
              <button class={['deck', myTurn ? 'ready' : '', dealTarget ? 'dealing' : ''].join(' ')} on:click={draw} disabled={!myTurn || !state || state.game_over}>
                <span>Deck</span>
                <small>Draw</small>
              </button>
              {#if dealTarget}
                {#key `${dealTarget}-${dealToken}`}
                  <div class={['deal-ghost', dealTarget].join(' ')} in:fly={{ x: dealTarget === 'you' ? 90 : -90, y: dealTarget === 'you' ? 55 : -55, duration: 300 }} out:fade={{ duration: 60 }}>
                    RK
                  </div>
                {/key}
              {/if}
            </div>
          </div>

          <div class={['hand-rail', 'you', myTurn ? 'active' : ''].join(' ')}>
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
                    style={`--stagger:${idx};--fan:${idx - (myHandCards.length - 1) / 2};`}
                    on:click={() => pickCard(c.idx)}
                    on:mouseenter={() => onCardHover(c.idx)}
                    on:mouseleave={() => onCardHover(null)}
                    on:focus={() => onCardHover(c.idx)}
                    on:blur={() => onCardHover(null)}
                    disabled={!myTurn}
                    title={`${c.label} [${keybinds.cards[c.idx] || '-'}]`}
                    in:fly={{ x: 28, y: 18, duration: 280, delay: idx * 45 }}
                    out:fade={{ duration: 120 }}
                  >
                    {#if selectedCardIndex === c.idx && useHero}
                      <span class="hero-badge">HERO</span>
                    {/if}
                    <span class="corner">{c.direction}</span>
                    <span class="center-dir">{directionGlyph(c.direction)}</span>
                    <span class="dist">{c.distance}</span>
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
            <div class="end">{winnerLabel(state.players) ?? 'Game over'}</div>
          {:else}
            <div class={['turn', myTurn ? 'my' : 'their'].join(' ')}>
              <span>{myTurn ? 'Your turn' : `${state.current_turn.toUpperCase()} to move`}</span>
              {#if selectedMove}
                <span class="muted">Selected: {cardLabel(selectedMove.card)} {selectedMove.use_hero ? '(Hero)' : ''}</span>
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
        </div>

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
    background: linear-gradient(180deg, rgba(242, 193, 78, 0.22), rgba(242, 193, 78, 0.08));
    border: 1px solid rgba(242, 193, 78, 0.34);
    box-shadow: 0 14px 30px rgba(0, 0, 0, 0.35);
    font-weight: 800;
    letter-spacing: 0.02em;
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
    grid-template-columns: 1fr 360px;
    gap: 16px;
    align-items: start;
  }

  .board-panel {
    padding: 16px;
  }

  .arena {
    display: grid;
    grid-template-columns: 112px minmax(0, 1fr) 112px;
    gap: 12px;
    align-items: center;
  }

  .board-frame {
    display: grid;
    justify-items: center;
    gap: 10px;
  }

  .deck-zone {
    position: relative;
    min-height: 60px;
    display: grid;
    place-items: center;
  }

  .deck {
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

  .deal-ghost {
    position: absolute;
    top: 2px;
    width: 62px;
    height: 42px;
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.24);
    display: grid;
    place-items: center;
    color: rgba(255, 255, 255, 0.86);
    font-size: 11px;
    font-weight: 800;
    background: linear-gradient(145deg, rgba(24, 34, 58, 0.95), rgba(8, 10, 16, 0.95));
    pointer-events: none;
  }

  .hand-rail {
    min-height: 560px;
    border-radius: 16px;
    border: 1px solid var(--stroke);
    background: linear-gradient(180deg, rgba(0, 0, 0, 0.20), rgba(0, 0, 0, 0.32));
    display: grid;
    grid-template-rows: auto 1fr;
    padding: 10px 8px;
    gap: 10px;
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
    border: 1px solid rgba(255, 255, 255, 0.20);
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
      radial-gradient(circle at 25% 20%, rgba(255, 255, 255, 0.18), transparent 48%),
      repeating-linear-gradient(45deg, rgba(242, 193, 78, 0.20) 0 6px, rgba(8, 12, 20, 0.65) 6px 12px),
      linear-gradient(160deg, rgba(24, 34, 58, 0.92), rgba(10, 12, 18, 0.96));
    color: rgba(255, 255, 255, 0.86);
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.08em;
  }

  .play-card.face {
    position: relative;
    display: grid;
    place-items: center;
    cursor: pointer;
    background:
      radial-gradient(circle at 22% 18%, rgba(255, 255, 255, 0.40), transparent 48%),
      linear-gradient(180deg, rgba(245, 242, 228, 0.96), rgba(223, 217, 198, 0.95));
    color: rgba(19, 25, 34, 0.95);
    transform: translateY(calc(var(--fan, 0) * 1px)) rotate(calc(var(--fan, 0) * 3.5deg));
  }

  .play-card.face .corner {
    position: absolute;
    left: 8px;
    top: 8px;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.08em;
  }

  .play-card.face .center-dir {
    font-size: 28px;
    font-weight: 800;
    line-height: 1;
    margin-top: -4px;
  }

  .play-card.face .dist {
    position: absolute;
    right: 8px;
    bottom: 8px;
    width: 22px;
    height: 22px;
    border-radius: 999px;
    display: grid;
    place-items: center;
    font-size: 12px;
    font-weight: 900;
    background: rgba(19, 25, 34, 0.1);
    border: 1px solid rgba(19, 25, 34, 0.22);
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
