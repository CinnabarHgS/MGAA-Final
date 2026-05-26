from __future__ import annotations

import argparse
import csv
import inspect
import os
import random as py_random
from concurrent.futures import ProcessPoolExecutor
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
)
from grid_battle.pcg import (
    ENEMY_COUNT_LEVELS,
    ITEM_LEVELS,
    MAP_SIZES,
    MAP_TYPES,
    WALL_DENSITY_LEVELS,
    analyze_level,
    generate_preset_level,
)


AGENT_PROFILES = (
    "random",
    "heuristic",
    "mcts_weak",
    "mcts_medium",
    "mcts_strong",
)

BALANCE_AGENT_PROFILES = (
    "random",
    "heuristic",
    "mcts_weak",
    "mcts_medium",
    "mcts_strong",
)


@dataclass(frozen=True)
class MctsProfile:
    iterations: int
    rollout_depth: int
    exploration: float = 2 ** 0.5


MCTS_PROFILES: dict[str, MctsProfile] = {
    "mcts_weak": MctsProfile(iterations=50, rollout_depth=10),
    "mcts_medium": MctsProfile(iterations=200, rollout_depth=30),
    "mcts_strong": MctsProfile(iterations=800, rollout_depth=40),
}


CSV_COLUMNS = [
    "engine",
    "agent",
    "mcts_iterations",
    "mcts_rollout_depth",
    "mcts_exploration",
    "size",
    "map_type",
    "items",
    "enemy_count_setting",
    "wall_density",
    "max_steps",
    "seed",
    "episode",
    "map_seed",
    "swept_variable",
    "swept_value",
    "won",
    "turns",
    "damage_taken",
    "final_hp",
    "remaining_enemies",
    "map_width",
    "map_height",
    "generated_enemy_count",
    "generated_obstacle_count",
    "generated_obstacle_density",
    "structurally_valid",
    "reachable_floor_fraction",
    "interior_wall_density",
    "dead_end_count",
    "chokepoint_count",
    "min_enemy_attack_distance",
    "avg_enemy_attack_distance",
    "max_enemy_attack_distance",
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
    csv_out: str | None = None
    quiet: bool = False
    swept_variable: str = ""
    swept_value: str = ""
    workers: int = 1


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
    generated_enemy_count: int
    generated_obstacle_count: int
    generated_obstacle_density: float
    structurally_valid: bool
    reachable_floor_fraction: float
    interior_wall_density: float
    dead_end_count: int
    chokepoint_count: int
    min_enemy_attack_distance: int | None
    avg_enemy_attack_distance: float | None
    max_enemy_attack_distance: int | None


def mcts_profile_for(agent_name: str) -> MctsProfile | None:
    return MCTS_PROFILES.get(agent_name)


def build_mcts_agent(profile_name: str, seed: int) -> MctsAgent:
    profile = MCTS_PROFILES[profile_name]
    signature = inspect.signature(MctsAgent)
    supported = signature.parameters

    kwargs = {}
    if "iterations" in supported:
        kwargs["iterations"] = profile.iterations
    if "rollout_depth" in supported:
        kwargs["rollout_depth"] = profile.rollout_depth
    if "exploration" in supported:
        kwargs["exploration"] = profile.exploration
    if "seed" in supported:
        kwargs["seed"] = seed

    return MctsAgent(**kwargs)


def build_agent(name: str, seed: int) -> Agent:
    if name == "random":
        return RandomAgent(seed=seed)

    if name == "heuristic":
        return HeuristicAgent()

    if name in MCTS_PROFILES:
        return build_mcts_agent(name, seed)

    raise ValueError(f"Unknown agent profile: {name}")


def run_episode(
    *,
    layout: str,
    agent: Agent,
    max_steps: int,
    map_seed: int,
    map_width: int,
    map_height: int,
    generated_enemy_count: int,
    generated_obstacle_count: int,
    generated_obstacle_density: float,
) -> EpisodeResult:
    analysis = analyze_level(layout)

    # The real environment has stochastic mechanics, e.g. bush dodge.
    # Seed them per episode so evaluation and replay are reproducible.
    py_random.seed(map_seed)

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
            generated_enemy_count=generated_enemy_count,
            generated_obstacle_count=generated_obstacle_count,
            generated_obstacle_density=generated_obstacle_density,
            structurally_valid=analysis.structurally_valid,
            reachable_floor_fraction=analysis.reachable_floor_fraction,
            interior_wall_density=analysis.interior_wall_density,
            dead_end_count=analysis.dead_end_count,
            chokepoint_count=analysis.chokepoint_count,
            min_enemy_attack_distance=analysis.min_enemy_attack_distance,
            avg_enemy_attack_distance=analysis.avg_enemy_attack_distance,
            max_enemy_attack_distance=analysis.max_enemy_attack_distance,
        )

    finally:
        close = getattr(env, "close", None)
        if callable(close):
            close()


def _run_episode_from_config(task: tuple[ExperimentConfig, int]) -> tuple[int, EpisodeResult]:
    config, episode_index = task
    map_seed = config.seed + episode_index

    # Fresh agent per episode: independent, parallel-safe, replayable.
    agent = build_agent(config.agent, seed=map_seed)

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
        generated_enemy_count=generated.enemy_count,
        generated_obstacle_count=generated.obstacle_count,
        generated_obstacle_density=generated.obstacle_density,
    )

    return episode_index, result


def append_results_to_csv(
    csv_path: str,
    config: ExperimentConfig,
    results: list[EpisodeResult],
) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = path.exists() and path.stat().st_size > 0
    profile = mcts_profile_for(config.agent)

    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)

        if not file_exists:
            writer.writeheader()

        for episode_index, result in enumerate(results):
            writer.writerow(
                {
                    "engine": "griddly",
                    "agent": config.agent,
                    "mcts_iterations": profile.iterations if profile else "",
                    "mcts_rollout_depth": profile.rollout_depth if profile else "",
                    "mcts_exploration": profile.exploration if profile else "",
                    "size": config.size,
                    "map_type": config.map_type,
                    "items": config.items,
                    "enemy_count_setting": config.enemy_count,
                    "wall_density": config.wall_density,
                    "max_steps": config.max_steps,
                    "seed": config.seed,
                    "episode": episode_index,
                    "map_seed": result.map_seed,
                    "swept_variable": config.swept_variable,
                    "swept_value": config.swept_value,
                    "won": int(result.won),
                    "turns": result.turns,
                    "damage_taken": result.damage_taken,
                    "final_hp": result.final_hp,
                    "remaining_enemies": result.remaining_enemies,
                    "map_width": result.map_width,
                    "map_height": result.map_height,
                    "generated_enemy_count": result.generated_enemy_count,
                    "generated_obstacle_count": result.generated_obstacle_count,
                    "generated_obstacle_density": result.generated_obstacle_density,
                    "structurally_valid": int(result.structurally_valid),
                    "reachable_floor_fraction": result.reachable_floor_fraction,
                    "interior_wall_density": result.interior_wall_density,
                    "dead_end_count": result.dead_end_count,
                    "chokepoint_count": result.chokepoint_count,
                    "min_enemy_attack_distance": result.min_enemy_attack_distance,
                    "avg_enemy_attack_distance": result.avg_enemy_attack_distance,
                    "max_enemy_attack_distance": result.max_enemy_attack_distance,
                }
            )


def run_evaluation(config: ExperimentConfig) -> list[EpisodeResult]:
    workers = max(1, int(config.workers))
    tasks = [(config, episode_index) for episode_index in range(config.episodes)]

    if workers == 1 or config.episodes == 1:
        indexed_results = [_run_episode_from_config(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            indexed_results = list(executor.map(_run_episode_from_config, tasks))

    indexed_results.sort(key=lambda item: item[0])
    results = [result for _episode_index, result in indexed_results]

    if config.csv_out:
        append_results_to_csv(config.csv_out, config, results)

    if not config.quiet:
        print_summary(config, results)

    return results


def win_rate(results: list[EpisodeResult]) -> float:
    return sum(result.won for result in results) / len(results)


def avg_or_zero(values: list[float | int]) -> float:
    return mean(values) if values else 0.0


def print_summary(config: ExperimentConfig, results: list[EpisodeResult]) -> None:
    losses = [result for result in results if not result.won]
    profile = mcts_profile_for(config.agent)

    print("Real-environment evaluation summary")
    print("Engine: Griddly-backed GridBattleEnv")
    print(f"Agent: {config.agent}")

    if profile:
        print(f"MCTS iterations: {profile.iterations}")
        print(f"MCTS rollout depth: {profile.rollout_depth}")

    print(f"Episodes: {config.episodes}")
    print(f"Workers: {config.workers}")
    print(f"Map type: {config.map_type}")
    print(f"Map size preset: {config.size}")
    print(
        "PCG settings: "
        f"items={config.items}, "
        f"enemy_count={config.enemy_count}, "
        f"wall_density={config.wall_density}"
    )
    print(f"Max steps: {config.max_steps}")
    print(f"Win rate: {win_rate(results):.1%}")
    print(f"Average turns: {mean(result.turns for result in results):.2f}")
    print(f"Average damage taken: {mean(result.damage_taken for result in results):.2f}")
    print(f"Average final HP: {mean(result.final_hp for result in results):.2f}")
    print(
        "Average enemies left on losses: "
        f"{avg_or_zero([result.remaining_enemies for result in losses]):.2f}"
    )
    print(
        "Average reachable floor fraction: "
        f"{mean(result.reachable_floor_fraction for result in results):.1%}"
    )
    print(f"Average chokepoints: {mean(result.chokepoint_count for result in results):.2f}")


def print_compact_result(config: ExperimentConfig, results: list[EpisodeResult]) -> None:
    profile = mcts_profile_for(config.agent)
    profile_note = ""

    if profile:
        profile_note = f" ({profile.iterations} it, depth {profile.rollout_depth})"

    print(
        f"{config.size:>6} | "
        f"{config.map_type:>11} | "
        f"{config.agent:<12}{profile_note:<18} | "
        f"WR {win_rate(results):>6.1%} | "
        f"turns {mean(result.turns for result in results):>5.1f} | "
        f"dmg {mean(result.damage_taken for result in results):>4.1f} | "
        f"choke {mean(result.chokepoint_count for result in results):>4.1f} | "
        f"reach {mean(result.reachable_floor_fraction for result in results):>6.1%}"
    )


def direction_name(direction: int | None) -> str:
    names = {
        1: "up",
        2: "right",
        3: "down",
        4: "left",
    }
    if direction is None:
        return "none"
    return names.get(direction, str(direction))


def describe_turn(turn: TurnAction) -> str:
    parts: list[str] = []

    if turn.activate_item is not None:
        parts.append(f"activate={turn.activate_item}")

    if turn.move_directions:
        move_text = ",".join(direction_name(direction) for direction in turn.move_directions)
        parts.append(f"move=[{move_text}]")
    else:
        parts.append(f"move={direction_name(turn.move_direction)}")

    if turn.action is not None:
        parts.append(
            f"attack={turn.action.action_type}:{direction_name(turn.action.direction)}"
        )
    else:
        parts.append("attack=none")

    if turn.action2 is not None:
        parts.append(
            f"attack2={turn.action2.action_type}:{direction_name(turn.action2.direction)}"
        )

    return " | ".join(parts)


def render_snapshot_text(snapshot: BattleSnapshot) -> str:
    grid = [["." for _ in range(snapshot.width)] for _ in range(snapshot.height)]

    for x, y in snapshot.walls:
        if 0 <= x < snapshot.width and 0 <= y < snapshot.height:
            grid[y][x] = "#"

    for x, y in snapshot.hills:
        if 0 <= x < snapshot.width and 0 <= y < snapshot.height and grid[y][x] == ".":
            grid[y][x] = "H"

    for x, y in snapshot.bushes:
        if 0 <= x < snapshot.width and 0 <= y < snapshot.height and grid[y][x] == ".":
            grid[y][x] = "B"

    for x, y in snapshot.bunkers:
        if 0 <= x < snapshot.width and 0 <= y < snapshot.height and grid[y][x] == ".":
            grid[y][x] = "K"

    for (x, y), item_name in snapshot.map_items:
        if 0 <= x < snapshot.width and 0 <= y < snapshot.height and grid[y][x] == ".":
            grid[y][x] = item_name[:1].upper()

    for enemy in snapshot.enemies:
        x, y = enemy.position
        if 0 <= x < snapshot.width and 0 <= y < snapshot.height:
            grid[y][x] = "E"

    if snapshot.player is not None:
        x, y = snapshot.player.position
        if 0 <= x < snapshot.width and 0 <= y < snapshot.height:
            grid[y][x] = "P"

    return "\n".join("".join(row) for row in grid)


def snapshot_status(snapshot: BattleSnapshot) -> str:
    player_hp = snapshot.player.health if snapshot.player is not None else 0
    inventory = ", ".join(snapshot.inventory) if snapshot.inventory else "-"
    effects = (
        ", ".join(f"{effect.name}:{effect.turns_left}" for effect in snapshot.active_effects)
        if snapshot.active_effects
        else "-"
    )

    return (
        f"turn={snapshot.player_turns} | "
        f"hp={player_hp} | "
        f"enemies={snapshot.remaining_enemies} | "
        f"inventory={inventory} | "
        f"effects={effects}"
    )


def replay_header(args: argparse.Namespace, map_seed: int, generated, analysis) -> str:
    return "\n".join(
        [
            "Replay",
            "Engine: Griddly-backed GridBattleEnv",
            f"Agent: {args.agent}",
            f"Size: {args.size}",
            f"Map type: {args.map_type}",
            f"Episode: {args.episode}",
            f"Seed: {args.seed}",
            f"Map seed: {map_seed}",
            f"Items: {args.items}",
            f"Enemy count setting: {args.enemy_count}",
            f"Wall density: {args.wall_density}",
            f"Dimensions: {generated.width}x{generated.height}",
            f"Generated enemies: {generated.enemy_count}",
            f"Generated obstacles: {generated.obstacle_count}",
            f"Generated obstacle density: {generated.obstacle_density:.3f}",
            f"Structurally valid: {analysis.structurally_valid}",
            f"Reachable floor fraction: {analysis.reachable_floor_fraction:.1%}",
            f"Interior wall density: {analysis.interior_wall_density:.1%}",
            f"Dead ends: {analysis.dead_end_count}",
            f"Chokepoints: {analysis.chokepoint_count}",
            f"Enemy attack distance min/avg/max: "
            f"{analysis.min_enemy_attack_distance}/"
            f"{analysis.avg_enemy_attack_distance}/"
            f"{analysis.max_enemy_attack_distance}",
            "",
            "Legend:",
            "  P player, E enemy, # wall, H hill, B bush, K bunker",
            "  G golden gun, D dual berettas, S shotgun, V vehicle",
            "",
        ]
    )


def run_replay(args: argparse.Namespace) -> None:
    map_seed = args.seed + args.episode

    generated = generate_preset_level(
        size=args.size,
        map_type=args.map_type,
        seed=map_seed,
        item_level=args.items,
        enemy_count=args.enemy_count,
        wall_density=args.wall_density,
    )

    analysis = analyze_level(generated.layout)

    # Match run_evaluation: fresh agent per episode, seeded by map_seed.
    py_random.seed(map_seed)
    agent = build_agent(args.agent, seed=map_seed)

    if args.ui:
        run_replay_ui(args, generated.layout, generated, analysis, agent, map_seed)
        return

    log_lines: list[str] = [replay_header(args, map_seed, generated, analysis)]

    env = GridBattleEnv(generated.layout, max_steps=args.max_steps)

    try:
        snapshot = env.reset()

        while (
            snapshot.player is not None
            and snapshot.remaining_enemies > 0
            and snapshot.player_turns < args.max_steps
        ):
            log_lines.append("=" * 72)
            log_lines.append(snapshot_status(snapshot))
            log_lines.append(render_snapshot_text(snapshot))

            turn = agent.act(snapshot)
            log_lines.append(f"action: {describe_turn(turn)}")

            before_hp = snapshot.player.health if snapshot.player is not None else 0
            before_enemies = snapshot.remaining_enemies
            before_bunkers = set(snapshot.bunkers)
            before_items = set(snapshot.map_items)

            snapshot, reward, done, info = env.step(turn)
            del reward, info

            after_hp = snapshot.player.health if snapshot.player is not None else 0
            after_bunkers = set(snapshot.bunkers)
            after_items = set(snapshot.map_items)

            log_lines.append(
                "result: "
                f"hp_delta={after_hp - before_hp}, "
                f"enemies_delta={snapshot.remaining_enemies - before_enemies}, "
                f"bunkers_used={sorted(before_bunkers - after_bunkers)}, "
                f"items_picked={sorted(before_items - after_items)}"
            )

            if args.pause:
                print("\n".join(log_lines[-6:]))
                input("Press Enter for next turn...")

            if done:
                break

        log_lines.append("=" * 72)
        log_lines.append("Final state")
        log_lines.append(snapshot_status(snapshot))
        log_lines.append(render_snapshot_text(snapshot))

        final_hp = snapshot.player.health if snapshot.player is not None else 0
        won = snapshot.player is not None and snapshot.remaining_enemies == 0

        log_lines.append("")
        log_lines.append(f"Won: {won}")
        log_lines.append(f"Turns: {snapshot.player_turns}")
        log_lines.append(f"Final HP: {final_hp}")
        log_lines.append(f"Remaining enemies: {snapshot.remaining_enemies}")

    finally:
        close = getattr(env, "close", None)
        if callable(close):
            close()

    output = "\n".join(log_lines)

    if args.log_out:
        log_path = Path(args.log_out)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output)
        print(f"Wrote replay log to {log_path}")
    else:
        print(output)


def run_replay_ui(args: argparse.Namespace, layout: str, generated, analysis, agent: Agent, map_seed: int) -> None:
    from grid_battle.ui_pygame import GridBattleWindow

    def make_agent() -> Agent:
        return build_agent(args.agent, seed=map_seed)

    py_random.seed(map_seed)

    env = GridBattleEnv(layout, max_steps=args.max_steps)

    window = GridBattleWindow(
        env,
        max_steps=args.max_steps,
        window_title=(
            f"GridBattle Replay - {args.agent} - "
            f"{args.size}/{args.map_type} - seed {map_seed}"
        ),
        tile_size=args.tile_size,
        agent=make_agent(),
        agent_name=args.agent,
        agent_delay_ms=args.delay_ms,
        agent_start_paused=args.pause,
        agent_factory=make_agent,
        replay_seed=map_seed,
    )

    window.last_turn_summary = (
        f"Replay map seed {map_seed}. "
        f"Reachable floor {analysis.reachable_floor_fraction:.1%}, "
        f"chokepoints {analysis.chokepoint_count}, "
        f"dead ends {analysis.dead_end_count}."
    )

    window.status_message = (
        f"Agent replay: {args.agent}. "
        "Space pauses/resumes, Enter steps once, R resets, Esc quits."
    )

    window.run()


def add_worker_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Number of worker processes for parallel episode evaluation. "
            "Use 1 for sequential execution."
        ),
    )


def add_common_eval_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--size", choices=list(MAP_SIZES.keys()), default="medium")
    parser.add_argument("--map-type", choices=list(MAP_TYPES), default="random_walk")
    parser.add_argument("--items", choices=list(ITEM_LEVELS), default="default")
    parser.add_argument("--enemy-count", choices=list(ENEMY_COUNT_LEVELS), default="default")
    parser.add_argument("--wall-density", choices=list(WALL_DENSITY_LEVELS), default="default")
    parser.add_argument("--max-steps", type=int, default=120)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run GridBattle balancing experiments using the real Griddly-backed environment."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser(
        "smoke",
        help="Run a quick real-environment sanity check.",
    )
    smoke.add_argument("--episodes", type=int, default=2)
    smoke.add_argument("--seed", type=int, default=11)
    smoke.add_argument("--max-steps", type=int, default=60)
    add_worker_arg(smoke)

    eval_parser = subparsers.add_parser(
        "eval",
        help="Run one real-environment evaluation configuration.",
    )
    add_common_eval_args(eval_parser)
    eval_parser.add_argument("--agent", choices=AGENT_PROFILES, default="heuristic")
    eval_parser.add_argument("--csv-out", default=None)
    eval_parser.add_argument("--quiet", action="store_true")
    add_worker_arg(eval_parser)

    pilot = subparsers.add_parser(
        "balance-pilot",
        help="Run the first PCG balancing pilot: size x map_type x skill ladder.",
    )
    pilot.add_argument("--episodes", type=int, default=10)
    pilot.add_argument("--seed", type=int, default=11)
    pilot.add_argument("--items", choices=list(ITEM_LEVELS), default="default")
    pilot.add_argument("--enemy-count", choices=list(ENEMY_COUNT_LEVELS), default="default")
    pilot.add_argument("--wall-density", choices=list(WALL_DENSITY_LEVELS), default="default")
    pilot.add_argument("--max-steps", type=int, default=120)
    pilot.add_argument("--csv-out", default="results/balance_pilot.csv")
    pilot.add_argument("--overwrite", action="store_true")
    add_worker_arg(pilot)

    replay = subparsers.add_parser(
        "replay",
        help="Inspect one generated game as text or with the normal Pygame UI.",
    )
    add_common_eval_args(replay)
    replay.add_argument("--agent", choices=AGENT_PROFILES, default="heuristic")
    replay.add_argument(
        "--episode",
        type=int,
        default=0,
        help="Episode index. The generated map seed is seed + episode.",
    )
    replay.add_argument(
        "--pause",
        action="store_true",
        help="Pause after every turn in text mode; start paused in UI mode.",
    )
    replay.add_argument(
        "--log-out",
        default=None,
        help="Optional path for writing the replay text log.",
    )
    replay.add_argument(
        "--ui",
        action="store_true",
        help="Show the existing Pygame UI as an autoplay replay viewer.",
    )
    replay.add_argument(
        "--delay-ms",
        type=int,
        default=600,
        help="Delay between automatic UI steps.",
    )
    replay.add_argument(
        "--tile-size",
        type=int,
        default=68,
        help="Tile size used by the existing Pygame UI.",
    )

    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> ExperimentConfig:
    return ExperimentConfig(
        agent=args.agent,
        episodes=args.episodes,
        seed=args.seed,
        size=args.size,
        map_type=args.map_type,
        items=args.items,
        enemy_count=args.enemy_count,
        wall_density=args.wall_density,
        max_steps=args.max_steps,
        csv_out=args.csv_out,
        quiet=args.quiet,
        workers=getattr(args, "workers", 1),
    )


def run_smoke(args: argparse.Namespace) -> None:
    print("Running real-environment smoke test.")
    print("This uses GridBattleEnv directly and does not open the Pygame UI.")
    print()

    smoke_agents = ("random", "heuristic", "mcts_weak")

    for agent_name in smoke_agents:
        config = ExperimentConfig(
            agent=agent_name,
            episodes=args.episodes,
            seed=args.seed,
            size="small",
            map_type="baseline",
            items="default",
            enemy_count="default",
            wall_density="default",
            max_steps=args.max_steps,
            workers=getattr(args, "workers", 1),
        )
        run_evaluation(config)
        print()


def run_balance_pilot(args: argparse.Namespace) -> None:
    csv_out = args.csv_out

    if args.overwrite and os.path.exists(csv_out):
        os.remove(csv_out)

    print("Running PCG balance pilot.")
    print("Engine: Griddly-backed GridBattleEnv")
    print("Design: size x map_type x skill ladder")
    print(f"Episodes per cell: {args.episodes}")
    print(f"Workers per cell: {args.workers}")
    print(f"CSV output: {csv_out}")
    print()
    print(
        "  size |    map_type | agent                         | "
        "winrate | turns |  dmg | choke | reach "
    )
    print("-" * 96)

    cells = [
        (size, map_type, agent_name)
        for size in MAP_SIZES
        for map_type in MAP_TYPES
        for agent_name in BALANCE_AGENT_PROFILES
    ]

    for size, map_type, agent_name in cells:
        config = ExperimentConfig(
            agent=agent_name,
            episodes=args.episodes,
            seed=args.seed,
            size=size,
            map_type=map_type,
            items=args.items,
            enemy_count=args.enemy_count,
            wall_density=args.wall_density,
            max_steps=args.max_steps,
            csv_out=csv_out,
            quiet=True,
            swept_variable="balance_pilot",
            swept_value=f"{size}:{map_type}:{agent_name}",
            workers=getattr(args, "workers", 1),
        )

        results = run_evaluation(config)
        print_compact_result(config, results)

    print()
    print(f"Done. Results written to {csv_out}")


def main() -> None:
    args = parse_args()

    if args.command == "smoke":
        run_smoke(args)
    elif args.command == "eval":
        run_evaluation(config_from_args(args))
    elif args.command == "balance-pilot":
        run_balance_pilot(args)
    elif args.command == "replay":
        run_replay(args)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
