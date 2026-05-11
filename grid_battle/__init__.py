from .agents import HeuristicAgent, RandomAgent, heuristic_turn
from .mcts import MctsAgent
from .simulator import simulate_turn
from .combat import (
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
    CombatRules,
    DEFAULT_COMBAT_RULES,
    DIRECTION_NAMES,
    UnitCombatProfile,
    find_attack_action,
    find_attack_direction,
    get_unit_profile,
    positions_that_can_attack_target,
)
from .state import BattleSnapshot, PhaseAction, TurnAction, UnitState

# griddly only ships an x86_64 wheel on pypi so it breaks on arm64 mac.
# wrap the import so the rest of the package still works without it
# (simulator, agents and pcg dont need griddly).
try:
    from .game import (
        ATTACK_ACTION,
        MOVE_ACTION,
        RANGED_ATTACK_ACTION,
        WAIT_ACTION,
        GridBattleEnv,
    )
except ImportError as _griddly_import_error:  # pragma: no cover
    ATTACK_ACTION = MOVE_ACTION = RANGED_ATTACK_ACTION = WAIT_ACTION = None  # type: ignore[assignment]
    GridBattleEnv = None  # type: ignore[assignment]
    _griddly_unavailable_reason = str(_griddly_import_error)
from .pcg import (
    BASELINE_PRESETS,
    DEFAULT_LEVEL,
    MAP_SIZES,
    MAP_TYPES,
    GenerationPreset,
    GeneratedLevel,
    MapAnalysis,
    analyze_level,
    format_analysis,
    generate_level,
    generate_preset_level,
)

__all__ = [
    "ATTACK_ACTION",
    "ActiveEffect",
    "BASELINE_PRESETS",
    "BattleSnapshot",
    "CombatRules",
    "DEFAULT_LEVEL",
    "DEFAULT_COMBAT_RULES",
    "DIRECTION_NAMES",
    "GenerationPreset",
    "GeneratedLevel",
    "GridBattleEnv",
    "HeuristicAgent",
    "ITEM_DUAL_BERETTAS",
    "ITEM_DURATIONS",
    "ITEM_GOLDEN_GUN",
    "ITEM_MAP_CHARS",
    "ITEM_SHOTGUN",
    "ITEM_VEHICLE",
    "MAP_SIZES",
    "MAP_TYPES",
    "MOVE_ACTION",
    "MapAnalysis",
    "MctsAgent",
    "PhaseAction",
    "RANGED_ATTACK_ACTION",
    "RandomAgent",
    "TERRAIN_BUNKER",
    "TERRAIN_BUSH",
    "TERRAIN_HILL",
    "TERRAIN_MAP_CHARS",
    "TurnAction",
    "UnitCombatProfile",
    "UnitState",
    "WAIT_ACTION",
    "analyze_level",
    "find_attack_action",
    "find_attack_direction",
    "format_analysis",
    "generate_level",
    "generate_preset_level",
    "get_unit_profile",
    "heuristic_turn",
    "positions_that_can_attack_target",
    "simulate_turn",
]
