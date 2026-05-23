from __future__ import annotations

import dataclasses
from collections import deque

from .combat import (
    DIRECTION_TO_DELTA,
    find_attack_direction,
    get_unit_profile,
)
from .state import BattleSnapshot, TurnAction, UnitState, action_to_delta


# forward model used by MCTS for rollouts. covers the basics: player move,
# player attack(s), and an enemy phase where each enemy bfs-chases the
# player and attacks if adjacent. terrain bonuses and item effects are not
# modelled in detail, the new snapshot fields (hills, bushes, bunkers,
# inventory, active_effects) are just carried through unchanged.
_ATTACK_TYPES = {"attack", "ranged_attack"}


def simulate_turn(snapshot: BattleSnapshot, turn: TurnAction) -> BattleSnapshot:
    width = snapshot.width
    height = snapshot.height
    walls = snapshot.walls

    if snapshot.player is None or not snapshot.enemies:
        return snapshot

    player_position = snapshot.player.position
    player_health = snapshot.player.health
    enemy_positions = {enemy.position: enemy.health for enemy in snapshot.enemies}

    on_bunker = player_position in snapshot.bunkers

    # player move (skipped on bunker, matches the real env in game.py)
    if not on_bunker and turn.move_direction is not None:
        dx, dy = action_to_delta(turn.move_direction)
        target = (player_position[0] + dx, player_position[1] + dy)
        if (
            0 <= target[0] < width
            and 0 <= target[1] < height
            and target not in walls
            and target not in enemy_positions
        ):
            player_position = target

    # primary attack
    if turn.action is not None and turn.action.action_type in _ATTACK_TYPES and turn.action.direction is not None:
        _apply_player_attack(snapshot, turn.action.direction, player_position, walls, enemy_positions)

    # second attack (used with dual_berettas in the real env). we apply the
    # damage but dont check the prerequisite effect.
    if turn.action2 is not None and turn.action2.action_type in _ATTACK_TYPES and turn.action2.direction is not None:
        _apply_player_attack(snapshot, turn.action2.direction, player_position, walls, enemy_positions)

    # enemy phase
    enemy_order = sorted(enemy_positions.keys())
    for original_position in enemy_order:
        if original_position not in enemy_positions:
            continue
        if player_position is None:
            break

        enemy_profile = get_unit_profile(snapshot, "enemy", original_position)
        next_step = _next_step_toward(
            start=original_position,
            goal=player_position,
            walls=walls,
            other_enemies=set(enemy_positions.keys()) - {original_position},
            width=width,
            height=height,
        )
        if next_step is None:
            continue

        if next_step == player_position:
            if not on_bunker:
                player_health -= enemy_profile.attack_damage
                if player_health <= 0:
                    player_position = None
                    player_health = 0
            continue

        enemy_health = enemy_positions.pop(original_position)
        enemy_positions[next_step] = enemy_health

    enemies = tuple(
        sorted(
            (UnitState(position=pos, health=hp) for pos, hp in enemy_positions.items()),
            key=lambda unit: unit.position,
        )
    )
    player = UnitState(position=player_position, health=player_health) if player_position is not None else None

    return dataclasses.replace(
        snapshot,
        game_ticks=snapshot.game_ticks + 1,
        player_turns=snapshot.player_turns + 1,
        player=player,
        enemies=enemies,
    )


def _apply_player_attack(
    snapshot: BattleSnapshot,
    direction: int,
    player_position: tuple[int, int],
    walls: frozenset[tuple[int, int]],
    enemy_positions: dict[tuple[int, int], int],
) -> None:
    player_profile = get_unit_profile(snapshot, "player", player_position)
    for enemy_position in list(enemy_positions.keys()):
        hit_direction = find_attack_direction(
            player_position,
            enemy_position,
            player_profile.attack_range,
            blocking_positions=walls | (set(enemy_positions.keys()) - {enemy_position}),
        )
        if hit_direction == direction:
            enemy_health = enemy_positions[enemy_position] - player_profile.attack_damage
            if enemy_health <= 0:
                del enemy_positions[enemy_position]
            else:
                enemy_positions[enemy_position] = enemy_health
            return


def _next_step_toward(
    start: tuple[int, int],
    goal: tuple[int, int],
    walls: frozenset[tuple[int, int]],
    other_enemies: set[tuple[int, int]],
    width: int,
    height: int,
) -> tuple[int, int] | None:
    if start == goal:
        return start

    queue: deque[tuple[int, int]] = deque([start])
    parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    while queue:
        current = queue.popleft()
        if current == goal:
            return _first_step(parents, current)
        for _direction, (dx, dy) in DIRECTION_TO_DELTA.items():
            neighbor = (current[0] + dx, current[1] + dy)
            if not (0 <= neighbor[0] < width and 0 <= neighbor[1] < height):
                continue
            if neighbor in parents:
                continue
            if neighbor in walls:
                continue
            if neighbor != goal and neighbor in other_enemies:
                continue
            parents[neighbor] = current
            if neighbor == goal:
                return _first_step(parents, neighbor)
            queue.append(neighbor)

    return None


def _first_step(
    parents: dict[tuple[int, int], tuple[int, int] | None],
    goal: tuple[int, int],
) -> tuple[int, int]:
    current = goal
    while parents[current] is not None and parents[parents[current]] is not None:
        current = parents[current]
    return current
