"""Run agent evaluation with the pure-python simulator (no griddly needed).

Numbers wont be identical to evaluate_demo.py since that one uses the real
griddly env, but comparing agents against each other is still fine because
they all play the same simulated env. Useful when you cant get griddly
working locally (e.g. arm64 mac, the pypi wheel is x86_64 only)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from statistics import mean
from typing import Protocol

from grid_battle import (
    BattleSnapshot,
    HeuristicAgent,
    MctsAgent,
    PhaseAction,
    RandomAgent,
    TurnAction,
    UnitState,
    generate_preset_level,
    simulate_turn,
)
from grid_battle.combat import (
    DEFAULT_COMBAT_RULES,
    ITEM_MAP_CHARS,
    TERRAIN_BUNKER,
    TERRAIN_BUSH,
    TERRAIN_HILL,
    TERRAIN_MAP_CHARS,
)
from grid_battle.pcg import MAP_SIZES, MAP_TYPES


class Agent(Protocol):
    def act(self, snapshot: BattleSnapshot) -> TurnAction: ...


AGENT_CHOICES = ("heuristic", "random", "mcts")


def build_agent(name: str, *, mcts_iterations: int, seed: int) -> Agent:
    if name == "heuristic":
        return HeuristicAgent()
    if name == "random":
        return RandomAgent(seed=seed)
    if name == "mcts":
        return MctsAgent(iterations=mcts_iterations, seed=seed)
    raise ValueError(f"Unknown agent: {name}")


def snapshot_from_layout(layout: str) -> BattleSnapshot:
    rows = layout.splitlines()
    height = len(rows)
    width = len(rows[0])
    player: UnitState | None = None
    enemies: list[UnitState] = []
    walls: set[tuple[int, int]] = set()
    hills: set[tuple[int, int]] = set()
    bushes: set[tuple[int, int]] = set()
    bunkers: set[tuple[int, int]] = set()
    map_items: list[tuple[tuple[int, int], str]] = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            pos = (x, y)
            if ch == "W":
                walls.add(pos)
            elif ch == "A":
                player = UnitState(position=pos, health=DEFAULT_COMBAT_RULES.player.max_health)
            elif ch == "E":
                enemies.append(UnitState(position=pos, health=DEFAULT_COMBAT_RULES.enemy.max_health))
            elif ch in TERRAIN_MAP_CHARS:
                terrain_name = TERRAIN_MAP_CHARS[ch]
                if terrain_name == TERRAIN_HILL:
                    hills.add(pos)
                elif terrain_name == TERRAIN_BUSH:
                    bushes.add(pos)
                elif terrain_name == TERRAIN_BUNKER:
                    bunkers.add(pos)
            elif ch in ITEM_MAP_CHARS:
                map_items.append((pos, ITEM_MAP_CHARS[ch]))
    enemies.sort(key=lambda u: u.position)
    return BattleSnapshot(
        width=width,
        height=height,
        game_ticks=0,
        player_turns=0,
        player=player,
        enemies=tuple(enemies),
        walls=frozenset(walls),
        hills=frozenset(hills),
        bushes=frozenset(bushes),
        bunkers=frozenset(bunkers),
        map_items=tuple(sorted(map_items)),
    )


@dataclass(frozen=True)
class EpisodeResult:
    won: bool
    turns: int
    damage_taken: int
    remaining_enemies: int


def run_episode(initial: BattleSnapshot, agent: Agent, max_steps: int) -> EpisodeResult:
    assert initial.player is not None
    initial_health = initial.player.health
    state = initial
    while (
        state.player is not None
        and state.remaining_enemies > 0
        and state.player_turns < max_steps
    ):
        state = simulate_turn(state, agent.act(state))
    final_health = state.player.health if state.player else 0
    return EpisodeResult(
        won=state.remaining_enemies == 0 and state.player is not None,
        turns=state.player_turns,
        damage_taken=initial_health - final_health,
        remaining_enemies=state.remaining_enemies,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--size", choices=list(MAP_SIZES.keys()), default="small")
    parser.add_argument("--map-type", choices=list(MAP_TYPES), default="baseline")
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--agent", choices=AGENT_CHOICES, default="heuristic")
    parser.add_argument("--mcts-iterations", type=int, default=200)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    agent = build_agent(args.agent, mcts_iterations=args.mcts_iterations, seed=args.seed)
    results: list[EpisodeResult] = []
    last_width = last_height = 0

    for i in range(args.episodes):
        generated = generate_preset_level(size=args.size, map_type=args.map_type, seed=args.seed + i)
        last_width, last_height = generated.width, generated.height
        initial = snapshot_from_layout(generated.layout)
        results.append(run_episode(initial, agent, args.max_steps))

    wins = sum(r.won for r in results)
    win_rate = wins / len(results)
    avg_turns = mean(r.turns for r in results)
    avg_damage = mean(r.damage_taken for r in results)
    losses = [r for r in results if not r.won]
    avg_remaining = mean(r.remaining_enemies for r in losses) if losses else 0.0

    print("Simulator evaluation summary (Griddly-free)")
    print(f"Agent: {args.agent}")
    print(f"Episodes: {args.episodes}")
    print(f"Map type: {args.map_type}")
    print(f"Map size preset: {args.size}")
    print(f"Map dimensions: {last_width}x{last_height}")
    print(f"Win rate: {win_rate:.1%}")
    print(f"Average turns: {avg_turns:.2f}")
    print(f"Average damage taken: {avg_damage:.2f}")
    print(f"Average enemies left on losses: {avg_remaining:.2f}")


if __name__ == "__main__":
    main()
