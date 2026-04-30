from __future__ import annotations

import contextlib
import io
import textwrap
from dataclasses import dataclass
from typing import Iterable, Sequence

from .combat import (
    DEFAULT_COMBAT_RULES,
    DELTA_TO_DIRECTION,
    DIRECTION_NAMES,
    DIRECTION_TO_DELTA,
)

with contextlib.redirect_stderr(io.StringIO()):
    from griddly import gd
    from griddly.GymWrapper import GymWrapper

MOVE_ACTION = 0
ATTACK_ACTION = 1
WAIT_ACTION = 2

LOW_LEVEL_ACTION_IDS = {
    "move": MOVE_ACTION,
    "attack": ATTACK_ACTION,
    "wait": WAIT_ACTION,
}

GDY_TEMPLATE = """
Version: "0.1"
Environment:
  Name: GridBattleDemo
  Description: Minimal turn-based tactical battle demo.
  Observers:
    Block2D:
      TileSize: 24
  Player:
    AvatarObject: player
  Termination:
    Win:
      - eq: [enemy:count, 0]
    Lose:
      - eq: [player:count, 0]
  Levels:
__LEVELS__
Actions:
  - Name: move
    InputMapping:
      Inputs:
        1:
          Description: Up
          VectorToDest: [0, -1]
        2:
          Description: Right
          VectorToDest: [1, 0]
        3:
          Description: Down
          VectorToDest: [0, 1]
        4:
          Description: Left
          VectorToDest: [-1, 0]
    Behaviours:
      - Src:
          Object: player
          Commands:
            - mov: _dest
        Dst:
          Object: _empty

  # Attack is currently single-tile melee in the Griddly rule layer.
  # The Python combat helpers centralize all range and damage decisions so
  # future ranged variants only need one rule update point.
  - Name: attack
    InputMapping:
      Inputs:
        1:
          Description: Up
          VectorToDest: [0, -1]
        2:
          Description: Right
          VectorToDest: [1, 0]
        3:
          Description: Down
          VectorToDest: [0, 1]
        4:
          Description: Left
          VectorToDest: [-1, 0]
    Behaviours:
      - Src:
          Object: player
        Dst:
          Object: enemy
          Commands:
            - sub: [health, __PLAYER_ATTACK_DAMAGE__]
            - lt:
                Arguments: [health, 1]
                Commands:
                  - remove: true
                  - reward: 1

  - Name: wait
    InputMapping:
      Inputs:
        1:
          Description: Wait
          VectorToDest: [0, 0]
    Behaviours:
      - Src:
          Object: player
        Dst:
          Object: player

  - Name: enemy_turn
    InputMapping:
      Inputs:
        1:
          Description: Up
          VectorToDest: [0, -1]
        2:
          Description: Right
          VectorToDest: [1, 0]
        3:
          Description: Down
          VectorToDest: [0, 1]
        4:
          Description: Left
          VectorToDest: [-1, 0]
      Internal: true
    Behaviours:
      - Src:
          Object: enemy
          Commands:
            - exec:
                Action: enemy_turn
                Delay: 1
                Search:
                  ImpassableObjects: [wall, enemy]
                  TargetObjectName: player
        Dst:
          Object: player
          Commands:
            - sub: [health, __ENEMY_ATTACK_DAMAGE__]
            - lt:
                Arguments: [health, 1]
                Commands:
                  - remove: true
      - Src:
          Object: enemy
          Commands:
            - mov: _dest
            - exec:
                Action: enemy_turn
                Delay: 1
                Search:
                  ImpassableObjects: [wall, enemy]
                  TargetObjectName: player
        Dst:
          Object: _empty
      - Src:
          Object: enemy
          Commands:
            - exec:
                Action: enemy_turn
                Delay: 1
                Search:
                  ImpassableObjects: [wall, enemy]
                  TargetObjectName: player
        Dst:
          Object: [wall, enemy]

Objects:
  - Name: player
    MapCharacter: A
    Variables:
      - Name: health
        InitialValue: __PLAYER_MAX_HEALTH__
    Observers:
      Block2D:
        - Shape: square
          Color: [0.18, 0.44, 0.95]
          Scale: 0.82

  - Name: enemy
    MapCharacter: E
    Variables:
      - Name: health
        InitialValue: __ENEMY_MAX_HEALTH__
    InitialActions:
      - Action: enemy_turn
        Delay: 1
        Search:
          ImpassableObjects: [wall, enemy]
          TargetObjectName: player
    Observers:
      Block2D:
        - Shape: triangle
          Color: [0.92, 0.2, 0.2]
          Scale: 0.82

  - Name: wall
    MapCharacter: W
    Observers:
      Block2D:
        - Shape: square
          Color: [0.38, 0.38, 0.42]
          Scale: 1.0
""".strip()


@dataclass(frozen=True)
class UnitState:
    position: tuple[int, int]
    health: int


@dataclass(frozen=True)
class BattleSnapshot:
    width: int
    height: int
    game_ticks: int
    player_turns: int
    player: UnitState | None
    enemies: tuple[UnitState, ...]
    walls: frozenset[tuple[int, int]]

    @property
    def remaining_enemies(self) -> int:
        return len(self.enemies)


@dataclass(frozen=True)
class PhaseAction:
    action_type: str
    direction: int | None = None


@dataclass(frozen=True)
class TurnAction:
    move_direction: int | None = None
    action: PhaseAction | None = None


def normalize_level(level: str) -> str:
    cleaned = textwrap.dedent(level).strip()
    rows = [row.strip() for row in cleaned.splitlines() if row.strip()]
    if not rows:
        raise ValueError("Level must contain at least one row.")

    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("Every level row must have the same width.")

    return "\n".join(rows)


def _indent_level(level: str) -> str:
    normalized = normalize_level(level)
    return "\n".join(f"      {row}" for row in normalized.splitlines())


def build_gdy_yaml(levels: Sequence[str]) -> str:
    if not levels:
        raise ValueError("At least one level is required.")

    levels_block = "\n".join(f"    - |\n{_indent_level(level)}" for level in levels)
    return (
        GDY_TEMPLATE.replace("__LEVELS__", levels_block)
        .replace("__PLAYER_MAX_HEALTH__", str(DEFAULT_COMBAT_RULES.player.max_health))
        .replace("__ENEMY_MAX_HEALTH__", str(DEFAULT_COMBAT_RULES.enemy.max_health))
        .replace("__PLAYER_ATTACK_DAMAGE__", str(DEFAULT_COMBAT_RULES.player.attack_damage))
        .replace("__ENEMY_ATTACK_DAMAGE__", str(DEFAULT_COMBAT_RULES.enemy.attack_damage))
    )


def _health_from_object(object_state: dict) -> int:
    return int(object_state.get("Variables", {}).get("health", 0))


def snapshot_from_state(state: dict, player_turns: int) -> BattleSnapshot:
    player = None
    enemies: list[UnitState] = []
    walls: set[tuple[int, int]] = set()

    for obj in state["Objects"]:
        position = tuple(obj["Location"])
        name = obj["Name"]

        if name == "player":
            player = UnitState(position=position, health=_health_from_object(obj))
        elif name == "enemy":
            enemies.append(UnitState(position=position, health=_health_from_object(obj)))
        elif name == "wall":
            walls.add(position)

    enemies.sort(key=lambda unit: unit.position)

    return BattleSnapshot(
        width=state["Grid"]["Width"],
        height=state["Grid"]["Height"],
        game_ticks=state["GameTicks"],
        player_turns=player_turns,
        player=player,
        enemies=tuple(enemies),
        walls=frozenset(walls),
    )


def action_to_delta(action_id: int) -> tuple[int, int]:
    return DIRECTION_TO_DELTA[action_id]


def delta_to_action_id(delta: tuple[int, int]) -> int:
    return DELTA_TO_DIRECTION[delta]


class GridBattleEnv:
    def __init__(self, level: str, max_steps: int = 40):
        self._level = normalize_level(level)
        self._yaml = build_gdy_yaml([self._level])
        self._env = GymWrapper(
            yaml_string=self._yaml,
            global_observer_type=gd.ObserverType.ASCII,
            player_observer_type=gd.ObserverType.ASCII,
            max_steps=max_steps,
        )
        self._env.enable_history(True)
        self.player_turns = 0

    @property
    def level(self) -> str:
        return self._level

    def reset(self) -> BattleSnapshot:
        self.player_turns = 0
        self._env.reset()
        return self.snapshot()

    def step(self, turn: TurnAction) -> tuple[BattleSnapshot, float, bool, dict]:
        low_level_actions = self._encode_turn(turn)
        observation, reward, done, info = self._env.step(low_level_actions)
        del observation
        self.player_turns += 1
        return self.snapshot(), reward, done, info

    def snapshot(self) -> BattleSnapshot:
        return snapshot_from_state(self._env.get_state(), self.player_turns)

    def render_ascii(self) -> str:
        return self._env.render(observer="global", mode="human")

    def _encode_turn(self, turn: TurnAction) -> list[list[int]]:
        desired_sequence: list[PhaseAction] = []

        if turn.move_direction is not None:
            desired_sequence.append(PhaseAction(action_type="move", direction=turn.move_direction))

        if turn.action is not None:
            desired_sequence.append(turn.action)

        if not desired_sequence:
            desired_sequence.append(PhaseAction(action_type="wait", direction=1))

        # Griddly executes multi-actions in reverse row order, so we reverse the
        # player's intended sequence before sending it to the engine.
        return [self._encode_phase_action(phase_action) for phase_action in reversed(desired_sequence)]

    def _encode_phase_action(self, phase_action: PhaseAction) -> list[int]:
        if phase_action.action_type not in LOW_LEVEL_ACTION_IDS:
            raise ValueError(f"Unknown action type: {phase_action.action_type}")

        if phase_action.direction is None:
            if phase_action.action_type == "wait":
                direction = 1
            else:
                raise ValueError(f"{phase_action.action_type} requires a direction.")
        else:
            if phase_action.direction not in DIRECTION_TO_DELTA:
                raise ValueError(f"Invalid direction id: {phase_action.direction}")
            direction = phase_action.direction

        return [LOW_LEVEL_ACTION_IDS[phase_action.action_type], direction]


def positions_around(position: tuple[int, int]) -> Iterable[tuple[int, int]]:
    x, y = position
    for dx, dy in DIRECTION_TO_DELTA.values():
        yield x + dx, y + dy
