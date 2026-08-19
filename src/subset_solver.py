"""
Baseline 2 — "SubSweep": Subset / Constraint-Subtraction Solver.

WHAT IT ADDS OVER BASELINE 1 (naive_solver.py)
-----------------------------------------------
Baseline 1 only ever looks at ONE revealed number at a time. SubSweep
compares PAIRS of revealed numbers and reasons about their neighborhoods
as sets — the standard "subset rule" used by most real Minesweeper
solvers, one step below full CSP/backtracking.

Each revealed numbered cell defines a constraint:

    constraint = (S, k)

where S is the set of its still-hidden, unflagged neighbor cells, and k
is how many mines remain to be found among them:

    k = number_shown_on_cell - already_flagged_neighbors

(Note k automatically shrinks as neighboring mines get flagged — that's
the "reduction" you described: once a bomb is found, every constraint
touching it gets one less mine to look for on the next pass.)

Baseline 1's two rules are just the special cases k == 0 and k == len(S).
SubSweep adds the general case:

    Subset rule: if constraint A = (S_A, k_A) and constraint B = (S_B, k_B)
    with S_A a *strict subset* of S_B, then the cells only in B
    (S_B - S_A) contain exactly (k_B - k_A) mines.

      - if (k_B - k_A) == 0                    -> every cell in S_B - S_A is SAFE
      - if (k_B - k_A) == len(S_B - S_A)        -> every cell in S_B - S_A is a MINE

This lets SubSweep solve patterns baseline 1 can never resolve without
guessing (classic example: a "1" next to a "2" sharing cells, where the
"2"'s extra cell is provably a mine even though neither number alone is
satisfied or exhausted).

Everything else — including the guessing strategy when truly stuck
(uniform random hidden cell) — is kept IDENTICAL to baseline 1 on
purpose, so any difference in the global score is attributable only to
the extra deduction power, not to a different guessing heuristic.
"""
import engine as E
import guessing


def _build_constraints(game):
    """One constraint per revealed numbered cell with hidden neighbors left."""
    constraints = []
    for y in range(game.height):
        for x in range(game.width):
            if game.cell_state[y][x] != "revealed":
                continue
            number = game.adjacent[y][x]
            if number == 0:
                continue

            neigh = E.neighbors_of(game.width, game.height, x, y)
            hidden = frozenset((nx, ny) for nx, ny in neigh if game.cell_state[ny][nx] == "hidden")
            if not hidden:
                continue
            flagged_count = sum(1 for nx, ny in neigh if game.cell_state[ny][nx] == "flagged")
            k = number - flagged_count
            constraints.append((hidden, k))
    return constraints


def _deduce_pass(game):
    """One full round of: single-point rules + pairwise subset rule.
    Returns (safe_cells, mine_cells) discovered this round."""
    constraints = _build_constraints(game)
    safe_cells = set()
    mine_cells = set()

    # Single-point rules (k==0 -> all safe; k==len(S) -> all mines).
    # These are just the subset rule against the "empty constraint", kept
    # explicit because they're the cheapest, most common deductions.
    for cells, k in constraints:
        if k == 0:
            safe_cells |= cells
        elif k == len(cells):
            mine_cells |= cells

    # Index constraints by cell so we only compare pairs that actually
    # overlap, instead of every pair on the board (keeps this fast even
    # on Expert-sized boards with hundreds of active constraints).
    by_cell = {}
    for idx, (cells, _k) in enumerate(constraints):
        for c in cells:
            by_cell.setdefault(c, []).append(idx)

    candidate_pairs = set()
    for idxs in by_cell.values():
        for i in idxs:
            for j in idxs:
                if i != j:
                    candidate_pairs.add((i, j))

    for i, j in candidate_pairs:
        cells_a, k_a = constraints[i]
        cells_b, k_b = constraints[j]
        if len(cells_a) >= len(cells_b):
            continue  # need a strict subset; skip equal/larger sets
        if not cells_a.issubset(cells_b):
            continue
        diff = cells_b - cells_a
        diff_k = k_b - k_a
        if diff_k == 0:
            safe_cells |= diff
        elif diff_k == len(diff):
            mine_cells |= diff
        # 0 < diff_k < len(diff): genuinely ambiguous from this pair alone —
        # left for a probability-based baseline 3 to handle, not SubSweep.

    # Don't re-flag/re-reveal cells the caller already knows about.
    safe_cells -= mine_cells  # (shouldn't overlap if constraints are consistent, but be safe)
    return safe_cells, mine_cells


def solve_level(level, rng, max_touches=None, guess_fn=None):
    """Same signature/return shape as naive_solver.solve_level, so
    run_baseline.py can run either solver interchangeably.

    guess_fn(game, rng) -> (x, y) is called whenever neither single-point
    nor subset reasoning finds a certain move; defaults to
    guessing.random_guess. Pass guessing.probability_guess to plug in a
    smarter guesser without touching this file."""
    guess_fn = guess_fn or guessing.random_guess
    game = E.create_game(level["width"], level["height"], level["mine_cells"])
    touches = 0
    guesses = 0

    E.reveal(game, level["start_cell"][0], level["start_cell"][1])
    touches += 1

    total_safe_cells = game.width * game.height - game.mines

    while game.status == "playing":
        if max_touches is not None and touches >= max_touches:
            break

        safe_cells, mine_cells = _deduce_pass(game)

        for x, y in mine_cells:
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
            continue

        if mine_cells:
            continue

        # Stuck: neither single-point nor subset reasoning found anything certain.
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
    else:
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
