from __future__ import annotations

import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "results_analysis" / "report_assets"
FIG_DIR = OUT_DIR / "figures"
TABLE_DIR = OUT_DIR / "tables"
SCREENSHOT_DIR = OUT_DIR / "screenshots"

AGENT_ORDER = ["random", "heuristic", "mcts_small", "mcts_medium"]
SIZE_ORDER = ["small", "medium", "large"]
MAP_TYPE_ORDER = ["baseline", "random_walk", "arena"]
ENEMY_ORDER = ["normal", "medium_plus", "heavy"]
ITEM_ORDER = ["normal", "many"]
WALL_ORDER = ["open", "normal"]
FACTOR_ORDER = [
    "enemy_hp",
    "enemy_profile",
    "player_hp",
    "size",
    "item_profile",
    "wall_profile",
    "map_type",
]

AGENT_LABELS = {
    "random": "Random",
    "heuristic": "Heuristic",
    "mcts_small": "MCTS-small",
    "mcts_medium": "MCTS-medium",
}

FACTOR_LABELS = {
    "size": "Map size",
    "map_type": "Map type",
    "enemy_profile": "Enemy profile",
    "item_profile": "Item profile",
    "wall_profile": "Wall profile",
    "player_hp": "Player HP",
    "enemy_hp": "Enemy HP",
}

COLORS = {
    "ink": "#172033",
    "muted": "#64748B",
    "grid": "#E2E8F0",
    "axis": "#334155",
    "panel": "#F8FAFC",
    "random": "#94A3B8",
    "heuristic": "#D97706",
    "mcts_small": "#0E7490",
    "mcts_medium": "#2563EB",
    "both_win": "#16A34A",
    "mcts_only": "#2563EB",
    "heuristic_only": "#F59E0B",
    "both_loss": "#CBD5E1",
    "baseline": "#6366F1",
    "random_walk": "#059669",
    "arena": "#DC2626",
}


def ensure_dirs() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def clean_generated_outputs() -> None:
    for path in TABLE_DIR.glob("*"):
        if path.suffix.lower() in {".md", ".tex"}:
            path.unlink()
    manifest = OUT_DIR / "manifest.md"
    if manifest.exists():
        manifest.unlink()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value in ("", None):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def i(row: dict[str, str], key: str, default: int = 0) -> int:
    return int(round(f(row, key, default)))


def pct(value: float, decimals: int = 0) -> str:
    return f"{value * 100:.{decimals}f}%"


def short_pct(value: float) -> str:
    return f"{value * 100:.0f}"


def color(hex_color: str) -> tuple[int, int, int]:
    named = {
        "white": "#FFFFFF",
        "black": "#000000",
    }
    hex_color = named.get(hex_color, hex_color)
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[n : n + 2], 16) for n in (0, 2, 4))


def blend(a: str, b: str, t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    ca = color(a)
    cb = color(b)
    return tuple(round(ca[k] + (cb[k] - ca[k]) * t) for k in range(3))


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1.0 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return max(0.0, center - half), min(1.0, center + half)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend(
            [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/SFNS.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        )
    candidates.extend(
        [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


FONT_TITLE = font(42, bold=True)
FONT_SUBTITLE = font(24)
FONT_H2 = font(30, bold=True)
FONT_LABEL = font(22)
FONT_SMALL = font(18)
FONT_TINY = font(15)
FONT_MONO = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", size=17) if Path("/System/Library/Fonts/SFNSMono.ttf").exists() else font(17)


def text_size(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.ImageFont) -> tuple[int, int]:
    if not text:
        return 0, 0
    bbox = draw.textbbox((0, 0), text, font=face)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str, width: int) -> None:
    draw.text((70, 42), title, font=FONT_TITLE, fill=color(COLORS["ink"]))
    draw.text((72, 98), subtitle, font=FONT_SUBTITLE, fill=color(COLORS["muted"]))
    draw.line((70, 140, width - 70, 140), fill=color("#CBD5E1"), width=2)


def save_canvas(img: Image.Image, path: Path) -> None:
    img.save(path)


def new_canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    return img, draw


def sx(value: float) -> int:
    return round(value)


def scaled_rect(rect: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(sx(v) for v in rect)  # type: ignore[return-value]


def draw_round(
    draw: ImageDraw.ImageDraw,
    rect: tuple[float, float, float, float],
    fill: str | tuple[int, int, int],
    outline: str | tuple[int, int, int] | None = None,
    width: int = 1,
    radius: int = 14,
) -> None:
    fill_color = color(fill) if isinstance(fill, str) else fill
    outline_color = color(outline) if isinstance(outline, str) else outline
    draw.rounded_rectangle(
        scaled_rect(rect),
        radius=sx(radius),
        fill=fill_color,
        outline=outline_color,
        width=sx(width) if outline else 1,
    )


def draw_text_scaled(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    face: ImageFont.ImageFont,
    fill: str | tuple[int, int, int] = COLORS["ink"],
    anchor: str | None = None,
) -> None:
    fill_color = color(fill) if isinstance(fill, str) else fill
    draw.text((sx(xy[0]), sx(xy[1])), text, font=face, fill=fill_color, anchor=anchor)


def draw_line_scaled(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float, float, float],
    fill: str | tuple[int, int, int],
    width: int = 1,
) -> None:
    fill_color = color(fill) if isinstance(fill, str) else fill
    draw.line(tuple(sx(v) for v in xy), fill=fill_color, width=sx(width))


def draw_grid_y(
    draw: ImageDraw.ImageDraw,
    left: float,
    top: float,
    right: float,
    bottom: float,
    ticks: Iterable[float],
    value_to_y,
    label_format=pct,
) -> None:
    for tick in ticks:
        y = value_to_y(tick)
        draw_line_scaled(draw, (left, y, right, y), COLORS["grid"], width=1)
        draw_text_scaled(draw, (left - 14, y - 10), label_format(tick), FONT_SMALL, COLORS["muted"], anchor="ra")


def group_rows(rows: list[dict[str, str]], keys: list[str]) -> dict[tuple[str, ...], list[dict[str, str]]]:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key, "") for key in keys)].append(row)
    return grouped


def aggregate_agent_results(rows: list[dict[str, str]], keys: list[str]) -> list[dict[str, object]]:
    records = []
    for group_key, group in group_rows(rows, keys).items():
        wins = sum(i(row, "won") for row in group)
        n = len(group)
        ci_low, ci_high = wilson_interval(wins, n)
        record: dict[str, object] = dict(zip(keys, group_key))
        record.update(
            {
                "episodes": n,
                "wins": wins,
                "win_rate": wins / n if n else 0.0,
                "ci_low": ci_low,
                "ci_high": ci_high,
                "avg_turns": statistics.mean(f(row, "turns") for row in group),
                "avg_damage": statistics.mean(f(row, "damage_taken") for row in group),
                "avg_final_hp": statistics.mean(f(row, "final_hp") for row in group),
                "avg_chokepoints": statistics.mean(f(row, "chokepoint_count") for row in group),
                "avg_dead_ends": statistics.mean(f(row, "dead_end_count") for row in group),
                "avg_reachable_floor": statistics.mean(f(row, "reachable_floor_fraction") for row in group),
            }
        )
        records.append(record)
    return records


def pivot_win_rates(rows: list[dict[str, str]], config_keys: list[str]) -> dict[tuple[str, ...], dict[str, float]]:
    by_agent = aggregate_agent_results(rows, config_keys + ["agent"])
    pivot: dict[tuple[str, ...], dict[str, float]] = defaultdict(dict)
    for row in by_agent:
        key = tuple(str(row[k]) for k in config_keys)
        pivot[key][str(row["agent"])] = float(row["win_rate"])
    return pivot


def balance_score(r: float, h: float, m: float) -> float:
    return 1.0 - abs(m - 0.80) - 0.7 * abs(h - 0.50) + 0.6 * (m - h) - 0.5 * r


def balance_label(r: float, h: float, m: float) -> str:
    if m < 0.50:
        return "too hard"
    if h >= 0.90 and m >= 0.95:
        return "too easy"
    if r >= 0.50 and h >= 0.90:
        return "too easy"
    if 0.30 <= h <= 0.70 and 0.60 <= m <= 0.95 and m > h:
        return "balanced"
    if h < 0.30 and m >= 0.60:
        return "expert-leaning"
    if h >= 0.70 and m >= h:
        return "easy"
    return "mixed"


def final_config_order_key(row: dict[str, object]) -> tuple[int, int]:
    return (
        SIZE_ORDER.index(str(row["size"])) if str(row["size"]) in SIZE_ORDER else 99,
        MAP_TYPE_ORDER.index(str(row["map_type"])) if str(row["map_type"]) in MAP_TYPE_ORDER else 99,
    )


def plot_final_size_win_rates(final_rows: list[dict[str, str]]) -> Path:
    records = aggregate_agent_results(final_rows, ["size", "agent"])
    by_key = {(str(r["size"]), str(r["agent"])): r for r in records}

    width, height = 1650, 980
    img, draw = new_canvas(width, height)

    left, top, right, bottom = 150, 95, width - 90, height - 150

    def value_to_y(value: float) -> float:
        return bottom - value * (bottom - top)

    draw_grid_y(draw, left, top, right, bottom, [0, 0.25, 0.5, 0.75, 1.0], value_to_y)
    draw_line_scaled(draw, (left, bottom, right, bottom), COLORS["axis"], width=2)
    draw_line_scaled(draw, (left, top, left, bottom), COLORS["axis"], width=2)
    draw_text_scaled(draw, (left - 105, top - 58), "Win rate", FONT_LABEL, COLORS["axis"])

    group_width = (right - left) / len(SIZE_ORDER)
    bar_width = 58
    gap = 15
    for group_index, size in enumerate(SIZE_ORDER):
        center = left + group_width * group_index + group_width / 2
        first_x = center - (len(AGENT_ORDER) * bar_width + (len(AGENT_ORDER) - 1) * gap) / 2
        for agent_index, agent in enumerate(AGENT_ORDER):
            record = by_key[(size, agent)]
            wr = float(record["win_rate"])
            ci_low = float(record["ci_low"])
            ci_high = float(record["ci_high"])
            x0 = first_x + agent_index * (bar_width + gap)
            y0 = value_to_y(wr)
            draw_round(draw, (x0, y0, x0 + bar_width, bottom), COLORS[agent], radius=8)

            cx = x0 + bar_width / 2
            draw_line_scaled(draw, (cx, value_to_y(ci_low), cx, value_to_y(ci_high)), "#1E293B", width=2)
            draw_line_scaled(draw, (cx - 10, value_to_y(ci_low), cx + 10, value_to_y(ci_low)), "#1E293B", width=2)
            draw_line_scaled(draw, (cx - 10, value_to_y(ci_high), cx + 10, value_to_y(ci_high)), "#1E293B", width=2)

        draw_text_scaled(draw, (center, bottom + 35), size.title(), FONT_H2, COLORS["ink"], anchor="mm")

    legend_x = left
    legend_y = height - 75
    for agent in AGENT_ORDER:
        draw_round(draw, (legend_x, legend_y, legend_x + 28, legend_y + 18), COLORS[agent], radius=5)
        draw_text_scaled(draw, (legend_x + 38, legend_y - 3), AGENT_LABELS[agent], FONT_SMALL, COLORS["ink"])
        legend_x += 245

    path = FIG_DIR / "01_final_validation_difficulty_ladder.png"
    save_canvas(img, path)
    return path


def final_config_records(final_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    config_keys = ["size", "map_type", "enemy_profile", "item_profile", "wall_profile"]
    pivot = pivot_win_rates(final_rows, config_keys)
    agent_records = aggregate_agent_results(final_rows, config_keys + ["agent"])
    metric_by_config_agent = {
        tuple(str(r[k]) for k in config_keys) + (str(r["agent"]),): r for r in agent_records
    }

    records = []
    for key, rates in pivot.items():
        row: dict[str, object] = dict(zip(config_keys, key))
        row.update({f"wr_{agent}": rates.get(agent, 0.0) for agent in AGENT_ORDER})
        row["skill_gap"] = float(row["wr_mcts_medium"]) - float(row["wr_heuristic"])
        row["score"] = balance_score(float(row["wr_random"]), float(row["wr_heuristic"]), float(row["wr_mcts_medium"]))
        row["label"] = balance_label(float(row["wr_random"]), float(row["wr_heuristic"]), float(row["wr_mcts_medium"]))
        mcts_metrics = metric_by_config_agent[key + ("mcts_medium",)]
        heuristic_metrics = metric_by_config_agent[key + ("heuristic",)]
        row["mcts_turns"] = float(mcts_metrics["avg_turns"])
        row["heuristic_turns"] = float(heuristic_metrics["avg_turns"])
        row["chokepoints"] = float(mcts_metrics["avg_chokepoints"])
        row["dead_ends"] = float(mcts_metrics["avg_dead_ends"])
        records.append(row)
    records.sort(key=final_config_order_key)
    return records


def config_label(row: dict[str, object], compact: bool = False) -> str:
    size = str(row["size"])
    map_type = str(row["map_type"]).replace("_", " ")
    if compact:
        return f"{size[0].upper()} {map_type}"
    return f"{size.title()} - {map_type}"


def plot_final_config_skill_gap(final_rows: list[dict[str, str]]) -> Path:
    records = final_config_records(final_rows)
    width, height = 1750, 1120
    img, draw = new_canvas(width, height)

    left, top, right, bottom = 430, 105, width - 150, height - 125

    def x_for(value: float) -> float:
        return left + value * (right - left)

    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        x = x_for(tick)
        draw_line_scaled(draw, (x, top, x, bottom), COLORS["grid"], width=1)
        draw_text_scaled(draw, (x, bottom + 20), pct(tick), FONT_SMALL, COLORS["muted"], anchor="ma")
    draw_line_scaled(draw, (left, bottom, right, bottom), COLORS["axis"], width=2)
    draw_text_scaled(draw, ((left + right) / 2, bottom + 62), "Win rate", FONT_LABEL, COLORS["axis"], anchor="mm")

    row_gap = (bottom - top) / (len(records) - 1)
    for idx, row in enumerate(records):
        y = top + idx * row_gap
        label = config_label(row)
        draw_text_scaled(draw, (left - 24, y - 12), label, FONT_SMALL, COLORS["ink"], anchor="ra")
        draw_text_scaled(
            draw,
            (left - 24, y + 12),
            f"{row['enemy_profile']}, {row['item_profile']}, {row['wall_profile']}",
            FONT_TINY,
            COLORS["muted"],
            anchor="ra",
        )

        r = float(row["wr_random"])
        h = float(row["wr_heuristic"])
        s = float(row["wr_mcts_small"])
        m = float(row["wr_mcts_medium"])
        draw_line_scaled(draw, (x_for(h), y, x_for(m), y), "#93C5FD", width=9)
        for value, agent, radius in [
            (r, "random", 7),
            (h, "heuristic", 10),
            (s, "mcts_small", 8),
            (m, "mcts_medium", 12),
        ]:
            x = x_for(value)
            draw.ellipse(
                scaled_rect((x - radius, y - radius, x + radius, y + radius)),
                fill=color(COLORS[agent]),
                outline=color("white"),
                width=sx(2),
            )
        draw_text_scaled(draw, (right + 20, y - 10), f"+{pct(float(row['skill_gap']))}", FONT_SMALL, COLORS["mcts_medium"])

    legend_x = left
    legend_y = 45
    for agent in ["random", "heuristic", "mcts_small", "mcts_medium"]:
        draw.ellipse(scaled_rect((legend_x, legend_y, legend_x + 18, legend_y + 18)), fill=color(COLORS[agent]))
        draw_text_scaled(draw, (legend_x + 28, legend_y - 3), AGENT_LABELS[agent], FONT_SMALL, COLORS["ink"])
        legend_x += 230

    path = FIG_DIR / "02_final_validation_skill_gap_dumbbell.png"
    save_canvas(img, path)
    return path


def plot_paired_outcomes(final_rows: list[dict[str, str]]) -> Path:
    config_keys = ["size", "map_type", "enemy_profile", "item_profile", "wall_profile"]
    by_key: dict[tuple[str, ...], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in final_rows:
        if row["agent"] not in {"heuristic", "mcts_medium"}:
            continue
        key = tuple(row[k] for k in config_keys + ["map_seed"])
        by_key[key][row["agent"]] = row

    counts: dict[tuple[str, ...], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    metadata: dict[tuple[str, ...], dict[str, str]] = {}
    for key, agents in by_key.items():
        if "heuristic" not in agents or "mcts_medium" not in agents:
            continue
        config_key = key[:-1]
        metadata[config_key] = {k: v for k, v in zip(config_keys, config_key)}
        h = i(agents["heuristic"], "won")
        m = i(agents["mcts_medium"], "won")
        if h and m:
            bucket = "both_win"
        elif (not h) and m:
            bucket = "mcts_only"
        elif h and (not m):
            bucket = "heuristic_only"
        else:
            bucket = "both_loss"
        counts[config_key][bucket] += 1

    rows = []
    for config_key, bucket_counts in counts.items():
        row: dict[str, object] = dict(metadata[config_key])
        row.update({bucket: bucket_counts.get(bucket, 0) for bucket in ["both_win", "mcts_only", "heuristic_only", "both_loss"]})
        row["total"] = sum(int(row[b]) for b in ["both_win", "mcts_only", "heuristic_only", "both_loss"])
        rows.append(row)
    rows.sort(key=final_config_order_key)

    width, height = 1750, 1080
    img, draw = new_canvas(width, height)

    left, top, right, bottom = 440, 105, width - 120, height - 145
    bar_h = 46
    row_gap = (bottom - top) / len(rows)

    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        x = left + tick * (right - left)
        draw_line_scaled(draw, (x, top - 20, x, bottom + 10), COLORS["grid"], width=1)
        draw_text_scaled(draw, (x, bottom + 26), pct(tick), FONT_SMALL, COLORS["muted"], anchor="ma")

    order = ["both_win", "mcts_only", "heuristic_only", "both_loss"]
    labels = {
        "both_win": "Both win",
        "mcts_only": "MCTS only",
        "heuristic_only": "Heuristic only",
        "both_loss": "Both lose",
    }

    for idx, row in enumerate(rows):
        y = top + idx * row_gap + row_gap / 2
        draw_text_scaled(draw, (left - 25, y - 13), config_label(row), FONT_SMALL, COLORS["ink"], anchor="ra")
        total = max(1, int(row["total"]))
        x = left
        for bucket in order:
            value = int(row[bucket])
            frac = value / total
            w = frac * (right - left)
            if w > 0:
                draw_round(draw, (x, y - bar_h / 2, x + w, y + bar_h / 2), COLORS[bucket], radius=6)
                if w > 70:
                    text_fill = "white" if bucket in {"both_win", "mcts_only", "heuristic_only"} else COLORS["ink"]
                    draw_text_scaled(draw, (x + w / 2, y - 10), pct(frac), FONT_TINY, text_fill, anchor="ma")
            x += w

    legend_x = left
    legend_y = 45
    for bucket in order:
        draw_round(draw, (legend_x, legend_y, legend_x + 32, legend_y + 20), COLORS[bucket], radius=5)
        draw_text_scaled(draw, (legend_x + 42, legend_y - 2), labels[bucket], FONT_SMALL, COLORS["ink"])
        legend_x += 250

    path = FIG_DIR / "03_paired_heuristic_vs_mcts_outcomes.png"
    save_canvas(img, path)
    return path


def medium_tuning_records(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    config_keys = ["size", "map_type", "enemy_profile", "item_profile", "wall_profile"]
    pivot = pivot_win_rates(rows, config_keys)
    records = []
    for key, rates in pivot.items():
        row: dict[str, object] = dict(zip(config_keys, key))
        r = rates.get("random", 0.0)
        h = rates.get("heuristic", 0.0)
        m = rates.get("mcts_medium", 0.0)
        s = rates.get("mcts_small", 0.0)
        row.update(
            {
                "wr_random": r,
                "wr_heuristic": h,
                "wr_mcts_small": s,
                "wr_mcts_medium": m,
                "score": balance_score(r, h, m),
                "label": balance_label(r, h, m),
            }
        )
        records.append(row)
    return records


def score_color(value: float, vmin: float = 0.45, vmax: float = 1.20) -> tuple[int, int, int]:
    t = (value - vmin) / (vmax - vmin)
    if t < 0.5:
        return blend("#F1F5F9", "#BAE6FD", t * 2)
    return blend("#BAE6FD", "#166534", (t - 0.5) * 2)


def plot_medium_tuning_heatmap(rows: list[dict[str, str]]) -> Path:
    records = [
        row
        for row in medium_tuning_records(rows)
        if row["size"] == "medium" and row["wall_profile"] == "open"
    ]
    by_key = {
        (str(row["map_type"]), str(row["enemy_profile"]), str(row["item_profile"])): row
        for row in records
    }

    width, height = 1680, 650
    img, draw = new_canvas(width, height)

    panel_w = 485
    panel_h = 455
    start_x = 80
    start_y = 145
    gap = 45
    label_w = 135
    cell_w = 145
    cell_h = 116

    for panel_idx, map_type in enumerate(MAP_TYPE_ORDER):
        px = start_x + panel_idx * (panel_w + gap)
        py = start_y
        draw_round(draw, (px, py - 60, px + panel_w, py + panel_h), COLORS["panel"], "#CBD5E1", radius=18)
        draw_text_scaled(draw, (px + panel_w / 2, py - 40), map_type.replace("_", " ").title(), FONT_H2, COLORS["ink"], anchor="mm")

        for c, item in enumerate(ITEM_ORDER):
            draw_text_scaled(draw, (px + label_w + c * cell_w + (cell_w - 16) / 2, py + 8), item.title(), FONT_SMALL, COLORS["muted"], anchor="mm")
        for r, enemy in enumerate(ENEMY_ORDER):
            draw_text_scaled(draw, (px + 24, py + 70 + r * cell_h), enemy.replace("_", " "), FONT_SMALL, COLORS["ink"], anchor="la")
            for c, item in enumerate(ITEM_ORDER):
                x0 = px + label_w + c * cell_w
                y0 = py + 35 + r * cell_h
                rec = by_key.get((map_type, enemy, item))
                if not rec:
                    fill = "#F8FAFC"
                    text = "n/a"
                    detail = ""
                else:
                    score = float(rec["score"])
                    fill = score_color(score)
                    text = f"{score:.2f}"
                    detail = f"H {short_pct(float(rec['wr_heuristic']))} / M {short_pct(float(rec['wr_mcts_medium']))}"
                draw_round(draw, (x0, y0, x0 + cell_w - 16, y0 + cell_h - 16), fill, "white", width=3, radius=14)
                draw_text_scaled(draw, (x0 + (cell_w - 16) / 2, y0 + 27), text, FONT_H2, "white" if rec and float(rec["score"]) > 0.95 else COLORS["ink"], anchor="mm")
                draw_text_scaled(draw, (x0 + (cell_w - 16) / 2, y0 + 67), detail, FONT_TINY, "white" if rec and float(rec["score"]) > 0.95 else COLORS["muted"], anchor="mm")

    path = FIG_DIR / "04_medium_enemy_tuning_balance_heatmap.png"
    save_canvas(img, path)
    return path


def plot_ofat_effect_sizes() -> Path:
    rows = read_csv(ROOT / "results_analysis" / "ofat_real" / "tables" / "ofat_effect_sizes.csv")
    values: dict[tuple[str, str], float] = {}
    for row in rows:
        values[(row["factor"], row["agent"])] = f(row, "win_rate_range")

    width, height = 1600, 980
    img, draw = new_canvas(width, height)

    left, top, right, bottom = 320, 105, width - 100, height - 130

    def x_for(value: float) -> float:
        return left + value * (right - left)

    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        x = x_for(tick)
        draw_line_scaled(draw, (x, top, x, bottom), COLORS["grid"], width=1)
        draw_text_scaled(draw, (x, bottom + 24), pct(tick), FONT_SMALL, COLORS["muted"], anchor="ma")

    row_h = (bottom - top) / len(FACTOR_ORDER)
    bar_h = 13
    agent_offsets = [-24, -8, 8, 24]
    for idx, factor_name in enumerate(FACTOR_ORDER):
        y = top + row_h * idx + row_h / 2
        draw_text_scaled(draw, (left - 20, y - 13), FACTOR_LABELS[factor_name], FONT_LABEL, COLORS["ink"], anchor="ra")
        for agent_idx, agent in enumerate(AGENT_ORDER):
            value = values.get((factor_name, agent), 0.0)
            y0 = y + agent_offsets[agent_idx]
            draw_round(draw, (left, y0 - bar_h / 2, x_for(value), y0 + bar_h / 2), COLORS[agent], radius=6)
            if value >= 0.15:
                draw_text_scaled(draw, (x_for(value) + 8, y0 - 9), pct(value), FONT_TINY, COLORS["muted"])

    legend_x = left
    legend_y = 45
    for agent in AGENT_ORDER:
        draw_round(draw, (legend_x, legend_y, legend_x + 28, legend_y + 18), COLORS[agent], radius=5)
        draw_text_scaled(draw, (legend_x + 38, legend_y - 3), AGENT_LABELS[agent], FONT_SMALL, COLORS["ink"])
        legend_x += 245

    path = FIG_DIR / "05_ofat_factor_sensitivity.png"
    save_canvas(img, path)
    return path


def plot_hp_sensitivity() -> Path:
    rows = read_csv(ROOT / "results_analysis" / "ofat_real" / "tables" / "ofat_factor_summary.csv")
    rows = [row for row in rows if row["factor"] in {"player_hp", "enemy_hp"}]
    by_factor_agent: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_factor_agent[(row["factor"], row["agent"])].append(row)

    width, height = 1650, 900
    img, draw = new_canvas(width, height)

    panels = [
        ("player_hp", "Player HP", [3, 4, 5, 6], 150),
        ("enemy_hp", "Enemy HP", [1, 2, 3], 900),
    ]

    for factor_name, title, x_values, left in panels:
        top, right, bottom = 135, left + 600, height - 140

        def x_for(value: float) -> float:
            if len(x_values) == 1:
                return (left + right) / 2
            return left + (x_values.index(int(value)) / (len(x_values) - 1)) * (right - left)

        def y_for(value: float) -> float:
            return bottom - value * (bottom - top)

        draw_text_scaled(draw, ((left + right) / 2, top - 45), title, FONT_H2, COLORS["ink"], anchor="mm")
        for tick in [0, 0.25, 0.5, 0.75, 1.0]:
            y = y_for(tick)
            draw_line_scaled(draw, (left, y, right, y), COLORS["grid"], width=1)
            draw_text_scaled(draw, (left - 14, y - 10), pct(tick), FONT_TINY, COLORS["muted"], anchor="ra")
        draw_line_scaled(draw, (left, bottom, right, bottom), COLORS["axis"], width=2)
        draw_line_scaled(draw, (left, top, left, bottom), COLORS["axis"], width=2)

        for xv in x_values:
            x = x_for(xv)
            draw_line_scaled(draw, (x, bottom, x, bottom + 8), COLORS["axis"], width=2)
            draw_text_scaled(draw, (x, bottom + 20), str(xv), FONT_SMALL, COLORS["muted"], anchor="ma")

        for agent in AGENT_ORDER:
            points = []
            for row in by_factor_agent.get((factor_name, agent), []):
                value = int(float(row["value"]))
                if value in x_values:
                    points.append((value, f(row, "win_rate")))
            points.sort()
            for a, b in zip(points, points[1:]):
                draw_line_scaled(draw, (x_for(a[0]), y_for(a[1]), x_for(b[0]), y_for(b[1])), COLORS[agent], width=4)
            for xv, wr in points:
                x = x_for(xv)
                y = y_for(wr)
                draw.ellipse(scaled_rect((x - 8, y - 8, x + 8, y + 8)), fill=color(COLORS[agent]), outline=color("white"), width=sx(2))

    legend_x = 150
    legend_y = height - 90
    for agent in AGENT_ORDER:
        draw.ellipse(scaled_rect((legend_x, legend_y, legend_x + 18, legend_y + 18)), fill=color(COLORS[agent]))
        draw_text_scaled(draw, (legend_x + 28, legend_y - 3), AGENT_LABELS[agent], FONT_SMALL, COLORS["ink"])
        legend_x += 245

    path = FIG_DIR / "06_hp_sensitivity_curves.png"
    save_canvas(img, path)
    return path


def plot_structure_pacing(final_rows: list[dict[str, str]]) -> Path:
    records = [r for r in aggregate_agent_results(final_rows, ["size", "map_type", "agent"]) if r["agent"] == "mcts_medium"]
    width, height = 1500, 1000
    img, draw = new_canvas(width, height)

    left, top, right, bottom = 180, 120, width - 130, height - 155
    max_choke = max(float(r["avg_chokepoints"]) for r in records) * 1.08
    max_turns = max(float(r["avg_turns"]) for r in records) * 1.08

    def x_for(value: float) -> float:
        return left + (value / max_choke) * (right - left)

    def y_for(value: float) -> float:
        return bottom - (value / max_turns) * (bottom - top)

    for tick in [0, 5, 10, 15]:
        x = x_for(tick)
        draw_line_scaled(draw, (x, top, x, bottom), COLORS["grid"], width=1)
        draw_text_scaled(draw, (x, bottom + 22), str(tick), FONT_SMALL, COLORS["muted"], anchor="ma")
    for tick in [0, 10, 20, 30, 40]:
        y = y_for(tick)
        draw_line_scaled(draw, (left, y, right, y), COLORS["grid"], width=1)
        draw_text_scaled(draw, (left - 15, y - 10), str(tick), FONT_SMALL, COLORS["muted"], anchor="ra")

    draw_line_scaled(draw, (left, bottom, right, bottom), COLORS["axis"], width=2)
    draw_line_scaled(draw, (left, top, left, bottom), COLORS["axis"], width=2)
    draw_text_scaled(draw, ((left + right) / 2, bottom + 60), "Average chokepoints", FONT_LABEL, COLORS["axis"], anchor="mm")
    draw_text_scaled(draw, (left - 100, top - 30), "Avg. turns", FONT_LABEL, COLORS["axis"])

    # Least-squares trend line.
    xs = [float(r["avg_chokepoints"]) for r in records]
    ys = [float(r["avg_turns"]) for r in records]
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    denom = sum((x - x_mean) ** 2 for x in xs) or 1
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
    intercept = y_mean - slope * x_mean
    x0, x1 = 0, max_choke
    draw_line_scaled(draw, (x_for(x0), y_for(intercept + slope * x0), x_for(x1), y_for(intercept + slope * x1)), "#94A3B8", width=3)

    for row in records:
        mt = str(row["map_type"])
        x = x_for(float(row["avg_chokepoints"]))
        y = y_for(float(row["avg_turns"]))
        radius = 14
        draw.ellipse(scaled_rect((x - radius, y - radius, x + radius, y + radius)), fill=color(COLORS[mt]), outline=color("white"), width=sx(3))
        label = f"{str(row['size'])[0].upper()} {mt.replace('_', ' ')}"
        draw_text_scaled(draw, (x + 18, y - 12), label, FONT_TINY, COLORS["ink"])

    legend_x = left
    legend_y = 55
    for map_type in MAP_TYPE_ORDER:
        draw.ellipse(scaled_rect((legend_x, legend_y, legend_x + 18, legend_y + 18)), fill=color(COLORS[map_type]))
        draw_text_scaled(draw, (legend_x + 28, legend_y - 3), map_type.replace("_", " ").title(), FONT_SMALL, COLORS["ink"])
        legend_x += 240

    path = FIG_DIR / "07_structure_vs_pacing.png"
    save_canvas(img, path)
    return path


def write_csv_table(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(headers)
        writer.writerows(rows)


def write_report_tables(final_rows: list[dict[str, str]]) -> list[Path]:
    written: list[Path] = []
    final_records = final_config_records(final_rows)
    final_table = []
    for row in final_records:
        final_table.append(
            [
                str(row["size"]),
                str(row["map_type"]),
                str(row["enemy_profile"]),
                str(row["item_profile"]),
                str(row["wall_profile"]),
                pct(float(row["wr_random"])),
                pct(float(row["wr_heuristic"])),
                pct(float(row["wr_mcts_small"])),
                pct(float(row["wr_mcts_medium"])),
                pct(float(row["skill_gap"])),
                str(row["label"]),
            ]
        )
    headers = ["Size", "Map", "Enemy", "Items", "Walls", "Random", "Heuristic", "MCTS-S", "MCTS-M", "Gap", "Label"]
    path = TABLE_DIR / "final_validation_config_summary.csv"
    write_csv_table(path, headers, final_table)
    written.append(path)

    by_size = aggregate_agent_results(final_rows, ["size", "agent"])
    rows_by_size = []
    for size in SIZE_ORDER:
        row = [size]
        for agent in AGENT_ORDER:
            match = next(r for r in by_size if r["size"] == size and r["agent"] == agent)
            row.append(pct(float(match["win_rate"]), decimals=1))
        rows_by_size.append(row)
    headers = ["Size", "Random", "Heuristic", "MCTS-small", "MCTS-medium"]
    path = TABLE_DIR / "final_validation_by_size.csv"
    write_csv_table(path, headers, rows_by_size)
    written.append(path)

    ofat_rows = read_csv(ROOT / "results_analysis" / "ofat_real" / "tables" / "ofat_effect_sizes.csv")
    by_factor_agent = {(row["factor"], row["agent"]): f(row, "win_rate_range") for row in ofat_rows}
    effect_rows = []
    for factor_name in FACTOR_ORDER:
        effect_rows.append(
            [
                FACTOR_LABELS[factor_name],
                pct(by_factor_agent.get((factor_name, "random"), 0.0), decimals=1),
                pct(by_factor_agent.get((factor_name, "heuristic"), 0.0), decimals=1),
                pct(by_factor_agent.get((factor_name, "mcts_small"), 0.0), decimals=1),
                pct(by_factor_agent.get((factor_name, "mcts_medium"), 0.0), decimals=1),
            ]
        )
    headers = ["Factor", "Random", "Heuristic", "MCTS-small", "MCTS-medium"]
    path = TABLE_DIR / "ofat_effect_sizes.csv"
    write_csv_table(path, headers, effect_rows)
    written.append(path)

    experiment_rows = [
        ["PCG screening", "648", "20", "12,960", "Broad search over generator profiles"],
        ["Medium enemy tuning", "144", "30", "4,320", "Tune medium-map enemy profile"],
        ["OFAT sensitivity", "68", "30", "2,040", "Local sensitivity around tuned baseline"],
        ["Final validation", "36", "50", "1,800", "Validate selected final defaults"],
    ]
    headers = ["Experiment", "Cells", "Episodes/cell", "Total episodes", "Purpose"]
    path = TABLE_DIR / "experiment_scale.csv"
    write_csv_table(path, headers, experiment_rows)
    written.append(path)
    return written


def wrap_text(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if text_size(draw, candidate, face)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_map_screenshot(
    size: str,
    map_type: str,
    enemy_profile: str,
    item_profile: str,
    wall_profile: str,
    enemy_count: str,
    items: str,
    wall_density: str,
    seed: int,
    title: str,
    path: Path,
) -> Path:
    sys.path.insert(0, str(ROOT))
    from grid_battle.pcg import analyze_level, generate_preset_level

    generated = generate_preset_level(
        size=size,
        map_type=map_type,
        seed=seed,
        item_level=items,
        enemy_count=enemy_count,
        wall_density=wall_density,
    )
    analysis = analyze_level(generated.layout)

    rows = generated.layout.splitlines()
    map_w = len(rows[0])
    map_h = len(rows)

    canvas_w, canvas_h = 1600, 980
    margin = 70
    sidebar_w = 430
    board_area_w = canvas_w - sidebar_w - margin * 3
    board_area_h = canvas_h - 190
    tile = min(board_area_w // map_w, board_area_h // map_h)
    board_w = tile * map_w
    board_h = tile * map_h
    board_x = margin
    board_y = 165

    img = Image.new("RGB", (canvas_w, canvas_h), color("#F8FAFC"))
    draw = ImageDraw.Draw(img)
    draw_header(draw, title, f"{size} / {map_type.replace('_', ' ')} / seed {seed}", canvas_w)

    # Board shell.
    draw_round(draw, (board_x - 18, board_y - 18, board_x + board_w + 18, board_y + board_h + 18), "#1E293B", radius=22)
    draw_round(draw, (board_x - 8, board_y - 8, board_x + board_w + 8, board_y + board_h + 8), "#334155", radius=14)

    asset_dir = ROOT / "assets" / "sprites"
    sprite_map = {
        "A": "player.png",
        "E": "enemy.png",
        "W": "wall.png",
        "H": "hill.png",
        "B": "bush.png",
        "K": "bunker.png",
        "D": "item_dual_berettas.png",
        "S": "item_shotgun.png",
        "G": "item_golden_gun.png",
        "V": "item_vehicle.png",
    }
    sprites: dict[str, Image.Image] = {}
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    for symbol, filename in sprite_map.items():
        sprite_path = asset_dir / filename
        if sprite_path.exists():
            sprites[symbol] = Image.open(sprite_path).convert("RGBA").resize((tile, tile), resampling)

    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            x0 = board_x + x * tile
            y0 = board_y + y * tile
            rect = (x0, y0, x0 + tile, y0 + tile)
            floor = "#64748B" if (x + y) % 2 else "#708090"
            if ch == "W":
                floor = "#334155"
            draw.rectangle(rect, fill=color(floor))
            draw.rectangle(rect, outline=color("#475569"), width=1)
            if ch != "." and ch in sprites:
                img.paste(sprites[ch], (x0, y0), sprites[ch])

    side_x = board_x + board_w + 60
    side_y = board_y - 18
    draw_round(draw, (side_x, side_y, canvas_w - margin, side_y + board_h + 36), "white", "#CBD5E1", radius=20)
    draw_text_scaled(draw, (side_x + 30, side_y + 32), "Generated Map", FONT_H2, COLORS["ink"])
    draw_text_scaled(draw, (side_x + 30, side_y + 78), "Final generator profile", FONT_SMALL, COLORS["muted"])

    facts = [
        ("Size", size),
        ("Map type", map_type.replace("_", " ")),
        ("Enemy profile", enemy_profile.replace("_", "+")),
        ("Items", item_profile),
        ("Walls", wall_profile),
        ("Dimensions", f"{generated.width} x {generated.height}"),
        ("Enemies", str(generated.enemy_count)),
        ("Chokepoints", str(analysis.chokepoint_count)),
        ("Dead ends", str(analysis.dead_end_count)),
        ("Reachable floor", pct(analysis.reachable_floor_fraction, decimals=1)),
    ]
    fy = side_y + 130
    for label, value in facts:
        draw_text_scaled(draw, (side_x + 30, fy), label, FONT_SMALL, COLORS["muted"])
        draw_text_scaled(draw, (canvas_w - margin - 28, fy), value, FONT_SMALL, COLORS["ink"], anchor="ra")
        fy += 39

    legend = "Legend: A player, E enemy, W wall, H hill, B bush, K bunker, D/S/G/V items."
    for line in wrap_text(draw, legend, FONT_SMALL, canvas_w - margin - side_x - 60):
        draw_text_scaled(draw, (side_x + 30, fy + 18), line, FONT_SMALL, COLORS["muted"])
        fy += 28

    img.save(path)
    return path


def make_screenshots() -> list[Path]:
    presets = [
        {
            "size": "small",
            "map_type": "baseline",
            "enemy_profile": "normal",
            "item_profile": "normal",
            "wall_profile": "normal",
            "enemy_count": "default",
            "items": "normal",
            "wall_density": "default",
            "seed": 11,
            "title": "Tutorial-like final map",
            "filename": "ui_small_baseline_final.png",
        },
        {
            "size": "medium",
            "map_type": "arena",
            "enemy_profile": "medium_plus",
            "item_profile": "many",
            "wall_profile": "open",
            "enemy_count": "medium_plus",
            "items": "many",
            "wall_density": "low",
            "seed": 11,
            "title": "Balanced medium final map",
            "filename": "ui_medium_arena_final.png",
        },
        {
            "size": "large",
            "map_type": "random_walk",
            "enemy_profile": "normal",
            "item_profile": "many",
            "wall_profile": "open",
            "enemy_count": "default",
            "items": "many",
            "wall_density": "low",
            "seed": 14,
            "title": "Long-form random-walk final map",
            "filename": "ui_large_random_walk_final.png",
        },
    ]
    paths = []
    for preset in presets:
        filename = str(preset.pop("filename"))
        path = SCREENSHOT_DIR / filename
        render_map_screenshot(path=path, **preset)
        paths.append(path)
    return paths


def main() -> None:
    ensure_dirs()
    clean_generated_outputs()
    final_rows = read_csv(ROOT / "results" / "final_validation.csv")
    medium_rows = read_csv(ROOT / "results" / "medium_enemy_tuning.csv")

    figure_paths = [
        plot_final_size_win_rates(final_rows),
        plot_final_config_skill_gap(final_rows),
        plot_paired_outcomes(final_rows),
        plot_medium_tuning_heatmap(medium_rows),
        plot_ofat_effect_sizes(),
        plot_hp_sensitivity(),
        plot_structure_pacing(final_rows),
    ]
    table_paths = write_report_tables(final_rows)
    screenshot_paths = make_screenshots()

    print(f"Wrote {len(figure_paths)} figures to {FIG_DIR}")
    print(f"Wrote {len(table_paths)} tables to {TABLE_DIR}")
    print(f"Wrote {len(screenshot_paths)} screenshots to {SCREENSHOT_DIR}")


if __name__ == "__main__":
    main()
