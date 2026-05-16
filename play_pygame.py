from __future__ import annotations

import argparse

from grid_battle.game import GridBattleEnv
from grid_battle.pcg import DEFAULT_LEVEL, generate_level
from grid_battle.ui_pygame import GridBattleWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play the GridBattle demo in a pygame window.")
    parser.add_argument("--random-map", action="store_true", help="Generate a fresh map instead of using the fixed demo map.")
    parser.add_argument("--seed", type=int, default=7, help="Seed for random map generation.")
    parser.add_argument("--width", type=int, default=9, help="Map width for random generation.")
    parser.add_argument("--height", type=int, default=7, help="Map height for random generation.")
    parser.add_argument("--enemies", type=int, default=2, help="Enemy count for random generation.")
    parser.add_argument("--obstacle-density", type=float, default=0.18, help="Wall density for random generation.")
    parser.add_argument("--max-steps", type=int, default=40, help="Maximum player turns before the episode stops.")
    parser.add_argument("--tile-size", type=int, default=68, help="Pixel size for each grid tile.")
    parser.add_argument(
        "--auto-close-ms",
        type=int,
        default=0,
        help="Optional smoke-test helper: close the window automatically after this many milliseconds.",
    )
    return parser.parse_args()


def load_level(args: argparse.Namespace) -> str:
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


def main() -> None:
    args = parse_args()
    level = load_level(args)
    env = GridBattleEnv(level, max_steps=args.max_steps)
    window = GridBattleWindow(
        env,
        max_steps=args.max_steps,
        tile_size=args.tile_size,
        auto_close_ms=args.auto_close_ms,
    )
    window.run()


if __name__ == "__main__":
    main()
