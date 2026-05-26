# experiment.py
from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Protocol

from grid_battle import (
    BattleSnapshot,
    GridBattleEnv,
    HeuristicAgent,
    MctsAgent,
    RandomAgent,
    TurnAction,
    generate_preset_level,
)
from grid_battle.pcg import (
    ENEMY_COUNT_LEVELS,
    ITEM_LEVELS,
    MAP_SIZES,
    MAP_TYPES,
    WALL_DENSITY_LEVELS,
)


AGENTS = ("random", "heuristic", "mcts")

# Keep the sweep focused on real game parameters that are actually represented
# in generated maps. Combat stat sweeps were simulator-only and are intentionally
# removed from the real-environment experiment interface.
SWEEP_DEFAULTS: dict[str, str] = {
    "size": "medium",
    "map_type": "random_walk",
    "items": "default",
    "enemy_count": "default",
    "wall_density": "default",
}

SWEEP_VARIABLES: dict[str, tuple[str, list[str]]] = {
    "size": ("size", ["small", "medium", "large"]),
    "map_type": ("map_type", ["baseline", "random_walk", "arena"]),
    "items": ("items", ["none", "default", "double"]),
    "enemy_count": ("enemy_count", ["low", "default", "high"]),
    "wall_density": ("wall_density", ["low", "default", "high"]),
}

CSV_COLUMNS = [
    "engine",
    "agent",
    "size",
    "map_type",
    "items",
    "enemy_count",
    "wall_density",
    "mcts_iterations",
    "max_steps",
    "seed",
    "episode",
    "map_seed",
    "map_width",
    "map_height",
    "swept_variable",
    "swept_value",
    "won",
    "turns",
    "damage_taken",
    "final_hp",
    "remaining_enemies",
]


class Agent(Protocol):
    def act(self, snapshot: BattleSnapshot) -> TurnAction:
        ...


@dataclass(frozen=True)
class ExperimentConfig:
    agent: str
    episodes: int
    seed: int
    size: str
    map_type: str
    items: str
    enemy_count: str
    wall_density: str
    max_steps: int
    mcts_iterations: int
    csv_out: str | None = None
    quiet: bool = False
    swept_variable: str = ""
    swept_value: str = ""


@dataclass(frozen=True)
class EpisodeResult:
    won: bool
    turns: int
    damage_taken: int
    final_hp: int
    remaining_enemies: int
    map_seed: int
    map_width: int
    map_height: int


def require_real_environment() -> None:
    if GridBattleEnv is None:
        raise SystemExit(
            "GridBattleEnv could not be imported. "
            "Real-environment experiments require Griddly to be installed."
        )


def build_agent(name: str, *, mcts_iterations: int, seed: int) -> Agent:
    if name == "heuristic":
        return HeuristicAgent()

    if name == "random":
        return RandomAgent(seed=seed)

    if name == "mcts":
        return MctsAgent(iterations=mcts_iterations, seed=seed)

    raise ValueError(f"Unknown agent: {name}")


def run_episode(
    *,
    layout: str,
    agent: Agent,
    max_steps: int,
    map_seed: int,
    map_width: int,
    map_height: int,
) -> EpisodeResult:
    env = GridBattleEnv(layout, max_steps=max_steps)

    try:
        snapshot = env.reset()
        initial_health = snapshot.player.health if snapshot.player else 0

        while (
            snapshot.player is not None
            and snapshot.remaining_enemies > 0
            and snapshot.player_turns < max_steps
        ):
            action = agent.act(snapshot)
            snapshot, reward, done, info = env.step(action)
            del reward, info

            if done:
                break

        final_health = snapshot.player.health if snapshot.player else 0

        return EpisodeResult(
            won=snapshot.remaining_enemies == 0 and snapshot.player is not None,
            turns=snapshot.player_turns,
            damage_taken=initial_health - final_health,
            final_hp=final_health,
            remaining_enemies=snapshot.remaining_enemies,
            map_seed=map_seed,
            map_width=map_width,
            map_height=map_height,
        )

    finally:
        close = getattr(env, "close", None)
        if callable(close):
            close()


def append_results_to_csv(
    csv_path: str,
    config: ExperimentConfig,
    results: list[EpisodeResult],
) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = path.exists() and path.stat().st_size > 0

    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)

        if not file_exists:
            writer.writeheader()

        for episode_index, result in enumerate(results):
            writer.writerow(
                {
                    "engine": "griddly",
                    "agent": config.agent,
                    "size": config.size,
                    "map_type": config.map_type,
                    "items": config.items,
                    "enemy_count": config.enemy_count,
                    "wall_density": config.wall_density,
                    "mcts_iterations": config.mcts_iterations,
                    "max_steps": config.max_steps,
                    "seed": config.seed,
                    "episode": episode_index,
                    "map_seed": result.map_seed,
                    "map_width": result.map_width,
                    "map_height": result.map_height,
                    "swept_variable": config.swept_variable,
                    "swept_value": config.swept_value,
                    "won": int(result.won),
                    "turns": result.turns,
                    "damage_taken": result.damage_taken,
                    "final_hp": result.final_hp,
                    "remaining_enemies": result.remaining_enemies,
                }
            )


def run_evaluation(config: ExperimentConfig) -> list[EpisodeResult]:
    require_real_environment()

    agent = build_agent(
        config.agent,
        mcts_iterations=config.mcts_iterations,
        seed=config.seed,
    )

    results: list[EpisodeResult] = []

    for episode_index in range(config.episodes):
        map_seed = config.seed + episode_index

        generated = generate_preset_level(
            size=config.size,
            map_type=config.map_type,
            seed=map_seed,
            item_level=config.items,
            enemy_count=config.enemy_count,
            wall_density=config.wall_density,
        )

        result = run_episode(
            layout=generated.layout,
            agent=agent,
            max_steps=config.max_steps,
            map_seed=map_seed,
            map_width=generated.width,
            map_height=generated.height,
        )

        results.append(result)

    if config.csv_out:
        append_results_to_csv(config.csv_out, config, results)

    if not config.quiet:
        print_summary(config, results)

    return results


def print_summary(config: ExperimentConfig, results: list[EpisodeResult]) -> None:
    wins = sum(result.won for result in results)
    win_rate = wins / len(results)
    losses = [result for result in results if not result.won]

    avg_remaining_enemies_on_losses = (
        mean(result.remaining_enemies for result in losses) if losses else 0.0
    )

    print("Real-environment evaluation summary")
    print("Engine: Griddly-backed GridBattleEnv")
    print(f"Agent: {config.agent}")
    print(f"Episodes: {config.episodes}")
    print(f"Map type: {config.map_type}")
    print(f"Map size preset: {config.size}")
    print(
        "PCG settings: "
        f"items={config.items}, "
        f"enemy_count={config.enemy_count}, "
        f"wall_density={config.wall_density}"
    )
    print(f"Max steps: {config.max_steps}")
    if config.agent == "mcts":
        print(f"MCTS iterations: {config.mcts_iterations}")
    print(f"Win rate: {win_rate:.1%}")
    print(f"Average turns: {mean(result.turns for result in results):.2f}")
    print(f"Average damage taken: {mean(result.damage_taken for result in results):.2f}")
    print(f"Average final HP: {mean(result.final_hp for result in results):.2f}")
    print(f"Average enemies left on losses: {avg_remaining_enemies_on_losses:.2f}")


def add_common_eval_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--size", choices=list(MAP_SIZES.keys()), default="small")
    parser.add_argument("--map-type", choices=list(MAP_TYPES), default="baseline")
    parser.add_argument("--items", choices=list(ITEM_LEVELS), default="default")
    parser.add_argument(
        "--enemy-count",
        choices=list(ENEMY_COUNT_LEVELS),
        default="default",
    )
    parser.add_argument(
        "--wall-density",
        choices=list(WALL_DENSITY_LEVELS),
        default="default",
    )
    parser.add_argument("--max-steps", type=int, default=120)
    parser.add_argument("--mcts-iterations", type=int, default=200)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run GridBattle experiments using the real Griddly-backed environment."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser(
        "smoke",
        help="Run a quick real-environment sanity check for all agents.",
    )
    add_common_eval_args(smoke)
    smoke.set_defaults(episodes=3, max_steps=60, mcts_iterations=50)

    eval_parser = subparsers.add_parser(
        "eval",
        help="Run one real-environment evaluation configuration.",
    )
    add_common_eval_args(eval_parser)
    eval_parser.add_argument("--agent", choices=AGENTS, default="heuristic")
    eval_parser.add_argument(
        "--csv-out",
        default=None,
        help="Optional CSV path. If set, one row per episode is appended.",
    )
    eval_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Skip the summary printout.",
    )

    sweep = subparsers.add_parser(
        "sweep",
        help="Run a real-environment OFAT sweep over PCG parameters.",
    )
    sweep.add_argument("--episodes", type=int, default=50)
    sweep.add_argument("--seed", type=int, default=11)
    sweep.add_argument("--mcts-iterations", type=int, default=200)
    sweep.add_argument("--max-steps", type=int, default=120)
    sweep.add_argument("--csv-out", default="results/ofat_griddly.csv")
    sweep.add_argument(
        "--only",
        default=None,
        help=(
            "Comma-separated subset of variables to sweep. "
            f"Valid: {', '.join(SWEEP_VARIABLES)}"
        ),
    )
    sweep.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete the output CSV before running.",
    )
    sweep.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned cells without running them.",
    )

    return parser.parse_args()


def config_from_args(args: argparse.Namespace, *, agent: str | None = None) -> ExperimentConfig:
    return ExperimentConfig(
        agent=agent or args.agent,
        episodes=args.episodes,
        seed=args.seed,
        size=args.size,
        map_type=args.map_type,
        items=args.items,
        enemy_count=args.enemy_count,
        wall_density=args.wall_density,
        max_steps=args.max_steps,
        mcts_iterations=args.mcts_iterations,
        csv_out=getattr(args, "csv_out", None),
        quiet=getattr(args, "quiet", False),
    )


def run_smoke(args: argparse.Namespace) -> None:
    print("Running real-environment smoke test.")
    print("This uses GridBattleEnv directly and does not open the Pygame UI.")

    for agent in AGENTS:
        print()
        config = config_from_args(args, agent=agent)
        run_evaluation(config)


def parse_only_filter(raw: str | None) -> list[str]:
    if raw is None:
        return list(SWEEP_VARIABLES)

    selected = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [name for name in selected if name not in SWEEP_VARIABLES]

    if unknown:
        raise SystemExit(
            f"Unknown sweep variable(s): {unknown}. "
            f"Valid: {list(SWEEP_VARIABLES)}"
        )

    return selected


def run_sweep(args: argparse.Namespace) -> None:
    require_real_environment()

    selected_variables = parse_only_filter(args.only)

    cells: list[tuple[str, str, str]] = []
    for variable in selected_variables:
        _, levels = SWEEP_VARIABLES[variable]
        for level in levels:
            for agent in AGENTS:
                cells.append((variable, level, agent))

    print("Real-environment OFAT sweep")
    print("Engine: Griddly-backed GridBattleEnv")
    print(f"Cells: {len(cells)}")
    print(f"Episodes per cell: {args.episodes}")
    print(f"Total episodes: {len(cells) * args.episodes}")
    print(f"CSV output: {args.csv_out}")

    if args.dry_run:
        print()
        print("Dry run only. Planned cells:")
        for variable, level, agent in cells:
            print(f"  {variable}={level}, agent={agent}")
        return

    if args.overwrite and os.path.exists(args.csv_out):
        os.remove(args.csv_out)

    for index, (variable, level, agent) in enumerate(cells, start=1):
        flag_name, _ = SWEEP_VARIABLES[variable]
        values = dict(SWEEP_DEFAULTS)
        values[flag_name] = level

        config = ExperimentConfig(
            agent=agent,
            episodes=args.episodes,
            seed=args.seed,
            size=values["size"],
            map_type=values["map_type"],
            items=values["items"],
            enemy_count=values["enemy_count"],
            wall_density=values["wall_density"],
            max_steps=args.max_steps,
            mcts_iterations=args.mcts_iterations,
            csv_out=args.csv_out,
            quiet=True,
            swept_variable=variable,
            swept_value=level,
        )

        print(
            f"[{index}/{len(cells)}] "
            f"{variable}={level}, agent={agent}, "
            f"episodes={args.episodes}"
        )

        run_evaluation(config)

    print()
    print(f"Done. Results written to {args.csv_out}")


def main() -> None:
    args = parse_args()

    if args.command == "smoke":
        run_smoke(args)
    elif args.command == "eval":
        run_evaluation(config_from_args(args))
    elif args.command == "sweep":
        run_sweep(args)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()