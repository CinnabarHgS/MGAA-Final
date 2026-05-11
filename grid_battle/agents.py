from __future__ import annotations

from collections import deque

from .combat import ITEM_DURATIONS, find_attack_action, get_unit_profile, positions_that_can_attack_target
from .game import BattleSnapshot, PhaseAction, TurnAction, delta_to_action_id


class HeuristicAgent:
    def act(self, snapshot: BattleSnapshot) -> TurnAction:
        if snapshot.player is None:
            return TurnAction()
        if not snapshot.enemies:
            return TurnAction()

        activate_item = _choose_item_to_activate(snapshot)

        player_position = snapshot.player.position
        enemy_positions = {enemy.position for enemy in snapshot.enemies}
        blocking_positions = set(snapshot.walls)
        move_direction = None
        attack_action = None
        player_profile = get_unit_profile(snapshot, "player", player_position)

        for enemy in snapshot.enemies:
            result = find_attack_action(
                player_position,
                enemy.position,
                player_profile.attack_range,
                blocking_positions=blocking_positions | (enemy_positions - {enemy.position}),
            )
            if result is not None:
                attack_action = PhaseAction(result[0], result[1])
                action2 = _find_second_attack(snapshot, player_position, enemy.position, blocking_positions, enemy_positions, player_profile)
                return TurnAction(move_direction=None, action=attack_action, action2=action2, activate_item=activate_item)

        blocked = set(snapshot.walls) | enemy_positions
        targets = {
            target
            for enemy in snapshot.enemies
            for target in positions_that_can_attack_target(
                enemy.position,
                player_profile.attack_range,
                snapshot.width,
                snapshot.height,
                occupied_positions=blocked,
                blocking_positions=blocking_positions | (enemy_positions - {enemy.position}),
            )
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
            move_direction = delta_to_action_id((dx, dy))
            player_position = next_position

        elif move_direction is None:
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                candidate = (player_position[0] + dx, player_position[1] + dy)
                if candidate in blocked:
                    continue
                if not (0 <= candidate[0] < snapshot.width and 0 <= candidate[1] < snapshot.height):
                    continue
                move_direction = delta_to_action_id((dx, dy))
                player_position = candidate
                break

        if move_direction is not None:
            player_profile = get_unit_profile(snapshot, "player", player_position)

        for enemy in snapshot.enemies:
            result = find_attack_action(
                player_position,
                enemy.position,
                player_profile.attack_range,
                blocking_positions=blocking_positions | (enemy_positions - {enemy.position}),
            )
            if result is not None:
                attack_action = PhaseAction(result[0], result[1])
                break

        action2 = None
        if attack_action is not None:
            action2 = _find_second_attack(snapshot, player_position, None, blocking_positions, enemy_positions, player_profile)

        return TurnAction(move_direction=move_direction, action=attack_action, action2=action2, activate_item=activate_item)


def _choose_item_to_activate(snapshot: BattleSnapshot) -> str | None:
    active_names = {e.name for e in snapshot.active_effects}
    for item in snapshot.inventory:
        if item not in active_names and item in ITEM_DURATIONS:
            return item
        if item not in active_names:
            return item
    return None


def _find_second_attack(
    snapshot: BattleSnapshot,
    attacker_pos: tuple[int, int],
    skip_position: tuple[int, int] | None,
    blocking_positions: set[tuple[int, int]],
    enemy_positions: set[tuple[int, int]],
    player_profile,
) -> PhaseAction | None:
    active_names = {e.name for e in snapshot.active_effects}
    if "dual_berettas" not in active_names:
        return None
    for enemy in snapshot.enemies:
        if enemy.position == skip_position:
            continue
        result = find_attack_action(
            attacker_pos,
            enemy.position,
            player_profile.attack_range,
            blocking_positions=blocking_positions | (enemy_positions - {enemy.position}),
        )
        if result is not None:
            return PhaseAction(result[0], result[1])
    return None


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
