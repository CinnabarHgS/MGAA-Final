from __future__ import annotations

import dataclasses
import random
from collections import deque
from typing import Iterable

from .combat import (
    DEFAULT_COMBAT_RULES,
    DIRECTION_TO_DELTA,
    ITEM_DUAL_BERETTAS,
    ITEM_DURATIONS,
    ITEM_GOLDEN_GUN,
    ITEM_SHOTGUN,
    ITEM_VEHICLE,
    ActiveEffect,
    cardinal_relation,
    get_unit_profile,
    has_clear_line,
)
from .state import BattleSnapshot, PhaseAction, TurnAction, UnitState, action_to_delta


_ATTACK_TYPES = {"attack", "ranged_attack"}


def simulate_turn(
    snapshot: BattleSnapshot,
    turn: TurnAction,
    rng: random.Random | None = None,
) -> BattleSnapshot:
    """Forward model used by MCTS.

    This simulates the project-level game mechanics that sit on top of Griddly:
    terrain, item activation, item pickup, active item effects, bunker cover,
    bush dodge, vehicle movement, dual berettas, golden gun, shotgun, and hills.

    It is still a planning model, not a Griddly engine replacement for final
    evaluation. Final experiment outcomes should still be measured by
    GridBattleEnv.
    """

    if rng is None:
        rng = random.Random()

    if snapshot.player is None or not snapshot.enemies:
        return snapshot

    width = snapshot.width
    height = snapshot.height
    walls = snapshot.walls

    player_position = snapshot.player.position
    player_health = snapshot.player.health
    enemy_positions = {enemy.position: enemy.health for enemy in snapshot.enemies}

    bunkers = set(snapshot.bunkers)
    map_items = dict(snapshot.map_items)
    inventory = list(snapshot.inventory)
    active_effects = list(snapshot.active_effects)

    # 1. Activate item before acting, matching GridBattleEnv.step().
    if turn.activate_item is not None and turn.activate_item in inventory:
        inventory.remove(turn.activate_item)
        duration = (
            1
            if turn.activate_item == ITEM_GOLDEN_GUN
            else ITEM_DURATIONS.get(turn.activate_item, 1)
        )
        active_effects.append(ActiveEffect(turn.activate_item, duration))

    active_names = _active_names(active_effects)

    working_snapshot = dataclasses.replace(
        snapshot,
        inventory=tuple(inventory),
        active_effects=tuple(active_effects),
        bunkers=frozenset(bunkers),
        map_items=tuple(sorted(map_items.items())),
    )

    # 2. Player movement. Vehicle can move up to two steps.
    for direction in _effective_move_sequence(turn, active_names):
        dx, dy = action_to_delta(direction)
        target = (player_position[0] + dx, player_position[1] + dy)

        if (
            0 <= target[0] < width
            and 0 <= target[1] < height
            and target not in walls
            and target not in enemy_positions
        ):
            player_position = target

    # 3. Pick up an item on the final player position.
    if player_position in map_items:
        inventory.append(map_items.pop(player_position))

    working_snapshot = dataclasses.replace(
        working_snapshot,
        player=UnitState(player_position, player_health),
        inventory=tuple(inventory),
        active_effects=tuple(active_effects),
        map_items=tuple(sorted(map_items.items())),
    )

    # 4. Player attack sequence.
    attack_sequence = _effective_attack_sequence(turn, working_snapshot)

    for attack in attack_sequence:
        _apply_player_attack(
            snapshot=working_snapshot,
            action=attack,
            player_position=player_position,
            walls=walls,
            enemy_positions=enemy_positions,
        )

        working_snapshot = dataclasses.replace(
            working_snapshot,
            enemies=_enemy_tuple(enemy_positions),
        )

    # 5. Enemy phase.
    enemy_order = sorted(enemy_positions.keys())

    for original_position in enemy_order:
        if original_position not in enemy_positions:
            continue

        if player_position is None:
            break

        enemy_profile = get_unit_profile(working_snapshot, "enemy", original_position)

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
            damage = enemy_profile.attack_damage

            # Bush: 50% chance to dodge incoming damage.
            if player_position in snapshot.bushes and damage > 0:
                if rng.random() < 0.5:
                    damage = 0

            # Bunker: absorb exactly 1 incoming damage once, then collapse.
            if player_position in bunkers and damage > 0:
                damage = max(0, damage - 1)
                bunkers.remove(player_position)

            player_health -= damage

            if player_health <= 0:
                player_position = None
                player_health = 0

            continue

        enemy_health = enemy_positions.pop(original_position)
        enemy_positions[next_step] = enemy_health

    # 6. Active effects tick down after the turn.
    active_effects = [
        ActiveEffect(effect.name, effect.turns_left - 1)
        for effect in active_effects
        if effect.turns_left > 1
    ]

    enemies = _enemy_tuple(enemy_positions)
    player = (
        UnitState(position=player_position, health=player_health)
        if player_position is not None
        else None
    )

    return dataclasses.replace(
        snapshot,
        game_ticks=snapshot.game_ticks + 1,
        player_turns=snapshot.player_turns + 1,
        player=player,
        enemies=enemies,
        bunkers=frozenset(bunkers),
        map_items=tuple(sorted(map_items.items())),
        inventory=tuple(inventory),
        active_effects=tuple(active_effects),
    )


def _active_names(active_effects: Iterable[ActiveEffect]) -> set[str]:
    return {effect.name for effect in active_effects}


def _effective_move_sequence(turn: TurnAction, active_names: set[str]) -> tuple[int, ...]:
    move_sequence = tuple(turn.move_directions)

    if not move_sequence and turn.move_direction is not None:
        move_sequence = (turn.move_direction,)

    if ITEM_VEHICLE in active_names:
        if turn.move_directions:
            return tuple(turn.move_directions[:2])

        if len(move_sequence) == 1:
            # Matches GridBattleEnv._encode_turn(): a single move_direction is
            # repeated while vehicle is active.
            return (move_sequence[0], move_sequence[0])

        return tuple(move_sequence[:2])

    return tuple(move_sequence[:1])


def _effective_attack_sequence(
    turn: TurnAction,
    snapshot: BattleSnapshot,
) -> list[PhaseAction]:
    active_names = {effect.name for effect in snapshot.active_effects}
    sequence: list[PhaseAction] = []

    if turn.action is not None:
        if ITEM_GOLDEN_GUN in active_names:
            for _ in range(DEFAULT_COMBAT_RULES.enemy.max_health + 1):
                sequence.append(turn.action)
        elif ITEM_SHOTGUN in active_names and turn.action.action_type == "attack":
            sequence.append(turn.action)
            sequence.append(turn.action)
        else:
            sequence.append(turn.action)

    if ITEM_DUAL_BERETTAS in active_names and turn.action2 is not None:
        sequence.append(turn.action2)

    return sequence


def _apply_player_attack(
    snapshot: BattleSnapshot,
    action: PhaseAction,
    player_position: tuple[int, int],
    walls: frozenset[tuple[int, int]],
    enemy_positions: dict[tuple[int, int], int],
) -> None:
    if action.action_type not in _ATTACK_TYPES or action.direction is None:
        return

    player_profile = get_unit_profile(snapshot, "player", player_position)

    # Resolve the nearest valid enemy in the chosen direction.
    candidates = sorted(
        enemy_positions.keys(),
        key=lambda pos: abs(pos[0] - player_position[0]) + abs(pos[1] - player_position[1]),
    )

    for enemy_position in candidates:
        relation = cardinal_relation(player_position, enemy_position)

        if relation is None:
            continue

        direction, distance = relation

        if direction != action.direction:
            continue

        if distance > player_profile.attack_range:
            continue

        if action.action_type == "attack" and distance != 1:
            continue

        if action.action_type == "ranged_attack" and distance <= 1:
            continue

        blocking = walls | (set(enemy_positions.keys()) - {enemy_position})
        if not has_clear_line(player_position, enemy_position, blocking):
            continue

        enemy_health = enemy_positions[enemy_position] - player_profile.attack_damage

        if enemy_health <= 0:
            del enemy_positions[enemy_position]
        else:
            enemy_positions[enemy_position] = enemy_health

        return


def _enemy_tuple(enemy_positions: dict[tuple[int, int], int]) -> tuple[UnitState, ...]:
    return tuple(
        sorted(
            (UnitState(position=pos, health=hp) for pos, hp in enemy_positions.items()),
            key=lambda unit: unit.position,
        )
    )


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
