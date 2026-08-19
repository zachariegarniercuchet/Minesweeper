# Guessing strategies (`guessing.py`) — baseline 3

A **pluggable guessing module**: any solver that gets stuck (no certain
deduction left) calls `guess_fn(game, rng) -> (x, y)` instead of hard-coding
its own guess logic. `naive_solver.py` and `subset_solver.py` both accept an
optional `guess_fn=` argument now, defaulting to the old behavior
(`guessing.random_guess`) so nothing about baselines 1/2 changed unless you
explicitly ask for a different guesser — verified byte-for-byte identical
scores against the previous runs.

```python
solve_level(level, rng, guess_fn=guessing.probability_guess)
```

```bash
python3 run_baseline.py --method subset --guess probability          # SubSweep + smart guessing
python3 run_baseline.py --compare                                    # all 4 method x guess combos
```

## `random_guess` (the existing baseline)

Uniform random hidden cell. Kept as the default/reference guesser.

## `probability_guess` — baseline 3

This is the standard **CSP frontier-probability** approach used by most real
Minesweeper solvers (see Studholme, *"Minesweeper as a Constraint
Satisfaction Problem"*, and the Becerra/Harvard thesis on Minesweeper
solvers). Steps:

1. Every revealed number is a constraint `(S, k)`: its hidden neighbor set
   `S` needs exactly `k` more mines (`k` = shown number − flagged
   neighbors — same "reduction" idea as SubSweep).
2. Hidden cells are grouped into **connected components**: two cells are
   linked if some constraint mentions both, transitively. Constraints in
   different components can't influence each other.
3. Each component is **exactly enumerated** via backtracking with
   incremental pruning (a partial assignment is abandoned the instant a
   touched constraint becomes impossible to satisfy) — not sampled,
   not approximated, for components up to `MAX_EXACT_COMPONENT_SIZE`
   (22) cells. Bigger components fall back to a cheap per-cell heuristic
   (average `k/|S|` across its constraints) to keep worst-case runtime
   bounded.
4. `P(mine)` for a frontier cell = (valid assignments where it's a mine)
   / (valid assignments total) **within its component**.
5. Hidden cells touched by no constraint at all ("free" cells) share one
   probability: remaining mines minus the mines expected in the frontier,
   spread evenly over the free cells — so the guesser can correctly
   prefer open background over a risky frontier cell (or vice versa).
6. Reveal whichever hidden cell has the lowest probability; ties (very
   common among free cells) are broken randomly but reproducibly.

I verified the enumeration core against a hand-built textbook case before
running it at scale: a "1" touching `{A,B}` and a neighboring "2" touching
`{A,B,C}` — the algorithm correctly finds `P(C)=1.0` (certain mine, the
same conclusion SubSweep's subset rule reaches) and `P(A)=P(B)=0.5`.

**Known simplification, stated plainly:** this computes `P(mine | that
component's constraints only)`. It does **not** reweight probabilities
across components using the *global* remaining-mine count (the fully
rigorous version does, via a combinatorial convolution over how many mines
land in each component — see Studholme). That refinement is a natural
"baseline 4"-level improvement; what's here already captures the
interesting logic and, as the results below show, closes most of the gap.

## Results on all 1000 levels (seed=1)

| Deduction | Guess | Win rate | Global score |
|---|---|---|---|
| Naive | random | 49.1% | 106.44 |
| Naive | **probability** | 68.6% | 98.57 |
| SubSweep | random | 67.1% | 101.29 |
| SubSweep | **probability** | **75.6%** | **94.78** |

By difficulty, SubSweep + probability vs. SubSweep + random:

```
              win rate            avg score
            random  prob        random   prob
beginner     97.0%  98.0%        17.94   17.80
intermediate 74.0%  79.7%        87.77   83.64
expert       15.5%  37.5%       252.25  232.61
mixed        63.5%  74.0%        95.62   89.12
```

Expert win rate **more than doubles** (15.5% → 37.5%) just by swapping the
guessing strategy — same deduction logic, same levels, same RNG seed. This
is the clearest confirmation that guessing quality, not deduction power
alone, is the main bottleneck once a solver already has subset-level logic;
it matches the literature's usual finding that a smarter guess (probability
or, better, backtracking-based CSP) contributes as much or more to win rate
than adding more deduction rules.

## Performance note

Exact enumeration only runs when a solver is actually stuck, and only over
the (usually small) components touching the frontier — not the whole
board. Full 1000-level runs: naive+probability ≈ 10s, subset+probability
≈ 6.5s (SubSweep needs to guess less often, since it resolves more of the
board with certainty first).

## Files

- `guessing.py` — `random_guess`, `probability_guess`, and the exact
  component-enumeration machinery behind the latter.
- `naive_solver.py`, `subset_solver.py` — both now accept `guess_fn=`.
- `run_baseline.py` — `--guess {random,probability}`; `--compare` now runs
  all 4 method × guess combinations.

## What's next

The stated known simplification above (global mine-count reweighting
across components) is the natural refinement if you want probability
estimates closer to the true joint distribution. Beyond that, a proper
baseline 4 would fold this probability estimate into an actual
information-gain / risk trade-off — e.g. among near-tied lowest-probability
cells, prefer the one bordering the most already-revealed numbers (more
information if it turns out safe) — which is the idea you raised as a
possible next step once you've had time to think it through.
