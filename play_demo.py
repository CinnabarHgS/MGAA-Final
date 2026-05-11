from __future__ import annotations

import argparse

from grid_battle.combat import DEFAULT_COMBAT_RULES, ITEM_DUAL_BERETTAS, ITEM_MAP_CHARS, TERRAIN_MAP_CHARS
from grid_battle.game import BattleSnapshot, GridBattleEnv, PhaseAction, TurnAction
from grid_battle.pcg import DEFAULT_LEVEL, generate_level

_ITEM_DISPLAY = {v: k for k, v in ITEM_MAP_CHARS.items()}
_TERRAIN_DISPLAY = {v: k for k, v in TERRAIN_MAP_CHARS.items()}

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


def _render_map(snapshot: BattleSnapshot) -> str:
    grid = [["." for _ in range(snapshot.width)] for _ in range(snapshot.height)]
    for x, y in snapshot.walls:
        grid[y][x] = "W"
    for x, y in snapshot.hills:
        grid[y][x] = _TERRAIN_DISPLAY["hill"]
    for x, y in snapshot.bushes:
        grid[y][x] = _TERRAIN_DISPLAY["bush"]
    for x, y in snapshot.bunkers:
        grid[y][x] = _TERRAIN_DISPLAY["bunker"]
    for (x, y), item_name in snapshot.map_items:
        grid[y][x] = _ITEM_DISPLAY.get(item_name, "?")
    for enemy in snapshot.enemies:
        grid[enemy.position[1]][enemy.position[0]] = "E"
    if snapshot.player:
        grid[snapshot.player.position[1]][snapshot.player.position[0]] = "A"
    return "\n".join("   ".join(row) for row in grid)


def _health_bar(current: int, maximum: int, width: int = 10) -> str:
    filled = max(0, round(current / maximum * width))
    return "[" + "█" * filled + "░" * (width - filled) + "]"


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

    if any(
        event["ActionName"] == "move" and event["DestinationObjectName"] == "enemy"
        for event in player_events
    ) and "your attack connected" not in notes:
        notes.append("you bumped into an enemy instead of moving")

    if after.inventory and len(after.inventory) > len(before.inventory):
        gained = set(after.inventory) - set(before.inventory)
        notes.append(f"picked up {', '.join(gained)}")

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


def _read_item_input(inventory: tuple[str, ...]) -> str | None | str:
    if not inventory:
        return None
    choices = {str(i + 1): item for i, item in enumerate(inventory)}
    while True:
        try:
            key = input("item> ").strip().lower()
        except EOFError:
            return "quit"

        if key == "q":
            return "quit"
        if key == "":
            return None
        if key in choices:
            return choices[key]

        options = ", ".join(f"{k}={v}" for k, v in choices.items())
        print(f"Choose item: {options}, or Enter to skip.")


def main() -> None:
    args = parse_args()
    level = _load_level(args)
    env = GridBattleEnv(level, max_steps=args.max_steps)
    snapshot = env.reset()
    max_hp = DEFAULT_COMBAT_RULES.player.max_health

    print("GridBattle")
    print("Goal: defeat all enemies before they defeat you.")
    print("Move: w/a/s/d  Attack: i/j/k/l  Skip phase: Enter  Quit: q")
    print("Terrain: H=hill(+range)  B=bush(50% dodge)  K=bunker(immune+no move 1 turn)")
    # print("Items: pick up by walking over. Activate with item> prompt (1/2/3...).")
    print()

    while True:
        print(_render_map(snapshot))
        player_health = snapshot.player.health if snapshot.player else 0
        bar = _health_bar(player_health, max_hp)
        terrain_here = []
        if snapshot.player and snapshot.player.position in snapshot.hills:
            terrain_here.append("HILL")
        if snapshot.player and snapshot.player.position in snapshot.bushes:
            terrain_here.append("BUSH")
        if snapshot.player and snapshot.player.position in snapshot.bunkers:
            terrain_here.append("BUNKER")
        terrain_str = f" [{', '.join(terrain_here)}]" if terrain_here else ""
        print(
            f"Turn {snapshot.player_turns}/{args.max_steps} | "
            f"HP {player_health}/{max_hp} {bar} | "
            f"Enemies {snapshot.remaining_enemies}{terrain_str}"
        )
        if snapshot.inventory:
            inv_str = ", ".join(f"{i+1}:{item}" for i, item in enumerate(snapshot.inventory))
            print(f"Inventory: {inv_str}")
        if snapshot.active_effects:
            eff_str = ", ".join(f"{e.name}({e.turns_left})" for e in snapshot.active_effects)
            print(f"Active: {eff_str}")

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

        action2 = None
        if any(e.name == ITEM_DUAL_BERETTAS for e in snapshot.active_effects):
            attack_direction2 = _read_phase_input(
                "action2> ",
                ATTACK_KEYS,
                "Dual Berettas: use i/j/k/l for second attack direction, or Enter to skip.",
            )
            if attack_direction2 == "quit":
                print("Quit.")
                break
            action2 = PhaseAction("attack", attack_direction2) if attack_direction2 is not None else None

        activate_item = _read_item_input(snapshot.inventory)
        if activate_item == "quit":
            print("Quit.")
            break

        turn_action = TurnAction(
            move_direction=move_direction,
            action=PhaseAction("attack", attack_direction) if attack_direction is not None else None,
            action2=action2,
            activate_item=activate_item,
        )

        previous = snapshot
        snapshot, reward, done, info = env.step(turn_action)
        del reward
        print(_describe_turn(previous, snapshot, info.get("History", [])))
        print()

        if done and snapshot.remaining_enemies == 0:
            print(_render_map(snapshot))
            print("You won.")
            break
        if done and snapshot.player is None:
            print(_render_map(snapshot))
            print("You lost.")
            break


if __name__ == "__main__":
    main()
