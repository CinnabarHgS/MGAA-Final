from __future__ import annotations

import random
import textwrap
from collections import deque
from dataclasses import dataclass
from typing import Literal

from .combat import DEFAULT_COMBAT_RULES, ITEM_MAP_CHARS, TERRAIN_MAP_CHARS, positions_that_can_attack_target

# DEFAULT_LEVEL = textwrap.dedent(
#     """
#     WWWWWWWWW
#     W..E....W
#     W.W.WW..W
#     W.H.A..SW
#     W..WW.W.W
#     W.B..E..W
#     WWWWWWWWW
#     """
# ).strip()



MapSize = Literal["tiny", "small", "medium", "large", "giant"]
MapType = Literal["baseline", "random_walk", "arena"]

MAP_SIZES: dict[MapSize, tuple[int, int]] = {
    "tiny": (9, 7),
    "small": (13, 11),
    "medium": (17, 13),
    "large": (19, 17),
    "giant": (25, 21),
}

MAP_TYPES: tuple[MapType, ...] = ("baseline", "random_walk", "arena")


@dataclass(frozen=True)
class GenerationPreset:
    enemy_count: int
    obstacle_density: float


@dataclass(frozen=True)
class RandomWalkPreset:
    enemy_count: int
    floor_fraction: float
    branch_chance: float = 0.15


@dataclass(frozen=True)
class ArenaPreset:
    enemy_count: int
    obstacle_density: float


BASELINE_PRESETS: dict[MapSize, GenerationPreset] = {
    "tiny": GenerationPreset(enemy_count=1, obstacle_density=0.10),
    "small": GenerationPreset(enemy_count=2, obstacle_density=0.18),
    "medium": GenerationPreset(enemy_count=3, obstacle_density=0.20),
    "large": GenerationPreset(enemy_count=5, obstacle_density=0.22),
    "giant": GenerationPreset(enemy_count=7, obstacle_density=0.24),
}

RANDOM_WALK_PRESETS: dict[MapSize, RandomWalkPreset] = {
    "tiny": RandomWalkPreset(enemy_count=1, floor_fraction=0.34, branch_chance=0.20),
    "small": RandomWalkPreset(enemy_count=2, floor_fraction=0.36, branch_chance=0.18),
    "medium": RandomWalkPreset(enemy_count=3, floor_fraction=0.38, branch_chance=0.16),
    "large": RandomWalkPreset(enemy_count=5, floor_fraction=0.40, branch_chance=0.14),
    "giant": RandomWalkPreset(enemy_count=8, floor_fraction=0.42, branch_chance=0.12),
}

ARENA_PRESETS: dict[MapSize, ArenaPreset] = {
    "tiny": ArenaPreset(enemy_count=1, obstacle_density=0.1),
    "small": ArenaPreset(enemy_count=2, obstacle_density=0.12),
    "medium": ArenaPreset(enemy_count=4, obstacle_density=0.14),
    "large": ArenaPreset(enemy_count=6, obstacle_density=0.14),
    "giant": ArenaPreset(enemy_count=8, obstacle_density=0.14),
}

DEFAULT_LEVEL = textwrap.dedent(
    """
    WWWWWWWWWWWWW
    W...H..E....W
    W.W.WW..B...W
    W..KA..E....W
    W..WW.W.H...W
    W.S..E...D..W
    W....G...V..W
    WWWWWWWWWWWWW
"""
).strip()


_TERRAIN_CHARS = set(TERRAIN_MAP_CHARS)
_ITEM_CHARS = set(ITEM_MAP_CHARS)
_SPECIAL_CHARS = _TERRAIN_CHARS | _ITEM_CHARS


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


def _interior_positions(width: int, height: int) -> list[tuple[int, int]]:
    return [(x, y) for y in range(1, height - 1) for x in range(1, width - 1)]


def _make_wall_grid(width: int, height: int, interior_fill: str = ".") -> list[list[str]]:
    grid = [[interior_fill for _x in range(width)] for _y in range(height)]

    for x in range(width):
        grid[0][x] = "W"
        grid[height - 1][x] = "W"
    for y in range(height):
        grid[y][0] = "W"
        grid[y][width - 1] = "W"

    return grid


def _count_interior_walls(grid: list[list[str]]) -> int:
    width = len(grid[0])
    height = len(grid)

    return sum(
        1
        for y in range(1, height - 1)
        for x in range(1, width - 1)
        if grid[y][x] == "W"
    )


def _stamp_actors(
    grid: list[list[str]],
    player: tuple[int, int],
    enemies: list[tuple[int, int]],
) -> list[list[str]]:
    actor_grid = [row[:] for row in grid]

    px, py = player
    actor_grid[py][px] = "A"

    for ex, ey in enemies:
        actor_grid[ey][ex] = "E"

    return actor_grid


def _place_actors_on_floor(
    grid: list[list[str]],
    rng: random.Random,
    enemy_count: int,
    preferred_player: tuple[int, int] | None = None,
    prefer_far_enemies: bool = True,
    min_enemy_distance: int = 3,
    min_enemy_spacing: int = 2,
) -> tuple[tuple[int, int], list[tuple[int, int]]] | None:
    floor_positions = [
        (x, y)
        for y, row in enumerate(grid)
        for x, cell in enumerate(row)
        if cell != "W"
    ]

    if not floor_positions:
        return None

    if preferred_player is not None and preferred_player in floor_positions:
        player_candidates = [preferred_player]
    else:
        player_candidates = floor_positions[:]
        rng.shuffle(player_candidates)

    for player in player_candidates[:80]:
        distances = _distances_from(grid, player, blocked_positions=set())

        enemy_candidates = [
            position
            for position, distance in distances.items()
            if position != player and distance >= min_enemy_distance
        ]

        rng.shuffle(enemy_candidates)

        if prefer_far_enemies:
            enemy_candidates.sort(
                key=lambda position: distances[position],
                reverse=True,
            )

        enemies: list[tuple[int, int]] = []

        for candidate in enemy_candidates:
            if any(
                _manhattan(candidate, existing) < min_enemy_spacing
                for existing in enemies
            ):
                continue

            enemies.append(candidate)

            if len(enemies) == enemy_count:
                return player, enemies

    return None


def _finalize_generated_candidate(
    grid: list[list[str]],
    rng: random.Random,
    enemy_count: int,
    obstacle_density: float,
    seed: int | None,
    preferred_player: tuple[int, int] | None = None,
    prefer_far_enemies: bool = True,
    item_level: str = "default",
) -> GeneratedLevel | None:
    placement = _place_actors_on_floor(
        grid=grid,
        rng=rng,
        enemy_count=enemy_count,
        preferred_player=preferred_player,
        prefer_far_enemies=prefer_far_enemies,
    )

    if placement is None:
        return None

    player, enemies = placement

    if not _is_playable(grid, player, enemies):
        return None

    actor_grid = _stamp_actors(grid, player, enemies)
    _place_terrain_and_items(actor_grid, rng, item_level=item_level)

    return GeneratedLevel(
        layout=_grid_to_string(actor_grid),
        width=len(grid[0]),
        height=len(grid),
        enemy_count=enemy_count,
        obstacle_count=_count_interior_walls(grid),
        obstacle_density=obstacle_density,
        seed=seed,
    )



ITEM_LEVELS = ("none", "default", "double")


def _pools_for_item_level(item_level: str) -> tuple[list[str], list[str], bool]:
    """Return (terrain_pool, item_pool, allow_golden_gun) for a given level name."""
    if item_level == "none":
        return [], [], False
    if item_level == "default":
        return list("HHBBK"), ["D", "V", "S"], True
    if item_level == "double":
        return list("HHHHBBBBKK"), ["D", "D", "V", "V", "S", "S"], True
    raise ValueError(f"Unknown item_level: {item_level!r}. Choose from {ITEM_LEVELS}.")


def _place_terrain_and_items(
    grid: list[list[str]],
    rng: random.Random,
    item_level: str = "default",
) -> None:
    """Scatter terrain tiles and items onto free floor cells in-place."""
    height = len(grid)
    width = len(grid[0]) if height else 0
    free = [
        (x, y)
        for y in range(1, height - 1)
        for x in range(1, width - 1)
        if grid[y][x] == "."
    ]
    rng.shuffle(free)

    terrain_pool, item_pool, allow_golden_gun = _pools_for_item_level(item_level)

    for i, (tx, ty) in enumerate(free[: len(terrain_pool)]):
        grid[ty][tx] = terrain_pool[i]

    offset = len(terrain_pool)
    for i, (ix, iy) in enumerate(free[offset : offset + len(item_pool)]):
        grid[iy][ix] = item_pool[i]

    if allow_golden_gun and rng.random() < 1 / (width * height):
        remaining = [pos for pos in free[offset + len(item_pool) :]]
        if remaining:
            gx, gy = rng.choice(remaining)
            grid[gy][gx] = "G"


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
    item_level: str = "default",
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

        _place_terrain_and_items(grid, rng, item_level=item_level)

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


def generate_random_walk_level(
    width: int = 9,
    height: int = 7,
    enemy_count: int = 2,
    floor_fraction: float = 0.40,
    branch_chance: float = 0.15,
    seed: int | None = None,
    max_attempts: int = 200,
    item_level: str = "default",
) -> GeneratedLevel:
    """Generate a cave-like tunnel system with occasional open chambers.

    The generator alternates between two behaviours:

    1. Tunnel carving:
       A constrained random walk carves mostly one-tile-wide corridors.
       It avoids carving next to existing floor tiles, which prevents the
       walk from turning into one large blob.

    2. Chamber carving:
       At intervals, the current tunnel endpoint is expanded into a small
       rough chamber. The walk may then continue from the chamber edge.

    The result should look more like connected caves: corridors, pockets,
    branches, dead ends, and chokepoints.
    """

    if width < 7 or height < 7:
        raise ValueError("Use at least a 7x7 grid so the map has enough room.")
    if enemy_count < 1:
        raise ValueError("enemy_count must be at least 1.")
    if not 0.20 <= floor_fraction <= 0.70:
        raise ValueError("floor_fraction must be between 0.20 and 0.70.")
    if not 0.0 <= branch_chance <= 1.0:
        raise ValueError("branch_chance must be between 0.0 and 1.0.")

    rng = random.Random(seed)
    interior = _interior_positions(width, height)

    target_floor_count = max(
        enemy_count * 6 + 10,
        round(len(interior) * floor_fraction),
    )
    target_floor_count = min(target_floor_count, len(interior))

    directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]

    turn_chance = 0.30
    loop_chance = 0.025
    chamber_chance = 0.45

    min_tunnel_length = 3
    max_tunnel_length = max(5, min(width, height) // 2)

    min_chamber_gap = 5
    max_chamber_gap = max(8, min(width, height))

    max_chamber_radius = 1
    if min(width, height) >= 11:
        max_chamber_radius = 2
    if min(width, height) >= 17:
        max_chamber_radius = 3

    def add_direction(
        position: tuple[int, int],
        direction: tuple[int, int],
    ) -> tuple[int, int]:
        return position[0] + direction[0], position[1] + direction[1]

    def is_interior(position: tuple[int, int]) -> bool:
        x, y = position
        return 0 < x < width - 1 and 0 < y < height - 1

    def carved_neighbor_count(
        position: tuple[int, int],
        carved: set[tuple[int, int]],
        ignored: set[tuple[int, int]] | None = None,
    ) -> int:
        ignored = ignored or set()
        return sum(
            neighbor in carved
            for neighbor in _neighbors(position)
            if neighbor not in ignored
        )

    def carve(
        grid: list[list[str]],
        carved: set[tuple[int, int]],
        position: tuple[int, int],
    ) -> None:
        x, y = position
        grid[y][x] = "."
        carved.add(position)

    def choose_start(
        carved: set[tuple[int, int]],
    ) -> tuple[int, int]:
        """Choose where the next tunnel starts.

        Usually starts from a tunnel endpoint. Sometimes starts from the middle
        of an existing tunnel or chamber edge to create side branches.
        """

        endpoints = [
            position
            for position in carved
            if carved_neighbor_count(position, carved) <= 1
        ]

        frontier = [
            position
            for position in carved
            if any(
                is_interior(neighbor) and neighbor not in carved
                for neighbor in _neighbors(position)
            )
        ]

        if rng.random() < branch_chance and frontier:
            return rng.choice(frontier)

        if endpoints:
            return rng.choice(endpoints)

        return rng.choice(tuple(carved))

    def valid_step_directions(
        current: tuple[int, int],
        carved: set[tuple[int, int]],
        max_adjacent_carved: int,
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
        """Return preferred and fallback directions.

        For normal tunnel carving, max_adjacent_carved is 0. This means the
        next tile may only touch the current tile, not other carved tiles.

        When exiting a chamber, max_adjacent_carved is temporarily higher so
        the tunnel can escape from the open room.
        """

        preferred: list[tuple[int, int]] = []
        fallback: list[tuple[int, int]] = []

        for direction in directions:
            candidate = add_direction(current, direction)

            if not is_interior(candidate):
                continue
            if candidate in carved:
                continue

            adjacent_carved = carved_neighbor_count(
                candidate,
                carved,
                ignored={current},
            )

            if adjacent_carved <= max_adjacent_carved:
                preferred.append(direction)
            elif adjacent_carved == max_adjacent_carved + 1 and rng.random() < loop_chance:
                fallback.append(direction)

        return preferred, fallback

    def choose_direction(
        current_direction: tuple[int, int],
        options: list[tuple[int, int]],
    ) -> tuple[int, int]:
        """Prefer continuing straight, but allow turns."""

        if current_direction in options and rng.random() > turn_chance:
            return current_direction

        return rng.choice(options)

    def rough_chamber_cells(
        center: tuple[int, int],
        radius_x: int,
        radius_y: int,
    ) -> set[tuple[int, int]]:
        """Return a small rough ellipse-like chamber."""

        cx, cy = center
        cells: set[tuple[int, int]] = set()

        for dy in range(-radius_y, radius_y + 1):
            for dx in range(-radius_x, radius_x + 1):
                position = (cx + dx, cy + dy)

                if not is_interior(position):
                    continue

                # Ellipse-ish shape with slight roughness.
                normalized = (dx / max(1, radius_x)) ** 2 + (dy / max(1, radius_y)) ** 2

                if normalized <= 1.0:
                    cells.add(position)
                elif normalized <= 1.45 and rng.random() < 0.35:
                    cells.add(position)

        return cells

    def chamber_exit_candidates(
        cells: set[tuple[int, int]],
        carved: set[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        return [
            cell
            for cell in cells
            if any(
                is_interior(neighbor) and neighbor not in carved
                for neighbor in _neighbors(cell)
            )
        ]

    def try_carve_chamber(
        grid: list[list[str]],
        carved: set[tuple[int, int]],
        center: tuple[int, int],
    ) -> list[tuple[int, int]]:
        """Try to carve a small chamber and return possible exit cells."""

        if len(carved) >= target_floor_count:
            return []

        radius_x = rng.randint(1, max_chamber_radius)
        radius_y = rng.randint(1, max_chamber_radius)

        # Avoid too many perfectly square rooms.
        if rng.random() < 0.50:
            radius_x = max(1, radius_x - 1)
        if rng.random() < 0.50:
            radius_y = max(1, radius_y - 1)

        cells = rough_chamber_cells(center, radius_x, radius_y)

        if not cells:
            return []

        already_carved = sum(cell in carved for cell in cells)

        # Avoid merging a chamber into a large existing open area.
        # Some overlap is fine because the chamber is attached to a tunnel.
        if already_carved > max(2, len(cells) // 3):
            return []

        new_cells = [cell for cell in cells if cell not in carved]

        # Avoid huge overshoot of the requested floor budget.
        if len(carved) + len(new_cells) > target_floor_count + max(4, len(cells) // 2):
            return []

        for cell in cells:
            carve(grid, carved, cell)

        return chamber_exit_candidates(cells, carved)

    center = (width // 2, height // 2)
    center_candidates = [
        position
        for position in interior
        if _manhattan(position, center) <= 2
    ] or interior

    for _attempt in range(max_attempts):
        grid = _make_wall_grid(width, height, interior_fill="W")

        start = rng.choice(center_candidates)
        carved: set[tuple[int, int]] = set()
        carve(grid, carved, start)

        current = start
        current_direction = rng.choice(directions)

        tiles_until_next_chamber = rng.randint(min_chamber_gap, max_chamber_gap)
        tunnel_budget = target_floor_count * 16

        for _tunnel_index in range(tunnel_budget):
            if len(carved) >= target_floor_count:
                break

            # Continue from the current tunnel/chamber edge most of the time.
            # Occasionally branch elsewhere.
            if rng.random() < branch_chance:
                current = choose_start(carved)
                current_direction = rng.choice(directions)

            tunnel_length = rng.randint(min_tunnel_length, max_tunnel_length)

            for _step_index in range(tunnel_length):
                if len(carved) >= target_floor_count:
                    break

                # If current is in an open chamber, allow the first step out to
                # touch more carved cells. Otherwise keep corridors narrow.
                current_neighbor_count = carved_neighbor_count(current, carved)
                max_adjacent_carved = 2 if current_neighbor_count >= 3 else 0

                preferred, fallback = valid_step_directions(
                    current=current,
                    carved=carved,
                    max_adjacent_carved=max_adjacent_carved,
                )
                options = preferred or fallback

                if not options:
                    break

                current_direction = choose_direction(current_direction, options)
                current = add_direction(current, current_direction)

                carve(grid, carved, current)
                tiles_until_next_chamber -= 1

                if (
                    tiles_until_next_chamber <= 0
                    and rng.random() < chamber_chance
                    and len(carved) < target_floor_count
                ):
                    exits = try_carve_chamber(grid, carved, current)

                    if exits:
                        current = rng.choice(exits)
                        current_direction = rng.choice(directions)

                    tiles_until_next_chamber = rng.randint(
                        min_chamber_gap,
                        max_chamber_gap,
                    )

        if len(carved) < max(enemy_count * 6 + 10, target_floor_count * 0.80):
            continue

        result = _finalize_generated_candidate(
            grid=grid,
            rng=rng,
            enemy_count=enemy_count,
            obstacle_density=1.0 - floor_fraction,
            seed=seed,
            preferred_player=None,
            prefer_far_enemies=True,
            item_level=item_level,
        )

        if result is not None:
            return result

    raise RuntimeError("Failed to generate a playable random-walk level.")


def _mirrored_positions(
    position: tuple[int, int],
    width: int,
    height: int,
) -> set[tuple[int, int]]:
    x, y = position

    return {
        (x, y),
        (width - 1 - x, y),
        (x, height - 1 - y),
        (width - 1 - x, height - 1 - y),
    }


def generate_arena_level(
    width: int = 9,
    height: int = 7,
    enemy_count: int = 2,
    obstacle_density: float = 0.10,
    seed: int | None = None,
    max_attempts: int = 200,
    item_level: str = "default",
) -> GeneratedLevel:
    """Generate an open combat arena with sparse mirrored pillar obstacles."""

    if width < 7 or height < 7:
        raise ValueError("Use at least a 7x7 grid so the map has enough room.")
    if enemy_count < 1:
        raise ValueError("enemy_count must be at least 1.")
    if not 0.0 <= obstacle_density <= 0.25:
        raise ValueError("obstacle_density must be between 0.0 and 0.25.")

    rng = random.Random(seed)
    interior = _interior_positions(width, height)
    target_obstacle_count = round(len(interior) * obstacle_density)

    player_position = (width // 2, height // 2)

    protected_positions = {
        position
        for position in interior
        if _manhattan(position, player_position) <= 1
    }

    for _attempt in range(max_attempts):
        grid = _make_wall_grid(width, height, interior_fill=".")
        obstacle_positions: set[tuple[int, int]] = set()

        placement_budget = max(30, target_obstacle_count * 12)

        for _ in range(placement_budget):
            if len(obstacle_positions) >= target_obstacle_count:
                break

            candidate = rng.choice(interior)
            group = _mirrored_positions(candidate, width, height)

            if any(position in protected_positions for position in group):
                continue
            if any(position in obstacle_positions for position in group):
                continue

            # Allow the first mirrored group even if it slightly overshoots.
            # After that, avoid overshooting too much.
            if len(obstacle_positions) + len(group) > target_obstacle_count + 3:
                if obstacle_positions:
                    continue

            obstacle_positions.update(group)

        for x, y in obstacle_positions:
            grid[y][x] = "W"

        result = _finalize_generated_candidate(
            grid=grid,
            rng=rng,
            enemy_count=enemy_count,
            obstacle_density=obstacle_density,
            seed=seed,
            preferred_player=player_position,
            prefer_far_enemies=True,
            item_level=item_level,
        )

        if result is not None:
            return result

    raise RuntimeError("Failed to generate a playable arena level.")


WALL_DENSITY_LEVELS = ("low", "default", "high")
_WALL_DENSITY_MULTIPLIER = {"low": 0.5, "default": 1.0, "high": 1.5}

ENEMY_COUNT_LEVELS = ("low", "default", "high")
_ENEMY_COUNT_DELTA = {"low": -1, "default": 0, "high": +2}


def _resolve_enemy_count(preset_count: int, enemy_count: "int | str | None") -> int:
    if enemy_count is None or enemy_count == "default":
        return preset_count
    if isinstance(enemy_count, str):
        if enemy_count not in _ENEMY_COUNT_DELTA:
            raise ValueError(
                f"enemy_count must be int, None, or one of {ENEMY_COUNT_LEVELS}, got {enemy_count!r}"
            )
        return max(1, preset_count + _ENEMY_COUNT_DELTA[enemy_count])
    return max(1, int(enemy_count))


def _resolve_wall_multiplier(wall_density: str) -> float:
    if wall_density not in _WALL_DENSITY_MULTIPLIER:
        raise ValueError(
            f"wall_density must be one of {WALL_DENSITY_LEVELS}, got {wall_density!r}"
        )
    return _WALL_DENSITY_MULTIPLIER[wall_density]


def generate_preset_level(
    size: MapSize = "small",
    map_type: MapType = "baseline",
    seed: int | None = None,
    max_attempts: int = 200,
    item_level: str = "default",
    enemy_count: "int | str | None" = None,
    wall_density: str = "default",
) -> GeneratedLevel:
    """Generate a map using a named size and generator type."""

    if size not in MAP_SIZES:
        raise ValueError(f"Unknown map size: {size}")
    if map_type not in MAP_TYPES:
        raise ValueError(f"Unknown map type: {map_type}")

    width, height = MAP_SIZES[size]
    wall_mult = _resolve_wall_multiplier(wall_density)

    if map_type == "baseline":
        preset = BASELINE_PRESETS[size]
        scaled_density = min(0.35, max(0.0, preset.obstacle_density * wall_mult))

        return generate_level(
            width=width,
            height=height,
            enemy_count=_resolve_enemy_count(preset.enemy_count, enemy_count),
            obstacle_density=scaled_density,
            seed=seed,
            max_attempts=max_attempts,
            item_level=item_level,
        )

    if map_type == "random_walk":
        preset = RANDOM_WALK_PRESETS[size]
        # floor_fraction is inversely related to wall density: more walls = lower floor.
        # Apply the multiplier to (1 - floor_fraction), then invert back.
        wall_share = (1.0 - preset.floor_fraction) * wall_mult
        scaled_floor = min(0.70, max(0.20, 1.0 - wall_share))

        return generate_random_walk_level(
            width=width,
            height=height,
            enemy_count=_resolve_enemy_count(preset.enemy_count, enemy_count),
            floor_fraction=scaled_floor,
            branch_chance=preset.branch_chance,
            seed=seed,
            max_attempts=max_attempts,
            item_level=item_level,
        )

    if map_type == "arena":
        preset = ARENA_PRESETS[size]
        scaled_density = min(0.25, max(0.0, preset.obstacle_density * wall_mult))

        return generate_arena_level(
            width=width,
            height=height,
            enemy_count=_resolve_enemy_count(preset.enemy_count, enemy_count),
            obstacle_density=scaled_density,
            seed=seed,
            max_attempts=max_attempts,
            item_level=item_level,
        )

    raise ValueError(f"Unsupported map type: {map_type}")
