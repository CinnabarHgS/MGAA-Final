from __future__ import annotations

import contextlib
import dataclasses
import io
import random
import textwrap
from typing import Iterable, Sequence

from .combat import (
    DEFAULT_COMBAT_RULES,
    DIRECTION_NAMES,
    DIRECTION_TO_DELTA,
    ITEM_DUAL_BERETTAS,
    ITEM_DURATIONS,
    ITEM_GOLDEN_GUN,
    ITEM_MAP_CHARS,
    ITEM_SHOTGUN,
    ITEM_VEHICLE,
    TERRAIN_BUNKER,
    TERRAIN_BUSH,
    TERRAIN_HILL,
    TERRAIN_MAP_CHARS,
    ActiveEffect,
)
from .state import (
    BattleSnapshot,
    PhaseAction,
    TurnAction,
    UnitState,
    delta_to_action_id,
)

with contextlib.redirect_stderr(io.StringIO()):
    from griddly import gd
    from griddly.GymWrapper import GymWrapper

MOVE_ACTION = 0
ATTACK_ACTION = 1
WAIT_ACTION = 2
RANGED_ATTACK_ACTION = 3

LOW_LEVEL_ACTION_IDS = {
    "move": MOVE_ACTION,
    "attack": ATTACK_ACTION,
    "wait": WAIT_ACTION,
    "ranged_attack": RANGED_ATTACK_ACTION,
}

_GRIDDLY_PLAYER_HP = 9999

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

  - Name: ranged_attack
    InputMapping:
      Inputs:
        1:
          Description: Up
          VectorToDest: [0, -2]
        2:
          Description: Right
          VectorToDest: [2, 0]
        3:
          Description: Down
          VectorToDest: [0, 2]
        4:
          Description: Left
          VectorToDest: [-2, 0]
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


def _strip_special_tiles(
    level: str,
) -> tuple[str, dict[str, frozenset[tuple[int, int]]], dict[tuple[int, int], str]]:
    terrain: dict[str, set[tuple[int, int]]] = {t: set() for t in TERRAIN_MAP_CHARS.values()}
    items: dict[tuple[int, int], str] = {}
    rows = normalize_level(level).splitlines()
    new_rows = []
    for y, row in enumerate(rows):
        new_row = list(row)
        for x, ch in enumerate(row):
            if ch in TERRAIN_MAP_CHARS:
                terrain[TERRAIN_MAP_CHARS[ch]].add((x, y))
                new_row[x] = "."
            elif ch in ITEM_MAP_CHARS:
                items[(x, y)] = ITEM_MAP_CHARS[ch]
                new_row[x] = "."
        new_rows.append("".join(new_row))
    return "\n".join(new_rows), {k: frozenset(v) for k, v in terrain.items()}, items


def build_gdy_yaml(levels: Sequence[str]) -> str:
    if not levels:
        raise ValueError("At least one level is required.")

    levels_block = "\n".join(f"    - |\n{_indent_level(level)}" for level in levels)
    return (
        GDY_TEMPLATE.replace("__LEVELS__", levels_block)
        .replace("__PLAYER_MAX_HEALTH__", str(_GRIDDLY_PLAYER_HP))
        .replace("__ENEMY_MAX_HEALTH__", str(DEFAULT_COMBAT_RULES.enemy.max_health))
        .replace("__PLAYER_ATTACK_DAMAGE__", str(DEFAULT_COMBAT_RULES.player.attack_damage))
        .replace("__ENEMY_ATTACK_DAMAGE__", str(DEFAULT_COMBAT_RULES.enemy.attack_damage))
    )


def _health_from_object(object_state: dict) -> int:
    return int(object_state.get("Variables", {}).get("health", 0))


def _griddly_player_health_from_state(state: dict) -> int | None:
    for obj in state["Objects"]:
        if obj["Name"] == "player":
            return _health_from_object(obj)
    return None


def _player_position_from_state(state: dict) -> tuple[int, int] | None:
    for obj in state["Objects"]:
        if obj["Name"] == "player":
            return tuple(obj["Location"])
    return None


def snapshot_from_state(state: dict, player_turns: int) -> BattleSnapshot:
    player = None
    enemies: list[UnitState] = []
    walls: set[tuple[int, int]] = set()
    all_locations: list[tuple[int, int]] = []

    for obj in state["Objects"]:
        position = tuple(obj["Location"])
        all_locations.append(position)
        name = obj["Name"]

        if name == "player":
            player = UnitState(position=position, health=_health_from_object(obj))
        elif name == "enemy":
            enemies.append(UnitState(position=position, health=_health_from_object(obj)))
        elif name == "wall":
            walls.add(position)

    enemies.sort(key=lambda unit: unit.position)

    if "Grid" in state:
        grid_width = state["Grid"]["Width"]
        grid_height = state["Grid"]["Height"]
    else:
        grid_width = (max(loc[0] for loc in all_locations) + 1) if all_locations else 0
        grid_height = (max(loc[1] for loc in all_locations) + 1) if all_locations else 0

    return BattleSnapshot(
        width=grid_width,
        height=grid_height,
        game_ticks=state["GameTicks"],
        player_turns=player_turns,
        player=player,
        enemies=tuple(enemies),
        walls=frozenset(walls),
    )


class GridBattleEnv:
    def __init__(self, level: str, max_steps: int = 40):
        cleaned_level, terrain, map_items = _strip_special_tiles(level)
        self._hills: frozenset[tuple[int, int]] = terrain[TERRAIN_HILL]
        self._bushes: frozenset[tuple[int, int]] = terrain[TERRAIN_BUSH]
        self._bunkers: frozenset[tuple[int, int]] = terrain[TERRAIN_BUNKER]
        self._original_map_items: dict[tuple[int, int], str] = dict(map_items)
        self._map_items: dict[tuple[int, int], str] = dict(map_items)
        self._player_hp: int = DEFAULT_COMBAT_RULES.player.max_health
        self._prev_griddly_player_hp: int = _GRIDDLY_PLAYER_HP
        self._player_pos: tuple[int, int] | None = None
        self._inventory: list[str] = []
        self._active_effects: list[ActiveEffect] = []
        self._level = normalize_level(cleaned_level)
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
        self._player_hp = DEFAULT_COMBAT_RULES.player.max_health
        self._prev_griddly_player_hp = _GRIDDLY_PLAYER_HP
        self._player_pos = None
        self._map_items = dict(self._original_map_items)
        self._inventory = []
        self._active_effects = []
        self._env.reset()
        state = self._env.get_state()
        self._player_pos = _player_position_from_state(state)
        return self.snapshot()

    def step(self, turn: TurnAction) -> tuple[BattleSnapshot, float, bool, dict]:
        if turn.activate_item is not None and turn.activate_item in self._inventory:
            self._inventory.remove(turn.activate_item)
            duration = 1 if turn.activate_item == ITEM_GOLDEN_GUN else ITEM_DURATIONS.get(turn.activate_item, 1)
            self._active_effects.append(ActiveEffect(turn.activate_item, duration))

        on_bunker = self._player_pos is not None and self._player_pos in self._bunkers
        if on_bunker:
            turn = TurnAction(
                move_direction=None,
                move_directions=(),
                action=turn.action,
                action2=turn.action2,
                activate_item=None,
            )

        low_level_actions = self._encode_turn(turn)
        observation, reward, done, info = self._env.step(low_level_actions)
        del observation
        self.player_turns += 1

        griddly_state = self._env.get_state()
        griddly_hp = _griddly_player_health_from_state(griddly_state)
        if griddly_hp is not None:
            raw_damage = self._prev_griddly_player_hp - griddly_hp
            if raw_damage > 0:
                new_pos = _player_position_from_state(griddly_state)
                if new_pos in self._bushes and random.random() < 0.5:
                    raw_damage = 0
                if on_bunker:
                    raw_damage = 0
                self._player_hp = max(0, self._player_hp - raw_damage)
            self._prev_griddly_player_hp = griddly_hp

        new_pos = _player_position_from_state(griddly_state)
        if new_pos is not None and new_pos in self._map_items:
            self._inventory.append(self._map_items.pop(new_pos))

        self._player_pos = new_pos

        self._active_effects = [
            ActiveEffect(e.name, e.turns_left - 1)
            for e in self._active_effects
            if e.turns_left > 1
        ]

        done = done or self._player_hp <= 0
        return self.snapshot(), reward, done, info

    def snapshot(self) -> BattleSnapshot:
        raw = snapshot_from_state(self._env.get_state(), self.player_turns)
        player = (
            UnitState(raw.player.position, self._player_hp)
            if raw.player is not None and self._player_hp > 0
            else None
        )
        return dataclasses.replace(
            raw,
            player=player,
            hills=self._hills,
            bushes=self._bushes,
            bunkers=self._bunkers,
            map_items=tuple(sorted(self._map_items.items())),
            inventory=tuple(self._inventory),
            active_effects=tuple(self._active_effects),
        )

    def render_ascii(self) -> str:
        return self._env.render(observer="global", mode="human")

    def _encode_turn(self, turn: TurnAction) -> list[list[int]]:
        active_names = {e.name for e in self._active_effects}
        desired_sequence: list[PhaseAction] = []

        move_sequence = list(turn.move_directions)
        if not move_sequence and turn.move_direction is not None:
            move_sequence = [turn.move_direction]

        if ITEM_VEHICLE in active_names:
            if turn.move_directions:
                move_sequence = move_sequence[:2]
            elif len(move_sequence) == 1:
                move_sequence.append(move_sequence[0])
        else:
            move_sequence = move_sequence[:1]

        for direction in move_sequence:
            desired_sequence.append(PhaseAction(action_type="move", direction=direction))

        if turn.action is not None:
            if ITEM_GOLDEN_GUN in active_names:
                for _ in range(DEFAULT_COMBAT_RULES.enemy.max_health + 1):
                    desired_sequence.append(turn.action)
            elif ITEM_SHOTGUN in active_names and turn.action.action_type == "attack":
                desired_sequence.append(turn.action)
                desired_sequence.append(turn.action)
            else:
                desired_sequence.append(turn.action)

        if ITEM_DUAL_BERETTAS in active_names and turn.action2 is not None:
            desired_sequence.append(turn.action2)

        if not desired_sequence:
            desired_sequence.append(PhaseAction(action_type="wait", direction=1))

        return [self._encode_phase_action(pa) for pa in reversed(desired_sequence)]

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
