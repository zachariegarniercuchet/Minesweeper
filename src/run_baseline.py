#!/usr/bin/env python3
"""
Run a solver baseline across the level bank and print a global score report.

Available methods (deduction logic): naive (baseline 1), subset (baseline 2, "SubSweep").
Available guess strategies (used only when logic runs out): random (baseline),
probability (baseline 3 — picks the hidden cell with the lowest estimated
mine probability; see guessing.py).

Examples
--------
  python3 run_baseline.py                                   # naive + random guess, all 1000 levels
  python3 run_baseline.py --method subset --guess probability   # SubSweep + probability guess
  python3 run_baseline.py --method subset --guess probability --level 42   # one level, verbose
  python3 run_baseline.py --n 100 --seed 7                    # random sample of 100
  python3 run_baseline.py --difficulty expert                 # only expert levels
  python3 run_baseline.py --csv results.csv                   # dump per-level rows
  python3 run_baseline.py --compare                           # run all 4 method x guess combos
"""
import argparse
import csv
import json
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naive_solver  # noqa: E402
import subset_solver  # noqa: E402
import guessing  # noqa: E402

METHODS = {
    "naive": ("Baseline 1: Naive Single-Point Solver", naive_solver),
    "subset": ("Baseline 2: SubSweep (Subset / Constraint-Subtraction Solver)", subset_solver),
}

GUESS_STRATEGIES = {
    "random": ("random guess", guessing.random_guess),
    "probability": ("probability-weighted guess", guessing.probability_guess),
}

LEVELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "levels.json")


def load_levels():
    with open(LEVELS_PATH) as f:
        return json.load(f)


def guess_rng_for_level(base_seed, level_id):
    """Each level gets its own reproducible RNG, derived from a single
    base seed, so re-running with the same --seed always replays the
    same guesses (needed to compare baselines fairly later)."""
    return random.Random((base_seed * 1_000_003 + level_id) & 0xFFFFFFFF)


def summarize(results):
    n = len(results)
    wins = [r for r in results if r["status"] == "won"]
    losses = [r for r in results if r["status"] == "lost"]

    print(f"Levels played        : {n}")
    print(f"Wins                 : {len(wins)} ({100*len(wins)/n:.1f}%)")
    print(f"Losses               : {len(losses)} ({100*len(losses)/n:.1f}%)")

    if wins:
        touches_won = [r["touches"] for r in wins]
        print(f"Avg touches (won only): {statistics.mean(touches_won):.2f}"
              f"  (min {min(touches_won)}, max {max(touches_won)})")
    if losses:
        prog_losses = [100 * r["revealed_count"] / r["total_safe_cells"] for r in losses]
        print(f"Avg board completion at time of loss: {statistics.mean(prog_losses):.1f}%")

    global_score = statistics.mean(r["score"] for r in results)
    print()
    print(f"GLOBAL SCORE (mean of per-level score, lower=better): {global_score:.2f}")
    print("  score = touches if won; touches + hidden-safe-cells-remaining if lost")

    print()
    print("By difficulty:")
    by_diff = {}
    for r in results:
        by_diff.setdefault(r["difficulty"], []).append(r)
    for diff, rows in by_diff.items():
        w = [r for r in rows if r["status"] == "won"]
        avg_touch = statistics.mean(r["touches"] for r in w) if w else float("nan")
        avg_score = statistics.mean(r["score"] for r in rows)
        print(f"  {diff:<13} n={len(rows):<4} win rate={100*len(w)/len(rows):5.1f}%   "
              f"avg touches (won)={avg_touch:6.2f}   avg score={avg_score:6.2f}")

    return global_score


def run_combo(method_key, guess_key, levels, seed):
    label, module = METHODS[method_key]
    guess_label, guess_fn = GUESS_STRATEGIES[guess_key]
    full_label = f"{label} + {guess_label}"
    print(f"=== {full_label} ===")
    print(f"Running on {len(levels)} level(s) from levels.json (seed={seed})\n")

    t0 = time.time()
    results = []
    for lv in levels:
        rng = guess_rng_for_level(seed, lv["id"])
        r = module.solve_level(lv, rng, guess_fn=guess_fn)
        r["method"] = method_key
        r["guess"] = guess_key
        results.append(r)
        if len(levels) == 1:
            print(f"Level #{r['id']} ({r['difficulty']}, {r['width']}x{r['height']}, "
                  f"{r['mines']} mines) -> {r['status'].upper()} "
                  f"in {r['touches']} touches ({r['guesses']} guesses), score={r['score']}")
    elapsed = time.time() - t0

    global_score = None
    if len(levels) > 1:
        print()
        global_score = summarize(results)

    print(f"\n(elapsed: {elapsed:.2f}s)")
    return results, global_score


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", choices=list(METHODS.keys()), default="naive",
                     help="Deduction logic to use (default: naive).")
    ap.add_argument("--guess", choices=list(GUESS_STRATEGIES.keys()), default="random",
                     help="Guessing strategy for when logic runs out (default: random).")
    ap.add_argument("--compare", action="store_true",
                     help="Run all method x guess combinations on the same levels and print a comparison table.")
    ap.add_argument("--level", type=int, default=None, help="Run a single level by id (1-1000).")
    ap.add_argument("--n", type=int, default=None, help="Run a random sample of N levels instead of all 1000.")
    ap.add_argument("--difficulty", choices=["beginner", "intermediate", "expert", "mixed"], default=None)
    ap.add_argument("--seed", type=int, default=1, help="Base RNG seed for guesses (default: 1).")
    ap.add_argument("--csv", type=str, default=None, help="Write per-level results to this CSV path.")
    args = ap.parse_args()

    levels = load_levels()
    if args.difficulty:
        levels = [lv for lv in levels if lv["difficulty"] == args.difficulty]
    if args.level is not None:
        levels = [lv for lv in levels if lv["id"] == args.level]
        if not levels:
            print(f"No level with id={args.level}")
            return
    if args.n is not None:
        sampler = random.Random(args.seed)
        levels = sampler.sample(levels, min(args.n, len(levels)))

    if args.compare:
        all_results = []
        scores = {}
        for method_key in METHODS:
            for guess_key in GUESS_STRATEGIES:
                results, score = run_combo(method_key, guess_key, levels, args.seed)
                all_results.extend(results)
                scores[(method_key, guess_key)] = score
                print("\n" + "-" * 60 + "\n")

        if all(s is not None for s in scores.values()):
            print("=== Comparison (global score, lower = better) ===")
            for (method_key, guess_key), score in scores.items():
                label = f"{METHODS[method_key][0]} + {GUESS_STRATEGIES[guess_key][0]}"
                print(f"  {label:<75} {score:8.2f}")

        if args.csv:
            with open(args.csv, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(all_results[0].keys()))
                writer.writeheader()
                writer.writerows(all_results)
            print(f"\nPer-level results (all combos) written to {args.csv}")
        return

    results, _ = run_combo(args.method, args.guess, levels, args.seed)

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
        print(f"Per-level results written to {args.csv}")


if __name__ == "__main__":
    main()
