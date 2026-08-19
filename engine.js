/**
 * Minesweeper ("Démineur") core engine — classic rules, zero DOM dependency.
 *
 * Cell states:  'hidden' | 'revealed' | 'flagged'
 * Game status:  'ready' | 'playing' | 'won' | 'lost'
 *
 * Classic rules implemented:
 *  - A grid of W x H cells, M of which are mines.
 *  - Revealing a mine ends the game (loss).
 *  - Revealing a safe cell shows the count of mines among its up-to-8
 *    neighbors. If that count is 0, all neighbors are auto-revealed too
 *    (flood fill), recursively.
 *  - Flagging marks a hidden cell as (suspected) mine; flagged cells can't
 *    be revealed by a direct click (must be unflagged first).
 *  - "Chording": clicking a revealed numbered cell whose flagged-neighbor
 *    count equals its number reveals all remaining unflagged neighbors.
 *    If any of those turns out to be a mine, the game is lost.
 *  - The game is won when every non-mine cell has been revealed.
 *
 * This file exposes a single global: `window.MinesweeperEngine`
 * (also usable in Node via `module.exports` for solver baselines / tests).
 */
(function (root) {
  'use strict';

  function inBounds(width, height, x, y) {
    return x >= 0 && x < width && y >= 0 && y < height;
  }

  function neighborsOf(width, height, x, y) {
    const out = [];
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        if (dx === 0 && dy === 0) continue;
        const nx = x + dx, ny = y + dy;
        if (inBounds(width, height, nx, ny)) out.push([nx, ny]);
      }
    }
    return out;
  }

  /**
   * Build a fresh game state from an explicit list of mine cells.
   * mineCells: array of [x, y] pairs (0-indexed, x = column, y = row).
   */
  function createGame(width, height, mineCells) {
    const isMine = Array.from({ length: height }, () => new Array(width).fill(false));
    for (const [x, y] of mineCells) {
      if (!inBounds(width, height, x, y)) {
        throw new Error(`Mine out of bounds: (${x}, ${y})`);
      }
      isMine[y][x] = true;
    }

    const adjacent = Array.from({ length: height }, () => new Array(width).fill(0));
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (isMine[y][x]) continue;
        let count = 0;
        for (const [nx, ny] of neighborsOf(width, height, x, y)) {
          if (isMine[ny][nx]) count++;
        }
        adjacent[y][x] = count;
      }
    }

    const cellState = Array.from({ length: height }, () => new Array(width).fill('hidden'));

    return {
      width,
      height,
      mines: mineCells.length,
      isMine,
      adjacent,
      cellState,
      status: 'ready',      // ready | playing | won | lost
      revealedCount: 0,
      flagCount: 0,
      firstRevealDone: false,
      lastAction: null,     // {type, x, y} for UI/animation hooks
    };
  }

  /**
   * Reveal a single cell (no cascade). Internal helper — callers should
   * use `reveal()` which handles flood fill and game-over bookkeeping.
   */
  function revealSingle(game, x, y) {
    if (game.cellState[y][x] !== 'hidden') return;
    game.cellState[y][x] = 'revealed';
    game.revealedCount++;
  }

  /**
   * Reveal the cell at (x, y). Classic flood-fill: if the revealed cell
   * has 0 adjacent mines, automatically reveal all its neighbors too
   * (recursively). Returns the mutated game state.
   */
  function reveal(game, x, y) {
    if (game.status === 'won' || game.status === 'lost') return game;
    if (!inBounds(game.width, game.height, x, y)) return game;
    if (game.cellState[y][x] !== 'hidden') return game;

    game.lastAction = { type: 'reveal', x, y };

    if (game.status === 'ready') game.status = 'playing';

    if (game.isMine[y][x]) {
      revealSingle(game, x, y);
      game.status = 'lost';
      revealAllMinesOnLoss(game);
      return game;
    }

    // Flood fill using an explicit stack (safe for large boards).
    const stack = [[x, y]];
    while (stack.length) {
      const [cx, cy] = stack.pop();
      if (game.cellState[cy][cx] !== 'hidden') continue;
      revealSingle(game, cx, cy);
      if (game.adjacent[cy][cx] === 0) {
        for (const [nx, ny] of neighborsOf(game.width, game.height, cx, cy)) {
          if (game.cellState[ny][nx] === 'hidden' && !game.isMine[ny][nx]) {
            stack.push([nx, ny]);
          }
        }
      }
    }

    game.firstRevealDone = true;
    checkWin(game);
    return game;
  }

  function revealAllMinesOnLoss(game) {
    for (let y = 0; y < game.height; y++) {
      for (let x = 0; x < game.width; x++) {
        if (game.isMine[y][x] && game.cellState[y][x] === 'hidden') {
          game.cellState[y][x] = 'revealed';
        }
      }
    }
  }

  /** Toggle a hidden cell between 'hidden' and 'flagged'. */
  function toggleFlag(game, x, y) {
    if (game.status === 'won' || game.status === 'lost') return game;
    if (!inBounds(game.width, game.height, x, y)) return game;
    const s = game.cellState[y][x];
    if (s === 'hidden') {
      game.cellState[y][x] = 'flagged';
      game.flagCount++;
    } else if (s === 'flagged') {
      game.cellState[y][x] = 'hidden';
      game.flagCount--;
    }
    game.lastAction = { type: 'flag', x, y };
    return game;
  }

  /**
   * "Chording": if (x, y) is revealed and numbered, and the number of
   * flagged neighbors equals that number, reveal all remaining hidden
   * (unflagged) neighbors at once. Classic speed-play convenience.
   */
  function chord(game, x, y) {
    if (game.status === 'won' || game.status === 'lost') return game;
    if (!inBounds(game.width, game.height, x, y)) return game;
    if (game.cellState[y][x] !== 'revealed') return game;

    const number = game.adjacent[y][x];
    if (number === 0) return game;

    const neighbors = neighborsOf(game.width, game.height, x, y);
    const flagged = neighbors.filter(([nx, ny]) => game.cellState[ny][nx] === 'flagged');
    if (flagged.length !== number) return game;

    game.lastAction = { type: 'chord', x, y };
    for (const [nx, ny] of neighbors) {
      if (game.cellState[ny][nx] === 'hidden') {
        reveal(game, nx, ny);
        if (game.status === 'lost') break;
      }
    }
    return game;
  }

  function checkWin(game) {
    const totalSafeCells = game.width * game.height - game.mines;
    if (game.revealedCount >= totalSafeCells && game.status !== 'lost') {
      game.status = 'won';
      // Auto-flag remaining mines for a clean final board.
      for (let y = 0; y < game.height; y++) {
        for (let x = 0; x < game.width; x++) {
          if (game.isMine[y][x] && game.cellState[y][x] === 'hidden') {
            game.cellState[y][x] = 'flagged';
          }
        }
      }
    }
  }

  // ---------------------------------------------------------------------
  // Seedable PRNG (mulberry32) — used for reproducible generation and for
  // client-side freeplay boards. Not cryptographic; fine for a game.
  // ---------------------------------------------------------------------
  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function shuffleInPlace(arr, rng) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }

  /**
   * Generate mine positions such that (safeX, safeY) and its up-to-8
   * neighbors are guaranteed mine-free — the classic "first click is
   * always safe" behavior for freeplay boards.
   * `rng` defaults to Math.random; pass a seeded one for reproducibility.
   */
  function generateMineCells(width, height, mines, safeX, safeY, rng) {
    rng = rng || Math.random;
    const forbidden = new Set();
    for (const [nx, ny] of [[safeX, safeY], ...neighborsOf(width, height, safeX, safeY)]) {
      forbidden.add(`${nx},${ny}`);
    }
    const candidates = [];
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (!forbidden.has(`${x},${y}`)) candidates.push([x, y]);
      }
    }
    if (mines > candidates.length) {
      throw new Error('Too many mines for this board size / safe zone.');
    }
    shuffleInPlace(candidates, rng);
    return candidates.slice(0, mines);
  }

  const MinesweeperEngine = {
    createGame,
    reveal,
    toggleFlag,
    chord,
    neighborsOf,
    inBounds,
    generateMineCells,
    mulberry32,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = MinesweeperEngine;
  } else {
    root.MinesweeperEngine = MinesweeperEngine;
  }
})(typeof window !== 'undefined' ? window : globalThis);