from __future__ import annotations

from collections import deque

from .game import ATTACK_ACTION, MOVE_ACTION, BattleSnapshot, delta_to_action_id, positions_around


class HeuristicAgent:
    def act(self, snapshot: BattleSnapshot) -> tuple[int, int]:
        if snapshot.player is None:
            return MOVE_ACTION, 1
        if not snapshot.enemies:
            return MOVE_ACTION, 1

        player_position = snapshot.player.position
        enemy_positions = {enemy.position for enemy in snapshot.enemies}

        for enemy in snapshot.enemies:
            dx = enemy.position[0] - player_position[0]
            dy = enemy.position[1] - player_position[1]
            if abs(dx) + abs(dy) == 1:
                return ATTACK_ACTION, delta_to_action_id((dx, dy))

        blocked = set(snapshot.walls) | enemy_positions
        targets = {
            target
            for enemy in snapshot.enemies
            for target in positions_around(enemy.position)
            if 0 <= target[0] < snapshot.width
            and 0 <= target[1] < snapshot.height
            and target not in blocked
        }

        path = _shortest_path(
            start=player_position,
            goals=targets,
            blocked=blocked,
            width=snapshot.width,
            height=snapshot.height,
        )

        if path and len(path) > 1:
            next_position = path[1]
            dx = next_position[0] - player_position[0]
            dy = next_position[1] - player_position[1]
            return MOVE_ACTION, delta_to_action_id((dx, dy))

        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            candidate = (player_position[0] + dx, player_position[1] + dy)
            if candidate in blocked:
                continue
            if not (0 <= candidate[0] < snapshot.width and 0 <= candidate[1] < snapshot.height):
                continue
            return MOVE_ACTION, delta_to_action_id((dx, dy))

        return MOVE_ACTION, 1


def _shortest_path(
    start: tuple[int, int],
    goals: set[tuple[int, int]],
    blocked: set[tuple[int, int]],
    width: int,
    height: int,
) -> list[tuple[int, int]] | None:
    if start in goals:
        return [start]

    queue = deque([start])
    parents = {start: None}

    while queue:
        x, y = queue.popleft()
        for neighbor in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if not (0 <= neighbor[0] < width and 0 <= neighbor[1] < height):
                continue
            if neighbor in blocked or neighbor in parents:
                continue
            parents[neighbor] = (x, y)
            if neighbor in goals:
                return _reconstruct_path(parents, neighbor)
            queue.append(neighbor)

    return None


def _reconstruct_path(
    parents: dict[tuple[int, int], tuple[int, int] | None],
    goal: tuple[int, int],
) -> list[tuple[int, int]]:
    path = [goal]
    current = goal
    while parents[current] is not None:
        current = parents[current]
        path.append(current)
    path.reverse()
    return path

