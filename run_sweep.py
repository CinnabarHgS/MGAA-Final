"""OFAT sweep over the PCG and combat knobs.

Vary one variable at a time, keep the rest at default. Each cell runs all
three agents (random, heuristic, mcts) and appends every episode to one
csv that you can pivot in pandas later.

Defaults: medium random_walk, items/enemy_count/wall_density all default,
player 4HP-1dmg-1rng, enemy 2HP-1dmg-1rng, mcts 200 iters, max-steps 120,
seed 11, 50 episodes per cell.

Resumable: if the output CSV already has rows for a (config, agent) cell
matching the current --episodes count, that cell is skipped. Partially
written cells (fewer rows than --episodes) get their old rows wiped and
the cell is rerun from scratch.

Usage:
    python run_sweep.py                       # full sweep, a few hours
    python run_sweep.py --episodes 5          # quick smoke test
    python run_sweep.py --dry-run             # print commands, dont run
    python run_sweep.py --only size,items     # only the listed variables
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import tempfile
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

# CSV columns that together identify a "cell" (one run of evaluate_simulator.py).
# Must match the columns evaluate_simulator.py writes.
CELL_KEY_COLUMNS = (
    "agent",
    "size",
    "map_type",
    "items",
    "enemy_count",
    "wall_density",
    "player_hp",
    "enemy_hp",
    "player_damage",
    "enemy_damage",
    "player_range",
    "enemy_range",
)


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


def cell_key_for(
    *,
    agent: str,
    swept_variable: str,
    swept_value: str,
) -> tuple[str, ...]:
    """The CSV-row key that identifies this cell.

    Built from DEFAULTS + the swept override + agent. Must be aligned with
    CELL_KEY_COLUMNS so it can be compared against rows read from disk.
    """
    flag_values = dict(DEFAULTS)
    flag_values[swept_variable] = swept_value
    flag_values_with_agent = {"agent": agent, **flag_values}
    return tuple(flag_values_with_agent[col] for col in CELL_KEY_COLUMNS)


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


def scan_existing_csv(
    csv_path: str,
    *,
    expected_seed: int,
    expected_mcts_iterations: int,
) -> tuple[dict[tuple[str, ...], int], list[str]]:
    """Read the CSV and return per-cell episode counts plus any warnings.

    Rows whose seed / mcts_iterations dont match the current run are
    ignored for skip-detection (and a warning is returned), so reruns
    with different settings dont silently reuse stale data.
    """
    counts: dict[tuple[str, ...], int] = {}
    warnings: list[str] = []
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return counts, warnings

    mismatched_keys: set[tuple[str, ...]] = set()
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return counts, warnings
        for row in reader:
            try:
                row_seed = int(row["seed"])
                row_mcts = int(row["mcts_iterations"])
            except (KeyError, ValueError):
                # Malformed row, ignore.
                continue
            key = tuple(row[col] for col in CELL_KEY_COLUMNS)
            if row_seed != expected_seed or (
                row["agent"] == "mcts" and row_mcts != expected_mcts_iterations
            ):
                mismatched_keys.add(key)
                continue
            counts[key] = counts.get(key, 0) + 1

    if mismatched_keys:
        warnings.append(
            f"Ignored {len(mismatched_keys)} cell(s) in CSV with mismatched "
            f"seed/mcts_iterations (will be re-run and old rows wiped)."
        )
    return counts, warnings


def rewrite_csv_without_keys(
    csv_path: str,
    keys_to_drop: set[tuple[str, ...]],
) -> int:
    """Rewrite csv_path keeping only rows whose CELL_KEY_COLUMNS tuple isnt in keys_to_drop.

    Atomic: writes to a temp file in the same directory, then os.replace.
    Returns the number of rows removed.
    """
    if not keys_to_drop or not os.path.exists(csv_path):
        return 0

    removed = 0
    dirpath = os.path.dirname(os.path.abspath(csv_path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".sweep_tmp_", dir=dirpath)
    try:
        with os.fdopen(fd, "w", newline="") as out_f, open(csv_path, "r", newline="") as in_f:
            reader = csv.DictReader(in_f)
            if reader.fieldnames is None:
                # Empty/headerless file, just leave it alone.
                os.unlink(tmp_path)
                return 0
            writer = csv.DictWriter(out_f, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                key = tuple(row.get(col, "") for col in CELL_KEY_COLUMNS)
                if key in keys_to_drop:
                    removed += 1
                    continue
                writer.writerow(row)
        os.replace(tmp_path, csv_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return removed


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

    # Read whats already on disk, decide which cells to skip vs wipe-and-rerun.
    existing_counts, scan_warnings = scan_existing_csv(
        args.csv_out,
        expected_seed=args.seed,
        expected_mcts_iterations=args.mcts_iterations,
    )
    for w in scan_warnings:
        print(f"warning: {w}")

    cells_to_skip: set[tuple[str, str, str]] = set()
    keys_to_wipe: set[tuple[str, ...]] = set()
    for variable, level, agent in cells:
        key = cell_key_for(agent=agent, swept_variable=variable, swept_value=level)
        count = existing_counts.get(key, 0)
        if count == args.episodes:
            cells_to_skip.add((variable, level, agent))
        elif count > 0:
            # Partial: wipe and rerun. Also covers count > episodes (changed --episodes).
            keys_to_wipe.add(key)

    if keys_to_wipe and not args.dry_run:
        removed = rewrite_csv_without_keys(args.csv_out, keys_to_wipe)
        print(f"Wiped {removed} stale/partial row(s) across {len(keys_to_wipe)} cell(s).")
    elif keys_to_wipe:
        print(f"(dry run) would wipe rows for {len(keys_to_wipe)} partial/stale cell(s).")

    to_run = total - len(cells_to_skip)
    print(f"Plan: {total} cells total, {len(cells_to_skip)} already done, {to_run} to run, "
          f"{args.episodes} episodes each = {to_run * args.episodes} new episodes")
    print(f"CSV output: {args.csv_out}")
    if args.dry_run:
        print("(dry run, no commands will execute)\n")

    started = time.time()
    ran = 0
    for i, (variable, level, agent) in enumerate(cells, start=1):
        if (variable, level, agent) in cells_to_skip:
            print(f"[{i}/{total}] {variable}={level} agent={agent} -- skip (already done)")
            continue
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
        ran += 1
        print(f"[{i}/{total}] {variable}={level} agent={agent} (elapsed {elapsed:.0f}s)")
        if args.dry_run:
            print("  " + " ".join(cmd))
            continue

        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"  FAILED with exit {result.returncode}, stopping.", file=sys.stderr)
            raise SystemExit(result.returncode)

    elapsed = time.time() - started
    print(f"\nDone. Ran {ran} cell(s) ({len(cells_to_skip)} skipped) in {elapsed:.0f}s. "
          f"CSV: {args.csv_out}")


if __name__ == "__main__":
    main()