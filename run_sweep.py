"""OFAT sweep over the PCG and combat knobs.

Vary one variable at a time, keep the rest at default. Each cell runs all
three agents (random, heuristic, mcts) and appends every episode to one
csv that you can pivot in pandas later.

Defaults: medium random_walk, items/enemy_count/wall_density all default,
player 4HP-1dmg-1rng, enemy 2HP-1dmg-1rng, mcts 200 iters, max-steps 120,
seed 11, 50 episodes per cell.

Usage:
    python run_sweep.py                       # full sweep, a few hours
    python run_sweep.py --episodes 5          # quick smoke test
    python run_sweep.py --dry-run             # print commands, dont run
    python run_sweep.py --only size,items     # only the listed variables
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import Iterable


AGENTS = ("random", "heuristic", "mcts")

# everything else stays at these values when sweeping one variable
DEFAULTS: dict[str, str] = {
    "size": "medium",
    "map_type": "random_walk",
    "items": "default",
    "enemy_count": "default",
    "wall_density": "default",
    "player_hp": "4",
    "enemy_hp": "2",
    "player_damage": "1",
    "enemy_damage": "1",
    "player_range": "1",
    "enemy_range": "1",
}

# what we vary: variable name -> (cli flag, levels to try)
VARIABLES: dict[str, tuple[str, list[str]]] = {
    "size":           ("--size",          ["small", "medium", "large"]),
    "map_type":       ("--map-type",      ["baseline", "random_walk", "arena"]),
    "items":          ("--items",         ["none", "default", "double"]),
    "enemy_count":    ("--enemy-count",   ["low", "default", "high"]),
    "wall_density":   ("--wall-density",  ["low", "default", "high"]),
    "player_hp":      ("--player-hp",     ["3", "4", "5"]),
    "enemy_hp":       ("--enemy-hp",      ["1", "2", "3"]),
    "player_range":   ("--player-range",  ["1", "2"]),
}

# cli flag for every parameter, used when filling in the defaults
DEFAULT_FLAGS: dict[str, str] = {
    "size":          "--size",
    "map_type":      "--map-type",
    "items":         "--items",
    "enemy_count":   "--enemy-count",
    "wall_density":  "--wall-density",
    "player_hp":     "--player-hp",
    "enemy_hp":      "--enemy-hp",
    "player_damage": "--player-damage",
    "enemy_damage":  "--enemy-damage",
    "player_range":  "--player-range",
    "enemy_range":   "--enemy-range",
}


def build_command(
    *,
    python_exe: str,
    agent: str,
    swept_variable: str,
    swept_value: str,
    episodes: int,
    seed: int,
    mcts_iterations: int,
    max_steps: int,
    csv_out: str,
) -> list[str]:
    """Build the evaluate_simulator.py command for one cell."""
    flag, _ = VARIABLES[swept_variable]

    # start from defaults, then override the variable were sweeping
    flag_values: dict[str, str] = dict(DEFAULTS)
    flag_values[swept_variable] = swept_value

    cmd = [
        python_exe,
        "evaluate_simulator.py",
        "--agent", agent,
        "--episodes", str(episodes),
        "--seed", str(seed),
        "--mcts-iterations", str(mcts_iterations),
        "--max-steps", str(max_steps),
        "--csv-out", csv_out,
        "--quiet",
    ]
    for key, value in flag_values.items():
        cmd.extend([DEFAULT_FLAGS[key], value])
    return cmd


def iter_cells(only: list[str] | None) -> Iterable[tuple[str, str, str]]:
    """Yield (variable, level, agent) for every cell to run."""
    variables = list(VARIABLES.keys()) if not only else only
    for variable in variables:
        if variable not in VARIABLES:
            raise SystemExit(f"Unknown variable: {variable}. Valid: {list(VARIABLES.keys())}")
        _, levels = VARIABLES[variable]
        for level in levels:
            for agent in AGENTS:
                yield variable, level, agent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--episodes", type=int, default=50, help="Episodes per cell (default 50).")
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--mcts-iterations", type=int, default=200)
    p.add_argument("--max-steps", type=int, default=120)
    p.add_argument(
        "--csv-out",
        default="results/ofat.csv",
        help="Output CSV path. Existing rows are appended to; delete first for a clean run.",
    )
    p.add_argument(
        "--only",
        default=None,
        help="Comma-separated subset of variables to sweep (default: all).",
    )
    p.add_argument(
        "--python",
        default=sys.executable,
        help="Path to the python interpreter (default: current).",
    )
    p.add_argument("--dry-run", action="store_true", help="Print commands without running.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None

    cells = list(iter_cells(only))
    total = len(cells)
    if total == 0:
        raise SystemExit("No cells to run.")

    if not args.dry_run:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv_out)) or ".", exist_ok=True)

    print(f"Plan: {total} cells, {args.episodes} episodes each "
          f"= {total * args.episodes} total episodes")
    print(f"CSV output: {args.csv_out}")
    if args.dry_run:
        print("(dry run, no commands will execute)\n")

    started = time.time()
    for i, (variable, level, agent) in enumerate(cells, start=1):
        cmd = build_command(
            python_exe=args.python,
            agent=agent,
            swept_variable=variable,
            swept_value=level,
            episodes=args.episodes,
            seed=args.seed,
            mcts_iterations=args.mcts_iterations,
            max_steps=args.max_steps,
            csv_out=args.csv_out,
        )
        elapsed = time.time() - started
        print(f"[{i}/{total}] {variable}={level} agent={agent} (elapsed {elapsed:.0f}s)")
        if args.dry_run:
            print("  " + " ".join(cmd))
            continue

        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"  FAILED with exit {result.returncode}, stopping.", file=sys.stderr)
            raise SystemExit(result.returncode)

    elapsed = time.time() - started
    print(f"\nDone. {total} cells in {elapsed:.0f}s. CSV: {args.csv_out}")


if __name__ == "__main__":
    main()
