# play.py
from __future__ import annotations

import argparse
import random

from grid_battle.game import GridBattleEnv
from grid_battle.pcg import (
    DEFAULT_LEVEL,
    ENEMY_COUNT_LEVELS,
    ITEM_LEVELS,
    MAP_SIZES,
    MAP_TYPES,
    WALL_DENSITY_LEVELS,
    generate_preset_level,
)
from grid_battle.ui_pygame import GridBattleWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Play GridBattle using the pygame UI."
    )

    parser.add_argument(
        "--default-map",
        action="store_true",
        help="Use the fixed default map instead of generating a preset map.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for generated maps. If omitted, a random seed is used.",
    )
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
        "--items",
        choices=list(ITEM_LEVELS),
        default="default",
        help="Item density preset.",
    )
    parser.add_argument(
        "--enemy-count",
        choices=list(ENEMY_COUNT_LEVELS),
        default="default",
        help="Enemy count preset.",
    )
    parser.add_argument(
        "--wall-density",
        choices=list(WALL_DENSITY_LEVELS),
        default="default",
        help="Wall density preset.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=120,
        help="Maximum player turns before the episode stops.",
    )
    parser.add_argument(
        "--tile-size",
        type=int,
        default=68,
        help="Pixel size for each grid tile.",
    )
    parser.add_argument(
        "--auto-close-ms",
        type=int,
        default=0,
        help="Smoke-test helper: close the window automatically after this many milliseconds.",
    )

    return parser.parse_args()


def load_level(args: argparse.Namespace) -> tuple[str, str]:
    if args.default_map:
        return DEFAULT_LEVEL, "default fixed map"

    seed = args.seed if args.seed is not None else random.randint(0, 999_999)

    generated = generate_preset_level(
        size=args.size,
        map_type=args.map_type,
        seed=seed,
        item_level=args.items,
        enemy_count=args.enemy_count,
        wall_density=args.wall_density,
    )

    description = (
        f"generated map: size={args.size}, map_type={args.map_type}, "
        f"items={args.items}, enemy_count={args.enemy_count}, "
        f"wall_density={args.wall_density}, seed={seed}"
    )

    return generated.layout, description


def main() -> None:
    args = parse_args()
    level, description = load_level(args)

    print(f"GridBattle: {description}")

    env = GridBattleEnv(level, max_steps=args.max_steps)
    window = GridBattleWindow(
        env,
        max_steps=args.max_steps,
        window_title="GridBattle",
        tile_size=args.tile_size,
        auto_close_ms=args.auto_close_ms,
    )
    window.run()


if __name__ == "__main__":
    main()