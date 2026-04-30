from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .game import BattleSnapshot


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


@dataclass(frozen=True)
class UnitCombatProfile:
    max_health: int
    attack_damage: int
    attack_range: int


@dataclass(frozen=True)
class CombatRules:
    player: UnitCombatProfile
    enemy: UnitCombatProfile


DEFAULT_COMBAT_RULES = CombatRules(
    player=UnitCombatProfile(max_health=4, attack_damage=1, attack_range=1),
    enemy=UnitCombatProfile(max_health=2, attack_damage=1, attack_range=1),
)


def get_unit_profile(
    snapshot: BattleSnapshot | None,
    unit_name: str,
    position: tuple[int, int] | None = None,
    rules: CombatRules = DEFAULT_COMBAT_RULES,
) -> UnitCombatProfile:
    if unit_name == "player":
        base_profile = rules.player
    elif unit_name == "enemy":
        base_profile = rules.enemy
    else:
        raise ValueError(f"Unknown unit type: {unit_name}")

    if snapshot is None or position is None:
        return base_profile

    return UnitCombatProfile(
        max_health=max(1, base_profile.max_health + _health_bonus(snapshot, unit_name, position)),
        attack_damage=max(1, base_profile.attack_damage + _attack_damage_bonus(snapshot, unit_name, position)),
        attack_range=max(1, base_profile.attack_range + _attack_range_bonus(snapshot, unit_name, position)),
    )


def _health_bonus(
    snapshot: BattleSnapshot,
    unit_name: str,
    position: tuple[int, int],
) -> int:
    del snapshot, unit_name, position
    return 0


def _attack_damage_bonus(
    snapshot: BattleSnapshot,
    unit_name: str,
    position: tuple[int, int],
) -> int:
    del snapshot, unit_name, position
    return 0


def _attack_range_bonus(
    snapshot: BattleSnapshot,
    unit_name: str,
    position: tuple[int, int],
) -> int:
    del snapshot, unit_name, position
    return 0


def cardinal_relation(
    source: tuple[int, int],
    target: tuple[int, int],
) -> tuple[int, int] | None:
    dx = target[0] - source[0]
    dy = target[1] - source[1]

    if dx == 0 and dy == 0:
        return None
    if dx != 0 and dy != 0:
        return None

    if dx != 0:
        step = (1 if dx > 0 else -1, 0)
        distance = abs(dx)
    else:
        step = (0, 1 if dy > 0 else -1)
        distance = abs(dy)

    return DELTA_TO_DIRECTION[step], distance


def positions_between(
    source: tuple[int, int],
    target: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
    relation = cardinal_relation(source, target)
    if relation is None:
        return ()

    direction, distance = relation
    dx, dy = DIRECTION_TO_DELTA[direction]
    return tuple((source[0] + dx * step, source[1] + dy * step) for step in range(1, distance + 1))


def has_clear_line(
    source: tuple[int, int],
    target: tuple[int, int],
    blocking_positions: set[tuple[int, int]] | frozenset[tuple[int, int]] | None = None,
) -> bool:
    relation = cardinal_relation(source, target)
    if relation is None:
        return False

    if not blocking_positions:
        return True

    intermediate_tiles = positions_between(source, target)[:-1]
    return all(tile not in blocking_positions for tile in intermediate_tiles)


def find_attack_direction(
    attacker_position: tuple[int, int],
    target_position: tuple[int, int],
    attack_range: int,
    blocking_positions: set[tuple[int, int]] | frozenset[tuple[int, int]] | None = None,
) -> int | None:
    relation = cardinal_relation(attacker_position, target_position)
    if relation is None:
        return None

    direction, distance = relation
    if distance > attack_range:
        return None
    if not has_clear_line(attacker_position, target_position, blocking_positions):
        return None

    return direction


def iter_attack_tiles(
    origin: tuple[int, int],
    attack_range: int,
    width: int,
    height: int,
) -> Iterable[tuple[int, int, tuple[int, int]]]:
    for direction, (dx, dy) in DIRECTION_TO_DELTA.items():
        for distance in range(1, attack_range + 1):
            tile = (origin[0] + dx * distance, origin[1] + dy * distance)
            if 0 <= tile[0] < width and 0 <= tile[1] < height:
                yield direction, distance, tile


def positions_that_can_attack_target(
    target_position: tuple[int, int],
    attack_range: int,
    width: int,
    height: int,
    occupied_positions: set[tuple[int, int]] | frozenset[tuple[int, int]] | None = None,
    blocking_positions: set[tuple[int, int]] | frozenset[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    valid_positions: set[tuple[int, int]] = set()
    occupied_positions = occupied_positions or set()
    blocking_positions = blocking_positions or set()

    for direction, distance, _tile in iter_attack_tiles(target_position, attack_range, width, height):
        dx, dy = DIRECTION_TO_DELTA[direction]
        attacker_position = (
            target_position[0] - dx * distance,
            target_position[1] - dy * distance,
        )
        if attacker_position in occupied_positions:
            continue
        if not has_clear_line(attacker_position, target_position, blocking_positions):
            continue
        valid_positions.add(attacker_position)

    return valid_positions
