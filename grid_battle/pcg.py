from __future__ import annotations

import random
import textwrap
from collections import deque
from dataclasses import dataclass
from typing import Literal

from .combat import DEFAULT_COMBAT_RULES, positions_that_can_attack_target


MapSize = Literal["tiny", "small", "medium", "large", "giant"]
MapType = Literal["baseline"]

MAP_SIZES: dict[MapSize, tuple[int, int]] = {
    "tiny": (9, 7),
    "small": (13, 11),
    "medium": (17, 13),
    "large": (19, 17),
    "giant": (25, 21),
}

MAP_TYPES: tuple[MapType, ...] = ("baseline",)


@dataclass(frozen=True)
class GenerationPreset:
    enemy_count: int
    obstacle_density: float


BASELINE_PRESETS: dict[MapSize, GenerationPreset] = {
    "tiny": GenerationPreset(enemy_count=1, obstacle_density=0.10),
    "small": GenerationPreset(enemy_count=2, obstacle_density=0.18),
    "medium": GenerationPreset(enemy_count=3, obstacle_density=0.20),
    "large": GenerationPreset(enemy_count=5, obstacle_density=0.22),
    "giant": GenerationPreset(enemy_count=7, obstacle_density=0.24),
}


DEFAULT_LEVEL = textwrap.dedent(
    """
    WWWWWWWWW
    W..E....W
    W.W.WW..W
    W...A...W
    W..WW.W.W
    W....E..W
    WWWWWWWWW
    """
).strip()


@dataclass(frozen=True)
class GeneratedLevel:
    layout: str
    width: int
    height: int
    enemy_count: int
    obstacle_count: int
    obstacle_density: float
    seed: int | None


@dataclass(frozen=True)
class MapAnalysis:
    width: int
    height: int
    player_count: int
    enemy_count: int
    wall_count: int
    interior_wall_count: int
    interior_wall_density: float
    total_wall_ratio: float
    floor_count: int
    reachable_floor_count: int
    reachable_floor_fraction: float
    enemy_attackability_valid: bool
    structurally_valid: bool
    dead_end_count: int
    chokepoint_count: int
    min_enemy_attack_distance: int | None
    avg_enemy_attack_distance: float | None
    max_enemy_attack_distance: int | None
    extra_symbols: tuple[str, ...]


def _neighbors(position: tuple[int, int]) -> list[tuple[int, int]]:
    x, y = position
    return [(x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)]


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _grid_to_string(grid: list[list[str]]) -> str:
    return "\n".join("".join(row) for row in grid)


def _layout_to_grid(layout: str) -> list[list[str]]:
    lines = [line.strip() for line in layout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Level layout is empty.")

    width = len(lines[0])
    if width == 0:
        raise ValueError("Level layout contains an empty row.")

    if any(len(line) != width for line in lines):
        raise ValueError("Level layout must be rectangular.")

    return [list(line) for line in lines]


def _find_positions(grid: list[list[str]], symbol: str) -> list[tuple[int, int]]:
    return [
        (x, y)
        for y, row in enumerate(grid)
        for x, cell in enumerate(row)
        if cell == symbol
    ]


def _reachable_tiles(
    grid: list[list[str]],
    start: tuple[int, int],
    blocked_positions: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    width = len(grid[0])
    height = len(grid)
    queue = deque([start])
    visited = {start}

    while queue:
        x, y = queue.popleft()
        for nx, ny in _neighbors((x, y)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in visited or (nx, ny) in blocked_positions:
                continue
            if grid[ny][nx] == "W":
                continue

            visited.add((nx, ny))
            queue.append((nx, ny))

    return visited


def _distances_from(
    grid: list[list[str]],
    start: tuple[int, int],
    blocked_positions: set[tuple[int, int]],
) -> dict[tuple[int, int], int]:
    width = len(grid[0])
    height = len(grid)
    queue = deque([start])
    distances = {start: 0}

    while queue:
        x, y = queue.popleft()
        for nx, ny in _neighbors((x, y)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in distances or (nx, ny) in blocked_positions:
                continue
            if grid[ny][nx] == "W":
                continue

            distances[(nx, ny)] = distances[(x, y)] + 1
            queue.append((nx, ny))

    return distances


def _articulation_points(nodes: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Return reachable tiles that act as graph articulation points."""

    if len(nodes) < 3:
        return set()

    discovery_time: dict[tuple[int, int], int] = {}
    low_time: dict[tuple[int, int], int] = {}
    parent: dict[tuple[int, int], tuple[int, int] | None] = {}
    articulation: set[tuple[int, int]] = set()
    time = 0

    def node_neighbors(position: tuple[int, int]) -> list[tuple[int, int]]:
        return [neighbor for neighbor in _neighbors(position) if neighbor in nodes]

    def dfs(node: tuple[int, int]) -> None:
        nonlocal time

        discovery_time[node] = time
        low_time[node] = time
        time += 1

        child_count = 0

        for neighbor in node_neighbors(node):
            if neighbor not in discovery_time:
                parent[neighbor] = node
                child_count += 1
                dfs(neighbor)

                low_time[node] = min(low_time[node], low_time[neighbor])

                is_root = parent.get(node) is None
                if is_root and child_count > 1:
                    articulation.add(node)
                if not is_root and low_time[neighbor] >= discovery_time[node]:
                    articulation.add(node)

            elif neighbor != parent.get(node):
                low_time[node] = min(low_time[node], discovery_time[neighbor])

    for node in nodes:
        if node not in discovery_time:
            parent[node] = None
            dfs(node)

    return articulation


def _is_playable(
    grid: list[list[str]],
    player: tuple[int, int],
    enemies: list[tuple[int, int]],
) -> bool:
    blocked = set(enemies)
    reachable = _reachable_tiles(grid, player, blocked)
    wall_positions = {
        (x, y)
        for y, row in enumerate(grid)
        for x, cell in enumerate(row)
        if cell == "W"
    }

    player_attack_range = DEFAULT_COMBAT_RULES.player.attack_range

    for enemy in enemies:
        attack_positions = positions_that_can_attack_target(
            enemy,
            player_attack_range,
            len(grid[0]),
            len(grid),
            occupied_positions=blocked,
            blocking_positions=wall_positions | (blocked - {enemy}),
        )
        if not attack_positions:
            return False
        if not any(position in reachable for position in attack_positions):
            return False

    floor_tiles = sum(cell != "W" for row in grid for cell in row)
    return len(reachable) >= max(4, floor_tiles // 3)


def analyze_level(layout: str) -> MapAnalysis:
    """Compute structural metrics for a map without running any agent."""

    grid = _layout_to_grid(layout)
    width = len(grid[0])
    height = len(grid)

    players = _find_positions(grid, "A")
    enemies = _find_positions(grid, "E")
    player = players[0] if len(players) == 1 else None

    wall_positions = {
        (x, y)
        for y, row in enumerate(grid)
        for x, cell in enumerate(row)
        if cell == "W"
    }

    interior_wall_positions = {
        (x, y)
        for x, y in wall_positions
        if 0 < x < width - 1 and 0 < y < height - 1
    }

    floor_count = sum(cell != "W" for row in grid for cell in row)
    interior_cell_count = max(0, (width - 2) * (height - 2))

    blocked = set(enemies)
    reachable: set[tuple[int, int]] = set()
    distances: dict[tuple[int, int], int] = {}

    if player is not None:
        reachable = _reachable_tiles(grid, player, blocked)
        distances = _distances_from(grid, player, blocked)

    player_attack_range = DEFAULT_COMBAT_RULES.player.attack_range
    enemy_attack_distances: list[int] = []
    enemy_attackability_valid = player is not None

    if player is None:
        enemy_attackability_valid = False
    else:
        for enemy in enemies:
            attack_positions = positions_that_can_attack_target(
                enemy,
                player_attack_range,
                width,
                height,
                occupied_positions=blocked,
                blocking_positions=wall_positions | (blocked - {enemy}),
            )

            reachable_attack_distances = [
                distances[position]
                for position in attack_positions
                if position in distances
            ]

            if not reachable_attack_distances:
                enemy_attackability_valid = False
            else:
                enemy_attack_distances.append(min(reachable_attack_distances))

    reachable_neighbor_counts = {
        position: sum(neighbor in reachable for neighbor in _neighbors(position))
        for position in reachable
    }

    dead_end_count = sum(
        count <= 1
        for position, count in reachable_neighbor_counts.items()
        if position != player
    )

    chokepoint_count = len(_articulation_points(reachable))

    extra_symbols = tuple(
        sorted(
            {
                cell
                for row in grid
                for cell in row
                if cell not in {".", "W", "A", "E"}
            }
        )
    )

    structurally_valid = (
        len(players) == 1
        and len(enemies) >= 1
        and enemy_attackability_valid
        and len(reachable) >= max(4, floor_count // 3)
    )

    return MapAnalysis(
        width=width,
        height=height,
        player_count=len(players),
        enemy_count=len(enemies),
        wall_count=len(wall_positions),
        interior_wall_count=len(interior_wall_positions),
        interior_wall_density=(
            len(interior_wall_positions) / interior_cell_count
            if interior_cell_count
            else 0.0
        ),
        total_wall_ratio=len(wall_positions) / (width * height),
        floor_count=floor_count,
        reachable_floor_count=len(reachable),
        reachable_floor_fraction=len(reachable) / floor_count if floor_count else 0.0,
        enemy_attackability_valid=enemy_attackability_valid,
        structurally_valid=structurally_valid,
        dead_end_count=dead_end_count,
        chokepoint_count=chokepoint_count,
        min_enemy_attack_distance=(
            min(enemy_attack_distances) if enemy_attack_distances else None
        ),
        avg_enemy_attack_distance=(
            sum(enemy_attack_distances) / len(enemy_attack_distances)
            if enemy_attack_distances
            else None
        ),
        max_enemy_attack_distance=(
            max(enemy_attack_distances) if enemy_attack_distances else None
        ),
        extra_symbols=extra_symbols,
    )


def format_analysis(analysis: MapAnalysis) -> str:
    """Format map metrics for manual terminal inspection."""

    def fmt_optional_int(value: int | None) -> str:
        return "n/a" if value is None else str(value)

    def fmt_optional_float(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.2f}"

    return "\n".join(
        [
            f"dimensions: {analysis.width}x{analysis.height}",
            f"structurally valid: {analysis.structurally_valid}",
            f"players: {analysis.player_count}",
            f"enemies: {analysis.enemy_count}",
            f"walls total: {analysis.wall_count}",
            f"interior walls: {analysis.interior_wall_count}",
            f"interior wall density: {analysis.interior_wall_density:.2%}",
            f"total wall ratio: {analysis.total_wall_ratio:.2%}",
            f"floor tiles: {analysis.floor_count}",
            f"reachable floor tiles: {analysis.reachable_floor_count}",
            f"reachable floor fraction: {analysis.reachable_floor_fraction:.2%}",
            f"enemy attackability valid: {analysis.enemy_attackability_valid}",
            f"dead ends: {analysis.dead_end_count}",
            f"chokepoints: {analysis.chokepoint_count}",
            f"min enemy attack distance: {fmt_optional_int(analysis.min_enemy_attack_distance)}",
            f"avg enemy attack distance: {fmt_optional_float(analysis.avg_enemy_attack_distance)}",
            f"max enemy attack distance: {fmt_optional_int(analysis.max_enemy_attack_distance)}",
            f"extra symbols: {', '.join(analysis.extra_symbols) if analysis.extra_symbols else 'none'}",
        ]
    )


def generate_level(
    width: int = 9,
    height: int = 7,
    enemy_count: int = 2,
    obstacle_density: float = 0.18,
    seed: int | None = None,
    max_attempts: int = 200,
) -> GeneratedLevel:
    if width < 7 or height < 7:
        raise ValueError("Use at least a 7x7 grid so the map has enough room.")
    if enemy_count < 1:
        raise ValueError("enemy_count must be at least 1.")
    if not 0.0 <= obstacle_density <= 0.35:
        raise ValueError("obstacle_density must be between 0.0 and 0.35.")

    rng = random.Random(seed)
    interior = [(x, y) for y in range(1, height - 1) for x in range(1, width - 1)]

    for _attempt in range(max_attempts):
        grid = [["." for _x in range(width)] for _y in range(height)]

        for x in range(width):
            grid[0][x] = "W"
            grid[height - 1][x] = "W"
        for y in range(height):
            grid[y][0] = "W"
            grid[y][width - 1] = "W"

        player = rng.choice(interior)

        shuffled = interior[:]
        rng.shuffle(shuffled)

        enemies: list[tuple[int, int]] = []
        for candidate in shuffled:
            if candidate == player or _manhattan(candidate, player) < 3:
                continue
            if any(_manhattan(candidate, existing) < 2 for existing in enemies):
                continue

            enemies.append(candidate)

            if len(enemies) == enemy_count:
                break

        if len(enemies) != enemy_count:
            continue

        reserved = {player, *enemies}
        obstacle_count = 0

        for x, y in interior:
            if (x, y) in reserved:
                continue
            if rng.random() < obstacle_density:
                grid[y][x] = "W"
                obstacle_count += 1

        if not _is_playable(grid, player, enemies):
            continue

        px, py = player
        grid[py][px] = "A"

        for ex, ey in enemies:
            grid[ey][ex] = "E"

        return GeneratedLevel(
            layout=_grid_to_string(grid),
            width=width,
            height=height,
            enemy_count=enemy_count,
            obstacle_count=obstacle_count,
            obstacle_density=obstacle_density,
            seed=seed,
        )

    raise RuntimeError("Failed to generate a playable level with the given parameters.")


def generate_preset_level(
    size: MapSize = "small",
    map_type: MapType = "baseline",
    seed: int | None = None,
    max_attempts: int = 200,
) -> GeneratedLevel:
    """Generate a map using a named size and generator type.

    The baseline generator itself is left unchanged. This function only chooses
    fixed dimensions and hidden baseline parameters for each size category.
    """

    if size not in MAP_SIZES:
        raise ValueError(f"Unknown map size: {size}")
    if map_type not in MAP_TYPES:
        raise ValueError(f"Unknown map type: {map_type}")

    if map_type == "baseline":
        width, height = MAP_SIZES[size]
        preset = BASELINE_PRESETS[size]
        return generate_level(
            width=width,
            height=height,
            enemy_count=preset.enemy_count,
            obstacle_density=preset.obstacle_density,
            seed=seed,
            max_attempts=max_attempts,
        )

    raise ValueError(f"Unsupported map type: {map_type}")