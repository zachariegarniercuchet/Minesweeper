# Solvers (`src/`)

Two Minesweeper-solving baselines that both play the same 1000-level
bank (`levels.json`) through the same engine (`engine.py`, a Python port
of the web page's `engine.js`), so their scores are directly comparable.

## Run it

```bash
cd src
python3 run_baseline.py                          # baseline 1 (naive), all 1000 levels
python3 run_baseline.py --method subset          # baseline 2 (SubSweep), all 1000 levels
python3 run_baseline.py --method subset --level 42   # one level, verbose
python3 run_baseline.py --compare                 # run BOTH on the same levels, side by side
python3 run_baseline.py --compare --csv out.csv   # + dump every per-level result to CSV
python3 run_baseline.py --n 100 --seed 7          # random sample of 100
python3 run_baseline.py --difficulty expert       # only expert levels
```

## Scoring (same for every baseline)

- **Touch** = one deliberate reveal decision (≈ one real mouse click,
  including the level's guaranteed-safe opening move). A 0-cell's
  cascade is free, like in the real game.
- **Per-level score:** `touches` if won; `touches + safe cells still
  hidden at the time of the loss` if lost — so a guess-into-a-mine early
  on a mostly unsolved board is penalized far more than losing right at
  the end.
- **Global score** = mean of the per-level score over every level run.
  Lower is better.

Both baselines use the **exact same guessing strategy** (uniform random
hidden cell, once no certain move remains) so that any difference in
score is attributable only to how much each solver can deduce with
certainty — not to a smarter guess.

---

## Baseline 1 — Naive Single-Point Solver (`naive_solver.py`)

Looks at **one** revealed number at a time:
- satisfied (flags already match the number) → remaining hidden neighbors are safe
- exhausted (hidden neighbors == remaining number) → all of them are mines

Guesses randomly whenever both rules run dry. See the original writeup
further down for full detail.

## Baseline 2 — "SubSweep": Subset / Constraint-Subtraction Solver (`subset_solver.py`)

This is the technique usually called the **subset rule** (or
constraint-subtraction rule) in Minesweeper-solving write-ups — the
standard step up from single-point logic, used by most real solvers
before they resort to full CSP/backtracking.

Every revealed number defines a constraint: `(S, k)`, where `S` is its
set of still-hidden neighbor cells and `k` is how many mines remain to
be found among them (`k` = shown number − already-flagged neighbors —
this is exactly the "reduction" idea: `k` automatically drops every time
a neighboring mine gets flagged on a later pass).

If constraint A's cell set `S_A` is a **strict subset** of constraint
B's `S_B`, the cells unique to B (`S_B - S_A`) must contain exactly
`k_B - k_A` mines:

- `k_B - k_A == 0` → every cell in `S_B - S_A` is **safe**
- `k_B - k_A == len(S_B - S_A)` → every cell in `S_B - S_A` is a **mine**

Baseline 1's two rules are just this same logic in the special case
where one of the sets is empty. SubSweep additionally compares every
pair of overlapping constraints on the board each pass (indexed by
shared cell, so it only compares constraints that actually overlap —
this keeps it fast even on Expert boards with hundreds of active
numbers). Classic pattern it solves that baseline 1 can't: a "1" and a
"2" sharing three of their four hidden neighbors, where the "2"'s one
extra cell is provably a mine even though neither number alone is
satisfied or exhausted.

## Results on the full 1000-level bank (seed=1)

```
Baseline 1: Naive Single-Point Solver                    global score = 106.44
Baseline 2: SubSweep (Subset / Constraint-Subtraction)    global score = 101.29
```

```
                  win rate                 avg touches (won)
              baseline1  baseline2      baseline1  baseline2
beginner        87.3%      97.0%           17.33      17.69
intermediate    50.0%      74.0%           78.77      80.74
expert           0.5%      15.5%          188.00     207.55
mixed           39.0%      63.5%           66.41      73.50

overall win rate: 49.1% -> 67.1%
```

Win rate jumps everywhere, most dramatically on Expert (0.5% → 15.5%,
a 30x improvement) — exactly the boards where overlapping constraints
are common and single-point logic runs dry fastest. The global score
only improves modestly (106 → 101) even though win rate jumps a lot:
winning more of the *hard* levels naturally costs more touches on
average (e.g. Expert wins now average 207 touches vs. 188 before,
simply because SubSweep is now winning boards baseline 1 almost never
reached the end of). Win rate and global score tell two different parts
of the story — worth keeping both when comparing future baselines.

## What's still missing (candidate baseline 3)

SubSweep still can't resolve cases where a pair of constraints overlap
*partially* without one containing the other (e.g. two "2"s sharing two
of three cells each) — that needs reasoning about several constraints
*together* (full CSP enumeration) or estimating per-cell mine
probability to pick the safest possible guess instead of a uniformly
random one. That's the natural next baseline, and is usually where the
biggest further win-rate gains on Expert-sized boards come from.

## Files

- `engine.py` — Python port of the JS game engine, verified cell-for-cell
  identical to `engine.js` on real levels.
- `naive_solver.py` — baseline 1.
- `subset_solver.py` — baseline 2 (SubSweep).
- `run_baseline.py` — CLI runner; `--method` selects the solver,
  `--compare` runs every registered method back to back.
