from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .combat import DELTA_TO_DIRECTION, DIRECTION_TO_DELTA, ActiveEffect


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
    hills: frozenset[tuple[int, int]] = dataclasses.field(default_factory=frozenset)
    bushes: frozenset[tuple[int, int]] = dataclasses.field(default_factory=frozenset)
    bunkers: frozenset[tuple[int, int]] = dataclasses.field(default_factory=frozenset)
    map_items: tuple[tuple[tuple[int, int], str], ...] = ()
    inventory: tuple[str, ...] = ()
    active_effects: tuple[ActiveEffect, ...] = ()

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
    action2: PhaseAction | None = None
    activate_item: str | None = None


def action_to_delta(action_id: int) -> tuple[int, int]:
    return DIRECTION_TO_DELTA[action_id]


def delta_to_action_id(delta: tuple[int, int]) -> int:
    return DELTA_TO_DIRECTION[delta]
