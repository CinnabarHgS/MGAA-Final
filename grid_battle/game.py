from __future__ import annotations

import contextlib
import io
import textwrap
from dataclasses import dataclass
from typing import Iterable, Sequence

with contextlib.redirect_stderr(io.StringIO()):
    from griddly import gd
    from griddly.GymWrapper import GymWrapper

MOVE_ACTION = 0
ATTACK_ACTION = 1

PLAYER_STARTING_HEALTH = 4
ENEMY_STARTING_HEALTH = 2

DIRECTION_TO_DELTA = {
    1: (0, -1),
    2: (1, 0),
    3: (0, 1),
    4: (-1, 0),
}

DELTA_TO_DIRECTION = {delta: action_id for action_id, delta in DIRECTION_TO_DELTA.items()}

DIRECTION_NAMES = {
    1: "up",
    2: "right",
    3: "down",
    4: "left",
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
            - sub: [health, 1]
            - lt:
                Arguments: [health, 1]
                Commands:
                  - remove: true
                  - reward: 1

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
            - sub: [health, 1]
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
        InitialValue: 4
    Observers:
      Block2D:
        - Shape: square
          Color: [0.18, 0.44, 0.95]
          Scale: 0.82

  - Name: enemy
    MapCharacter: E
    Variables:
      - Name: health
        InitialValue: 2
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
    return GDY_TEMPLATE.replace("__LEVELS__", levels_block)


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

    def step(self, action: tuple[int, int]) -> tuple[BattleSnapshot, float, bool, dict]:
        observation, reward, done, info = self._env.step(list(action))
        del observation
        self.player_turns += 1
        return self.snapshot(), reward, done, info

    def snapshot(self) -> BattleSnapshot:
        return snapshot_from_state(self._env.get_state(), self.player_turns)

    def render_ascii(self) -> str:
        return self._env.render(observer="global", mode="human")


def positions_around(position: tuple[int, int]) -> Iterable[tuple[int, int]]:
    x, y = position
    for dx, dy in DIRECTION_TO_DELTA.values():
        yield x + dx, y + dy

