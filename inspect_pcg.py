from __future__ import annotations

import argparse

from grid_battle.pcg import (
    MAP_SIZES,
    MAP_TYPES,
    analyze_level,
    format_analysis,
    generate_preset_level,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect generated PCG maps structurally.")
    parser.add_argument("--count", type=int, default=5, help="Number of maps to generate.")
    parser.add_argument("--seed", type=int, default=7, help="Base seed for generation.")
    parser.add_argument(
        "--size",
        choices=list(MAP_SIZES.keys()),
        default="small",
        help="Generated map size preset.",
    )
    parser.add_argument(
        "--all-sizes",
        action="store_true",
        help="Generate maps for all size presets instead of only --size.",
    )
    parser.add_argument(
        "--map-type",
        choices=list(MAP_TYPES),
        default="baseline",
        help="PCG generator type.",
    )
    parser.add_argument(
        "--no-layout",
        action="store_true",
        help="Only print metrics, not the ASCII map layout.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    sizes = list(MAP_SIZES.keys()) if args.all_sizes else [args.size]
    generated_index = 0

    for size in sizes:
        for local_index in range(args.count):
            seed = args.seed + generated_index
            generated_index += 1

            generated = generate_preset_level(
                size=size,
                map_type=args.map_type,
                seed=seed,
            )
            analysis = analyze_level(generated.layout)

            print("=" * 72)
            print(f"Map {local_index + 1}/{args.count}")
            print(f"type: {args.map_type}")
            print(f"size preset: {size}")
            print(f"seed: {seed}")
            print(f"interior wall count reported by generator: {generated.obstacle_count}")
            print(f"generator obstacle-density setting: {generated.obstacle_density:.2%}")  
            print()
            print(format_analysis(analysis))

            if not args.no_layout:
                print()
                print(generated.layout)

            print()


if __name__ == "__main__":
    main()