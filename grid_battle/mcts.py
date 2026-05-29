from __future__ import annotations

import dataclasses
import math
import random
from dataclasses import dataclass, field

from .agents import heuristic_turn
from .combat import (
    DIRECTION_TO_DELTA,
    ITEM_DUAL_BERETTAS,
    ITEM_DURATIONS,
    ITEM_GOLDEN_GUN,
    ITEM_VEHICLE,
    ActiveEffect,
    find_attack_action,
    get_unit_profile,
)
from .state import BattleSnapshot, PhaseAction, TurnAction
from .simulator import simulate_turn


def _legal_turns(snapshot: BattleSnapshot) -> list[TurnAction]:
    if snapshot.player is None or not snapshot.enemies:
        return [TurnAction()]

    turns: list[TurnAction] = []

    for activate_item in _activation_options(snapshot):
        planning_snapshot = _snapshot_after_activation(snapshot, activate_item)

        for move_sequence, post_move in _legal_move_sequences(planning_snapshot):
            attack_options = _attack_options(planning_snapshot, post_move)

            dual_active = _has_active_effect(planning_snapshot, ITEM_DUAL_BERETTAS)

            for primary_attack in attack_options:
                if dual_active and primary_attack is not None:
                    secondary_options = attack_options
                else:
                    secondary_options = [None]

                for secondary_attack in secondary_options:
                    if secondary_attack is not None and secondary_attack == primary_attack:
                        continue

                    turns.append(
                        TurnAction(
                            move_direction=None,
                            move_directions=move_sequence,
                            action=primary_attack,
                            action2=secondary_attack,
                            activate_item=activate_item,
                        )
                    )

    # Deduplicate while preserving order.
    return list(dict.fromkeys(turns))


def _activation_options(snapshot: BattleSnapshot) -> list[str | None]:
    options: list[str | None] = [None]
    active_names = {effect.name for effect in snapshot.active_effects}

    for item in snapshot.inventory:
        if item in active_names:
            continue

        if item not in options:
            options.append(item)

    return options


def _snapshot_after_activation(
    snapshot: BattleSnapshot,
    activate_item: str | None,
) -> BattleSnapshot:
    if activate_item is None:
        return snapshot

    inventory = list(snapshot.inventory)

    if activate_item not in inventory:
        return snapshot

    inventory.remove(activate_item)

    duration = (
        1
        if activate_item == ITEM_GOLDEN_GUN
        else ITEM_DURATIONS.get(activate_item, 1)
    )

    active_effects = list(snapshot.active_effects)
    active_effects.append(ActiveEffect(activate_item, duration))

    return dataclasses.replace(
        snapshot,
        inventory=tuple(inventory),
        active_effects=tuple(active_effects),
    )


def _legal_move_sequences(
    snapshot: BattleSnapshot,
) -> list[tuple[tuple[int, ...], tuple[int, int]]]:
    assert snapshot.player is not None

    start = snapshot.player.position

    if _has_active_effect(snapshot, ITEM_VEHICLE):
        sequences: list[tuple[tuple[int, ...], tuple[int, int]]] = [((), start)]

        for first_direction in _legal_step_directions(snapshot, start):
            first_position = _apply_step(snapshot, start, first_direction)
            assert first_position is not None

            sequences.append(((first_direction,), first_position))

            for second_direction in _legal_step_directions(snapshot, first_position):
                second_position = _apply_step(snapshot, first_position, second_direction)
                assert second_position is not None
                sequences.append(((first_direction, second_direction), second_position))

        return list(dict.fromkeys(sequences))

    sequences = [((), start)]

    for direction in _legal_step_directions(snapshot, start):
        target = _apply_step(snapshot, start, direction)
        assert target is not None
        sequences.append(((direction,), target))

    return sequences


def _legal_step_directions(
    snapshot: BattleSnapshot,
    position: tuple[int, int],
) -> list[int]:
    enemy_positions = {enemy.position for enemy in snapshot.enemies}
    blocked = set(snapshot.walls) | enemy_positions

    directions: list[int] = []

    for direction, (dx, dy) in DIRECTION_TO_DELTA.items():
        target = (position[0] + dx, position[1] + dy)

        if not (0 <= target[0] < snapshot.width and 0 <= target[1] < snapshot.height):
            continue

        if target in blocked:
            continue

        directions.append(direction)

    return directions


def _apply_step(
    snapshot: BattleSnapshot,
    position: tuple[int, int],
    direction: int,
) -> tuple[int, int] | None:
    dx, dy = DIRECTION_TO_DELTA[direction]
    target = (position[0] + dx, position[1] + dy)

    enemy_positions = {enemy.position for enemy in snapshot.enemies}
    blocked = set(snapshot.walls) | enemy_positions

    if not (0 <= target[0] < snapshot.width and 0 <= target[1] < snapshot.height):
        return None

    if target in blocked:
        return None

    return target


def _attack_options(
    snapshot: BattleSnapshot,
    player_position: tuple[int, int],
) -> list[PhaseAction | None]:
    enemy_positions = {enemy.position for enemy in snapshot.enemies}
    walls = set(snapshot.walls)
    profile = get_unit_profile(snapshot, "player", player_position)

    options: list[PhaseAction | None] = [None]

    for enemy in snapshot.enemies:
        result = find_attack_action(
            player_position,
            enemy.position,
            profile.attack_range,
            blocking_positions=walls | (enemy_positions - {enemy.position}),
        )

        if result is None:
            continue

        attack = PhaseAction(result[0], result[1])

        if attack not in options:
            options.append(attack)

    return options


def _has_active_effect(snapshot: BattleSnapshot, item_name: str) -> bool:
    return any(effect.name == item_name for effect in snapshot.active_effects)


@dataclass
class _Node:
    snapshot: BattleSnapshot
    parent: "_Node | None" = None
    incoming_action: TurnAction | None = None
    children: dict[TurnAction, "_Node"] = field(default_factory=dict)
    untried_actions: list[TurnAction] = field(default_factory=list)
    visits: int = 0
    total_value: float = 0.0
    is_terminal: bool = False

    @property
    def mean_value(self) -> float:
        if self.visits == 0:
            return 0.0

        return self.total_value / self.visits


def _is_terminal(snapshot: BattleSnapshot) -> bool:
    return snapshot.player is None or not snapshot.enemies


def _terminal_value(snapshot: BattleSnapshot) -> float:
    if snapshot.player is None:
        return -1.0

    if not snapshot.enemies:
        return 1.0

    return 0.0


class MctsAgent:
    def __init__(
        self,
        iterations: int = 200,
        exploration: float = math.sqrt(2.0),
        rollout_depth: int = 30,
        seed: int | None = None,
    ):
        self._iterations = iterations
        self._exploration = exploration
        self._rollout_depth = rollout_depth
        self._rng = random.Random(seed)

    def act(self, snapshot: BattleSnapshot) -> TurnAction:
        if snapshot.player is None or not snapshot.enemies:
            return TurnAction()

        root = _Node(snapshot=snapshot, is_terminal=False)
        root.untried_actions = _legal_turns(snapshot)
        self._rng.shuffle(root.untried_actions)

        for _ in range(self._iterations):
            node = self._select(root)

            if not node.is_terminal:
                node = self._expand(node)

            value = self._rollout(node.snapshot)
            self._backpropagate(node, value)

        if not root.children:
            return heuristic_turn(snapshot)

        best_action, _ = max(
            root.children.items(),
            key=lambda item: (item[1].visits, item[1].mean_value),
        )

        return best_action

    def _select(self, node: _Node) -> _Node:
        while not node.is_terminal:
            if node.untried_actions:
                return node

            if not node.children:
                node.is_terminal = True
                return node

            node = self._best_uct_child(node)

        return node

    def _best_uct_child(self, node: _Node) -> _Node:
        log_parent = math.log(node.visits) if node.visits > 0 else 0.0
        best_score = -math.inf
        best_child: _Node | None = None

        for child in node.children.values():
            if child.visits == 0:
                return child

            exploit = child.mean_value
            explore = self._exploration * math.sqrt(log_parent / child.visits)
            score = exploit + explore

            if score > best_score:
                best_score = score
                best_child = child

        assert best_child is not None
        return best_child

    def _expand(self, node: _Node) -> _Node:
        action = node.untried_actions.pop()
        next_snapshot = simulate_turn(node.snapshot, action, rng=self._rng)
        terminal = _is_terminal(next_snapshot)

        child = _Node(
            snapshot=next_snapshot,
            parent=node,
            incoming_action=action,
            is_terminal=terminal,
        )

        if not terminal:
            child.untried_actions = _legal_turns(next_snapshot)
            self._rng.shuffle(child.untried_actions)

        node.children[action] = child
        return child

    def _rollout(self, snapshot: BattleSnapshot) -> float:
        current = snapshot

        for _ in range(self._rollout_depth):
            if _is_terminal(current):
                return _terminal_value(current)

            action = heuristic_turn(current)
            current = simulate_turn(current, action, rng=self._rng)

        return _shaped_score(current)

    def _backpropagate(self, node: _Node, value: float) -> None:
        current: _Node | None = node

        while current is not None:
            current.visits += 1
            current.total_value += value
            current = current.parent


def _shaped_score(snapshot: BattleSnapshot) -> float:
    if snapshot.player is None:
        return -1.0

    if not snapshot.enemies:
        return 1.0

    enemy_count = len(snapshot.enemies)
    enemy_total_hp = sum(enemy.health for enemy in snapshot.enemies)
    player_hp = snapshot.player.health

    # Mild shaping only. Terminal wins/losses still dominate.
    return -0.1 * enemy_count - 0.02 * enemy_total_hp + 0.05 * player_hp
