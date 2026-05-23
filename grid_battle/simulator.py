from __future__ import annotations

import dataclasses
import random
from collections import deque

from .combat import (
    DEFAULT_COMBAT_RULES,
    DIRECTION_TO_DELTA,
    ITEM_DUAL_BERETTAS,
    ITEM_DURATIONS,
    ITEM_GOLDEN_GUN,
    ITEM_SHOTGUN,
    ITEM_VEHICLE,
    ActiveEffect,
    find_attack_direction,
    get_unit_profile,
)
from .state import BattleSnapshot, TurnAction, UnitState, action_to_delta


# Forward model used by MCTS for rollouts.
#
# Player phase: activate item → multi-step move (vehicle-aware) → primary
# attack (with golden-gun / shotgun multipliers) → optional second attack
# (dual_berettas).
#
# Enemy phase: each enemy moves one step toward the player and THEN attacks
# if now adjacent (matching the two-phase enemy_move / enemy_attack split in
# the real Griddly backend).  Bush 50 % dodge and bunker immunity are also
# modelled.
#
# Item pickup, active-effect duration decay, and item-activation state are
# all tracked so that multi-turn rollouts stay consistent with the real env.

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

    # ------------------------------------------------------------------ #
    # Mutable local copies of the fields that change during a turn        #
    # ------------------------------------------------------------------ #
    inventory: list[str] = list(snapshot.inventory)
    active_effects: list[ActiveEffect] = list(snapshot.active_effects)
    map_items: dict[tuple[int, int], str] = dict(snapshot.map_items)

    on_bunker = player_position in snapshot.bunkers

    # ------------------------------------------------------------------ #
    # 1. Item activation                                                  #
    # ------------------------------------------------------------------ #
    if turn.activate_item is not None and turn.activate_item in inventory:
        inventory.remove(turn.activate_item)
        duration = (
            1
            if turn.activate_item == ITEM_GOLDEN_GUN
            else ITEM_DURATIONS.get(turn.activate_item, 1)
        )
        active_effects.append(ActiveEffect(turn.activate_item, duration))

    # Build a snapshot reference that reflects activated item so that
    # profile lookups (get_unit_profile) see the correct active_effects.
    current_snapshot = dataclasses.replace(
        snapshot,
        inventory=tuple(inventory),
        active_effects=tuple(active_effects),
    )

    # ------------------------------------------------------------------ #
    # 2. Player move  (skipped when standing on a bunker)                 #
    # ------------------------------------------------------------------ #
    if not on_bunker:
        # Support both single-step (move_direction) and two-step vehicle
        # moves (move_directions).  The caller is responsible for only
        # passing two-step sequences when the vehicle effect is active.
        move_seq: list[int] = []
        if turn.move_directions:
            move_seq = list(turn.move_directions)
        elif turn.move_direction is not None:
            move_seq = [turn.move_direction]

        for mv in move_seq:
            dx, dy = action_to_delta(mv)
            target = (player_position[0] + dx, player_position[1] + dy)
            if (
                0 <= target[0] < width
                and 0 <= target[1] < height
                and target not in walls
                and target not in enemy_positions
            ):
                player_position = target
            # If a step is blocked, skip it but keep trying subsequent steps
            # (mirrors Griddly's per-step behaviour).

    # ------------------------------------------------------------------ #
    # 3. Item pickup at final player position                             #
    # ------------------------------------------------------------------ #
    if player_position in map_items:
        picked_up = map_items.pop(player_position)
        inventory.append(picked_up)
        current_snapshot = dataclasses.replace(
            current_snapshot,
            inventory=tuple(inventory),
            map_items=tuple(sorted(map_items.items())),
        )

    # ------------------------------------------------------------------ #
    # 4. Primary attack                                                   #
    # ------------------------------------------------------------------ #
    if (
        turn.action is not None
        and turn.action.action_type in _ATTACK_TYPES
        and turn.action.direction is not None
    ):
        _apply_player_attack(
            current_snapshot,
            turn.action.direction,
            player_position,
            walls,
            enemy_positions,
        )

    # ------------------------------------------------------------------ #
    # 5. Second attack  (dual_berettas)                                   #
    # ------------------------------------------------------------------ #
    if (
        turn.action2 is not None
        and turn.action2.action_type in _ATTACK_TYPES
        and turn.action2.direction is not None
    ):
        _apply_player_attack(
            current_snapshot,
            turn.action2.direction,
            player_position,
            walls,
            enemy_positions,
        )

    # ------------------------------------------------------------------ #
    # 6. Enemy phase — move THEN conditionally attack                     #
    # ------------------------------------------------------------------ #
    # Each enemy first takes one BFS step toward the player.  After
    # moving, if the enemy is now adjacent to the player it also attacks.
    # This matches the two-phase enemy_move → enemy_attack chain in the
    # real Griddly backend (Issue 1b fix).

    enemy_order = sorted(enemy_positions.keys())
    for original_position in enemy_order:
        if original_position not in enemy_positions:
            # Enemy was killed earlier this turn by the player.
            continue
        if player_position is None:
            break

        enemy_profile = get_unit_profile(current_snapshot, "enemy", original_position)

        # Compute the next BFS step from the enemy's current position.
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

        # -- Move phase ------------------------------------------------ #
        current_position = original_position
        if next_step != player_position:
            # The next BFS step is an empty tile: move there.
            enemy_health = enemy_positions.pop(original_position)
            enemy_positions[next_step] = enemy_health
            current_position = next_step
        # If next_step == player_position the enemy is already adjacent;
        # it cannot step into the player's tile, so it stays put.

        # -- Attack phase ---------------------------------------------- #
        # Re-check adjacency from the (possibly updated) position.
        post_move_step = _next_step_toward(
            start=current_position,
            goal=player_position,
            walls=walls,
            other_enemies=set(enemy_positions.keys()) - {current_position},
            width=width,
            height=height,
        )
        if post_move_step == player_position:
            # Enemy is adjacent → attack.
            if not on_bunker:
                # Bush gives a 50 % dodge chance (matches game.py).
                in_bush = player_position in snapshot.bushes
                if not (in_bush and random.random() < 0.5):
                    player_health -= enemy_profile.attack_damage
                    if player_health <= 0:
                        player_position = None
                        player_health = 0

    # ------------------------------------------------------------------ #
    # 7. Decrement active-effect durations                                #
    # ------------------------------------------------------------------ #
    new_active_effects = tuple(
        ActiveEffect(e.name, e.turns_left - 1)
        for e in active_effects
        if e.turns_left > 1
    )

    # ------------------------------------------------------------------ #
    # 8. Assemble the new snapshot                                        #
    # ------------------------------------------------------------------ #
    enemies = tuple(
        sorted(
            (UnitState(position=pos, health=hp) for pos, hp in enemy_positions.items()),
            key=lambda unit: unit.position,
        )
    )
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
        inventory=tuple(inventory),
        active_effects=new_active_effects,
        map_items=tuple(sorted(map_items.items())),
    )


def _apply_player_attack(
    snapshot: BattleSnapshot,
    direction: int,
    player_position: tuple[int, int],
    walls: frozenset[tuple[int, int]],
    enemy_positions: dict[tuple[int, int], int],
) -> None:
    """Apply one player attack in *direction*, respecting active item effects."""
    player_profile = get_unit_profile(snapshot, "player", player_position)
    active_names = {e.name for e in snapshot.active_effects}

    # Determine effective damage per hit and hit count.
    if ITEM_GOLDEN_GUN in active_names:
        # Golden Gun fires max_health+1 times — guaranteed one-shot kill.
        effective_damage = DEFAULT_COMBAT_RULES.enemy.max_health + 1
    elif ITEM_SHOTGUN in active_names:
        # Shotgun hits twice.
        effective_damage = player_profile.attack_damage * 2
    else:
        effective_damage = player_profile.attack_damage

    for enemy_position in list(enemy_positions.keys()):
        hit_direction = find_attack_direction(
            player_position,
            enemy_position,
            player_profile.attack_range,
            blocking_positions=walls | (set(enemy_positions.keys()) - {enemy_position}),
        )
        if hit_direction == direction:
            enemy_health = enemy_positions[enemy_position] - effective_damage
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
