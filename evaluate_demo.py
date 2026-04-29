from __future__ import annotations

import argparse
from dataclasses import dataclass
from statistics import mean

from grid_battle import GridBattleEnv, HeuristicAgent, generate_level


@dataclass(frozen=True)
class EpisodeResult:
    won: bool
    turns: int
    damage_taken: int
    remaining_enemies: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline AI evaluation for the GridBattle demo.")
    parser.add_argument("--episodes", type=int, default=20, help="Number of generated maps to evaluate.")
    parser.add_argument("--seed", type=int, default=11, help="Base seed for map generation.")
    parser.add_argument("--width", type=int, default=9, help="Generated map width.")
    parser.add_argument("--height", type=int, default=7, help="Generated map height.")
    parser.add_argument("--enemies", type=int, default=2, help="Enemy count per map.")
    parser.add_argument("--obstacle-density", type=float, default=0.18, help="Wall density for map generation.")
    parser.add_argument("--max-steps", type=int, default=40, help="Maximum player turns per episode.")
    return parser.parse_args()


def run_episode(env: GridBattleEnv, agent: HeuristicAgent, max_steps: int) -> EpisodeResult:
    snapshot = env.reset()
    initial_health = snapshot.player.health if snapshot.player else 0

    while snapshot.player is not None and snapshot.remaining_enemies > 0 and snapshot.player_turns < max_steps:
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
        remaining_enemies=snapshot.remaining_enemies,
    )


def main() -> None:
    args = parse_args()
    agent = HeuristicAgent()
    results: list[EpisodeResult] = []

    for episode_index in range(args.episodes):
        generated = generate_level(
            width=args.width,
            height=args.height,
            enemy_count=args.enemies,
            obstacle_density=args.obstacle_density,
            seed=args.seed + episode_index,
        )
        env = GridBattleEnv(generated.layout, max_steps=args.max_steps)
        results.append(run_episode(env, agent, args.max_steps))

    wins = sum(result.won for result in results)
    win_rate = wins / len(results)
    avg_turns = mean(result.turns for result in results)
    avg_damage = mean(result.damage_taken for result in results)
    losses = [result for result in results if not result.won]
    avg_remaining_enemies_on_losses = (
        mean(result.remaining_enemies for result in losses) if losses else 0.0
    )

    print("Baseline evaluation summary")
    print(f"Episodes: {args.episodes}")
    print(f"Map size: {args.width}x{args.height}")
    print(f"Enemies per map: {args.enemies}")
    print(f"Obstacle density: {args.obstacle_density:.2f}")
    print(f"Win rate: {win_rate:.1%}")
    print(f"Average turns: {avg_turns:.2f}")
    print(f"Average damage taken: {avg_damage:.2f}")
    print(f"Average enemies left on losses: {avg_remaining_enemies_on_losses:.2f}")


if __name__ == "__main__":
    main()
