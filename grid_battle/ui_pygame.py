from __future__ import annotations

import math
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pygame

from .combat import (
    DEFAULT_COMBAT_RULES,
    DIRECTION_NAMES,
    DIRECTION_TO_DELTA,
    ITEM_DUAL_BERETTAS,
    ITEM_GOLDEN_GUN,
    ITEM_SHOTGUN,
    ITEM_VEHICLE,
    TERRAIN_BUNKER,
    TERRAIN_BUSH,
    TERRAIN_HILL,
    ActiveEffect,
    find_attack_action,
)
from .game import BattleSnapshot, GridBattleEnv, PhaseAction, TurnAction

Color = tuple[int, int, int]


PALETTE = {
    "bg_top": (22, 28, 39),
    "bg_bottom": (49, 58, 74),
    "bg_glow": (182, 150, 93, 24),
    "board_shell": (36, 43, 57),
    "board_border": (156, 130, 87),
    "board_inner": (61, 69, 84),
    "board_label": (208, 190, 156),
    "tile_dark": (73, 79, 90),
    "tile_light": (83, 89, 100),
    "tile_inner_dark": (89, 96, 108),
    "tile_inner_light": (99, 105, 118),
    "grid_line": (133, 121, 100),
    "panel_fill": (30, 37, 50),
    "panel_border": (156, 130, 87),
    "panel_inner": (40, 47, 61),
    "panel_header": (26, 32, 44),
    "card_fill": (231, 223, 205),
    "card_fill_soft": (221, 212, 193),
    "card_border": (177, 161, 130),
    "ink": (44, 49, 58),
    "ink_soft": (86, 91, 101),
    "headline": (247, 238, 217),
    "headline_soft": (210, 194, 161),
    "accent_brass": (188, 153, 95),
    "accent_brass_light": (231, 208, 158),
    "accent_teal": (108, 153, 154),
    "accent_teal_light": (180, 220, 218),
    "accent_red": (169, 98, 90),
    "accent_red_light": (233, 195, 188),
    "accent_plum": (132, 108, 150),
    "accent_plum_light": (214, 196, 227),
    "button_primary_fill": (189, 155, 96),
    "button_primary_hover": (205, 172, 114),
    "button_primary_text": (34, 39, 47),
    "button_secondary_fill": (70, 79, 96),
    "button_secondary_hover": (83, 94, 114),
    "button_secondary_text": (237, 233, 224),
    "button_item_fill": (225, 217, 199),
    "button_item_hover": (235, 228, 212),
    "button_item_text": (46, 51, 59),
    "button_selected_fill": (149, 92, 81),
    "button_selected_hover": (164, 103, 92),
    "button_selected_text": (249, 241, 227),
    "button_disabled_fill": (79, 83, 91),
    "button_disabled_border": (112, 111, 108),
    "button_disabled_text": (190, 188, 181),
    "tooltip_fill": (244, 238, 222),
    "tooltip_border": (187, 167, 124),
    "tooltip_title": (66, 54, 40),
    "tooltip_text": (52, 50, 54),
    "line_shadow": (12, 16, 24),
}


ITEM_LABELS = {
    ITEM_GOLDEN_GUN: "Golden Gun",
    ITEM_DUAL_BERETTAS: "Dual Berettas",
    ITEM_SHOTGUN: "Shotgun",
    ITEM_VEHICLE: "Vehicle",
}

TERRAIN_LABELS = {
    TERRAIN_HILL: "Hill",
    TERRAIN_BUSH: "Bush",
    TERRAIN_BUNKER: "Bunker",
}


@dataclass(frozen=True)
class UiButton:
    name: str
    label: str
    rect: pygame.Rect
    enabled: bool = True
    payload: str | None = None
    selected: bool = False


@dataclass(frozen=True)
class AttackOption:
    target_position: tuple[int, int]
    action: PhaseAction


@dataclass(frozen=True)
class MoveOption:
    destination: tuple[int, int]
    directions: tuple[int, ...]
    uses_vehicle: bool = False


@dataclass(frozen=True)
class TurnFeedback:
    started_at: int
    duration_ms: int
    move_origin: tuple[int, int] | None = None
    move_directions: tuple[int, ...] = ()
    move_destination: tuple[int, int] | None = None
    attack_origin: tuple[int, int] | None = None
    attack_targets: tuple[tuple[tuple[int, int], str], ...] = ()
    player_final_tile: tuple[int, int] | None = None
    player_hit: bool = False
    activated_item: str | None = None


class SpriteAtlas:
    def __init__(self, tile_size: int):
        self.tile_size = tile_size
        self._cache: dict[str, pygame.Surface] = {}
        self._label_font = pygame.font.Font(None, max(18, tile_size // 4))
        self._asset_dir = Path(__file__).resolve().parent.parent / "assets" / "sprites"

    def get(self, key: str) -> pygame.Surface:
        if key not in self._cache:
            loaded = self._load_external_asset(key)
            if loaded is not None:
                self._cache[key] = loaded
            else:
                surface = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
                draw_fn = getattr(self, f"_draw_{key}", None)
                if draw_fn is None:
                    draw_fn = self._draw_unknown
                draw_fn(surface)
                self._cache[key] = surface
        return self._cache[key]

    def _load_external_asset(self, key: str) -> pygame.Surface | None:
        asset_path = self._asset_dir / f"{key}.png"
        if not asset_path.exists():
            return None

        image = pygame.image.load(str(asset_path))
        if pygame.display.get_surface() is not None:
            image = image.convert_alpha()

        canvas = pygame.Surface((self.tile_size, self.tile_size), pygame.SRCALPHA)
        safe_size = self._s(0.84)
        target_width, target_height = self._fit_inside(image.get_size(), safe_size, safe_size)
        scaled = pygame.transform.smoothscale(image, (target_width, target_height))
        rect = scaled.get_rect(center=(self.tile_size // 2, self.tile_size // 2))
        canvas.blit(scaled, rect)
        return canvas

    @staticmethod
    def _fit_inside(size: tuple[int, int], max_width: int, max_height: int) -> tuple[int, int]:
        width, height = size
        if width <= 0 or height <= 0:
            return max(1, max_width), max(1, max_height)
        scale = min(max_width / width, max_height / height)
        return max(1, int(round(width * scale))), max(1, int(round(height * scale)))

    def _s(self, factor: float) -> int:
        return max(1, int(round(self.tile_size * factor)))

    def _circle(self, surface: pygame.Surface, color: Color, center: tuple[float, float], radius: float, width: int = 0) -> None:
        pygame.draw.circle(
            surface,
            color,
            (int(round(center[0])), int(round(center[1]))),
            max(1, int(round(radius))),
            width,
        )

    def _draw_token_base(
        self,
        surface: pygame.Surface,
        *,
        field_color: Color,
        rim_color: Color,
        inner_ring_color: Color,
        glow_color: tuple[int, int, int, int],
    ) -> pygame.Rect:
        size = self.tile_size
        center = (size * 0.5, size * 0.46)

        shadow = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (8, 12, 20, 88), (self._s(0.18), self._s(0.72), self._s(0.64), self._s(0.14)))
        pygame.draw.circle(shadow, glow_color, (self._s(0.5), self._s(0.44)), self._s(0.29))
        surface.blit(shadow, (0, 0))

        self._circle(surface, (24, 30, 40), center, size * 0.31)
        self._circle(surface, rim_color, center, size * 0.29)
        self._circle(surface, inner_ring_color, center, size * 0.25)
        self._circle(surface, field_color, center, size * 0.22)
        pygame.draw.arc(
            surface,
            (255, 255, 255, 66),
            pygame.Rect(self._s(0.27), self._s(0.18), self._s(0.42), self._s(0.28)),
            3.3,
            5.9,
            max(1, self._s(0.035)),
        )

        for dot_x, dot_y in ((0.34, 0.28), (0.66, 0.28), (0.34, 0.64), (0.66, 0.64)):
            self._circle(surface, rim_color, (size * dot_x, size * dot_y), size * 0.018)

        return pygame.Rect(self._s(0.22), self._s(0.18), self._s(0.56), self._s(0.56))

    def _draw_marker_plaque(
        self,
        surface: pygame.Surface,
        *,
        fill_color: Color,
        edge_color: Color,
        inner_color: Color,
    ) -> pygame.Rect:
        outer = pygame.Rect(self._s(0.18), self._s(0.18), self._s(0.64), self._s(0.64))
        shadow = outer.move(0, self._s(0.05))
        pygame.draw.rect(surface, (11, 16, 22, 92), shadow, border_radius=self._s(0.12))
        pygame.draw.rect(surface, edge_color, outer, border_radius=self._s(0.12))
        inner = outer.inflate(-self._s(0.06), -self._s(0.06))
        pygame.draw.rect(surface, fill_color, inner, border_radius=self._s(0.1))
        face = inner.inflate(-self._s(0.06), -self._s(0.06))
        pygame.draw.rect(surface, inner_color, face, border_radius=self._s(0.08))
        pygame.draw.line(
            surface,
            (255, 255, 255, 70),
            (face.left + self._s(0.04), face.top + self._s(0.04)),
            (face.right - self._s(0.04), face.top + self._s(0.04)),
            max(1, self._s(0.025)),
        )
        return face

    def _draw_item_chip(
        self,
        surface: pygame.Surface,
        *,
        ring_color: Color,
        core_color: Color,
        accent_color: Color,
    ) -> pygame.Rect:
        size = self.tile_size
        center = (size * 0.5, size * 0.5)
        pygame.draw.ellipse(surface, (10, 15, 22, 88), (self._s(0.22), self._s(0.7), self._s(0.56), self._s(0.12)))
        self._circle(surface, (33, 28, 22), center, size * 0.245)
        self._circle(surface, ring_color, center, size * 0.225)
        self._circle(surface, core_color, center, size * 0.18)
        self._circle(surface, accent_color, center, size * 0.185, max(1, self._s(0.02)))
        return pygame.Rect(self._s(0.3), self._s(0.3), self._s(0.4), self._s(0.4))

    def _draw_player(self, surface: pygame.Surface) -> None:
        size = self.tile_size
        emblem = self._draw_token_base(
            surface,
            field_color=(70, 108, 192),
            rim_color=(208, 174, 118),
            inner_ring_color=(232, 223, 204),
            glow_color=(113, 172, 255, 36),
        )
        shield = [
            (emblem.centerx, emblem.top + self._s(0.05)),
            (emblem.left + self._s(0.08), emblem.top + self._s(0.14)),
            (emblem.left + self._s(0.1), emblem.centery + self._s(0.03)),
            (emblem.centerx, emblem.bottom - self._s(0.04)),
            (emblem.right - self._s(0.1), emblem.centery + self._s(0.03)),
            (emblem.right - self._s(0.08), emblem.top + self._s(0.14)),
        ]
        pygame.draw.polygon(surface, (246, 241, 229), shield)
        pygame.draw.polygon(surface, (186, 153, 94), shield, max(1, self._s(0.03)))
        pygame.draw.line(
            surface,
            (70, 108, 192),
            (emblem.centerx, emblem.top + self._s(0.1)),
            (emblem.centerx, emblem.bottom - self._s(0.08)),
            max(1, self._s(0.03)),
        )
        pygame.draw.line(
            surface,
            (70, 108, 192),
            (emblem.left + self._s(0.13), emblem.centery - self._s(0.02)),
            (emblem.right - self._s(0.13), emblem.centery - self._s(0.02)),
            max(1, self._s(0.03)),
        )
        self._circle(surface, (255, 232, 166), (size * 0.5, size * 0.26), size * 0.03)

    def _draw_enemy(self, surface: pygame.Surface) -> None:
        size = self.tile_size
        emblem = self._draw_token_base(
            surface,
            field_color=(163, 76, 73),
            rim_color=(208, 174, 118),
            inner_ring_color=(236, 223, 204),
            glow_color=(204, 106, 96, 32),
        )
        left_horn = [
            (emblem.left + self._s(0.08), emblem.top + self._s(0.14)),
            (emblem.left + self._s(0.03), emblem.top + self._s(0.03)),
            (emblem.left + self._s(0.16), emblem.top + self._s(0.09)),
        ]
        right_horn = [
            (emblem.right - self._s(0.08), emblem.top + self._s(0.14)),
            (emblem.right - self._s(0.03), emblem.top + self._s(0.03)),
            (emblem.right - self._s(0.16), emblem.top + self._s(0.09)),
        ]
        pygame.draw.polygon(surface, (255, 220, 162), left_horn)
        pygame.draw.polygon(surface, (255, 220, 162), right_horn)
        mask = [
            (emblem.centerx, emblem.top + self._s(0.08)),
            (emblem.left + self._s(0.12), emblem.top + self._s(0.2)),
            (emblem.left + self._s(0.16), emblem.centery + self._s(0.06)),
            (emblem.centerx, emblem.bottom - self._s(0.05)),
            (emblem.right - self._s(0.16), emblem.centery + self._s(0.06)),
            (emblem.right - self._s(0.12), emblem.top + self._s(0.2)),
        ]
        pygame.draw.polygon(surface, (247, 236, 219), mask)
        pygame.draw.polygon(surface, (110, 44, 43), mask, max(1, self._s(0.03)))
        pygame.draw.line(
            surface,
            (117, 36, 34),
            (emblem.left + self._s(0.18), emblem.top + self._s(0.2)),
            (emblem.centerx - self._s(0.03), emblem.centery - self._s(0.01)),
            max(1, self._s(0.03)),
        )
        pygame.draw.line(
            surface,
            (117, 36, 34),
            (emblem.right - self._s(0.18), emblem.top + self._s(0.2)),
            (emblem.centerx + self._s(0.03), emblem.centery - self._s(0.01)),
            max(1, self._s(0.03)),
        )
        pygame.draw.arc(
            surface,
            (117, 36, 34),
            pygame.Rect(emblem.left + self._s(0.15), emblem.centery - self._s(0.02), self._s(0.26), self._s(0.18)),
            0.2,
            2.9,
            max(1, self._s(0.03)),
        )

    def _draw_wall(self, surface: pygame.Surface) -> None:
        outer = pygame.Rect(self._s(0.08), self._s(0.1), self._s(0.84), self._s(0.78))
        pygame.draw.rect(surface, (43, 48, 58), outer.move(0, self._s(0.04)), border_radius=self._s(0.12))
        pygame.draw.rect(surface, (94, 101, 114), outer, border_radius=self._s(0.12))
        inner = outer.inflate(-self._s(0.08), -self._s(0.08))
        pygame.draw.rect(surface, (126, 133, 149), inner, border_radius=self._s(0.1))
        for row in range(3):
            y = inner.top + self._s(0.12) + row * self._s(0.16)
            pygame.draw.line(surface, (210, 214, 225), (inner.left + self._s(0.04), y), (inner.right - self._s(0.04), y), max(1, self._s(0.02)))
        for col in range(4):
            x = inner.left + self._s(0.08) + col * self._s(0.12)
            pygame.draw.line(surface, (84, 90, 103), (x, inner.top + self._s(0.02)), (x, inner.bottom - self._s(0.02)), max(1, self._s(0.02)))

    def _draw_hill(self, surface: pygame.Surface) -> None:
        face = self._draw_marker_plaque(
            surface,
            fill_color=(205, 176, 119),
            edge_color=(162, 130, 82),
            inner_color=(243, 224, 173),
        )
        ridge_back = [
            (face.left + self._s(0.04), face.bottom - self._s(0.08)),
            (face.centerx - self._s(0.02), face.top + self._s(0.08)),
            (face.right - self._s(0.08), face.bottom - self._s(0.08)),
        ]
        ridge_front = [
            (face.left + self._s(0.12), face.bottom - self._s(0.12)),
            (face.centerx + self._s(0.07), face.top + self._s(0.14)),
            (face.right - self._s(0.04), face.bottom - self._s(0.12)),
        ]
        pygame.draw.polygon(surface, (145, 106, 58), ridge_back)
        pygame.draw.polygon(surface, (187, 145, 86), ridge_front)

    def _draw_bush(self, surface: pygame.Surface) -> None:
        face = self._draw_marker_plaque(
            surface,
            fill_color=(120, 157, 115),
            edge_color=(91, 119, 85),
            inner_color=(206, 228, 188),
        )
        leaf_color = (78, 117, 73)
        accent = (117, 159, 109)
        self._circle(surface, leaf_color, (face.left + self._s(0.12), face.centery + self._s(0.05)), self.tile_size * 0.085)
        self._circle(surface, accent, (face.centerx, face.top + self._s(0.18)), self.tile_size * 0.095)
        self._circle(surface, leaf_color, (face.right - self._s(0.12), face.centery + self._s(0.04)), self.tile_size * 0.08)
        pygame.draw.rect(
            surface,
            (84, 98, 69),
            (face.left + self._s(0.14), face.bottom - self._s(0.12), self._s(0.28), self._s(0.06)),
            border_radius=self._s(0.03),
        )

    def _draw_bunker(self, surface: pygame.Surface) -> None:
        face = self._draw_marker_plaque(
            surface,
            fill_color=(120, 130, 145),
            edge_color=(84, 94, 108),
            inner_color=(210, 216, 221),
        )
        body = pygame.Rect(face.left + self._s(0.05), face.top + self._s(0.13), self._s(0.38), self._s(0.18))
        pygame.draw.rect(surface, (101, 108, 120), body, border_radius=self._s(0.06))
        slit = pygame.Rect(face.left + self._s(0.12), face.top + self._s(0.2), self._s(0.24), self._s(0.05))
        pygame.draw.rect(surface, (35, 39, 48), slit, border_radius=self._s(0.03))
        roof = [
            (body.left + self._s(0.02), body.top),
            (body.right + self._s(0.04), body.top),
            (body.right - self._s(0.02), body.top - self._s(0.08)),
            (body.left + self._s(0.08), body.top - self._s(0.08)),
        ]
        pygame.draw.polygon(surface, (76, 84, 96), roof)

    def _draw_item_golden_gun(self, surface: pygame.Surface) -> None:
        icon = self._draw_item_chip(
            surface,
            ring_color=(186, 146, 64),
            core_color=(246, 229, 188),
            accent_color=(226, 195, 111),
        )
        pygame.draw.rect(
            surface,
            (164, 120, 33),
            (icon.left + self._s(0.02), icon.centery - self._s(0.03), self._s(0.18), self._s(0.06)),
            border_radius=self._s(0.02),
        )
        pygame.draw.rect(
            surface,
            (205, 168, 77),
            (icon.centerx - self._s(0.01), icon.top + self._s(0.08), self._s(0.16), self._s(0.08)),
            border_radius=self._s(0.03),
        )
        pygame.draw.rect(
            surface,
            (141, 96, 28),
            (icon.left + self._s(0.03), icon.centery, self._s(0.07), self._s(0.12)),
            border_radius=self._s(0.02),
        )
        sparkle = [
            (icon.right - self._s(0.03), icon.top + self._s(0.04)),
            (icon.right - self._s(0.01), icon.top + self._s(0.08)),
            (icon.right - self._s(0.05), icon.top + self._s(0.08)),
        ]
        pygame.draw.polygon(surface, (255, 235, 171), sparkle)

    def _draw_item_dual_berettas(self, surface: pygame.Surface) -> None:
        icon = self._draw_item_chip(
            surface,
            ring_color=(123, 129, 148),
            core_color=(229, 224, 214),
            accent_color=(196, 193, 187),
        )
        for offset in (icon.left + self._s(0.06), icon.left + self._s(0.18)):
            pygame.draw.rect(
                surface,
                (95, 103, 120),
                (offset, icon.top + self._s(0.05), self._s(0.07), self._s(0.16)),
                border_radius=self._s(0.03),
            )
            pygame.draw.rect(
                surface,
                (48, 53, 62),
                (offset + self._s(0.02), icon.top + self._s(0.16), self._s(0.05), self._s(0.12)),
                border_radius=self._s(0.02),
            )
            pygame.draw.rect(
                surface,
                (196, 201, 208),
                (offset - self._s(0.02), icon.top + self._s(0.13), self._s(0.11), self._s(0.04)),
                border_radius=self._s(0.02),
            )

    def _draw_item_shotgun(self, surface: pygame.Surface) -> None:
        icon = self._draw_item_chip(
            surface,
            ring_color=(115, 96, 67),
            core_color=(236, 226, 208),
            accent_color=(200, 182, 138),
        )
        pygame.draw.rect(
            surface,
            (87, 96, 109),
            (icon.left + self._s(0.08), icon.centery - self._s(0.04), self._s(0.22), self._s(0.06)),
            border_radius=self._s(0.02),
        )
        pygame.draw.rect(
            surface,
            (209, 214, 221),
            (icon.left + self._s(0.27), icon.centery - self._s(0.03), self._s(0.07), self._s(0.04)),
            border_radius=self._s(0.02),
        )
        pygame.draw.rect(
            surface,
            (158, 122, 72),
            (icon.left + self._s(0.05), icon.centery - self._s(0.01), self._s(0.06), self._s(0.11)),
            border_radius=self._s(0.02),
        )

    def _draw_item_vehicle(self, surface: pygame.Surface) -> None:
        icon = self._draw_item_chip(
            surface,
            ring_color=(94, 124, 163),
            core_color=(224, 230, 238),
            accent_color=(165, 191, 226),
        )
        body = pygame.Rect(icon.left + self._s(0.04), icon.centery - self._s(0.03), self._s(0.26), self._s(0.11))
        pygame.draw.rect(surface, (107, 143, 197), body, border_radius=self._s(0.04))
        cab = pygame.Rect(icon.left + self._s(0.12), icon.top + self._s(0.07), self._s(0.12), self._s(0.08))
        pygame.draw.rect(surface, (76, 104, 148), cab, border_radius=self._s(0.03))
        for wheel_x in (body.left + self._s(0.05), body.right - self._s(0.05)):
            self._circle(surface, (37, 42, 50), (wheel_x, body.bottom), self.tile_size * 0.045)
            self._circle(surface, (201, 208, 220), (wheel_x, body.bottom), self.tile_size * 0.02)

    def _draw_unknown(self, surface: pygame.Surface) -> None:
        self._draw_item_chip(
            surface,
            ring_color=(108, 125, 155),
            core_color=(224, 230, 239),
            accent_color=(174, 194, 224),
        )
        label = self._label_font.render("?", True, (232, 241, 255))
        label_rect = label.get_rect(center=(self.tile_size // 2, self.tile_size // 2))
        surface.blit(label, label_rect)


class GridBattleWindow:
    def __init__(
        self,
        env: GridBattleEnv,
        max_steps: int,
        window_title: str = "GridBattle UI Demo",
        tile_size: int = 68,
        auto_close_ms: int = 0,
    ):
        pygame.init()
        pygame.font.init()
        pygame.display.set_caption(window_title)

        self.env = env
        self.max_steps = max_steps
        self.tile_size = max(48, tile_size)
        self.auto_close_ms = max(0, auto_close_ms)
        self.margin = 24
        self.sidebar_width = 350
        self.clock = pygame.time.Clock()
        self.started_at = pygame.time.get_ticks()

        self.title_font = pygame.font.Font(None, 40)
        self.section_font = pygame.font.Font(None, 28)
        self.body_font = pygame.font.Font(None, 24)
        self.small_font = pygame.font.Font(None, 20)
        self.sprite_atlas = SpriteAtlas(self.tile_size)

        self.snapshot = self.env.reset()
        self.selected_player = False
        self.planned_move_directions: tuple[int, ...] = ()
        self.selected_item: str | None = None
        self.vehicle_auto_selected = False
        self.primary_attack: AttackOption | None = None
        self.secondary_attack: AttackOption | None = None
        self.turn_feedback: TurnFeedback | None = None
        self.status_message = "Click the player to start planning a turn."
        self.last_turn_summary = "No turn taken yet."
        self.grid_line_color = PALETTE["grid_line"]

        board_width = self.snapshot.width * self.tile_size
        board_height = self.snapshot.height * self.tile_size
        action_panel_height = 400
        window_width = board_width + self.sidebar_width + self.margin * 3
        window_height = max(board_height + action_panel_height + self.margin * 2, 1020)

        self.screen = pygame.display.set_mode((window_width, window_height))
        self.running = True

    def run(self) -> None:
        while self.running:
            if self.auto_close_ms and pygame.time.get_ticks() - self.started_at >= self.auto_close_ms:
                self.running = False

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_keydown(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_left_click(event.pos)

            self._draw()
            self.clock.tick(60)

        pygame.quit()

    def _handle_keydown(self, key: int) -> None:
        if self._feedback_active() and key != pygame.K_r:
            return
        if key == pygame.K_ESCAPE:
            if self._has_move_preview():
                self._cancel_move_preview("Returned to the original tile. Choose a move or attack.")
            else:
                self._clear_selection("Selection cleared.")
        elif key == pygame.K_RETURN:
            if self.selected_player and self.snapshot.player is not None and not self._is_game_over():
                self._commit_turn()
        elif key == pygame.K_r:
            self._reset()
        elif key == pygame.K_SPACE and self.snapshot.player is not None and not self._is_game_over():
            self.selected_player = True
            self.status_message = "Player selected. Choose a destination, attack target, or item."

    def _handle_left_click(self, mouse_position: tuple[int, int]) -> None:
        if self._feedback_active():
            return
        for button in self._interactive_buttons():
            if button.rect.collidepoint(mouse_position):
                if button.enabled:
                    self._handle_button(button)
                return

        tile = self._screen_to_tile(mouse_position)
        if tile is None:
            return

        self._handle_grid_click(tile)

    def _handle_button(self, button: UiButton) -> None:
        if button.name == "reset":
            self._reset()
            return
        if button.name == "cancel_move":
            self._cancel_move_preview("Returned to the original tile. Choose a move or attack.")
            return
        if button.name == "cancel":
            self._clear_selection("Selection cleared.")
            return
        if button.name == "end_turn":
            if self.selected_player and self.snapshot.player is not None and not self._is_game_over():
                self._commit_turn()
            return
        if button.name == "item" and button.payload is not None:
            self._toggle_item(button.payload)

    def _handle_grid_click(self, tile: tuple[int, int]) -> None:
        if self.snapshot.player is None:
            self.status_message = "The player has been defeated. Press Reset to try again."
            return
        if self._is_game_over():
            self.status_message = "Combat is over. Press Reset to play again."
            return

        origin = self.snapshot.player.position

        if not self.selected_player:
            if tile == origin:
                self.selected_player = True
                self.status_message = "Player selected. Choose a destination, attack target, or item."
            else:
                self.status_message = "Click the player to begin the turn."
            return

        previewing_move = self._has_move_preview()
        move_options = self._move_options() if not self.primary_attack else {}
        attack_options = self._attack_options()

        if previewing_move:
            projected = self._projected_player_position()
            if tile == origin:
                self._cancel_move_preview("Returned to the original tile. Choose a move or attack.")
                return
            if tile == projected:
                self.status_message = "Preview active. Click a red enemy to attack, End Turn to confirm, or Cancel Move to go back."
                return

        if tile == origin and not previewing_move:
            self.status_message = "Player selected. Choose a destination, attack target, or item."
            return

        if tile in move_options:
            move_option = move_options[tile]
            self.planned_move_directions = move_option.directions
            self._sync_vehicle_selection_for_move(move_option)
            self.primary_attack = None
            self.secondary_attack = None
            if self._attack_options():
                self.status_message = "Preview active from the destination tile. Click a red enemy, End Turn, or Cancel Move."
            else:
                self.status_message = "Preview active. No enemy is in range from that tile, so End Turn will move only."
            return

        if self.primary_attack is not None and self._can_dual_attack() and tile in attack_options and tile != self.primary_attack.target_position:
            self.secondary_attack = attack_options[tile]
            self._commit_turn()
            return

        if tile in attack_options:
            chosen_attack = attack_options[tile]
            if self._can_dual_attack():
                self.primary_attack = chosen_attack
                self.secondary_attack = None
                remaining = self._secondary_attack_options()
                if remaining:
                    self.status_message = "Primary attack selected. Choose a second red enemy or press End Turn."
                else:
                    self.status_message = "Primary attack selected. No second target is available, so End Turn will confirm it."
                return
            self.primary_attack = chosen_attack
            self._commit_turn()
            return

        if self.primary_attack is not None:
            self.status_message = "Choose a valid second target, End Turn, or Clear Selection."
            return

        if self.planned_move_directions and not self._attack_options():
            self.status_message = "No enemy is in attack range from the planned destination."
        else:
            self.status_message = "That tile is not available for the current step."

    def _toggle_item(self, item_name: str) -> None:
        if item_name not in self.snapshot.inventory:
            return
        if item_name == ITEM_VEHICLE:
            self.status_message = "Vehicle is used automatically when you choose a 2-tile move."
            return
        if self.vehicle_auto_selected and self.planned_move_directions:
            self.status_message = "Cancel the 2-tile vehicle move first if you want to use another item."
            return

        if self.selected_item == item_name:
            self.selected_item = None
            self.vehicle_auto_selected = False
            self.primary_attack = None
            self.secondary_attack = None
            self.status_message = f"Cancelled {self._pretty_item_name(item_name)}."
            return

        self.selected_item = item_name
        self.vehicle_auto_selected = False
        self.primary_attack = None
        self.secondary_attack = None
        self.status_message = f"{self._pretty_item_name(item_name)} will activate this turn."

    def _reset(self) -> None:
        self._clear_selection("Click the player to start planning a turn.")
        self.last_turn_summary = "No turn taken yet."
        self.turn_feedback = None
        self.snapshot = self.env.reset()

    def _cancel_move_preview(self, message: str) -> None:
        self.planned_move_directions = ()
        self._clear_auto_vehicle_selection()
        self.primary_attack = None
        self.secondary_attack = None
        self.selected_player = self.snapshot.player is not None and not self._is_game_over()
        self.status_message = message

    def _clear_selection(self, message: str) -> None:
        self.selected_player = False
        self.planned_move_directions = ()
        self.selected_item = None
        self.vehicle_auto_selected = False
        self.primary_attack = None
        self.secondary_attack = None
        self.status_message = message

    def _commit_turn(self) -> None:
        previous_snapshot = self.snapshot
        activated_item = self.selected_item
        move_directions = self.planned_move_directions
        primary_attack = self.primary_attack
        secondary_attack = self.secondary_attack
        turn_action = TurnAction(
            move_direction=move_directions[0] if move_directions else None,
            move_directions=move_directions,
            action=primary_attack.action if primary_attack is not None else None,
            action2=secondary_attack.action if secondary_attack is not None else None,
            activate_item=self.selected_item,
        )
        snapshot, reward, done, info = self.env.step(turn_action)
        del reward

        self.turn_feedback = self._build_turn_feedback(
            previous_snapshot,
            snapshot,
            move_directions=move_directions,
            primary_attack=primary_attack,
            secondary_attack=secondary_attack,
            activated_item=activated_item,
        )
        self.snapshot = snapshot
        self.selected_player = False
        self.planned_move_directions = ()
        self.selected_item = None
        self.vehicle_auto_selected = False
        self.primary_attack = None
        self.secondary_attack = None
        self.last_turn_summary = self._describe_turn(previous_snapshot, snapshot, info.get("History", []), activated_item)

        if snapshot.player is None:
            self.status_message = "The player was defeated. Press Reset to try again."
        elif snapshot.remaining_enemies == 0:
            self.status_message = "All enemies defeated. Press Reset to play again."
        elif done and snapshot.player_turns >= self.max_steps:
            self.status_message = "Reached the turn limit. Press Reset to try another run."
        else:
            self.status_message = self.last_turn_summary

    def _draw(self) -> None:
        self._current_feedback()
        self.screen.fill((17, 21, 29))
        self._draw_background()
        self._draw_board()
        self._draw_action_panel()
        self._draw_sidebar()
        pygame.display.flip()

    def _draw_background(self) -> None:
        width, height = self.screen.get_size()
        for index in range(height):
            blend = index / max(1, height - 1)
            color = tuple(
                int(PALETTE["bg_top"][channel] + (PALETTE["bg_bottom"][channel] - PALETTE["bg_top"][channel]) * blend)
                for channel in range(3)
            )
            pygame.draw.line(self.screen, color, (0, index), (width, index))

        glow_center = (
            self.margin + self.snapshot.width * self.tile_size // 2,
            self.margin + self.snapshot.height * self.tile_size // 2,
        )
        glow = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.circle(glow, PALETTE["bg_glow"], glow_center, max(self.snapshot.width, self.snapshot.height) * self.tile_size // 2)
        self.screen.blit(glow, (0, 0))

    def _draw_board(self) -> None:
        board_rect = pygame.Rect(
            self.margin - 10,
            self.margin - 10,
            self.snapshot.width * self.tile_size + 20,
            self.snapshot.height * self.tile_size + 20,
        )
        self._draw_panel_shell(board_rect, PALETTE["board_shell"], PALETTE["board_border"], radius=22, inset_fill=PALETTE["board_inner"])

        mouse_tile = self._screen_to_tile(pygame.mouse.get_pos())
        previewing_move = self._has_move_preview()
        move_options = self._move_options() if self.selected_player and self.primary_attack is None else {}
        attack_options = self._attack_options()
        secondary_options = self._secondary_attack_options()
        projected_position = self._projected_player_position()
        pulse = self._pulse(0.0, 1.0, period_ms=1450)

        for y in range(self.snapshot.height):
            for x in range(self.snapshot.width):
                tile = (x, y)
                rect = self._tile_rect(tile)
                self._draw_floor(rect, tile)
                self._draw_terrain(tile, rect)
                self._draw_map_item(tile, rect)

                if tile == mouse_tile:
                    self._draw_tile_overlay(rect, (255, 255, 255, int(16 + 20 * pulse)))
                if previewing_move and self.snapshot.player is not None and tile == self.snapshot.player.position:
                    self._draw_tile_overlay(rect, (154, 168, 184, 44))
                    self._draw_tile_outline(rect, (220, 218, 206), 2)
                elif self.snapshot.player is not None and tile == self.snapshot.player.position and self.selected_player:
                    self._draw_tile_outline(rect, PALETTE["accent_brass_light"], 2 + int(round(3 * pulse)))
                if tile in move_options:
                    move_option = move_options[tile]
                    alpha = 88 if tile == mouse_tile else int(50 + 24 * pulse)
                    outline = 3 if tile == mouse_tile else 2
                    self._draw_tile_overlay(rect, (108, 153, 154, alpha))
                    self._draw_tile_outline(rect, PALETTE["accent_teal_light"], outline)
                    if move_option.uses_vehicle:
                        self._draw_tile_overlay(rect, (188, 153, 95, 24))
                if self.planned_move_directions and tile == projected_position:
                    self._draw_tile_overlay(rect, (188, 153, 95, int(74 + 32 * pulse)))
                    self._draw_tile_outline(rect, PALETTE["accent_brass_light"], 3 + int(round(pulse)))
                if tile in attack_options:
                    alpha = 94 if tile == mouse_tile else int(52 + 22 * pulse)
                    outline = 3 if tile == mouse_tile else 2
                    self._draw_tile_overlay(rect, (169, 98, 90, alpha))
                    self._draw_tile_outline(rect, PALETTE["accent_red_light"], outline)
                if self.primary_attack is not None and tile == self.primary_attack.target_position:
                    self._draw_tile_overlay(rect, (188, 153, 95, int(84 + 24 * pulse)))
                    self._draw_tile_outline(rect, PALETTE["accent_brass_light"], 3)
                if self.primary_attack is not None and tile in secondary_options:
                    alpha = 98 if tile == mouse_tile else int(56 + 24 * pulse)
                    outline = 3 if tile == mouse_tile else 2
                    self._draw_tile_overlay(rect, (132, 108, 150, alpha))
                    self._draw_tile_outline(rect, PALETTE["accent_plum_light"], outline)

                pygame.draw.rect(self.screen, self.grid_line_color, rect, 1, border_radius=12)

        if self.snapshot.player is not None:
            for enemy in self.snapshot.enemies:
                self._draw_unit("enemy", enemy.position, enemy.health, DEFAULT_COMBAT_RULES.enemy.max_health)

            if previewing_move:
                self._draw_preview_player()
            else:
                self._draw_unit("player", self.snapshot.player.position, self.snapshot.player.health, DEFAULT_COMBAT_RULES.player.max_health)

        self._draw_turn_feedback()
        self._draw_board_connectors(mouse_tile, move_options, attack_options, secondary_options)
        self._draw_hover_tooltip(mouse_tile, move_options, attack_options, secondary_options)
        self._draw_board_labels()

    def _draw_floor(self, rect: pygame.Rect, tile: tuple[int, int]) -> None:
        base_color = PALETTE["tile_light"] if (tile[0] + tile[1]) % 2 == 0 else PALETTE["tile_dark"]
        pygame.draw.rect(self.screen, base_color, rect, border_radius=12)
        inner = rect.inflate(-8, -8)
        shimmer = PALETTE["tile_inner_light"] if (tile[0] + tile[1]) % 2 == 0 else PALETTE["tile_inner_dark"]
        pygame.draw.rect(self.screen, shimmer, inner, border_radius=10)

    def _draw_terrain(self, tile: tuple[int, int], rect: pygame.Rect) -> None:
        if tile in self.snapshot.hills:
            self.screen.blit(self.sprite_atlas.get("hill"), rect.topleft)
        elif tile in self.snapshot.bushes:
            self.screen.blit(self.sprite_atlas.get("bush"), rect.topleft)
        elif tile in self.snapshot.bunkers:
            self.screen.blit(self.sprite_atlas.get("bunker"), rect.topleft)
        elif tile in self.snapshot.walls:
            self.screen.blit(self.sprite_atlas.get("wall"), rect.topleft)

    def _draw_map_item(self, tile: tuple[int, int], rect: pygame.Rect) -> None:
        item_name = dict(self.snapshot.map_items).get(tile)
        if item_name is None:
            return
        key = f"item_{item_name}"
        self.screen.blit(self.sprite_atlas.get(key), rect.topleft)

    def _draw_unit(self, kind: str, position: tuple[int, int], current_health: int, max_health: int) -> None:
        rect = self._tile_rect(position)
        sprite = self.sprite_atlas.get(kind)
        self.screen.blit(sprite, rect.topleft)
        self._draw_health_bar(rect, current_health, max_health, kind == "player")

    def _draw_preview_player(self) -> None:
        if self.snapshot.player is None:
            return

        origin_rect = self._tile_rect(self.snapshot.player.position)
        projected_position = self._projected_player_position()
        projected_rect = self._tile_rect(projected_position)

        ghost_sprite = self.sprite_atlas.get("player").copy()
        ghost_sprite.set_alpha(80)
        self.screen.blit(ghost_sprite, origin_rect.topleft)

        glow = pygame.Surface(projected_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(glow, (112, 188, 255, 48), glow.get_rect(), border_radius=18)
        self.screen.blit(glow, projected_rect.topleft)

        self._draw_unit("player", projected_position, self.snapshot.player.health, DEFAULT_COMBAT_RULES.player.max_health)

    def _draw_health_bar(self, rect: pygame.Rect, current_health: int, max_health: int, is_player: bool) -> None:
        bar_rect = pygame.Rect(rect.left + 10, rect.bottom - 14, rect.width - 20, 8)
        pygame.draw.rect(self.screen, (20, 24, 29), bar_rect, border_radius=6)
        if max_health > 0 and current_health > 0:
            width = int(bar_rect.width * (current_health / max_health))
            fill_rect = pygame.Rect(bar_rect.left, bar_rect.top, max(8, width), bar_rect.height)
            fill_color = (82, 212, 140) if is_player else (236, 122, 114)
            pygame.draw.rect(self.screen, fill_color, fill_rect, border_radius=6)

    def _draw_sidebar(self) -> None:
        left = self.margin * 2 + self.snapshot.width * self.tile_size
        panel_rect = pygame.Rect(left, self.margin, self.sidebar_width, self.screen.get_height() - self.margin * 2)
        self._draw_panel_shell(panel_rect, PALETTE["panel_fill"], PALETTE["panel_border"], radius=24, inset_fill=PALETTE["panel_inner"])

        header_rect = pygame.Rect(panel_rect.left + 14, panel_rect.top + 14, panel_rect.width - 28, 92)
        self._draw_panel_shell(header_rect, PALETTE["panel_header"], PALETTE["panel_border"], radius=18)

        title = self.title_font.render("GridBattle UI", True, PALETTE["headline"])
        self.screen.blit(title, (header_rect.left + 18, header_rect.top + 16))
        subtitle = self.small_font.render("Tabletop tactical presentation layer", True, PALETTE["headline_soft"])
        self.screen.blit(subtitle, (header_rect.left + 18, header_rect.top + 58))

        x = left + 18
        width = self.sidebar_width - 36
        y = header_rect.bottom + 14

        player_health = self.snapshot.player.health if self.snapshot.player else 0
        battle_lines = [
            f"Turn: {self.snapshot.player_turns}/{self.max_steps}",
            f"HP: {player_health}/{DEFAULT_COMBAT_RULES.player.max_health}",
            f"Enemies left: {self.snapshot.remaining_enemies}",
        ]
        terrain_here = self._terrain_at_player()
        if terrain_here:
            battle_lines.append(f"Standing on: {terrain_here}")
        y = self._draw_info_card("Battle State", battle_lines, x, y, width, self.body_font)

        y = self._draw_info_card("Current Plan", self._plan_summary_lines(), x, y + 10, width, self.small_font)

        loadout_lines = ["Inventory:"]
        loadout_lines.extend(self._inventory_lines())
        loadout_lines.append("Effects:")
        loadout_lines.extend(self._effect_lines())
        y = self._draw_info_card("Loadout", loadout_lines, x, y + 10, width, self.small_font)

        message_lines = [
            f"Now: {self.status_message}",
            f"Last: {self.last_turn_summary}",
        ]
        self._draw_info_card("Message Feed", message_lines, x, y + 10, width, self.small_font)

    def _draw_action_panel(self) -> None:
        panel_rect = self._action_panel_rect()
        self._draw_panel_shell(panel_rect, PALETTE["panel_fill"], PALETTE["panel_border"], radius=24, inset_fill=PALETTE["panel_inner"])

        title = self.section_font.render("Action Tray", True, PALETTE["headline"])
        self.screen.blit(title, (panel_rect.left + 18, panel_rect.top + 14))
        subtitle = self.small_font.render("Confirm movement, attacks, and item usage", True, PALETTE["headline_soft"])
        self.screen.blit(subtitle, (panel_rect.left + 18, panel_rect.top + 42))

        for button in self._buttons():
            self._draw_button(button)

        inventory_buttons = self._item_buttons()
        right_x = panel_rect.left + 330
        right_width = panel_rect.width - 348
        card_y = panel_rect.top + 68

        if inventory_buttons:
            label = self.section_font.render("Use Item This Turn", True, PALETTE["headline"])
            self.screen.blit(label, (right_x, panel_rect.top + 18))
            for button in inventory_buttons:
                self._draw_button(button, compact=True)
            card_y = inventory_buttons[-1].rect.bottom + 12

        quick_reference_lines = [
            "Blue: valid movement",
            "Brass: planned destination",
            "Red: valid attacks",
            "Plum: second Dual Berettas shot",
            "Vehicle auto-activates on 2-tile moves",
            "Esc cancels preview, Enter confirms turn",
        ]
        self._draw_info_card("Quick Reference", quick_reference_lines, right_x, card_y, right_width, self.small_font, theme="dark")

        terrain_lines = [
            "Hill: +1 attack range",
            "Bush: 50% dodge vs enemy attack",
            "Bunker: immune this turn, but cannot move",
        ]
        terrain_y = card_y + self._estimate_card_height(quick_reference_lines, self.small_font, right_width) + 10
        self._draw_info_card("Terrain Notes", terrain_lines, right_x, terrain_y, right_width, self.small_font, theme="dark")

    def _draw_button(self, button: UiButton, compact: bool = False) -> None:
        mouse_over = button.rect.collidepoint(pygame.mouse.get_pos())
        if not button.enabled:
            fill = PALETTE["button_disabled_fill"]
            border = PALETTE["button_disabled_border"]
            text_color = PALETTE["button_disabled_text"]
        else:
            if compact:
                fill = PALETTE["button_item_fill"]
                hover_fill = PALETTE["button_item_hover"]
                text_color = PALETTE["button_item_text"]
                border = PALETTE["card_border"]
            elif button.name == "end_turn":
                fill = PALETTE["button_primary_fill"]
                hover_fill = PALETTE["button_primary_hover"]
                text_color = PALETTE["button_primary_text"]
                border = PALETTE["accent_brass_light"]
            else:
                fill = PALETTE["button_secondary_fill"]
                hover_fill = PALETTE["button_secondary_hover"]
                text_color = PALETTE["button_secondary_text"]
                border = PALETTE["panel_border"]

            if button.selected:
                fill = PALETTE["button_selected_fill"]
                hover_fill = PALETTE["button_selected_hover"]
                text_color = PALETTE["button_selected_text"]
                border = PALETTE["accent_red_light"]
            elif mouse_over:
                fill = hover_fill

        pygame.draw.rect(self.screen, fill, button.rect, border_radius=16)
        pygame.draw.rect(self.screen, border, button.rect, 2, border_radius=16)
        font = self.small_font if compact else self.body_font
        label = font.render(button.label, True, text_color)
        label_rect = label.get_rect(center=button.rect.center)
        self.screen.blit(label, label_rect)

    def _draw_tile_overlay(self, rect: pygame.Rect, color: tuple[int, int, int, int]) -> None:
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(overlay, color, overlay.get_rect(), border_radius=12)
        self.screen.blit(overlay, rect.topleft)

    def _draw_tile_outline(self, rect: pygame.Rect, color: Color, width: int) -> None:
        pygame.draw.rect(self.screen, color, rect, width, border_radius=12)

    def _current_feedback(self) -> TurnFeedback | None:
        if self.turn_feedback is None:
            return None
        if pygame.time.get_ticks() - self.turn_feedback.started_at > self.turn_feedback.duration_ms:
            self.turn_feedback = None
            return None
        return self.turn_feedback

    def _feedback_active(self) -> bool:
        return self._current_feedback() is not None

    def _feedback_progress(self, feedback: TurnFeedback) -> float:
        age = pygame.time.get_ticks() - feedback.started_at
        return max(0.0, min(1.0, age / max(1, feedback.duration_ms)))

    def _build_turn_feedback(
        self,
        before: BattleSnapshot,
        after: BattleSnapshot,
        *,
        move_directions: tuple[int, ...],
        primary_attack: AttackOption | None,
        secondary_attack: AttackOption | None,
        activated_item: str | None,
    ) -> TurnFeedback | None:
        if before.player is None:
            return None

        move_origin = before.player.position
        move_destination = self._simulate_move_sequence(move_origin, move_directions)
        attack_targets: list[tuple[tuple[int, int], str]] = []
        if primary_attack is not None:
            attack_targets.append((primary_attack.target_position, primary_attack.action.action_type))
        if secondary_attack is not None:
            attack_targets.append((secondary_attack.target_position, secondary_attack.action.action_type))

        player_after_hp = after.player.health if after.player is not None else 0
        player_hit = player_after_hp < before.player.health

        if not move_directions and not attack_targets and not player_hit and activated_item is None:
            return None

        final_tile = after.player.position if after.player is not None else move_destination
        return TurnFeedback(
            started_at=pygame.time.get_ticks(),
            duration_ms=780,
            move_origin=move_origin,
            move_directions=move_directions,
            move_destination=move_destination,
            attack_origin=move_destination,
            attack_targets=tuple(attack_targets),
            player_final_tile=final_tile,
            player_hit=player_hit,
            activated_item=activated_item,
        )

    def _draw_turn_feedback(self) -> None:
        feedback = self._current_feedback()
        if feedback is None:
            return

        progress = self._feedback_progress(feedback)
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)

        if feedback.move_origin is not None and feedback.move_directions:
            move_window = max(0.0, 1.0 - progress / 0.55)
            if move_window > 0.0:
                self._draw_feedback_move_path(overlay, feedback.move_origin, feedback.move_directions, move_window)
                if feedback.move_destination is not None:
                    self._draw_feedback_tile_glow(overlay, feedback.move_destination, PALETTE["accent_teal_light"], move_window)

        if feedback.attack_origin is not None and feedback.attack_targets:
            attack_phase = max(0.0, min(1.0, (progress - 0.12) / 0.58))
            attack_strength = math.sin(attack_phase * math.pi) if attack_phase > 0 else 0.0
            if attack_strength > 0.0:
                for target_tile, action_type in feedback.attack_targets:
                    color = PALETTE["accent_brass_light"] if action_type == "ranged_attack" else PALETTE["accent_red_light"]
                    self._draw_feedback_connector(
                        overlay,
                        self._tile_center(feedback.attack_origin),
                        self._tile_center(target_tile),
                        color,
                        attack_strength,
                    )
                    self._draw_feedback_impact(overlay, target_tile, color, attack_strength)

        if feedback.player_hit and feedback.player_final_tile is not None:
            damage_phase = max(0.0, min(1.0, (progress - 0.45) / 0.45))
            damage_strength = math.sin(damage_phase * math.pi) if damage_phase > 0 else 0.0
            if damage_strength > 0.0:
                self._draw_feedback_tile_glow(overlay, feedback.player_final_tile, PALETTE["accent_red_light"], damage_strength)

        if feedback.activated_item is not None and feedback.player_final_tile is not None:
            item_phase = max(0.0, 1.0 - progress / 0.4)
            if item_phase > 0.0:
                self._draw_feedback_tile_glow(overlay, feedback.player_final_tile, PALETTE["accent_brass_light"], item_phase * 0.8)

        self.screen.blit(overlay, (0, 0))

    def _pulse(self, minimum: float, maximum: float, *, period_ms: int = 1200, phase_offset: float = 0.0) -> float:
        if maximum <= minimum:
            return minimum
        ticks = pygame.time.get_ticks()
        phase = ((ticks % period_ms) / period_ms) * math.tau + phase_offset
        blend = 0.5 + 0.5 * math.sin(phase)
        return minimum + (maximum - minimum) * blend

    def _tile_center(self, tile: tuple[int, int]) -> tuple[int, int]:
        rect = self._tile_rect(tile)
        return rect.centerx, rect.centery

    def _draw_move_path(self, start_tile: tuple[int, int], directions: tuple[int, ...]) -> None:
        if not directions:
            return

        points = [self._tile_center(start_tile)]
        current = start_tile
        for direction in directions:
            dx, dy = DIRECTION_TO_DELTA[direction]
            current = (current[0] + dx, current[1] + dy)
            points.append(self._tile_center(current))

        for index in range(len(points) - 1):
            self._draw_connector(points[index], points[index + 1], PALETTE["accent_teal_light"], width=4, endpoint_radius=6)

        start = points[-2]
        end = points[-1]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = max(1.0, math.hypot(dx, dy))
        ux = dx / length
        uy = dy / length
        head = 14
        wing = 8
        tip = (end[0] - ux * 12, end[1] - uy * 12)
        left = (tip[0] - ux * head + -uy * wing, tip[1] - uy * head + ux * wing)
        right = (tip[0] - ux * head - -uy * wing, tip[1] - uy * head - ux * wing)
        pygame.draw.polygon(self.screen, PALETTE["accent_teal_light"], [tip, left, right])

    def _draw_feedback_move_path(
        self,
        surface: pygame.Surface,
        start_tile: tuple[int, int],
        directions: tuple[int, ...],
        strength: float,
    ) -> None:
        if not directions:
            return

        points = [self._tile_center(start_tile)]
        current = start_tile
        for direction in directions:
            dx, dy = DIRECTION_TO_DELTA[direction]
            current = (current[0] + dx, current[1] + dy)
            points.append(self._tile_center(current))

        color = (*PALETTE["accent_teal_light"], int(180 * strength))
        width = max(3, int(round(4 + 3 * strength)))
        endpoint_radius = max(5, int(round(6 + 2 * strength)))
        for index in range(len(points) - 1):
            self._draw_feedback_connector(surface, points[index], points[index + 1], PALETTE["accent_teal_light"], strength, width=width, endpoint_radius=endpoint_radius)

        start = points[-2]
        end = points[-1]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = max(1.0, math.hypot(dx, dy))
        ux = dx / length
        uy = dy / length
        head = 14 + 4 * strength
        wing = 8 + 3 * strength
        tip = (end[0] - ux * 12, end[1] - uy * 12)
        left = (tip[0] - ux * head + -uy * wing, tip[1] - uy * head + ux * wing)
        right = (tip[0] - ux * head - -uy * wing, tip[1] - uy * head - ux * wing)
        pygame.draw.polygon(surface, color, [tip, left, right])

    def _draw_connector(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        color: Color,
        *,
        width: int = 4,
        endpoint_radius: int = 7,
    ) -> None:
        shadow_start = (start[0] + 2, start[1] + 2)
        shadow_end = (end[0] + 2, end[1] + 2)
        pygame.draw.line(self.screen, PALETTE["line_shadow"], shadow_start, shadow_end, width + 2)
        pygame.draw.line(self.screen, color, start, end, width)
        pygame.draw.circle(self.screen, color, start, endpoint_radius)
        pygame.draw.circle(self.screen, color, end, endpoint_radius)

    def _draw_feedback_connector(
        self,
        surface: pygame.Surface,
        start: tuple[int, int],
        end: tuple[int, int],
        color: Color,
        strength: float,
        *,
        width: int = 4,
        endpoint_radius: int = 7,
    ) -> None:
        alpha = int(210 * strength)
        shadow = (*PALETTE["line_shadow"], int(120 * strength))
        main = (*color, alpha)
        shadow_start = (start[0] + 2, start[1] + 2)
        shadow_end = (end[0] + 2, end[1] + 2)
        pygame.draw.line(surface, shadow, shadow_start, shadow_end, width + 2)
        pygame.draw.line(surface, main, start, end, width)
        pygame.draw.circle(surface, main, start, endpoint_radius)
        pygame.draw.circle(surface, main, end, endpoint_radius)

    def _draw_feedback_tile_glow(
        self,
        surface: pygame.Surface,
        tile: tuple[int, int],
        color: Color,
        strength: float,
    ) -> None:
        rect = self._tile_rect(tile)
        glow = pygame.Surface((rect.width + 28, rect.height + 28), pygame.SRCALPHA)
        alpha = int(110 * strength)
        pygame.draw.rect(
            glow,
            (*color, alpha),
            pygame.Rect(14, 14, rect.width, rect.height),
            border_radius=18,
        )
        pygame.draw.rect(
            glow,
            (*color, int(200 * strength)),
            pygame.Rect(14, 14, rect.width, rect.height),
            max(2, int(round(2 + 2 * strength))),
            border_radius=18,
        )
        surface.blit(glow, (rect.left - 14, rect.top - 14))

    def _draw_feedback_impact(
        self,
        surface: pygame.Surface,
        tile: tuple[int, int],
        color: Color,
        strength: float,
    ) -> None:
        center = self._tile_center(tile)
        radius = int(round(self.tile_size * (0.16 + 0.18 * strength)))
        ring_width = max(2, int(round(2 + 3 * strength)))
        glow = pygame.Surface((self.tile_size + 36, self.tile_size + 36), pygame.SRCALPHA)
        local_center = glow.get_rect().center
        pygame.draw.circle(glow, (*color, int(170 * strength)), local_center, radius, ring_width)
        pygame.draw.circle(glow, (*color, int(60 * strength)), local_center, max(8, radius // 2))
        surface.blit(glow, (center[0] - glow.get_width() // 2, center[1] - glow.get_height() // 2))

    def _draw_board_connectors(
        self,
        mouse_tile: tuple[int, int] | None,
        move_options: dict[tuple[int, int], MoveOption],
        attack_options: dict[tuple[int, int], AttackOption],
        secondary_options: dict[tuple[int, int], AttackOption],
    ) -> None:
        if self.snapshot.player is None or not self.selected_player:
            return

        origin = self.snapshot.player.position
        projected = self._projected_player_position()
        if self._has_move_preview():
            self._draw_move_path(origin, self.planned_move_directions)
        elif mouse_tile is not None and mouse_tile in move_options:
            self._draw_move_path(origin, move_options[mouse_tile].directions)

        if self.primary_attack is not None:
            self._draw_connector(
                self._tile_center(projected),
                self._tile_center(self.primary_attack.target_position),
                PALETTE["accent_brass_light"],
                width=5,
                endpoint_radius=8,
            )

        if self.secondary_attack is not None:
            self._draw_connector(
                self._tile_center(projected),
                self._tile_center(self.secondary_attack.target_position),
                PALETTE["accent_plum_light"],
                width=4,
                endpoint_radius=7,
            )

        if mouse_tile is None:
            return

        if self.primary_attack is not None and mouse_tile in secondary_options and self.secondary_attack is None:
            self._draw_connector(
                self._tile_center(projected),
                self._tile_center(mouse_tile),
                PALETTE["accent_plum_light"],
                width=4,
                endpoint_radius=7,
            )
        elif mouse_tile in attack_options and self.primary_attack is None:
            attack = attack_options[mouse_tile]
            color = PALETTE["accent_red_light"] if attack.action.action_type == "attack" else PALETTE["accent_brass_light"]
            self._draw_connector(
                self._tile_center(projected),
                self._tile_center(mouse_tile),
                color,
                width=4,
                endpoint_radius=7,
            )

    def _draw_hover_tooltip(
        self,
        mouse_tile: tuple[int, int] | None,
        move_options: dict[tuple[int, int], MoveOption],
        attack_options: dict[tuple[int, int], AttackOption],
        secondary_options: dict[tuple[int, int], AttackOption],
    ) -> None:
        if mouse_tile is None or self._feedback_active():
            return

        tooltip = self._tile_tooltip(mouse_tile, move_options, attack_options, secondary_options)
        if tooltip is None:
            return

        title, lines, accent = tooltip
        mouse_x, mouse_y = pygame.mouse.get_pos()
        font = self.small_font
        title_surface = self.small_font.render(title, True, PALETTE["tooltip_title"])
        width = max(title_surface.get_width(), *(font.size(line)[0] for line in lines)) + 28
        height = 20 + title_surface.get_height() + len(lines) * (font.get_height() + 4) + 12
        rect = pygame.Rect(mouse_x + 18, mouse_y + 18, width, height)

        if rect.right > self.screen.get_width() - 12:
            rect.right = mouse_x - 16
        if rect.bottom > self.screen.get_height() - 12:
            rect.bottom = self.screen.get_height() - 12
        if rect.left < 12:
            rect.left = 12
        if rect.top < 12:
            rect.top = 12

        shadow = rect.move(3, 4)
        pygame.draw.rect(self.screen, (8, 11, 18, 90), shadow, border_radius=14)
        pygame.draw.rect(self.screen, PALETTE["tooltip_fill"], rect, border_radius=14)
        pygame.draw.rect(self.screen, PALETTE["tooltip_border"], rect, 2, border_radius=14)
        accent_rect = pygame.Rect(rect.left + 10, rect.top + 10, 6, rect.height - 20)
        pygame.draw.rect(self.screen, accent, accent_rect, border_radius=4)

        self.screen.blit(title_surface, (rect.left + 24, rect.top + 12))
        text_y = rect.top + 16 + title_surface.get_height()
        for line in lines:
            label = font.render(line, True, PALETTE["tooltip_text"])
            self.screen.blit(label, (rect.left + 24, text_y))
            text_y += font.get_height() + 4

    def _tile_tooltip(
        self,
        tile: tuple[int, int],
        move_options: dict[tuple[int, int], MoveOption],
        attack_options: dict[tuple[int, int], AttackOption],
        secondary_options: dict[tuple[int, int], AttackOption],
    ) -> tuple[str, list[str], Color] | None:
        if self.snapshot.player is not None and tile == self.snapshot.player.position:
            lines = [f"HP {self.snapshot.player.health}/{DEFAULT_COMBAT_RULES.player.max_health}"]
            terrain = self._terrain_labels_at(tile)
            if terrain:
                lines.append("Terrain: " + ", ".join(terrain))
            if self.selected_player:
                lines.append("Selected for planning")
            else:
                lines.append("Click to select this unit")
            return "Player Token", lines, PALETTE["accent_teal_light"]

        enemy = next((candidate for candidate in self.snapshot.enemies if candidate.position == tile), None)
        if enemy is not None:
            lines = [f"HP {enemy.health}/{DEFAULT_COMBAT_RULES.enemy.max_health}"]
            if tile in secondary_options and self.primary_attack is not None and self.secondary_attack is None:
                lines.append("Click for second Dual Berettas shot")
                return "Second Target", lines, PALETTE["accent_plum_light"]
            if tile in attack_options:
                action_name = "Ranged attack" if attack_options[tile].action.action_type == "ranged_attack" else "Melee attack"
                lines.append(action_name + " available")
                lines.append("Click to confirm attack")
                color = PALETTE["accent_brass_light"] if attack_options[tile].action.action_type == "ranged_attack" else PALETTE["accent_red_light"]
                return "Enemy Target", lines, color
            lines.append("Currently out of range")
            return "Enemy Token", lines, PALETTE["accent_red_light"]

        if self.selected_player and self._has_move_preview() and tile == self._projected_player_position():
            lines = ["Planned destination", "Click a red target or End Turn"]
            if self.vehicle_auto_selected:
                lines.append("Vehicle will activate automatically")
            return "Destination", lines, PALETTE["accent_brass_light"]

        if tile in move_options:
            move_option = move_options[tile]
            path_text = " -> ".join(DIRECTION_NAMES[direction] for direction in move_option.directions)
            lines = [f"Move {path_text}", f"Attack range after move: {self._effective_attack_range(tile)}"]
            if move_option.uses_vehicle:
                lines.append("Uses Vehicle automatically")
            if tile in self.snapshot.hills:
                lines.append("Hill bonus applies here")
            if tile in self.snapshot.bunkers:
                lines.append("Bunker blocks future movement")
            return "Move Preview", lines, PALETTE["accent_teal_light"]

        terrain = self._terrain_labels_at(tile)
        item_name = dict(self.snapshot.map_items).get(tile)
        if terrain or item_name is not None or tile in self.snapshot.walls:
            lines: list[str] = []
            if terrain:
                lines.append("Terrain: " + ", ".join(terrain))
            if item_name is not None:
                lines.append("Pickup: " + self._pretty_item_name(item_name))
            description = self._terrain_description(tile)
            if description is not None:
                lines.append(description)
            return "Board Tile", lines, PALETTE["accent_brass"]

        return None

    def _draw_board_labels(self) -> None:
        for x in range(self.snapshot.width):
            label = self.small_font.render(str(x), True, PALETTE["board_label"])
            rect = label.get_rect(center=(self.margin + x * self.tile_size + self.tile_size // 2, self.margin - 14))
            self.screen.blit(label, rect)
        for y in range(self.snapshot.height):
            label = self.small_font.render(str(y), True, PALETTE["board_label"])
            rect = label.get_rect(center=(self.margin - 12, self.margin + y * self.tile_size + self.tile_size // 2))
            self.screen.blit(label, rect)

    def _draw_section_title(self, title: str, x: int, y: int) -> int:
        label = self.section_font.render(title, True, PALETTE["headline"])
        self.screen.blit(label, (x, y))
        return y + 30

    def _draw_panel_shell(
        self,
        rect: pygame.Rect,
        fill: Color,
        border: Color,
        *,
        radius: int = 24,
        inset_fill: Color | None = None,
    ) -> None:
        shadow = pygame.Surface((rect.width + 20, rect.height + 20), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (8, 11, 17, 76), pygame.Rect(10, 12, rect.width, rect.height), border_radius=radius + 2)
        self.screen.blit(shadow, (rect.left - 10, rect.top - 10))
        pygame.draw.rect(self.screen, fill, rect, border_radius=radius)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=radius)
        if inset_fill is not None:
            inset = rect.inflate(-14, -14)
            pygame.draw.rect(self.screen, inset_fill, inset, border_radius=max(12, radius - 6))
            pygame.draw.rect(self.screen, border, inset, 1, border_radius=max(12, radius - 6))

    def _draw_info_card(
        self,
        title: str,
        lines: list[str],
        x: int,
        y: int,
        width: int,
        font: pygame.font.Font,
        *,
        theme: str = "light",
    ) -> int:
        card_rect = pygame.Rect(x, y, width, self._estimate_card_height(lines, font, width))
        if theme == "dark":
            fill = PALETTE["panel_header"]
            inset_fill = PALETTE["panel_fill"]
            border = PALETTE["panel_border"]
            title_color = PALETTE["headline_soft"]
            text_color = PALETTE["headline"]
        else:
            fill = PALETTE["card_fill"]
            inset_fill = PALETTE["card_fill_soft"]
            border = PALETTE["card_border"]
            title_color = PALETTE["ink_soft"]
            text_color = PALETTE["ink"]

        pygame.draw.rect(self.screen, fill, card_rect, border_radius=18)
        pygame.draw.rect(self.screen, border, card_rect, 2, border_radius=18)
        inner = card_rect.inflate(-10, -10)
        pygame.draw.rect(self.screen, inset_fill, inner, border_radius=14)

        label = self.small_font.render(title.upper(), True, title_color)
        self.screen.blit(label, (card_rect.left + 14, card_rect.top + 12))

        text_y = card_rect.top + 38
        for line in lines:
            text_y = self._draw_wrapped_text(line, font, text_color, card_rect.left + 14, text_y, card_rect.width - 28)
            text_y += 2
        return card_rect.bottom

    def _estimate_card_height(self, lines: list[str], font: pygame.font.Font, width: int) -> int:
        height = 48
        text_width = width - 28
        for line in lines:
            wrapped_lines = self._wrap_text_lines(line, font, text_width)
            height += len(wrapped_lines) * (font.get_height() + 4) + 2
        return max(78, height + 12)

    def _draw_wrapped_text(self, text: str, font: pygame.font.Font, color: Color, x: int, y: int, width: int) -> int:
        lines = self._wrap_text_lines(text, font, width)
        for line in lines:
            label = font.render(line, True, color)
            self.screen.blit(label, (x, y))
            y += font.get_height() + 4
        return y

    def _wrap_text_lines(self, text: str, font: pygame.font.Font, width: int) -> list[str]:
        if not text:
            return [""]

        words = text.split()
        if not words:
            return [""]

        lines: list[str] = []
        current = words[0]

        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.size(candidate)[0] <= width:
                current = candidate
            else:
                lines.append(current)
                if font.size(word)[0] <= width:
                    current = word
                else:
                    chunk = ""
                    for char in word:
                        next_chunk = f"{chunk}{char}"
                        if chunk and font.size(next_chunk)[0] > width:
                            lines.append(chunk)
                            chunk = char
                        else:
                            chunk = next_chunk
                    current = chunk or word

        lines.append(current)
        return lines

    def _buttons(self) -> list[UiButton]:
        panel_rect = self._action_panel_rect()
        left = panel_rect.left + 18
        top = panel_rect.top + 78
        width = 250
        height = 46
        gap = 14
        can_take_turn = self.selected_player and self.snapshot.player is not None and not self._is_game_over()
        secondary_name = "cancel_move" if self._has_move_preview() else "cancel"
        secondary_label = "Cancel Move" if self._has_move_preview() else "Clear Selection"
        secondary_enabled = self.selected_player or bool(self.planned_move_directions) or self.selected_item is not None
        return [
            UiButton("end_turn", "End Turn", pygame.Rect(left, top, width, height), can_take_turn),
            UiButton(secondary_name, secondary_label, pygame.Rect(left, top + height + gap, width, height), secondary_enabled),
            UiButton("reset", "Reset Map", pygame.Rect(left, top + (height + gap) * 2, width, height), True),
        ]

    def _item_buttons(self) -> list[UiButton]:
        item_names = [item_name for item_name in self.snapshot.inventory if item_name != ITEM_VEHICLE]
        if not item_names:
            return []

        panel_rect = self._action_panel_rect()
        left = panel_rect.left + 330
        top = panel_rect.top + 56
        width = panel_rect.width - 328
        height = 38
        gap = 10
        buttons: list[UiButton] = []
        for index, item_name in enumerate(item_names):
            rect = pygame.Rect(left, top + index * (height + gap), width, height)
            buttons.append(
                UiButton(
                    "item",
                    self._pretty_item_name(item_name),
                    rect,
                    enabled=self.selected_player and not self._is_game_over(),
                    payload=item_name,
                    selected=self.selected_item == item_name,
                )
            )
        return buttons

    def _interactive_buttons(self) -> list[UiButton]:
        return self._buttons() + self._item_buttons()

    def _move_options(self) -> dict[tuple[int, int], MoveOption]:
        if self.snapshot.player is None or not self.selected_player:
            return {}

        origin = self.snapshot.player.position

        options: dict[tuple[int, int], MoveOption] = {}
        max_steps = self._max_move_steps()

        frontier: list[tuple[tuple[int, int], tuple[int, ...]]] = [(origin, ())]
        best_steps = {origin: 0}

        while frontier:
            current, directions = frontier.pop(0)
            if len(directions) >= max_steps:
                continue

            for direction, (dx, dy) in DIRECTION_TO_DELTA.items():
                candidate = (current[0] + dx, current[1] + dy)
                if not self._inside_bounds(candidate):
                    continue
                if candidate in self.snapshot.walls or any(enemy.position == candidate for enemy in self.snapshot.enemies):
                    continue

                next_directions = directions + (direction,)
                next_steps = len(next_directions)
                if candidate in best_steps and best_steps[candidate] <= next_steps:
                    continue

                best_steps[candidate] = next_steps
                uses_vehicle = next_steps > 1 and ITEM_VEHICLE not in {effect.name for effect in self.snapshot.active_effects}
                options[candidate] = MoveOption(candidate, next_directions, uses_vehicle=uses_vehicle)
                frontier.append((candidate, next_directions))
        return options

    def _max_move_steps(self) -> int:
        if self.snapshot.player is None:
            return 0
        if ITEM_VEHICLE in {effect.name for effect in self.snapshot.active_effects}:
            return 2
        if ITEM_VEHICLE in self.snapshot.inventory and self.selected_item in (None, ITEM_VEHICLE):
            return 2
        return 1

    def _simulate_move_sequence(self, origin: tuple[int, int], directions: tuple[int, ...]) -> tuple[int, int]:
        blockers = set(self.snapshot.walls) | {enemy.position for enemy in self.snapshot.enemies}
        current = origin
        for direction in directions:
            dx, dy = DIRECTION_TO_DELTA[direction]
            candidate = (current[0] + dx, current[1] + dy)
            if not self._inside_bounds(candidate):
                break
            if candidate in blockers:
                break
            current = candidate
        return current

    def _attack_options(self) -> dict[tuple[int, int], AttackOption]:
        if self.snapshot.player is None or not self.selected_player:
            return {}

        exclude_positions: set[tuple[int, int]] = set()
        if self.primary_attack is not None:
            exclude_positions.add(self.primary_attack.target_position)
        return self._compute_attack_options(exclude_positions)

    def _secondary_attack_options(self) -> dict[tuple[int, int], AttackOption]:
        if self.primary_attack is None or not self._can_dual_attack():
            return {}
        return self._compute_attack_options({self.primary_attack.target_position})

    def _compute_attack_options(self, exclude_positions: set[tuple[int, int]]) -> dict[tuple[int, int], AttackOption]:
        attacker_position = self._projected_player_position()
        attack_range = self._effective_attack_range(attacker_position)
        enemy_positions = {enemy.position for enemy in self.snapshot.enemies}
        base_blockers = set(self.snapshot.walls)
        options: dict[tuple[int, int], AttackOption] = {}

        for enemy in self.snapshot.enemies:
            if enemy.position in exclude_positions:
                continue
            blockers = base_blockers | (enemy_positions - {enemy.position})
            attack_result = find_attack_action(attacker_position, enemy.position, attack_range, blockers)
            if attack_result is None:
                continue
            action_type, direction = attack_result
            options[enemy.position] = AttackOption(enemy.position, PhaseAction(action_type, direction))

        return options

    def _effective_attack_range(self, position: tuple[int, int]) -> int:
        attack_range = DEFAULT_COMBAT_RULES.player.attack_range
        if position in self.snapshot.hills:
            attack_range += 1
        if ITEM_SHOTGUN in self._pending_active_names():
            attack_range += 1
        return attack_range

    def _projected_player_position(self) -> tuple[int, int]:
        if self.snapshot.player is None or not self.planned_move_directions:
            return self.snapshot.player.position if self.snapshot.player else (0, 0)
        return self._simulate_move_sequence(self.snapshot.player.position, self.planned_move_directions)

    def _pending_active_names(self) -> set[str]:
        active_names = {effect.name for effect in self.snapshot.active_effects}
        if self.selected_item is not None:
            active_names.add(self.selected_item)
        return active_names

    def _clear_auto_vehicle_selection(self) -> None:
        if self.vehicle_auto_selected and self.selected_item == ITEM_VEHICLE:
            self.selected_item = None
        self.vehicle_auto_selected = False

    def _sync_vehicle_selection_for_move(self, move_option: MoveOption) -> None:
        vehicle_active = ITEM_VEHICLE in {effect.name for effect in self.snapshot.active_effects}
        if move_option.uses_vehicle and not vehicle_active:
            self.selected_item = ITEM_VEHICLE
            self.vehicle_auto_selected = True
        else:
            self._clear_auto_vehicle_selection()

    def _can_dual_attack(self) -> bool:
        return ITEM_DUAL_BERETTAS in self._pending_active_names()

    def _terrain_at_player(self) -> str | None:
        if self.snapshot.player is None:
            return None
        labels = self._terrain_labels_at(self.snapshot.player.position)
        return ", ".join(labels) if labels else None

    def _terrain_labels_at(self, pos: tuple[int, int]) -> list[str]:
        labels: list[str] = []
        if pos in self.snapshot.hills:
            labels.append(TERRAIN_LABELS[TERRAIN_HILL])
        if pos in self.snapshot.bushes:
            labels.append(TERRAIN_LABELS[TERRAIN_BUSH])
        if pos in self.snapshot.bunkers:
            labels.append(TERRAIN_LABELS[TERRAIN_BUNKER])
        return labels

    def _terrain_description(self, pos: tuple[int, int]) -> str | None:
        if pos in self.snapshot.hills:
            return "Hill grants +1 attack range."
        if pos in self.snapshot.bushes:
            return "Bush gives dodge against enemy fire."
        if pos in self.snapshot.bunkers:
            return "Bunker protects you but limits movement."
        if pos in self.snapshot.walls:
            return "Wall blocks movement and attacks."
        return None

    def _inventory_lines(self) -> list[str]:
        if not self.snapshot.inventory:
            return ["No items collected yet."]
        lines = []
        for item_name in self.snapshot.inventory:
            if item_name == ITEM_VEHICLE:
                if ITEM_VEHICLE in {effect.name for effect in self.snapshot.active_effects}:
                    suffix = " (active)"
                elif self.vehicle_auto_selected:
                    suffix = " (auto for planned move)"
                else:
                    suffix = " (auto on 2-step move)"
            else:
                suffix = " (selected)" if self.selected_item == item_name else ""
            lines.append(self._pretty_item_name(item_name) + suffix)
        return lines

    def _effect_lines(self) -> list[str]:
        if not self.snapshot.active_effects and self.selected_item is None:
            return ["No active effects."]

        lines = [f"{self._pretty_item_name(effect.name)} ({effect.turns_left})" for effect in self.snapshot.active_effects]
        if self.selected_item is not None and all(effect.name != self.selected_item for effect in self.snapshot.active_effects):
            lines.append(f"{self._pretty_item_name(self.selected_item)} (pending this turn)")
        return lines

    def _plan_summary_lines(self) -> list[str]:
        if self.snapshot.player is None:
            return ["No active player."]
        if not self.selected_player:
            return ["Nothing selected.", "Click the player on the board."]

        origin = self.snapshot.player.position
        projected = self._projected_player_position()
        move_label = self._planned_move_label()
        lines = [
            f"From: {origin}",
            f"To: {projected}",
            f"Move: {move_label}",
            f"Attack range: {self._effective_attack_range(projected)}",
        ]

        if self.selected_item is not None:
            lines.append(f"Use item: {self._pretty_item_name(self.selected_item)}")

        if self.primary_attack is not None:
            lines.append(f"Action 1: {self.primary_attack.action.action_type} toward {self.primary_attack.target_position}")
        else:
            lines.append("Action 1: not selected")

        if self._can_dual_attack():
            if self.secondary_attack is not None:
                lines.append(f"Action 2: {self.secondary_attack.action.action_type} toward {self.secondary_attack.target_position}")
            else:
                lines.append("Action 2: available if another target is in range")

        return lines

    def _planned_move_label(self) -> str:
        if not self.planned_move_directions:
            return "stay in place"
        return " -> ".join(DIRECTION_NAMES[direction] for direction in self.planned_move_directions)

    def _describe_turn(
        self,
        before: BattleSnapshot,
        after: BattleSnapshot,
        history: list[dict],
        activated_item: str | None,
    ) -> str:
        notes: list[str] = []
        player_events = [event for event in history if event["PlayerId"] == 1]

        player_health_before = before.player.health if before.player else 0
        player_health_after = after.player.health if after.player else 0
        if player_health_after < player_health_before:
            notes.append(f"Enemy hit you for {player_health_before - player_health_after}.")

        if after.remaining_enemies < before.remaining_enemies:
            notes.append(f"You defeated {before.remaining_enemies - after.remaining_enemies} enemy.")
        else:
            before_enemy_health = sum(enemy.health for enemy in before.enemies)
            after_enemy_health = sum(enemy.health for enemy in after.enemies)
            if after_enemy_health < before_enemy_health:
                notes.append("Your attack connected.")

        if any(event["ActionName"] == "wait" for event in player_events):
            notes.append("You waited.")
        if any(event["ActionName"] == "ranged_attack" for event in player_events):
            notes.append("You used a ranged attack.")
        if after.inventory and len(after.inventory) > len(before.inventory):
            gained = set(after.inventory) - set(before.inventory)
            if gained:
                notes.append(f"Picked up {', '.join(self._pretty_item_name(item) for item in sorted(gained))}.")

        if activated_item is not None:
            notes.append(f"Activated {self._pretty_item_name(activated_item)}.")

        return " ".join(notes) if notes else "No major state change."

    def _screen_to_tile(self, mouse_position: tuple[int, int]) -> tuple[int, int] | None:
        x, y = mouse_position
        board_width = self.snapshot.width * self.tile_size
        board_height = self.snapshot.height * self.tile_size
        if not (self.margin <= x < self.margin + board_width and self.margin <= y < self.margin + board_height):
            return None
        return int((x - self.margin) // self.tile_size), int((y - self.margin) // self.tile_size)

    def _tile_rect(self, tile: tuple[int, int]) -> pygame.Rect:
        return pygame.Rect(
            self.margin + tile[0] * self.tile_size,
            self.margin + tile[1] * self.tile_size,
            self.tile_size,
            self.tile_size,
        )

    def _action_panel_rect(self) -> pygame.Rect:
        board_bottom = self.margin + self.snapshot.height * self.tile_size
        board_width = self.snapshot.width * self.tile_size
        panel_top = board_bottom + 18
        panel_height = max(390, 180 + len(self.snapshot.inventory) * 48)
        return pygame.Rect(self.margin - 4, panel_top, board_width + 8, panel_height)

    def _inside_bounds(self, tile: tuple[int, int]) -> bool:
        return 0 <= tile[0] < self.snapshot.width and 0 <= tile[1] < self.snapshot.height

    def _has_move_preview(self) -> bool:
        return self.selected_player and self.snapshot.player is not None and bool(self.planned_move_directions)

    def _pretty_item_name(self, item_name: str) -> str:
        return ITEM_LABELS.get(item_name, item_name.replace("_", " ").title())

    def _is_game_over(self) -> bool:
        if self.snapshot.player is None:
            return True
        if self.snapshot.remaining_enemies == 0:
            return True
        return self.snapshot.player_turns >= self.max_steps
