"""
guessing.py — pluggable "what do I click when logic runs out?" strategies.

Every solver (naive_solver.py, subset_solver.py, ...) calls a `guess_fn(game,
rng) -> (x, y)` whenever no certain deduction remains. This module provides
two interchangeable strategies with that exact signature:

  random_guess(game, rng)       — uniform random hidden cell (baseline).
  probability_guess(game, rng)  — pick the hidden cell with the LOWEST
                                   estimated probability of being a mine.

HOW probability_guess ESTIMATES PROBABILITIES
-----------------------------------------------
This is the standard CSP-based approach used by most real Minesweeper
solvers (see e.g. Studholme, "Minesweeper as a Constraint Satisfaction
Problem"):

1. Every revealed number is a constraint (S, k): its hidden neighbor set
   S needs exactly k more mines (k = shown number − already-flagged
   neighbors).

2. Group all hidden "frontier" cells into connected components: two
   cells are in the same component if some constraint mentions both of
   them, transitively. Constraints never share information across
   components, so each component can be solved independently.

3. For each component, EXACTLY enumerate every 0/1 (safe/mine)
   assignment to its cells that satisfies every constraint in that
   component, using backtracking with incremental pruning (a partial
   assignment is abandoned the moment some constraint it touches
   becomes impossible to satisfy). This is exact, not sampled — for the
   component sizes that actually occur in Minesweeper positions
   (usually well under a few dozen cells), it's fast. Components larger
   than MAX_EXACT_COMPONENT_SIZE fall back to a cheap heuristic instead
   of paying for combinatorial blow-up.

4. A cell's probability of being a mine = (# valid assignments where
   it's a mine) / (# valid assignments total), *within its component*.
   This is P(mine | local constraints only) — it does NOT reweight
   across components using the total-remaining-mine-count (the fully
   rigorous version does; see README for the note on this
   simplification). It's the standard first approximation and already
   captures the interesting logic (e.g. a cell touching a "1" that
   shares neighbors with a "2" gets a different probability than a
   cell touching the "1" alone).

5. Hidden cells touched by NO constraint at all ("free" cells, e.g. far
   corners of the board) share one estimated probability: the
   remaining mine count, minus the mines we expect to be in the
   frontier (summed from each component's average), spread evenly over
   the free cells. This lets the guesser correctly prefer the open
   background over a risky frontier cell late in a game, or vice versa.

probability_guess() then reveals whichever hidden cell has the lowest
probability (ties broken randomly, but reproducibly via the supplied
rng, exactly like random_guess).
"""
import engine as E

# Components larger than this fall back to a cheap heuristic instead of
# exact enumeration, to keep worst-case runtime bounded on big boards.
MAX_EXACT_COMPONENT_SIZE = 22


# ---------------------------------------------------------------------
# Constraint building / component grouping
# ---------------------------------------------------------------------
def _build_constraints(game):
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


class _UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, a):
        self.parent.setdefault(a, a)
        root = a
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[a] != root:
            self.parent[a], a = root, self.parent[a]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _group_into_components(constraints):
    """Returns a list of (cells:set, constraints:list[(cellset,k)])."""
    uf = _UnionFind()
    for cells, _k in constraints:
        cells = list(cells)
        for c in cells:
            uf.find(c)
        for c in cells[1:]:
            uf.union(cells[0], c)

    comp_cells = {}
    for cells, _k in constraints:
        for c in cells:
            root = uf.find(c)
            comp_cells.setdefault(root, set()).add(c)

    comp_constraints = {}
    for cells, k in constraints:
        root = uf.find(next(iter(cells)))
        comp_constraints.setdefault(root, []).append((cells, k))

    return [(comp_cells[root], comp_constraints[root]) for root in comp_cells]


# ---------------------------------------------------------------------
# Exact enumeration of one component via pruned backtracking
# ---------------------------------------------------------------------
def _enumerate_component(cells, constraints):
    """Returns (total_valid_assignments, {cell: mine_count}, mine_count_sum)
    or None if the component is too large / inconsistent."""
    variables = sorted(cells)
    n = len(variables)
    if n > MAX_EXACT_COMPONENT_SIZE:
        return None

    var_index = {v: i for i, v in enumerate(variables)}
    local_constraints = [([var_index[c] for c in cell_set], k) for cell_set, k in constraints]

    var_to_constraints = [[] for _ in range(n)]
    for ci, (idxs, _k) in enumerate(local_constraints):
        for vi in idxs:
            var_to_constraints[vi].append(ci)

    # Per-constraint running state: [assigned_count, assigned_sum, total_vars]
    state = [[0, 0, len(idxs)] for idxs, _k in local_constraints]
    assigned = [None] * n
    ones_count = [0] * n
    stats = {"total": 0, "mine_sum": 0}

    def backtrack(pos):
        if pos == n:
            stats["total"] += 1
            m = 0
            for i, v in enumerate(assigned):
                if v:
                    ones_count[i] += 1
                    m += 1
            stats["mine_sum"] += m
            return

        vi = pos  # simple left-to-right order; components are small enough
        touched = var_to_constraints[vi]
        for val in (0, 1):
            assigned[vi] = val
            ok = True
            for ci in touched:
                _idxs, k = local_constraints[ci]
                s = state[ci]
                s[0] += 1
                s[1] += val
                if s[1] > k or (s[1] + (s[2] - s[0])) < k:
                    ok = False
                elif s[0] == s[2] and s[1] != k:
                    ok = False
            if ok:
                backtrack(pos + 1)
            for ci in touched:
                s = state[ci]
                s[0] -= 1
                s[1] -= val
            assigned[vi] = None

    backtrack(0)

    if stats["total"] == 0:
        return None  # inconsistent — shouldn't happen on a well-formed board

    ones_dict = {variables[i]: ones_count[i] for i in range(n)}
    return stats["total"], ones_dict, stats["mine_sum"]


def _fallback_probabilities(cells, constraints, default):
    """Cheap heuristic for components too large to enumerate exactly:
    each cell's probability = average of (k / |S|) over the constraints
    touching it, falling back to the global default if it's in none."""
    probs = {}
    for c in cells:
        ratios = [k / len(cell_set) for cell_set, k in constraints if c in cell_set and len(cell_set) > 0]
        probs[c] = sum(ratios) / len(ratios) if ratios else default
    return probs


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def estimate_probabilities(game, mines_remaining=None):
    """Return {(x, y): P(mine)} for every currently hidden cell."""
    if mines_remaining is None:
        mines_remaining = game.mines - game.flag_count

    all_hidden = set(E.hidden_cells(game))
    constraints = _build_constraints(game)
    components = _group_into_components(constraints)

    frontier_cells = set()
    for cells, _cs in components:
        frontier_cells |= cells
    free_cells = all_hidden - frontier_cells

    global_default = mines_remaining / max(1, len(all_hidden))
    probs = {}
    expected_frontier_mines = 0.0

    for cells, cs in components:
        result = _enumerate_component(cells, cs)
        if result is None:
            comp_probs = _fallback_probabilities(cells, cs, global_default)
            probs.update(comp_probs)
            expected_frontier_mines += sum(comp_probs.values())
            continue

        total, ones, mine_sum = result
        for c in cells:
            probs[c] = ones[c] / total
        expected_frontier_mines += mine_sum / total

    if free_cells:
        remaining_for_free = mines_remaining - expected_frontier_mines
        free_prob = remaining_for_free / len(free_cells)
        free_prob = min(1.0, max(0.0, free_prob))
        for c in free_cells:
            probs[c] = free_prob

    return probs


def random_guess(game, rng):
    """Baseline guessing strategy: uniform random hidden cell."""
    hidden = E.hidden_cells(game)
    return rng.choice(hidden)


def probability_guess(game, rng):
    """Reveal the hidden cell with the lowest estimated mine probability.
    Ties (very common among free cells, which all share one estimate)
    are broken randomly but reproducibly via the supplied rng."""
    hidden = E.hidden_cells(game)
    if len(hidden) == 1:
        return hidden[0]

    probs = estimate_probabilities(game)
    best = min(probs.get(c, 1.0) for c in hidden)
    candidates = [c for c in hidden if probs.get(c, 1.0) <= best + 1e-9]
    return rng.choice(candidates)


STRATEGIES = {
    "random": random_guess,
    "probability": probability_guess,
}
