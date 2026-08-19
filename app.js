(function () {
  'use strict';
  const Engine = window.MinesweeperEngine;

  const DIFF_LABELS = {
    beginner: 'Beginner',
    intermediate: 'Intermediate',
    expert: 'Expert',
    mixed: 'Mixed',
  };

  const FREEPLAY_PRESETS = {
    beginner: { width: 9, height: 9, mines: 10 },
    intermediate: { width: 16, height: 16, mines: 40 },
    expert: { width: 30, height: 16, mines: 99 },
  };

  // ------------------------------------------------------------------
  // Global mutable state
  // ------------------------------------------------------------------
  const state = {
    mode: 'bank',                 // 'bank' | 'freeplay'
    game: null,                   // current Engine game object, or null
    pendingFreeplay: null,        // {width,height,mines} awaiting first click
    currentLevelMeta: null,       // {id, difficulty, seed, width, height, mines}
    freeplayPreset: 'beginner',
    flagMode: false,              // mobile "tap to flag" toggle
    timerStart: null,
    timerHandle: null,
    elapsedFrozen: 0,
  };

  // ------------------------------------------------------------------
  // DOM refs
  // ------------------------------------------------------------------
  const el = {
    menuBtn: document.getElementById('menu-btn'),
    closePanelBtn: document.getElementById('close-panel-btn'),
    backdrop: document.getElementById('backdrop'),

    tabBank: document.getElementById('tab-bank'),
    tabFreeplay: document.getElementById('tab-freeplay'),
    viewBank: document.getElementById('view-bank'),
    viewFreeplay: document.getElementById('view-freeplay'),

    diffFilter: document.getElementById('diff-filter'),
    levelIdInput: document.getElementById('level-id-input'),
    randomLevelBtn: document.getElementById('random-level-btn'),
    bankMeta: document.getElementById('bank-meta'),

    diffCards: Array.from(document.querySelectorAll('.diff-card')),
    customWidth: document.getElementById('custom-width'),
    customHeight: document.getElementById('custom-height'),
    customMines: document.getElementById('custom-mines'),
    startFreeplayBtn: document.getElementById('start-freeplay-btn'),

    mineDigits: document.getElementById('mine-digits'),
    timeDigits: document.getElementById('time-digits'),
    faceBtn: document.getElementById('face-btn'),
    boardStatus: document.getElementById('board-status'),
    board: document.getElementById('board'),
    flagModeBtn: document.getElementById('flag-mode-btn'),
  };

  // ------------------------------------------------------------------
  // Mobile drawer navigation (the level panel slides over the board)
  // ------------------------------------------------------------------
  const isMobile = () => window.matchMedia('(max-width: 720px), (max-height: 480px)').matches;

  function openDrawer() {
    document.body.classList.add('drawer-open');
  }

  function closeDrawer() {
    document.body.classList.remove('drawer-open');
  }

  el.menuBtn.addEventListener('click', openDrawer);
  el.closePanelBtn.addEventListener('click', closeDrawer);
  el.backdrop.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDrawer();
  });

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------
  function pad(n, width) {
    const neg = n < 0;
    let s = String(Math.abs(n));
    while (s.length < width - (neg ? 1 : 0)) s = '0' + s;
    return (neg ? '-' : '') + s;
  }

  function clearTimer() {
    if (state.timerHandle) {
      clearInterval(state.timerHandle);
      state.timerHandle = null;
    }
  }

  function startTimer() {
    clearTimer();
    state.timerStart = Date.now();
    state.timerHandle = setInterval(() => {
      const secs = Math.min(999, Math.floor((Date.now() - state.timerStart) / 1000));
      el.timeDigits.textContent = pad(secs, 3);
    }, 250);
  }

  function freezeTimer() {
    if (state.timerStart != null) {
      state.elapsedFrozen = Math.min(999, Math.floor((Date.now() - state.timerStart) / 1000));
    }
    clearTimer();
  }

  // ------------------------------------------------------------------
  // Board rendering
  // ------------------------------------------------------------------
  function cellSizeFor(width, height) {
    // Fit the board within both the available width AND the available
    // height (matters most in phone landscape, where height is the tight
    // dimension). Below MIN_CELL, digits/emoji stop rendering reliably on
    // mobile browsers, so we don't shrink further than that — the board
    // container scrolls instead (see .board { overflow: auto } in CSS).
    const MIN_CELL = 18;
    const availW = Math.min(window.innerWidth - 48, 720);
    const reservedV = isMobile() ? 190 : 260; // header + console + status + margins
    const availH = Math.min(window.innerHeight - reservedV, 640);
    const byWidth = Math.floor(availW / width);
    const byHeight = Math.floor(availH / height);
    return Math.max(MIN_CELL, Math.min(30, Math.min(byWidth, byHeight)));
  }

  function buildBoardDOM(width, height) {
    el.board.innerHTML = '';
    el.board.style.setProperty('--cell-size', cellSizeFor(width, height) + 'px');
    el.board.style.gridTemplateColumns = `repeat(${width}, var(--cell-size, 26px))`;
    el.board.style.gridTemplateRows = `repeat(${height}, var(--cell-size, 26px))`;

    const frag = document.createDocumentFragment();
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'cell hidden';
        btn.dataset.x = x;
        btn.dataset.y = y;
        btn.setAttribute('aria-label', `Cell ${x + 1}, ${y + 1}`);
        btn.addEventListener('click', onCellClick);
        btn.addEventListener('contextmenu', onCellRightClick);
        btn.addEventListener('auxclick', onCellAuxClick);
        btn.addEventListener('keydown', onCellKeydown);
        frag.appendChild(btn);
      }
    }
    el.board.appendChild(frag);
  }

  const NUMBER_GLYPH = ['', '1', '2', '3', '4', '5', '6', '7', '8'];

  function renderBoard() {
    const g = state.game;
    if (!g) return;
    const cells = el.board.children;
    for (let y = 0; y < g.height; y++) {
      for (let x = 0; x < g.width; x++) {
        const idx = y * g.width + x;
        const node = cells[idx];
        const s = g.cellState[y][x];
        node.className = 'cell';
        node.textContent = '';

        if (s === 'hidden') {
          node.classList.add('hidden');
        } else if (s === 'flagged') {
          node.classList.add('hidden', 'flagged');
          node.textContent = '🚩';
          if (g.status === 'lost' && !g.isMine[y][x]) {
            node.classList.add('mine-wrong');
            node.textContent = '❌';
          }
        } else if (s === 'revealed') {
          node.classList.add('revealed');
          if (g.isMine[y][x]) {
            node.classList.add('mine-cell');
            node.textContent = '💣';
          } else {
            const n = g.adjacent[y][x];
            if (n > 0) {
              node.classList.add('n' + n);
              node.textContent = NUMBER_GLYPH[n];
            }
          }
        }
      }
    }
  }

  function syncStatusAndCounters() {
    const g = state.game;
    if (!g) return;
    el.mineDigits.textContent = pad(g.mines - g.flagCount, 3);

    if (g.status === 'playing' && !state.timerHandle) startTimer();
    if (g.status === 'won' || g.status === 'lost') freezeTimer();
    if (g.status === 'ready') {
      el.timeDigits.textContent = pad(0, 3);
    }

    el.boardStatus.classList.remove('won', 'lost');
    if (g.status === 'won') {
      el.boardStatus.textContent = '✅ Won — every safe cell is revealed.';
      el.boardStatus.classList.add('won');
      el.faceBtn.textContent = '😎';
    } else if (g.status === 'lost') {
      el.boardStatus.textContent = '💥 Lost — you hit a mine.';
      el.boardStatus.classList.add('lost');
      el.faceBtn.textContent = '😵';
    } else {
      el.boardStatus.textContent = state.mode === 'freeplay' && state.pendingFreeplay
        ? 'Click a cell to start — the first click is always safe.'
        : ' ';
      el.faceBtn.textContent = '🙂';
    }
  }

  function refresh() {
    renderBoard();
    syncStatusAndCounters();
  }

  // ------------------------------------------------------------------
  // Game lifecycle
  // ------------------------------------------------------------------
  function loadBankLevel(level) {
    state.mode = 'bank';
    state.pendingFreeplay = null;
    state.currentLevelMeta = level;
    clearTimer();

    const g = Engine.createGame(level.width, level.height, level.mine_cells);
    state.game = g;
    buildBoardDOM(level.width, level.height);
    // The bank guarantees start_cell (+ neighbors) is mine-free — open it
    // immediately so every player/solver begins from the identical position.
    Engine.reveal(g, level.start_cell[0], level.start_cell[1]);

    el.bankMeta.innerHTML =
      `Level <b>#${level.id}</b> · ${DIFF_LABELS[level.difficulty]} · ` +
      `${level.width}×${level.height} · <b>${level.mines}</b> mines · seed=${level.seed}`;

    refresh();
  }

  function startFreeplay(width, height, mines) {
    state.mode = 'freeplay';
    state.currentLevelMeta = null;
    state.pendingFreeplay = { width, height, mines };
    state.game = null;
    clearTimer();
    el.timeDigits.textContent = pad(0, 3);
    el.mineDigits.textContent = pad(mines, 3);
    buildBoardDOM(width, height);

    // Show an all-hidden empty game so the grid + counters render before
    // the first click (which is when mines actually get placed).
    const dummy = Engine.createGame(width, height, []);
    dummy.mines = mines;
    state.game = dummy;
    refresh();
  }

  function materializeFreeplayFirstClick(x, y) {
    const { width, height, mines } = state.pendingFreeplay;
    const mineCells = Engine.generateMineCells(width, height, mines, x, y);
    const g = Engine.createGame(width, height, mineCells);
    state.game = g;
    state.pendingFreeplay = null;
    Engine.reveal(g, x, y);
  }

  function resetCurrent() {
    if (state.mode === 'bank' && state.currentLevelMeta) {
      loadBankLevel(state.currentLevelMeta);
    } else if (state.mode === 'freeplay') {
      const cfg = state.pendingFreeplay ||
        (state.game ? { width: state.game.width, height: state.game.height, mines: state.game.mines } : FREEPLAY_PRESETS.beginner);
      startFreeplay(cfg.width, cfg.height, cfg.mines);
    }
  }

  // ------------------------------------------------------------------
  // Cell interaction
  // ------------------------------------------------------------------
  function coordsFromEvent(e) {
    return [parseInt(e.currentTarget.dataset.x, 10), parseInt(e.currentTarget.dataset.y, 10)];
  }

  function ensureMaterialized(x, y) {
    if (state.mode === 'freeplay' && state.pendingFreeplay) {
      materializeFreeplayFirstClick(x, y);
      return true; // click already consumed as the reveal
    }
    return false;
  }

  function onCellClick(e) {
    const [x, y] = coordsFromEvent(e);
    if (!state.game || state.game.status === 'won' || state.game.status === 'lost') return;

    if (state.flagMode) {
      if (ensureMaterialized(x, y)) { refresh(); return; }
      Engine.toggleFlag(state.game, x, y);
      refresh();
      return;
    }

    if (ensureMaterialized(x, y)) { refresh(); return; }

    const s = state.game.cellState[y][x];
    if (s === 'revealed') {
      Engine.chord(state.game, x, y);
    } else if (s === 'hidden') {
      Engine.reveal(state.game, x, y);
    }
    refresh();
  }

  function onCellRightClick(e) {
    e.preventDefault();
    const [x, y] = coordsFromEvent(e);
    if (!state.game || state.game.status === 'won' || state.game.status === 'lost') return;
    if (state.mode === 'freeplay' && state.pendingFreeplay) return; // can't flag before board exists
    Engine.toggleFlag(state.game, x, y);
    refresh();
  }

  function onCellAuxClick(e) {
    if (e.button !== 1) return; // middle click only
    e.preventDefault();
    const [x, y] = coordsFromEvent(e);
    if (!state.game || state.game.status === 'won' || state.game.status === 'lost') return;
    if (state.game.cellState[y][x] === 'revealed') {
      Engine.chord(state.game, x, y);
      refresh();
    }
  }

  function onCellKeydown(e) {
    const [x, y] = coordsFromEvent(e);
    if (!state.game || state.game.status === 'won' || state.game.status === 'lost') return;
    if (e.key === 'f' || e.key === 'F') {
      e.preventDefault();
      if (state.mode === 'freeplay' && state.pendingFreeplay) return;
      Engine.toggleFlag(state.game, x, y);
      refresh();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (ensureMaterialized(x, y)) { refresh(); return; }
      const s = state.game.cellState[y][x];
      if (s === 'revealed') Engine.chord(state.game, x, y);
      else if (s === 'hidden') Engine.reveal(state.game, x, y);
      refresh();
    }
  }

  // ------------------------------------------------------------------
  // Controls wiring
  // ------------------------------------------------------------------
  function setMode(mode) {
    state.mode = mode;
    el.tabBank.classList.toggle('active', mode === 'bank');
    el.tabFreeplay.classList.toggle('active', mode === 'freeplay');
    el.viewBank.classList.toggle('active', mode === 'bank');
    el.viewFreeplay.classList.toggle('active', mode === 'freeplay');
  }

  el.tabBank.addEventListener('click', () => setMode('bank'));
  el.tabFreeplay.addEventListener('click', () => {
    setMode('freeplay');
    if (!state.game || state.mode !== 'freeplay') {
      const p = FREEPLAY_PRESETS[state.freeplayPreset];
      startFreeplay(p.width, p.height, p.mines);
    }
  });

  function filteredLevelIds() {
    const filter = el.diffFilter.value;
    if (filter === 'all') return LEVEL_BANK.map((l) => l.id);
    return LEVEL_BANK.filter((l) => l.difficulty === filter).map((l) => l.id);
  }

  const DIFF_ORDER = ['beginner', 'intermediate', 'expert', 'mixed'];

  function populateLevelSelect(preserveId) {
    const filter = el.diffFilter.value;
    const groups = { beginner: [], intermediate: [], expert: [], mixed: [] };
    for (const l of LEVEL_BANK) {
      if (filter !== 'all' && l.difficulty !== filter) continue;
      groups[l.difficulty].push(l);
    }

    el.levelIdInput.innerHTML = '';
    for (const diff of DIFF_ORDER) {
      if (!groups[diff].length) continue;
      const og = document.createElement('optgroup');
      og.label = DIFF_LABELS[diff];
      for (const l of groups[diff]) {
        const opt = document.createElement('option');
        opt.value = l.id;
        opt.textContent = `#${l.id} · ${l.width}×${l.height} · ${l.mines} mines`;
        og.appendChild(opt);
      }
      el.levelIdInput.appendChild(og);
    }

    const stillValid = preserveId != null &&
      (filter === 'all' || LEVEL_BANK.find((l) => l.id === preserveId)?.difficulty === filter);
    el.levelIdInput.value = stillValid ? String(preserveId) : el.levelIdInput.options[0]?.value;
  }

  el.diffFilter.addEventListener('change', () => {
    populateLevelSelect(state.currentLevelMeta ? state.currentLevelMeta.id : null);
  });

  el.levelIdInput.addEventListener('change', () => {
    const id = parseInt(el.levelIdInput.value, 10);
    const level = LEVEL_BANK.find((l) => l.id === id);
    if (!level) return;
    loadBankLevel(level);
    closeDrawer();
  });

  el.randomLevelBtn.addEventListener('click', () => {
    const ids = filteredLevelIds();
    const id = ids[Math.floor(Math.random() * ids.length)];
    const level = LEVEL_BANK.find((l) => l.id === id);
    el.levelIdInput.value = id;
    loadBankLevel(level);
    closeDrawer();
  });

  el.diffCards.forEach((card) => {
    card.addEventListener('click', () => {
      el.diffCards.forEach((c) => c.classList.remove('active'));
      card.classList.add('active');
      state.freeplayPreset = card.dataset.diff;
      const p = FREEPLAY_PRESETS[state.freeplayPreset];
      el.customWidth.value = p.width;
      el.customHeight.value = p.height;
      el.customMines.value = p.mines;
    });
  });

  el.startFreeplayBtn.addEventListener('click', () => {
    let w = parseInt(el.customWidth.value, 10);
    let h = parseInt(el.customHeight.value, 10);
    let m = parseInt(el.customMines.value, 10);
    w = Math.min(40, Math.max(5, w || 9));
    h = Math.min(24, Math.max(5, h || 9));
    const maxMines = w * h - 9;
    m = Math.min(maxMines, Math.max(1, m || 10));
    startFreeplay(w, h, m);
    closeDrawer();
  });

  el.faceBtn.addEventListener('click', resetCurrent);

  el.flagModeBtn.addEventListener('click', () => {
    state.flagMode = !state.flagMode;
    el.flagModeBtn.parentElement.classList.toggle('active', state.flagMode);
    el.flagModeBtn.textContent = state.flagMode ? '🚩 Flag mode: ON' : '🚩 Flag mode: OFF';
  });

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------
  populateLevelSelect();
  loadBankLevel(LEVEL_BANK[0]);
  // On mobile, land with the level panel slid open over level 1's board, so
  // picking a level is the very first thing you see. On desktop the panel
  // is always visible in its own column, so this has no visible effect.
  if (isMobile()) openDrawer();

  // Re-fit the board (without rebuilding it) when the viewport changes size
  // or orientation, e.g. rotating a phone.
  let resizeHandle = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeHandle);
    resizeHandle = setTimeout(() => {
      if (!state.game) return;
      el.board.style.setProperty('--cell-size', cellSizeFor(state.game.width, state.game.height) + 'px');
    }, 100);
  });
})();
