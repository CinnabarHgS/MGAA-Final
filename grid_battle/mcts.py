from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .agents import _choose_item_to_activate, heuristic_turn
from .combat import (
    DIRECTION_TO_DELTA,
    ITEM_DUAL_BERETTAS,
    ITEM_VEHICLE,
    find_attack_action,
    get_unit_profile,
)
from .state import BattleSnapshot, PhaseAction, TurnAction
from .simulator import simulate_turn


def _legal_turns(snapshot: BattleSnapshot) -> list[TurnAction]:
    """Return the full set of legal TurnActions for the current state.

    Covers:
    * Single-step moves in all four cardinal directions (or stay in place).
    * Two-step moves when the vehicle effect is active.
    * Primary attack (melee or ranged) from the post-move position.
    * Second attack (action2) when dual_berettas is active and a second
      target is reachable from the same post-move position.
    * Item activation: every base turn is duplicated with the highest-
      priority unused item activated alongside it.
    """
    if snapshot.player is None or not snapshot.enemies:
        return [TurnAction()]

    player_position = snapshot.player.position
    enemy_positions = {enemy.position for enemy in snapshot.enemies}
    walls = set(snapshot.walls)
    blocked = walls | enemy_positions
    active_names = {e.name for e in snapshot.active_effects}

    has_vehicle = ITEM_VEHICLE in active_names
    has_dual_berettas = ITEM_DUAL_BERETTAS in active_names

    # ------------------------------------------------------------------ #
    # Helper: compute all attack PhaseActions reachable from a position   #
    # ------------------------------------------------------------------ #
    def get_attacks(post_move: tuple[int, int]) -> list[PhaseAction | None]:
        profile = get_unit_profile(snapshot, "player", post_move)
        options: list[PhaseAction | None] = [None]
        for enemy in snapshot.enemies:
            result = find_attack_action(
                post_move,
                enemy.position,
                profile.attack_range,
                blocking_positions=walls | (enemy_positions - {enemy.position}),
            )
            if result is not None:
                attack = PhaseAction(result[0], result[1])
                if attack not in options:
                    options.append(attack)
        return options

    # ------------------------------------------------------------------ #
    # Helper: compute second-attack options (must differ from primary)    #
    # ------------------------------------------------------------------ #
    def get_action2_options(
        post_move: tuple[int, int], primary: PhaseAction
    ) -> list[PhaseAction]:
        profile = get_unit_profile(snapshot, "player", post_move)
        options: list[PhaseAction] = []
        for enemy in snapshot.enemies:
            result = find_attack_action(
                post_move,
                enemy.position,
                profile.attack_range,
                blocking_positions=walls | (enemy_positions - {enemy.position}),
            )
            if result is not None:
                a2 = PhaseAction(result[0], result[1])
                if a2 != primary and a2 not in options:
                    options.append(a2)
        return options

    turns: list[TurnAction] = []

    # ------------------------------------------------------------------ #
    # Single-step move options                                            #
    # ------------------------------------------------------------------ #
    single_step_moves: list[int | None] = [None]
    for direction, (dx, dy) in DIRECTION_TO_DELTA.items():
        target = (player_position[0] + dx, player_position[1] + dy)
        if not (0 <= target[0] < snapshot.width and 0 <= target[1] < snapshot.height):
            continue
        if target in blocked:
            continue
        single_step_moves.append(direction)

    for move in single_step_moves:
        if move is None:
            post_move = player_position
        else:
            dx, dy = DIRECTION_TO_DELTA[move]
            post_move = (player_position[0] + dx, player_position[1] + dy)

        for attack in get_attacks(post_move):
            turns.append(TurnAction(move_direction=move, action=attack))

            # Dual berettas: add a second attack on a different target.
            if has_dual_berettas and attack is not None:
                for a2 in get_action2_options(post_move, attack):
                    turns.append(
                        TurnAction(move_direction=move, action=attack, action2=a2)
                    )

    # ------------------------------------------------------------------ #
    # Two-step move options  (vehicle only)                               #
    # ------------------------------------------------------------------ #
    if has_vehicle:
        for dir1, (dx1, dy1) in DIRECTION_TO_DELTA.items():
            step1 = (player_position[0] + dx1, player_position[1] + dy1)
            if step1 in blocked or not (
                0 <= step1[0] < snapshot.width and 0 <= step1[1] < snapshot.height
            ):
                continue
            for dir2, (dx2, dy2) in DIRECTION_TO_DELTA.items():
                step2 = (step1[0] + dx2, step1[1] + dy2)
                if step2 in blocked or not (
                    0 <= step2[0] < snapshot.width
                    and 0 <= step2[1] < snapshot.height
                ):
                    continue
                post_move = step2

                for attack in get_attacks(post_move):
                    turns.append(
                        TurnAction(
                            move_direction=dir1,
                            move_directions=(dir1, dir2),
                            action=attack,
                        )
                    )

                    if has_dual_berettas and attack is not None:
                        for a2 in get_action2_options(post_move, attack):
                            turns.append(
                                TurnAction(
                                    move_direction=dir1,
                                    move_directions=(dir1, dir2),
                                    action=attack,
                                    action2=a2,
                                )
                            )

    # ------------------------------------------------------------------ #
    # Item activation: duplicate every base turn with the best item       #
    # ------------------------------------------------------------------ #
    best_item = _choose_item_to_activate(snapshot)
    if best_item is not None:
        base_turns = list(turns)  # snapshot before extending to avoid infinite generator loop
        turns.extend(
            TurnAction(
                move_direction=t.move_direction,
                move_directions=t.move_directions,
                action=t.action,
                action2=t.action2,
                activate_item=best_item,
            )
            for t in base_turns
        )

    return turns


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
        next_snapshot = simulate_turn(node.snapshot, action)
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
            current = simulate_turn(current, action)
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
    return -0.1 * enemy_count - 0.02 * enemy_total_hp + 0.05 * snapshot.player.health
