from __future__ import annotations

import argparse
import contextlib
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

import grid_battle.combat as combat_module
import grid_battle.game as game_module
import grid_battle.simulator as simulator_module
import grid_battle.mcts as mcts_module
from grid_battle.combat import CombatRules, UnitCombatProfile


AGENT_PROFILES = (
    "random",
    "heuristic",
    "mcts_small",
    "mcts_medium",
    "mcts_strong",
    "mcts_weak",  # backwards-compatible alias for mcts_small
)

VALIDATION_AGENT_PROFILES = (
    "random",
    "heuristic",
    "mcts_small",
    "mcts_medium",
)


@dataclass(frozen=True)
class MctsProfile:
    iterations: int
    rollout_depth: int
    exploration: float = 2 ** 0.5


MCTS_PROFILES: dict[str, MctsProfile] = {
    "mcts_small": MctsProfile(iterations=50, rollout_depth=10),
    "mcts_weak": MctsProfile(iterations=50, rollout_depth=10),
    "mcts_medium": MctsProfile(iterations=200, rollout_depth=30),
    "mcts_strong": MctsProfile(iterations=800, rollout_depth=40),
}


# These profiles are deliberately not just raw low/default/high switches.
# They encode the idea that the same raw parameter can mean different things
# on different map sizes.
ENEMY_PROFILES: dict[str, dict[str, str]] = {
    # Easier maps: fewer enemies than the size default.
    "light": {
        "small": "low",
        "medium": "low",
        "large": "low",
    },

    # Baseline size-scaled defaults from pcg.py.
    "normal": {
        "small": "default",
        "medium": "default",
        "large": "default",
    },

    # Targeted intermediate setting.
    # This is mainly meant to test whether medium maps are better with
    # one extra enemy, without also making large maps harder.
    "medium_plus": {
        "small": "default",
        "medium": "medium_plus",
        "large": "default",
    },

    # Harder maps.
    "heavy": {
        "small": "high",
        "medium": "high",
        "large": "high",
    },
}


ITEM_PROFILES: dict[str, dict[str, str]] = {
    # No no-item experiments: every profile keeps terrain/items in the game.
    # The actual number of placed objects scales with map size inside pcg.py.
    "few": {
        "small": "few",
        "medium": "few",
        "large": "few",
    },
    "normal": {
        "small": "normal",
        "medium": "normal",
        "large": "normal",
    },
    "many": {
        "small": "many",
        "medium": "many",
        "large": "many",
    },
}


# These are map-type-aware. Arena should remain relatively open, random_walk
# should remain cave-like, and baseline can vary more freely.
WALL_PROFILES: dict[str, dict[str, str]] = {
    "open": {
        "baseline": "low",
        "random_walk": "low",
        "arena": "low",
    },
    "normal": {
        "baseline": "default",
        "random_walk": "default",
        "arena": "default",
    },
    "tight": {
        "baseline": "high",
        "random_walk": "default",
        "arena": "default",
    },
}


DEFAULT_SCREEN_SIZES = ("small", "medium", "large")
DEFAULT_SCREEN_MAP_TYPES = ("baseline", "random_walk", "arena")
DEFAULT_SCREEN_ENEMY_PROFILES = ("light", "normal", "heavy")
DEFAULT_SCREEN_ITEM_PROFILES = ("few", "normal", "many")
DEFAULT_SCREEN_WALL_PROFILES = ("open", "normal")
DEFAULT_SCREEN_AGENTS = VALIDATION_AGENT_PROFILES

BASE_COMBAT_RULES = combat_module.DEFAULT_COMBAT_RULES
BASE_PLAYER_HP = BASE_COMBAT_RULES.player.max_health
BASE_ENEMY_HP = BASE_COMBAT_RULES.enemy.max_health

OFAT_FACTORS_DEFAULT = (
    "size",
    "map_type",
    "enemy_profile",
    "item_profile",
    "wall_profile",
    "player_hp",
    "enemy_hp",
)

OFAT_BASELINE = {
    "size": "medium",
    "map_type": "baseline",
    "enemy_profile": "medium_plus",
    "item_profile": "many",
    "wall_profile": "open",
    "player_hp": BASE_PLAYER_HP,
    "enemy_hp": BASE_ENEMY_HP,
}

OFAT_HEALTH_LEVELS = {
    "player_hp": (3, 4, 5, 6),
    "enemy_hp": (1, 2, 3),
}


FINAL_VALIDATION_PRESETS = (
    # Small maps: intentionally easy/tutorial-like.
    {
        "size": "small",
        "map_type": "baseline",
        "enemy_profile": "normal",
        "item_profile": "normal",
        "wall_profile": "normal",
    },
    {
        "size": "small",
        "map_type": "random_walk",
        "enemy_profile": "normal",
        "item_profile": "normal",
        "wall_profile": "normal",
    },
    {
        "size": "small",
        "map_type": "arena",
        "enemy_profile": "normal",
        "item_profile": "normal",
        "wall_profile": "normal",
    },

    # Medium maps: tuned balanced setting.
    {
        "size": "medium",
        "map_type": "baseline",
        "enemy_profile": "medium_plus",
        "item_profile": "many",
        "wall_profile": "open",
    },
    {
        "size": "medium",
        "map_type": "random_walk",
        "enemy_profile": "medium_plus",
        "item_profile": "many",
        "wall_profile": "open",
    },
    {
        "size": "medium",
        "map_type": "arena",
        "enemy_profile": "medium_plus",
        "item_profile": "many",
        "wall_profile": "open",
    },

    # Large maps: hard, but not overloaded with heavy enemies.
    {
        "size": "large",
        "map_type": "baseline",
        "enemy_profile": "normal",
        "item_profile": "many",
        "wall_profile": "normal",
    },
    {
        "size": "large",
        "map_type": "random_walk",
        "enemy_profile": "normal",
        "item_profile": "many",
        "wall_profile": "open",
    },
    {
        "size": "large",
        "map_type": "arena",
        "enemy_profile": "normal",
        "item_profile": "many",
        "wall_profile": "open",
    },
)

CSV_COLUMNS = [
    "engine",
    "agent",
    "mcts_iterations",
    "mcts_rollout_depth",
    "mcts_exploration",
    "size",
    "map_type",
    "enemy_profile",
    "item_profile",
    "wall_profile",
    "enemy_count_setting",
    "items",
    "wall_density",
    "player_hp",
    "enemy_hp",
    "ofat_factor",
    "ofat_value",
    "max_steps",
    "seed",
    "episode",
    "map_seed",
    "experiment_name",
    "cell_id",
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
    experiment_name: str = ""
    cell_id: str = ""
    enemy_profile: str = ""
    item_profile: str = ""
    wall_profile: str = ""
    player_hp: int = BASE_PLAYER_HP
    enemy_hp: int = BASE_ENEMY_HP
    ofat_factor: str = ""
    ofat_value: str = ""
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


def canonical_agent_name(agent_name: str) -> str:
    if agent_name == "mcts_weak":
        return "mcts_small"
    return agent_name


def build_mcts_agent(profile_name: str, seed: int) -> MctsAgent:
    profile_name = canonical_agent_name(profile_name)
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
    name = canonical_agent_name(name)

    if name == "random":
        return RandomAgent(seed=seed)

    if name == "heuristic":
        return HeuristicAgent()

    if name in MCTS_PROFILES:
        return build_mcts_agent(name, seed)

    raise ValueError(f"Unknown agent profile: {name}")



@contextlib.contextmanager
def temporary_combat_rules(player_hp: int, enemy_hp: int):
    """Temporarily override combat rules for one evaluated episode.

    This affects:
    - GridBattleEnv player HP bookkeeping,
    - Griddly enemy HP in the generated YAML,
    - heuristic/MCTS combat profile lookups,
    - MCTS simulator rollouts.

    The context is process-local, so it is safe with ProcessPoolExecutor.
    """

    player_hp = max(1, int(player_hp))
    enemy_hp = max(1, int(enemy_hp))

    new_rules = CombatRules(
        player=UnitCombatProfile(
            max_health=player_hp,
            attack_damage=BASE_COMBAT_RULES.player.attack_damage,
            attack_range=BASE_COMBAT_RULES.player.attack_range,
        ),
        enemy=UnitCombatProfile(
            max_health=enemy_hp,
            attack_damage=BASE_COMBAT_RULES.enemy.attack_damage,
            attack_range=BASE_COMBAT_RULES.enemy.attack_range,
        ),
    )

    modules = [combat_module, game_module, simulator_module, mcts_module]
    previous: list[tuple[object, CombatRules]] = []

    for module in modules:
        if hasattr(module, "DEFAULT_COMBAT_RULES"):
            previous.append((module, getattr(module, "DEFAULT_COMBAT_RULES")))
            setattr(module, "DEFAULT_COMBAT_RULES", new_rules)

    try:
        yield
    finally:
        for module, old_rules in previous:
            setattr(module, "DEFAULT_COMBAT_RULES", old_rules)


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
    # Combat rules are overridden for the whole episode so the real env,
    # heuristic logic, and MCTS rollouts agree on player/enemy HP.
    with temporary_combat_rules(config.player_hp, config.enemy_hp):
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
    profile = mcts_profile_for(canonical_agent_name(config.agent))
    agent_name = canonical_agent_name(config.agent)

    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)

        if not file_exists:
            writer.writeheader()

        for episode_index, result in enumerate(results):
            writer.writerow(
                {
                    "engine": "griddly",
                    "agent": agent_name,
                    "mcts_iterations": profile.iterations if profile else "",
                    "mcts_rollout_depth": profile.rollout_depth if profile else "",
                    "mcts_exploration": profile.exploration if profile else "",
                    "size": config.size,
                    "map_type": config.map_type,
                    "enemy_profile": config.enemy_profile,
                    "item_profile": config.item_profile,
                    "wall_profile": config.wall_profile,
                    "enemy_count_setting": config.enemy_count,
                    "items": config.items,
                    "wall_density": config.wall_density,
                    "player_hp": config.player_hp,
                    "enemy_hp": config.enemy_hp,
                    "ofat_factor": config.ofat_factor,
                    "ofat_value": config.ofat_value,
                    "max_steps": config.max_steps,
                    "seed": config.seed,
                    "episode": episode_index,
                    "map_seed": result.map_seed,
                    "experiment_name": config.experiment_name,
                    "cell_id": config.cell_id,
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
    profile = mcts_profile_for(canonical_agent_name(config.agent))

    print("Real-environment evaluation summary")
    print("Engine: Griddly-backed GridBattleEnv")
    print(f"Agent: {canonical_agent_name(config.agent)}")

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
    if config.enemy_profile or config.item_profile or config.wall_profile:
        print(
            "PCG profiles: "
            f"enemy_profile={config.enemy_profile or '-'}, "
            f"item_profile={config.item_profile or '-'}, "
            f"wall_profile={config.wall_profile or '-'}"
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
    agent_name = canonical_agent_name(config.agent)
    profile = mcts_profile_for(agent_name)
    profile_note = ""

    if profile:
        profile_note = f" ({profile.iterations} it, depth {profile.rollout_depth})"

    print(
        f"{config.size:>6} | "
        f"{config.map_type:>11} | "
        f"{config.enemy_profile or '-':>6} | "
        f"{config.item_profile or '-':>6} | "
        f"{config.wall_profile or '-':>6} | "
        f"{agent_name:<11}{profile_note:<18} | "
        f"WR {win_rate(results):>6.1%} | "
        f"turns {mean(result.turns for result in results):>5.1f} | "
        f"dmg {mean(result.damage_taken for result in results):>4.1f} | "
        f"choke {mean(result.chokepoint_count for result in results):>4.1f}"
    )


def direction_name(direction: int | None) -> str:
    names = {1: "up", 2: "right", 3: "down", 4: "left"}
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
            f"Agent: {canonical_agent_name(args.agent)}",
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
            f"GridBattle Replay - {canonical_agent_name(args.agent)} - "
            f"{args.size}/{args.map_type} - seed {map_seed}"
        ),
        tile_size=args.tile_size,
        agent=make_agent(),
        agent_name=canonical_agent_name(args.agent),
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
        f"Agent replay: {canonical_agent_name(args.agent)}. "
        "Space pauses/resumes, Enter steps once, R resets, Esc quits."
    )

    window.run()


def parse_csv_list(raw: str, valid: tuple[str, ...] | list[str], name: str) -> list[str]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    valid_set = set(valid)
    unknown = [value for value in values if value not in valid_set]

    if unknown:
        raise SystemExit(
            f"Invalid {name}: {unknown}. Valid values: {sorted(valid_set)}"
        )

    return values


def parse_int_csv_list(raw: str, name: str) -> list[int]:
    values: list[int] = []

    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue

        try:
            value = int(part)
        except ValueError as exc:
            raise SystemExit(f"Invalid integer in {name}: {part!r}") from exc

        if value < 1:
            raise SystemExit(f"{name} values must be positive integers, got {value}")

        values.append(value)

    if not values:
        raise SystemExit(f"{name} cannot be empty")

    return values



def add_worker_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes for parallel episode evaluation.",
    )


def add_common_eval_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--size", choices=list(MAP_SIZES.keys()), default="medium")
    parser.add_argument("--map-type", choices=list(MAP_TYPES), default="random_walk")
    parser.add_argument("--items", choices=list(ITEM_LEVELS), default="normal")
    parser.add_argument("--enemy-count", choices=list(ENEMY_COUNT_LEVELS), default="default")
    parser.add_argument("--wall-density", choices=list(WALL_DENSITY_LEVELS), default="default")
    parser.add_argument("--max-steps", type=int, default=120)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run GridBattle balancing experiments using the real Griddly-backed environment."
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser("smoke", help="Run a quick real-environment sanity check.")
    smoke.add_argument("--episodes", type=int, default=2)
    smoke.add_argument("--seed", type=int, default=11)
    smoke.add_argument("--max-steps", type=int, default=60)
    add_worker_arg(smoke)

    eval_parser = subparsers.add_parser("eval", help="Run one real-environment evaluation.")
    add_common_eval_args(eval_parser)
    eval_parser.add_argument("--agent", choices=AGENT_PROFILES, default="heuristic")
    eval_parser.add_argument("--csv-out", default=None)
    eval_parser.add_argument("--quiet", action="store_true")
    add_worker_arg(eval_parser)

    pilot = subparsers.add_parser(
        "balance-pilot",
        help="Quick size x map_type x validation-agent pilot.",
    )
    pilot.add_argument("--episodes", type=int, default=10)
    pilot.add_argument("--seed", type=int, default=11)
    pilot.add_argument("--items", choices=list(ITEM_LEVELS), default="normal")
    pilot.add_argument("--enemy-count", choices=list(ENEMY_COUNT_LEVELS), default="default")
    pilot.add_argument("--wall-density", choices=list(WALL_DENSITY_LEVELS), default="default")
    pilot.add_argument("--max-steps", type=int, default=120)
    pilot.add_argument("--csv-out", default="results/balance_pilot.csv")
    pilot.add_argument("--overwrite", action="store_true")
    add_worker_arg(pilot)

    screen = subparsers.add_parser(
        "pcg-screen",
        help="Reduced factorial PCG screening with size-scaled profiles.",
    )
    screen.add_argument("--episodes", type=int, default=10)
    screen.add_argument("--seed", type=int, default=11)
    screen.add_argument("--max-steps", type=int, default=120)
    screen.add_argument("--csv-out", default="results/pcg_screening.csv")
    screen.add_argument("--overwrite", action="store_true")
    screen.add_argument("--dry-run", action="store_true")
    screen.add_argument("--sizes", default=",".join(DEFAULT_SCREEN_SIZES))
    screen.add_argument("--map-types", default=",".join(DEFAULT_SCREEN_MAP_TYPES))
    screen.add_argument("--enemy-profiles", default=",".join(DEFAULT_SCREEN_ENEMY_PROFILES))
    screen.add_argument("--item-profiles", default=",".join(DEFAULT_SCREEN_ITEM_PROFILES))
    screen.add_argument("--wall-profiles", default=",".join(DEFAULT_SCREEN_WALL_PROFILES))
    screen.add_argument("--agents", default=",".join(DEFAULT_SCREEN_AGENTS))
    add_worker_arg(screen)


    ofat = subparsers.add_parser(
        "ofat",
        help="Run a real-environment one-factor-at-a-time experiment.",
    )
    ofat.add_argument("--episodes", type=int, default=30)
    ofat.add_argument("--seed", type=int, default=11)
    ofat.add_argument("--max-steps", type=int, default=120)
    ofat.add_argument("--csv-out", default="results/ofat_real.csv")
    ofat.add_argument("--overwrite", action="store_true")
    ofat.add_argument(
        "--factors",
        default=",".join(OFAT_FACTORS_DEFAULT),
        help=(
            "Comma-separated OFAT factors. Valid: "
            "size,map_type,enemy_profile,item_profile,wall_profile,player_hp,enemy_hp"
        ),
    )
    ofat.add_argument(
        "--agents",
        default=",".join(VALIDATION_AGENT_PROFILES),
        help="Comma-separated agents to evaluate.",
    )
    ofat.add_argument("--baseline-size", choices=list(MAP_SIZES.keys()), default=OFAT_BASELINE["size"])
    ofat.add_argument("--baseline-map-type", choices=list(MAP_TYPES), default=OFAT_BASELINE["map_type"])
    ofat.add_argument("--baseline-enemy-profile", choices=list(ENEMY_PROFILES), default=OFAT_BASELINE["enemy_profile"])
    ofat.add_argument("--baseline-item-profile", choices=list(ITEM_PROFILES), default=OFAT_BASELINE["item_profile"])
    ofat.add_argument("--baseline-wall-profile", choices=list(WALL_PROFILES), default=OFAT_BASELINE["wall_profile"])
    ofat.add_argument("--baseline-player-hp", type=int, default=OFAT_BASELINE["player_hp"])
    ofat.add_argument("--baseline-enemy-hp", type=int, default=OFAT_BASELINE["enemy_hp"])
    ofat.add_argument("--player-hp-levels", default=",".join(str(v) for v in OFAT_HEALTH_LEVELS["player_hp"]))
    ofat.add_argument("--enemy-hp-levels", default=",".join(str(v) for v in OFAT_HEALTH_LEVELS["enemy_hp"]))
    ofat.add_argument("--dry-run", action="store_true")
    add_worker_arg(ofat)



    final_validation = subparsers.add_parser(
        "final-validation",
        help="Run the final selected PCG defaults across all sizes, map types, and validation agents.",
    )
    final_validation.add_argument("--episodes", type=int, default=50)
    final_validation.add_argument("--seed", type=int, default=11)
    final_validation.add_argument("--max-steps", type=int, default=120)
    final_validation.add_argument("--csv-out", default="results/final_validation.csv")
    final_validation.add_argument("--overwrite", action="store_true")
    final_validation.add_argument("--dry-run", action="store_true")
    final_validation.add_argument(
        "--agents",
        default=",".join(VALIDATION_AGENT_PROFILES),
        help="Comma-separated agents to evaluate.",
    )
    add_worker_arg(final_validation)


    replay = subparsers.add_parser(
        "replay",
        help="Inspect one generated game as text or with the normal Pygame UI.",
    )
    add_common_eval_args(replay)
    replay.add_argument("--agent", choices=AGENT_PROFILES, default="heuristic")
    replay.add_argument("--episode", type=int, default=0)
    replay.add_argument("--pause", action="store_true")
    replay.add_argument("--log-out", default=None)
    replay.add_argument("--ui", action="store_true")
    replay.add_argument("--delay-ms", type=int, default=600)
    replay.add_argument("--tile-size", type=int, default=68)

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
        experiment_name="manual_eval",
        cell_id=(
            f"manual_eval:"
            f"size={args.size}:map_type={args.map_type}:"
            f"enemy_count={args.enemy_count}:items={args.items}:"
            f"wall_density={args.wall_density}:agent={canonical_agent_name(args.agent)}"
        ),
    )


def run_smoke(args: argparse.Namespace) -> None:
    print("Running real-environment smoke test.")
    print("This uses GridBattleEnv directly and does not open the Pygame UI.")
    print()

    smoke_agents = ("random", "heuristic", "mcts_small")

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
            experiment_name="smoke",
            cell_id=f"smoke:{agent_name}",
        )
        run_evaluation(config)
        print()


def run_balance_pilot(args: argparse.Namespace) -> None:
    csv_out = args.csv_out

    if args.overwrite and os.path.exists(csv_out):
        os.remove(csv_out)

    print("Running PCG balance pilot.")
    print("Engine: Griddly-backed GridBattleEnv")
    print("Design: size x map_type x validation agents")
    print(f"Episodes per cell: {args.episodes}")
    print(f"Workers per cell: {args.workers}")
    print(f"CSV output: {csv_out}")
    print()
    print(
        "  size |    map_type | enemy |  item |   wall | agent                        | "
        "winrate | turns |  dmg | choke"
    )
    print("-" * 122)

    cells = [
        (size, map_type, agent_name)
        for size in MAP_SIZES
        for map_type in MAP_TYPES
        for agent_name in VALIDATION_AGENT_PROFILES
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
            experiment_name="balance_pilot",
            cell_id=f"balance_pilot:{size}:{map_type}:{agent_name}",
            workers=getattr(args, "workers", 1),
        )

        results = run_evaluation(config)
        print_compact_result(config, results)

    print()
    print(f"Done. Results written to {csv_out}")


def run_pcg_screen(args: argparse.Namespace) -> None:
    sizes = parse_csv_list(args.sizes, list(MAP_SIZES.keys()), "sizes")
    map_types = parse_csv_list(args.map_types, list(MAP_TYPES), "map-types")
    enemy_profiles = parse_csv_list(args.enemy_profiles, list(ENEMY_PROFILES), "enemy-profiles")
    item_profiles = parse_csv_list(args.item_profiles, list(ITEM_PROFILES), "item-profiles")
    wall_profiles = parse_csv_list(args.wall_profiles, list(WALL_PROFILES), "wall-profiles")
    agents = parse_csv_list(args.agents, list(AGENT_PROFILES), "agents")

    csv_out = args.csv_out

    cells: list[ExperimentConfig] = []

    for size in sizes:
        for map_type in map_types:
            for enemy_profile in enemy_profiles:
                for item_profile in item_profiles:
                    for wall_profile in wall_profiles:
                        enemy_count = ENEMY_PROFILES[enemy_profile][size]
                        items = ITEM_PROFILES[item_profile][size]
                        wall_density = WALL_PROFILES[wall_profile][map_type]

                        for agent_name in agents:
                            canonical_agent = canonical_agent_name(agent_name)
                            cell_id = (
                                f"pcg_screen:"
                                f"size={size}:map_type={map_type}:"
                                f"enemy_profile={enemy_profile}:item_profile={item_profile}:"
                                f"wall_profile={wall_profile}:agent={canonical_agent}"
                            )

                            cells.append(
                                ExperimentConfig(
                                    agent=canonical_agent,
                                    episodes=args.episodes,
                                    seed=args.seed,
                                    size=size,
                                    map_type=map_type,
                                    items=items,
                                    enemy_count=enemy_count,
                                    wall_density=wall_density,
                                    max_steps=args.max_steps,
                                    csv_out=csv_out,
                                    quiet=True,
                                    experiment_name="pcg_screen",
                                    cell_id=cell_id,
                                    enemy_profile=enemy_profile,
                                    item_profile=item_profile,
                                    wall_profile=wall_profile,
                                    workers=getattr(args, "workers", 1),
                                )
                            )

    total_episodes = len(cells) * args.episodes

    print("Running PCG screening experiment.")
    print("Engine: Griddly-backed GridBattleEnv")
    print("Design: reduced factorial with size-aware enemy/item profiles and map-type-aware wall profiles")
    print(f"Cells: {len(cells)}")
    print(f"Episodes per cell: {args.episodes}")
    print(f"Total episodes: {total_episodes}")
    print(f"Workers per cell: {args.workers}")
    print(f"CSV output: {csv_out}")
    print()
    print(f"Sizes: {sizes}")
    print(f"Map types: {map_types}")
    print(f"Enemy profiles: {enemy_profiles}")
    print(f"Item profiles: {item_profiles}")
    print(f"Wall profiles: {wall_profiles}")
    print(f"Agents: {[canonical_agent_name(agent) for agent in agents]}")
    print()

    if args.dry_run:
        print("Dry run only. First 20 cells:")
        for config in cells[:20]:
            print(
                f"{config.cell_id} -> "
                f"enemy_count={config.enemy_count}, "
                f"items={config.items}, "
                f"wall_density={config.wall_density}"
            )
        if len(cells) > 20:
            print(f"... {len(cells) - 20} more cells")
        return

    if args.overwrite and os.path.exists(csv_out):
        os.remove(csv_out)

    print(
        "  size |    map_type | enemy |  item |   wall | agent                        | "
        "winrate | turns |  dmg | choke"
    )
    print("-" * 122)

    for index, config in enumerate(cells, start=1):
        results = run_evaluation(config)
        print(f"[{index:>3}/{len(cells)}] ", end="")
        print_compact_result(config, results)

    print()
    print(f"Done. Results written to {csv_out}")



def run_ofat(args: argparse.Namespace) -> None:
    valid_factors = list(OFAT_FACTORS_DEFAULT)
    factors = parse_csv_list(args.factors, valid_factors, "factors")
    agents = parse_csv_list(args.agents, list(AGENT_PROFILES), "agents")

    player_hp_levels = parse_int_csv_list(args.player_hp_levels, "player-hp-levels")
    enemy_hp_levels = parse_int_csv_list(args.enemy_hp_levels, "enemy-hp-levels")

    factor_levels: dict[str, list[object]] = {
        "size": list(MAP_SIZES.keys()),
        "map_type": list(MAP_TYPES),
        "enemy_profile": list(ENEMY_PROFILES.keys()),
        "item_profile": list(ITEM_PROFILES.keys()),
        "wall_profile": list(WALL_PROFILES.keys()),
        "player_hp": player_hp_levels,
        "enemy_hp": enemy_hp_levels,
    }

    baseline: dict[str, object] = {
        "size": args.baseline_size,
        "map_type": args.baseline_map_type,
        "enemy_profile": args.baseline_enemy_profile,
        "item_profile": args.baseline_item_profile,
        "wall_profile": args.baseline_wall_profile,
        "player_hp": args.baseline_player_hp,
        "enemy_hp": args.baseline_enemy_hp,
    }

    cells: list[ExperimentConfig] = []

    def add_cell(params: dict[str, object], factor: str, value: object, agent_name: str) -> None:
        size = str(params["size"])
        map_type = str(params["map_type"])
        enemy_profile = str(params["enemy_profile"])
        item_profile = str(params["item_profile"])
        wall_profile = str(params["wall_profile"])
        player_hp = int(params["player_hp"])
        enemy_hp = int(params["enemy_hp"])

        enemy_count = ENEMY_PROFILES[enemy_profile][size]
        items = ITEM_PROFILES[item_profile][size]
        wall_density = WALL_PROFILES[wall_profile][map_type]

        canonical_agent = canonical_agent_name(agent_name)

        cell_id = (
            f"ofat:"
            f"factor={factor}:value={value}:"
            f"size={size}:map_type={map_type}:"
            f"enemy_profile={enemy_profile}:item_profile={item_profile}:"
            f"wall_profile={wall_profile}:"
            f"player_hp={player_hp}:enemy_hp={enemy_hp}:"
            f"agent={canonical_agent}"
        )

        cells.append(
            ExperimentConfig(
                agent=canonical_agent,
                episodes=args.episodes,
                seed=args.seed,
                size=size,
                map_type=map_type,
                items=items,
                enemy_count=enemy_count,
                wall_density=wall_density,
                max_steps=args.max_steps,
                csv_out=args.csv_out,
                quiet=True,
                experiment_name="ofat_real",
                cell_id=cell_id,
                enemy_profile=enemy_profile,
                item_profile=item_profile,
                wall_profile=wall_profile,
                player_hp=player_hp,
                enemy_hp=enemy_hp,
                ofat_factor=factor,
                ofat_value=str(value),
                workers=getattr(args, "workers", 1),
            )
        )

    # One explicit baseline cell.
    for agent_name in agents:
        add_cell(dict(baseline), "baseline", "baseline", agent_name)

    # One-factor-at-a-time cells. Skip baseline value for each factor because
    # the baseline is already included once.
    for factor in factors:
        baseline_value = baseline[factor]

        for value in factor_levels[factor]:
            if str(value) == str(baseline_value):
                continue

            params = dict(baseline)
            params[factor] = value

            for agent_name in agents:
                add_cell(params, factor, value, agent_name)

    total_episodes = len(cells) * args.episodes

    print("Running real-environment OFAT experiment.")
    print("Engine: Griddly-backed GridBattleEnv")
    print("Design: one factor at a time around a tuned medium-map baseline")
    print(f"Cells: {len(cells)}")
    print(f"Episodes per cell: {args.episodes}")
    print(f"Total episodes: {total_episodes}")
    print(f"Workers per cell: {args.workers}")
    print(f"CSV output: {args.csv_out}")
    print()
    print(f"Factors: {factors}")
    print(f"Agents: {[canonical_agent_name(agent) for agent in agents]}")
    print(f"Baseline: {baseline}")
    print()

    if args.dry_run:
        print("Dry run only. First 30 cells:")
        for config in cells[:30]:
            print(
                f"{config.cell_id} -> "
                f"enemy_count={config.enemy_count}, "
                f"items={config.items}, "
                f"wall_density={config.wall_density}, "
                f"player_hp={config.player_hp}, "
                f"enemy_hp={config.enemy_hp}"
            )
        if len(cells) > 30:
            print(f"... {len(cells) - 30} more cells")
        return

    if args.overwrite and os.path.exists(args.csv_out):
        os.remove(args.csv_out)

    print(
        " factor       | value        | agent       | size   | map_type    | enemy | item | wall | hp      | winrate | turns | dmg"
    )
    print("-" * 128)

    for index, config in enumerate(cells, start=1):
        results = run_evaluation(config)
        wr = win_rate(results)
        avg_turns = mean(result.turns for result in results)
        avg_damage = mean(result.damage_taken for result in results)

        print(
            f"[{index:>3}/{len(cells)}] "
            f"{config.ofat_factor:<12} | "
            f"{config.ofat_value:<12} | "
            f"{config.agent:<11} | "
            f"{config.size:<6} | "
            f"{config.map_type:<11} | "
            f"{config.enemy_profile:<6} | "
            f"{config.item_profile:<4} | "
            f"{config.wall_profile:<4} | "
            f"P{config.player_hp}/E{config.enemy_hp:<3} | "
            f"WR {wr:>6.1%} | "
            f"{avg_turns:>5.1f} | "
            f"{avg_damage:>4.1f}"
        )

    print()
    print(f"Done. Results written to {args.csv_out}")



def run_final_validation(args: argparse.Namespace) -> None:
    agents = parse_csv_list(args.agents, list(AGENT_PROFILES), "agents")
    csv_out = args.csv_out

    cells: list[ExperimentConfig] = []

    for preset in FINAL_VALIDATION_PRESETS:
        size = preset["size"]
        map_type = preset["map_type"]
        enemy_profile = preset["enemy_profile"]
        item_profile = preset["item_profile"]
        wall_profile = preset["wall_profile"]

        enemy_count = ENEMY_PROFILES[enemy_profile][size]
        items = ITEM_PROFILES[item_profile][size]
        wall_density = WALL_PROFILES[wall_profile][map_type]

        for agent_name in agents:
            canonical_agent = canonical_agent_name(agent_name)

            cell_id = (
                f"final_validation:"
                f"size={size}:map_type={map_type}:"
                f"enemy_profile={enemy_profile}:item_profile={item_profile}:"
                f"wall_profile={wall_profile}:agent={canonical_agent}"
            )

            cells.append(
                ExperimentConfig(
                    agent=canonical_agent,
                    episodes=args.episodes,
                    seed=args.seed,
                    size=size,
                    map_type=map_type,
                    items=items,
                    enemy_count=enemy_count,
                    wall_density=wall_density,
                    max_steps=args.max_steps,
                    csv_out=csv_out,
                    quiet=True,
                    experiment_name="final_validation",
                    cell_id=cell_id,
                    enemy_profile=enemy_profile,
                    item_profile=item_profile,
                    wall_profile=wall_profile,
                    player_hp=BASE_PLAYER_HP,
                    enemy_hp=BASE_ENEMY_HP,
                    workers=getattr(args, "workers", 1),
                )
            )

    total_episodes = len(cells) * args.episodes

    print("Running final validation experiment.")
    print("Engine: Griddly-backed GridBattleEnv")
    print("Design: selected final PCG defaults across size x map_type x validation agents")
    print(f"Cells: {len(cells)}")
    print(f"Episodes per cell: {args.episodes}")
    print(f"Total episodes: {total_episodes}")
    print(f"Workers per cell: {args.workers}")
    print(f"CSV output: {csv_out}")
    print()
    print("Selected defaults:")
    for preset in FINAL_VALIDATION_PRESETS:
        print(
            "  "
            f"size={preset['size']}, "
            f"map_type={preset['map_type']}, "
            f"enemy_profile={preset['enemy_profile']}, "
            f"item_profile={preset['item_profile']}, "
            f"wall_profile={preset['wall_profile']}"
        )
    print()
    print(f"Agents: {[canonical_agent_name(agent) for agent in agents]}")
    print()

    if args.dry_run:
        print("Dry run only. Cells:")
        for config in cells:
            print(
                f"{config.cell_id} -> "
                f"enemy_count={config.enemy_count}, "
                f"items={config.items}, "
                f"wall_density={config.wall_density}, "
                f"player_hp={config.player_hp}, "
                f"enemy_hp={config.enemy_hp}"
            )
        return

    if args.overwrite and os.path.exists(csv_out):
        os.remove(csv_out)

    print(
        "  size |    map_type | enemy |  item |   wall | agent                        | "
        "winrate | turns |  dmg | choke"
    )
    print("-" * 122)

    for index, config in enumerate(cells, start=1):
        results = run_evaluation(config)
        print(f"[{index:>3}/{len(cells)}] ", end="")
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
    elif args.command == "pcg-screen":
        run_pcg_screen(args)
    elif args.command == "ofat":
        run_ofat(args)
    elif args.command == "final-validation":
        run_final_validation(args)
    elif args.command == "replay":
        run_replay(args)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
