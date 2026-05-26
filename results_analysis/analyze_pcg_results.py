from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


AGENT_ORDER = ["random", "heuristic", "mcts_small", "mcts_medium", "mcts_strong"]
SIZE_ORDER = ["small", "medium", "large"]
MAP_TYPE_ORDER = ["baseline", "random_walk", "arena"]
ENEMY_ORDER = ["light", "normal", "medium_plus", "heavy"]
ITEM_ORDER = ["few", "normal", "many"]
WALL_ORDER = ["open", "normal", "tight"]


GROUP_COLS = [
    "size",
    "map_type",
    "enemy_profile",
    "item_profile",
    "wall_profile",
    "enemy_count_setting",
    "items",
    "wall_density",
    "agent",
]


def ordered_values(values: list[str], preferred_order: list[str]) -> list[str]:
    present = [value for value in preferred_order if value in values]
    rest = sorted(value for value in values if value not in preferred_order)
    return present + rest


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0

    p = successes / n
    denom = 1.0 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return max(0.0, center - half), min(1.0, center + half)


def load_results(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = {
        "agent",
        "size",
        "map_type",
        "enemy_profile",
        "item_profile",
        "wall_profile",
        "won",
        "turns",
        "damage_taken",
        "final_hp",
        "remaining_enemies",
        "chokepoint_count",
        "reachable_floor_fraction",
    }

    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Missing required columns in {path}: {missing}")

    df = df.copy()
    df["won"] = df["won"].astype(int)
    df["turns"] = pd.to_numeric(df["turns"])
    df["damage_taken"] = pd.to_numeric(df["damage_taken"])
    df["final_hp"] = pd.to_numeric(df["final_hp"])
    df["remaining_enemies"] = pd.to_numeric(df["remaining_enemies"])

    for col in ["size", "map_type", "enemy_profile", "item_profile", "wall_profile", "agent"]:
        df[col] = df[col].astype(str)

    return df


def summarize_by_agent(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for keys, group in df.groupby(GROUP_COLS, dropna=False):
        key_dict = dict(zip(GROUP_COLS, keys))
        episodes = len(group)
        wins = int(group["won"].sum())
        low, high = wilson_interval(wins, episodes)

        losses = group[group["won"] == 0]

        row = {
            **key_dict,
            "episodes": episodes,
            "wins": wins,
            "win_rate": wins / episodes,
            "win_rate_ci_low": low,
            "win_rate_ci_high": high,
            "avg_turns": group["turns"].mean(),
            "std_turns": group["turns"].std(ddof=0),
            "avg_damage_taken": group["damage_taken"].mean(),
            "avg_final_hp": group["final_hp"].mean(),
            "avg_remaining_enemies": group["remaining_enemies"].mean(),
            "avg_remaining_enemies_on_losses": losses["remaining_enemies"].mean() if len(losses) else 0.0,
            "avg_chokepoints": group["chokepoint_count"].mean(),
            "avg_reachable_floor_fraction": group["reachable_floor_fraction"].mean(),
        }

        for optional in [
            "generated_enemy_count",
            "generated_obstacle_density",
            "interior_wall_density",
            "dead_end_count",
            "avg_enemy_attack_distance",
            "max_enemy_attack_distance",
        ]:
            if optional in group.columns:
                row[f"avg_{optional}"] = pd.to_numeric(group[optional]).mean()

        rows.append(row)

    return pd.DataFrame(rows)


def summarize_configs(agent_summary: pd.DataFrame) -> pd.DataFrame:
    config_cols = [
        "size",
        "map_type",
        "enemy_profile",
        "item_profile",
        "wall_profile",
        "enemy_count_setting",
        "items",
        "wall_density",
    ]

    pivot = agent_summary.pivot_table(
        index=config_cols,
        columns="agent",
        values=["win_rate", "avg_turns", "avg_damage_taken"],
        aggfunc="first",
    )

    pivot.columns = [f"{metric}_{agent}" for metric, agent in pivot.columns]
    pivot = pivot.reset_index()

    for agent in AGENT_ORDER:
        col = f"win_rate_{agent}"
        if col not in pivot.columns:
            pivot[col] = np.nan

    pivot["skill_gap_mcts_medium_vs_heuristic"] = (
        pivot["win_rate_mcts_medium"] - pivot["win_rate_heuristic"]
    )
    pivot["skill_gap_mcts_small_vs_heuristic"] = (
        pivot["win_rate_mcts_small"] - pivot["win_rate_heuristic"]
    )
    pivot["search_gain_medium_vs_small"] = (
        pivot["win_rate_mcts_medium"] - pivot["win_rate_mcts_small"]
    )

    # Simple balance score:
    # - Reward MCTS-medium being reliably successful.
    # - Reward heuristic not being perfect.
    # - Reward positive skill separation.
    # - Penalize random success.
    # This is only a ranking aid, not a formal objective.
    m = pivot["win_rate_mcts_medium"]
    h = pivot["win_rate_heuristic"]
    r = pivot["win_rate_random"]

    target_mcts = 0.80
    target_heuristic = 0.50

    pivot["balance_score"] = (
        1.0
        - (m - target_mcts).abs()
        - 0.7 * (h - target_heuristic).abs()
        + 0.6 * (m - h)
        - 0.5 * r.fillna(0)
    )

    pivot["balance_label"] = pivot.apply(label_config, axis=1)

    return pivot.sort_values("balance_score", ascending=False)


def label_config(row: pd.Series) -> str:
    h = row.get("win_rate_heuristic", np.nan)
    m = row.get("win_rate_mcts_medium", np.nan)
    r = row.get("win_rate_random", np.nan)

    if pd.isna(h) or pd.isna(m):
        return "incomplete"

    if m < 0.50:
        return "too hard"
    if h >= 0.90 and m >= 0.95:
        return "too easy"
    if r >= 0.50 and h >= 0.90:
        return "too easy / random succeeds"
    if 0.30 <= h <= 0.70 and 0.60 <= m <= 0.95 and m > h:
        return "balanced"
    if h < 0.30 and m >= 0.60:
        return "expert-leaning"
    if h >= 0.70 and m >= h:
        return "playable but easy"
    return "mixed"


def save_heatmap(
    data: pd.DataFrame,
    rows: list[str],
    cols: list[str],
    title: str,
    path: Path,
    value_format: str = ".0%",
    vmin: float | None = 0.0,
    vmax: float | None = 1.0,
) -> None:
    matrix = data.reindex(index=rows, columns=cols)

    fig, ax = plt.subplots(figsize=(1.8 * max(3, len(cols)), 1.2 * max(3, len(rows))))
    im = ax.imshow(matrix.values.astype(float), vmin=vmin, vmax=vmax)

    ax.set_xticks(np.arange(len(cols)))
    ax.set_yticks(np.arange(len(rows)))
    ax.set_xticklabels(cols, rotation=35, ha="right")
    ax.set_yticklabels(rows)
    ax.set_title(title)

    for i in range(len(rows)):
        for j in range(len(cols)):
            value = matrix.iloc[i, j]
            if pd.notna(value):
                ax.text(j, i, format(value, value_format), ha="center", va="center")

    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_agent_overview(agent_summary: pd.DataFrame, out_dir: Path) -> None:
    summary = (
        agent_summary.groupby(["size", "map_type", "agent"], as_index=False)
        .agg(win_rate=("win_rate", "mean"), avg_turns=("avg_turns", "mean"))
    )

    sizes = ordered_values(summary["size"].unique().tolist(), SIZE_ORDER)
    map_types = ordered_values(summary["map_type"].unique().tolist(), MAP_TYPE_ORDER)
    agents = ordered_values(summary["agent"].unique().tolist(), AGENT_ORDER)

    labels = [f"{size}\n{map_type}" for size in sizes for map_type in map_types]
    x = np.arange(len(labels))
    width = 0.8 / max(1, len(agents))

    fig, ax = plt.subplots(figsize=(max(10, len(labels) * 1.4), 6))

    for index, agent in enumerate(agents):
        values = []
        for size in sizes:
            for map_type in map_types:
                match = summary[
                    (summary["size"] == size)
                    & (summary["map_type"] == map_type)
                    & (summary["agent"] == agent)
                ]
                values.append(match["win_rate"].iloc[0] if len(match) else np.nan)

        ax.bar(x + (index - (len(agents) - 1) / 2) * width, values, width, label=agent)

    ax.set_ylabel("Win rate")
    ax.set_ylim(0, 1.05)
    ax.set_title("Average win rate by size, map type, and agent")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "01_agent_winrate_overview.png", dpi=180)
    plt.close(fig)


def plot_heatmaps(config_summary: pd.DataFrame, out_dir: Path) -> None:
    heatmap_dir = out_dir / "heatmaps"
    heatmap_dir.mkdir(parents=True, exist_ok=True)

    sizes = ordered_values(config_summary["size"].unique().tolist(), SIZE_ORDER)
    map_types = ordered_values(config_summary["map_type"].unique().tolist(), MAP_TYPE_ORDER)
    wall_profiles = ordered_values(config_summary["wall_profile"].unique().tolist(), WALL_ORDER)
    enemy_profiles = ordered_values(config_summary["enemy_profile"].unique().tolist(), ENEMY_ORDER)
    item_profiles = ordered_values(config_summary["item_profile"].unique().tolist(), ITEM_ORDER)

    heatmap_specs = [
        ("win_rate_heuristic", "Heuristic win rate", ".0%", 0.0, 1.0),
        ("win_rate_mcts_medium", "MCTS-medium win rate", ".0%", 0.0, 1.0),
        ("skill_gap_mcts_medium_vs_heuristic", "MCTS-medium minus heuristic", "+.0%", -1.0, 1.0),
        ("balance_score", "Balance score", ".2f", None, None),
    ]

    for size in sizes:
        for map_type in map_types:
            for wall_profile in wall_profiles:
                subset = config_summary[
                    (config_summary["size"] == size)
                    & (config_summary["map_type"] == map_type)
                    & (config_summary["wall_profile"] == wall_profile)
                ]

                if subset.empty:
                    continue

                for value_col, title, fmt, vmin, vmax in heatmap_specs:
                    if value_col not in subset.columns:
                        continue

                    pivot = subset.pivot_table(
                        index="enemy_profile",
                        columns="item_profile",
                        values=value_col,
                        aggfunc="mean",
                    )

                    filename = (
                        f"heatmap_{value_col}_{size}_{map_type}_{wall_profile}.png"
                        .replace("/", "_")
                    )
                    save_heatmap(
                        pivot,
                        rows=enemy_profiles,
                        cols=item_profiles,
                        title=f"{title}\n{size}, {map_type}, walls={wall_profile}",
                        path=heatmap_dir / filename,
                        value_format=fmt,
                        vmin=vmin,
                        vmax=vmax,
                    )


def plot_balance_candidates(config_summary: pd.DataFrame, out_dir: Path, top_n: int = 20) -> None:
    top = config_summary.head(top_n).copy()
    top["label"] = (
        top["size"]
        + " | "
        + top["map_type"]
        + " | e="
        + top["enemy_profile"]
        + " | i="
        + top["item_profile"]
        + " | w="
        + top["wall_profile"]
    )

    fig, ax = plt.subplots(figsize=(12, max(6, top_n * 0.35)))
    y = np.arange(len(top))

    ax.barh(y, top["balance_score"])
    ax.set_yticks(y)
    ax.set_yticklabels(top["label"])
    ax.invert_yaxis()
    ax.set_xlabel("Balance score")
    ax.set_title(f"Top {top_n} PCG configurations by balance score")

    fig.tight_layout()
    fig.savefig(out_dir / "02_top_balance_candidates.png", dpi=180)
    plt.close(fig)


def plot_structural_scatter(agent_summary: pd.DataFrame, out_dir: Path) -> None:
    subset = agent_summary[agent_summary["agent"].isin(["heuristic", "mcts_medium"])].copy()

    if subset.empty:
        return

    fig, ax = plt.subplots(figsize=(8, 6))

    for agent, group in subset.groupby("agent"):
        ax.scatter(group["avg_chokepoints"], group["avg_turns"], label=agent, alpha=0.75)

    ax.set_xlabel("Average chokepoints")
    ax.set_ylabel("Average turns")
    ax.set_title("Chokepoints vs. average turns")
    ax.legend()

    fig.tight_layout()
    fig.savefig(out_dir / "03_chokepoints_vs_turns.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 6))

    for agent, group in subset.groupby("agent"):
        ax.scatter(group["avg_chokepoints"], group["win_rate"], label=agent, alpha=0.75)

    ax.set_xlabel("Average chokepoints")
    ax.set_ylabel("Win rate")
    ax.set_ylim(0, 1.05)
    ax.set_title("Chokepoints vs. win rate")
    ax.legend()

    fig.tight_layout()
    fig.savefig(out_dir / "04_chokepoints_vs_winrate.png", dpi=180)
    plt.close(fig)


def write_markdown_report(
    df: pd.DataFrame,
    agent_summary: pd.DataFrame,
    config_summary: pd.DataFrame,
    out_dir: Path,
) -> None:
    lines: list[str] = []

    lines.append("# PCG Experiment Analysis")
    lines.append("")
    lines.append(f"Episodes: {len(df)}")
    lines.append(f"Unique cells: {df['cell_id'].nunique() if 'cell_id' in df.columns else 'n/a'}")
    lines.append("")

    lines.append("## Overall win rate by size and agent")
    lines.append("")
    overall = (
        df.groupby(["size", "agent"], as_index=False)
        .agg(win_rate=("won", "mean"), episodes=("won", "size"))
        .sort_values(["size", "agent"])
    )
    lines.append(overall.to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    lines.append("## Top balanced configurations")
    lines.append("")
    display_cols = [
        "size",
        "map_type",
        "enemy_profile",
        "item_profile",
        "wall_profile",
        "balance_label",
        "balance_score",
        "win_rate_random",
        "win_rate_heuristic",
        "win_rate_mcts_small",
        "win_rate_mcts_medium",
        "skill_gap_mcts_medium_vs_heuristic",
    ]
    available_cols = [col for col in display_cols if col in config_summary.columns]
    lines.append(config_summary[available_cols].head(20).to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    lines.append("## Label counts")
    lines.append("")
    label_counts = (
        config_summary["balance_label"]
        .value_counts()
        .rename_axis("label")
        .reset_index(name="count")
    )
    lines.append(label_counts.to_markdown(index=False))
    lines.append("")

    report_path = out_dir / "analysis_summary.md"
    report_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze GridBattle PCG experiment CSV files.")
    parser.add_argument("csv", help="Path to experiment CSV, e.g. results/medium_enemy_tuning.csv")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory. Default: results_analysis/<csv-stem>",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of top configurations to show in the top-candidates plot.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_dir = Path(args.out_dir) if args.out_dir else Path("results_analysis") / csv_path.stem
    figures_dir = out_dir / "figures"
    tables_dir = out_dir / "tables"

    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    df = load_results(csv_path)
    agent_summary = summarize_by_agent(df)
    config_summary = summarize_configs(agent_summary)

    df.to_csv(tables_dir / "episode_rows_copy.csv", index=False)
    agent_summary.to_csv(tables_dir / "agent_summary.csv", index=False)
    config_summary.to_csv(tables_dir / "config_summary.csv", index=False)

    plot_agent_overview(agent_summary, figures_dir)
    plot_heatmaps(config_summary, figures_dir)
    plot_balance_candidates(config_summary, figures_dir, top_n=args.top_n)
    plot_structural_scatter(agent_summary, figures_dir)

    write_markdown_report(df, agent_summary, config_summary, out_dir)

    print(f"Wrote tables to: {tables_dir}")
    print(f"Wrote figures to: {figures_dir}")
    print(f"Wrote report to: {out_dir / 'analysis_summary.md'}")


if __name__ == "__main__":
    main()
