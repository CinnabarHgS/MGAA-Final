from __future__ import annotations

import argparse

from grid_battle.game import ATTACK_ACTION, GridBattleEnv, MOVE_ACTION
from grid_battle.pcg import DEFAULT_LEVEL, generate_level

MOVE_KEYS = {
    "w": (MOVE_ACTION, 1),
    "d": (MOVE_ACTION, 2),
    "s": (MOVE_ACTION, 3),
    "a": (MOVE_ACTION, 4),
}

ATTACK_KEYS = {
    "i": (ATTACK_ACTION, 1),
    "l": (ATTACK_ACTION, 2),
    "k": (ATTACK_ACTION, 3),
    "j": (ATTACK_ACTION, 4),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play the GridBattle proposal demo.")
    parser.add_argument("--random-map", action="store_true", help="Generate a fresh map instead of using the fixed demo map.")
    parser.add_argument("--seed", type=int, default=7, help="Seed for random map generation.")
    parser.add_argument("--width", type=int, default=9, help="Map width for random generation.")
    parser.add_argument("--height", type=int, default=7, help="Map height for random generation.")
    parser.add_argument("--enemies", type=int, default=2, help="Enemy count for random generation.")
    parser.add_argument("--obstacle-density", type=float, default=0.18, help="Wall density for random generation.")
    parser.add_argument("--max-steps", type=int, default=40, help="Maximum player turns before the episode stops.")
    return parser.parse_args()


def _load_level(args: argparse.Namespace) -> str:
    if not args.random_map:
        return DEFAULT_LEVEL

    generated = generate_level(
        width=args.width,
        height=args.height,
        enemy_count=args.enemies,
        obstacle_density=args.obstacle_density,
        seed=args.seed,
    )
    return generated.layout


def _describe_turn(before, after, history: list[dict]) -> str:
    notes: list[str] = []

    player_health_before = before.player.health if before.player else 0
    player_health_after = after.player.health if after.player else 0
    if player_health_after < player_health_before:
        notes.append(f"enemy hit you for {player_health_before - player_health_after}")

    if after.remaining_enemies < before.remaining_enemies:
        notes.append(f"you defeated {before.remaining_enemies - after.remaining_enemies} enemy")
    else:
        before_enemy_health = sorted(enemy.health for enemy in before.enemies)
        after_enemy_health = sorted(enemy.health for enemy in after.enemies)
        if before_enemy_health and sum(after_enemy_health) < sum(before_enemy_health):
            notes.append("your attack connected")

    player_event = next((event for event in history if event["PlayerId"] == 1), None)
    if player_event and player_event["DestinationObjectName"] == "enemy" and "your attack connected" not in notes:
        notes.append("you bumped into an enemy instead of moving")

    return "; ".join(notes) if notes else "no major state change"


def main() -> None:
    args = parse_args()
    level = _load_level(args)
    env = GridBattleEnv(level, max_steps=args.max_steps)
    snapshot = env.reset()

    print("GridBattle demo")
    print("Goal: defeat all enemies before they defeat you.")
    print("Move with w/a/s/d, attack with i/j/k/l, quit with q.")
    print()

    while True:
        print(env.render_ascii())
        player_health = snapshot.player.health if snapshot.player else 0
        print(
            f"Turn {snapshot.player_turns}/{args.max_steps} | "
            f"HP {player_health} | Enemies left {snapshot.remaining_enemies}"
        )

        if snapshot.player is None:
            print("You lost.")
            break
        if snapshot.remaining_enemies == 0:
            print("You won.")
            break

        try:
            key = input("> ").strip().lower()
        except EOFError:
            print("Input ended. Quit.")
            break
        if key == "q":
            print("Quit.")
            break

        action = MOVE_KEYS.get(key) or ATTACK_KEYS.get(key)
        if action is None:
            print("Unknown input. Use w/a/s/d or i/j/k/l.")
            continue

        previous = snapshot
        snapshot, reward, done, info = env.step(action)
        del reward
        print(_describe_turn(previous, snapshot, info.get("History", [])))
        print()

        if done and snapshot.remaining_enemies == 0:
            print(env.render_ascii())
            print("You won.")
            break
        if done and snapshot.player is None:
            print(env.render_ascii())
            print("You lost.")
            break


if __name__ == "__main__":
    main()
