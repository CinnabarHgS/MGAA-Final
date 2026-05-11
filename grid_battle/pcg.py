from __future__ import annotations

import random
import textwrap
from collections import deque
from dataclasses import dataclass

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


def _neighbors(position: tuple[int, int]) -> list[tuple[int, int]]:
    x, y = position
    return [(x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)]


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _grid_to_string(grid: list[list[str]]) -> str:
    return "\n".join("".join(row) for row in grid)


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

        free = [(x, y) for x, y in interior if grid[y][x] == "."]
        rng.shuffle(free)

        terrain_pool = list("HHB BK".replace(" ", ""))
        for i, (tx, ty) in enumerate(free[: len(terrain_pool)]):
            grid[ty][tx] = terrain_pool[i]

        item_pool = ["D", "V", "S"]
        for i, (ix, iy) in enumerate(free[len(terrain_pool) : len(terrain_pool) + len(item_pool)]):
            grid[iy][ix] = item_pool[i]

        if rng.random() < 1 / (width * height):
            remaining = [(x, y) for x, y in interior if grid[y][x] == "."]
            if remaining:
                gx, gy = rng.choice(remaining)
                grid[gy][gx] = "G"

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
