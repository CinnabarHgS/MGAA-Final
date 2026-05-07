from __future__ import annotations

import argparse
import random

from grid_battle.game import GridBattleEnv, PhaseAction, TurnAction
from grid_battle.pcg import DEFAULT_LEVEL, MAP_SIZES, MAP_TYPES, generate_preset_level


MOVE_KEYS = {
    "w": 1,
    "d": 2,
    "s": 3,
    "a": 4,
}

ATTACK_KEYS = {
    "i": 1,
    "l": 2,
    "k": 3,
    "j": 4,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play the GridBattle proposal demo.")
    parser.add_argument(
        "--random-map",
        action="store_true",
        help="Generate a fresh map instead of using the fixed demo map.",
    )
    parser.add_argument("--seed", type=int, default=random.randint(0,9999), help="Seed for random map generation.")
    parser.add_argument(
        "--size",
        choices=list(MAP_SIZES.keys()),
        default="small",
        help="Generated map size preset.",
    )
    parser.add_argument(
        "--map-type",
        choices=list(MAP_TYPES),
        default="baseline",
        help="PCG generator type.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=100,
        help="Maximum player turns before the episode stops.",
    )
    return parser.parse_args()


def _load_level(args: argparse.Namespace) -> str:
    if not args.random_map:
        return DEFAULT_LEVEL

    generated = generate_preset_level(
        size=args.size,
        map_type=args.map_type,
        seed=args.seed,
    )
    return generated.layout


def _describe_turn(before, after, history: list[dict]) -> str:
    notes: list[str] = []
    player_events = [event for event in history if event["PlayerId"] == 1]

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

    if any(event["ActionName"] == "wait" for event in player_events):
        notes.append("you waited")

    if (
        any(
            event["ActionName"] == "move"
            and event["DestinationObjectName"] == "enemy"
            for event in player_events
        )
        and "your attack connected" not in notes
    ):
        notes.append("you bumped into an enemy instead of moving")

    return "; ".join(notes) if notes else "no major state change"


def _read_phase_input(prompt: str, mapping: dict[str, int], help_text: str) -> int | None | str:
    while True:
        try:
            key = input(prompt).strip().lower()
        except EOFError:
            return "quit"

        if key == "q":
            return "quit"
        if key == "":
            return None
        if key in mapping:
            return mapping[key]

        print(help_text)


def main() -> None:
    args = parse_args()
    level = _load_level(args)

    env = GridBattleEnv(level, max_steps=args.max_steps)
    snapshot = env.reset()

    print("GridBattle demo")
    print("Goal: defeat all enemies before they defeat you.")
    print("Each turn: choose one move, then one action.")
    print("Move with w/a/s/d, attack with i/j/k/l, press Enter to skip a phase, quit with q.")

    if args.random_map:
        print(f"Generated map: type={args.map_type}, size={args.size}, seed={args.seed}")

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

        move_direction = _read_phase_input(
            "move> ",
            MOVE_KEYS,
            "Use w/a/s/d to move, Enter to skip movement, or q to quit.",
        )
        if move_direction == "quit":
            print("Quit.")
            break

        attack_direction = _read_phase_input(
            "action> ",
            ATTACK_KEYS,
            "Use i/j/k/l to attack, Enter to skip the action, or q to quit.",
        )
        if attack_direction == "quit":
            print("Quit.")
            break

        turn_action = TurnAction(
            move_direction=move_direction,
            action=PhaseAction("attack", attack_direction)
            if attack_direction is not None
            else None,
        )

        previous = snapshot
        snapshot, reward, done, info = env.step(turn_action)
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