"""
Baseline #1 — Naive Single-Point Solver.

WHAT IT DOES
------------
This solver only ever looks at *one revealed number at a time* and applies
two textbook-simple deduction rules to it:

  Rule A ("satisfied"): a revealed cell showing number N has exactly N
  flagged neighbors already -> every OTHER hidden neighbor is guaranteed
  SAFE. Reveal them.

  Rule B ("exhausted"): a revealed cell showing number N has exactly N
  hidden neighbors *in total* -> every one of those hidden neighbors must
  be a mine. Flag them (this doesn't cost a "touch"; it only injects more
  information other cells' Rule A can use next).

The solver repeats "scan every revealed numbered cell, apply A and B"
until a full pass produces no new safe cell and no new flag. At that
point it is *stuck*: nothing can be deduced with certainty, so it must
guess — by default a uniformly random hidden cell, via the pluggable
`guess_fn` (see guessing.py); pass a different one (e.g.
guessing.probability_guess) to swap in a smarter guessing strategy
without touching this file.

This is intentionally the simplest possible deduction strategy — it has
no notion of probability, no global constraint solving across
overlapping neighborhoods, and no chording. It is the natural "naive"
baseline that smarter solvers (constraint propagation / probabilistic
guessing) will be compared against later.

SCORING
-------
A "touch" = one deliberate reveal decision made by the solver (matching
one real mouse click on a hidden cell — including the level's initial
guaranteed-safe opening move, since that is a click too). Cascades opened
for free by a 0-cell do NOT count as extra touches, exactly like a real
game. Flags are not counted as touches (in classic play you are never
required to flag anything to win).

Per-level score combines the two things that actually matter:
  - if WON: score = touches used (lower is better)
  - if LOST: score = touches used + (safe cells still hidden at the time
    of the loss) as a penalty, so a solver that guesses into a mine on a
    huge, mostly-unsolved board is scored much worse than one that loses
    right at the very end with almost nothing left to reveal.

The GLOBAL SCORE printed at the end is the mean of that per-level score
across every level that was run. Lower is better; it rewards both a high
win rate and playing efficiently.
"""
import random

import engine as E
import guessing


def _deduce_pass(game):
    """One full scan of every revealed numbered cell.
    Returns (safe_cells, new_flags) found by rules A and B."""
    safe_cells = set()
    new_flags = []

    for y in range(game.height):
        for x in range(game.width):
            if game.cell_state[y][x] != "revealed":
                continue
            number = game.adjacent[y][x]
            if number == 0:
                continue

            neigh = E.neighbors_of(game.width, game.height, x, y)
            hidden = [(nx, ny) for nx, ny in neigh if game.cell_state[ny][nx] == "hidden"]
            flagged = [(nx, ny) for nx, ny in neigh if game.cell_state[ny][nx] == "flagged"]
            if not hidden:
                continue

            # Rule A: satisfied -> remaining hidden neighbors are safe.
            if len(flagged) == number:
                for c in hidden:
                    safe_cells.add(c)
                continue

            # Rule B: exhausted -> every hidden neighbor is a mine.
            if len(flagged) + len(hidden) == number:
                for c in hidden:
                    new_flags.append(c)

    return safe_cells, new_flags


def solve_level(level, rng, max_touches=None, guess_fn=None):
    """Play a single level with the naive solver.

    guess_fn(game, rng) -> (x, y) is called whenever no certain deduction
    remains; defaults to guessing.random_guess. Pass guessing.probability_guess
    (or any function with the same signature) to plug in a smarter guesser.

    Returns a dict with the outcome: status, touches, revealed_count,
    total_safe_cells, guesses_made.
    """
    guess_fn = guess_fn or guessing.random_guess
    game = E.create_game(level["width"], level["height"], level["mine_cells"])
    touches = 0
    guesses = 0

    # The level's guaranteed-safe opening move — counts as touch #1,
    # identical to what happens automatically when the web page loads it.
    E.reveal(game, level["start_cell"][0], level["start_cell"][1])
    touches += 1

    total_safe_cells = game.width * game.height - game.mines

    while game.status == "playing":
        if max_touches is not None and touches >= max_touches:
            break

        safe_cells, new_flags = _deduce_pass(game)

        # Apply newly deduced mines first — cheap, and helps later passes.
        for x, y in new_flags:
            if game.cell_state[y][x] == "hidden":
                E.toggle_flag(game, x, y)

        if safe_cells:
            for x, y in safe_cells:
                if game.cell_state[y][x] != "hidden":
                    continue
                E.reveal(game, x, y)
                touches += 1
                if game.status != "playing":
                    break
            continue  # re-scan with fresh information before guessing

        if new_flags:
            # New flags alone might unlock a Rule A elsewhere next pass.
            continue

        # Stuck: no certain deduction possible anywhere on the board.
        hidden = E.hidden_cells(game)
        if not hidden:
            break
        guesses += 1
        x, y = guess_fn(game, rng)
        E.reveal(game, x, y)
        touches += 1

    hidden_safe_remaining = sum(
        1
        for yy in range(game.height)
        for xx in range(game.width)
        if game.cell_state[yy][xx] != "revealed" and not game.is_mine[yy][xx]
    )

    if game.status == "won":
        score = touches
    elif game.status == "lost":
        score = touches + hidden_safe_remaining
    else:  # hit max_touches cap without resolving (shouldn't normally happen)
        score = touches + hidden_safe_remaining

    return {
        "id": level["id"],
        "difficulty": level["difficulty"],
        "width": level["width"],
        "height": level["height"],
        "mines": level["mines"],
        "status": game.status,
        "touches": touches,
        "guesses": guesses,
        "revealed_count": game.revealed_count,
        "total_safe_cells": total_safe_cells,
        "score": score,
    }
