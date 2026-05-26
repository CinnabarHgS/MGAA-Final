from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


AGENT_ORDER = ["random", "heuristic", "mcts_small", "mcts_medium"]
FACTOR_ORDER = [
    "size",
    "map_type",
    "enemy_profile",
    "item_profile",
    "wall_profile",
    "player_hp",
    "enemy_hp",
]
FACTOR_LABELS = {
    "size": "Map size",
    "map_type": "Map type",
    "enemy_profile": "Enemy profile",
    "item_profile": "Item profile",
    "wall_profile": "Wall profile",
    "player_hp": "Player HP",
    "enemy_hp": "Enemy HP",
}
VALUE_ORDER = {
    "size": ["small", "medium", "large"],
    "map_type": ["baseline", "random_walk", "arena"],
    "enemy_profile": ["light", "normal", "medium_plus", "heavy"],
    "item_profile": ["few", "normal", "many"],
    "wall_profile": ["open", "normal", "tight"],
    "player_hp": ["3", "4", "5", "6"],
    "enemy_hp": ["1", "2", "3"],
}


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0

    p = successes / n
    denom = 1.0 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return max(0.0, center - half), min(1.0, center + half)


def ordered(values: list[str], preferred: list[str]) -> list[str]:
    present = [value for value in preferred if value in values]
    rest = sorted(value for value in values if value not in preferred)
    return present + rest


def load_results(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = {
        "agent",
        "won",
        "turns",
        "damage_taken",
        "final_hp",
        "remaining_enemies",
        "ofat_factor",
        "ofat_value",
        "size",
        "map_type",
        "enemy_profile",
        "item_profile",
        "wall_profile",
        "player_hp",
        "enemy_hp",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Missing required columns in {path}: {missing}")

    df = df.copy()
    df["won"] = df["won"].astype(int)

    for col in [
        "turns",
        "damage_taken",
        "final_hp",
        "remaining_enemies",
        "player_hp",
        "enemy_hp",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in [
        "agent",
        "ofat_factor",
        "ofat_value",
        "size",
        "map_type",
        "enemy_profile",
        "item_profile",
        "wall_profile",
    ]:
        df[col] = df[col].astype(str)

    return df


def summarize_raw_cells(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = [
        "ofat_factor",
        "ofat_value",
        "agent",
        "size",
        "map_type",
        "enemy_profile",
        "item_profile",
        "wall_profile",
        "player_hp",
        "enemy_hp",
    ]

    rows: list[dict[str, object]] = []

    for keys, group in df.groupby(group_cols, dropna=False):
        key_dict = dict(zip(group_cols, keys))
        episodes = len(group)
        wins = int(group["won"].sum())
        ci_low, ci_high = wilson_interval(wins, episodes)

        losses = group[group["won"] == 0]

        rows.append(
            {
                **key_dict,
                "episodes": episodes,
                "wins": wins,
                "win_rate": wins / episodes,
                "win_rate_ci_low": ci_low,
                "win_rate_ci_high": ci_high,
                "avg_turns": group["turns"].mean(),
                "std_turns": group["turns"].std(ddof=0),
                "avg_damage_taken": group["damage_taken"].mean(),
                "avg_final_hp": group["final_hp"].mean(),
                "avg_remaining_enemies": group["remaining_enemies"].mean(),
                "avg_remaining_enemies_on_losses": (
                    losses["remaining_enemies"].mean() if len(losses) else 0.0
                ),
                "avg_chokepoints": (
                    group["chokepoint_count"].mean()
                    if "chokepoint_count" in group.columns
                    else np.nan
                ),
                "avg_reachable_floor_fraction": (
                    group["reachable_floor_fraction"].mean()
                    if "reachable_floor_fraction" in group.columns
                    else np.nan
                ),
            }
        )

    return pd.DataFrame(rows)


def infer_baseline_values(baseline_summary: pd.DataFrame) -> dict[str, str]:
    if baseline_summary.empty:
        raise SystemExit("No baseline rows found. Expected ofat_factor == 'baseline'.")

    row = baseline_summary.iloc[0]

    return {
        "size": str(row["size"]),
        "map_type": str(row["map_type"]),
        "enemy_profile": str(row["enemy_profile"]),
        "item_profile": str(row["item_profile"]),
        "wall_profile": str(row["wall_profile"]),
        "player_hp": str(int(row["player_hp"])),
        "enemy_hp": str(int(row["enemy_hp"])),
    }


def build_factor_summary(cell_summary: pd.DataFrame) -> pd.DataFrame:
    baseline = cell_summary[cell_summary["ofat_factor"] == "baseline"].copy()
    baseline_values = infer_baseline_values(baseline)

    rows: list[pd.DataFrame] = []

    # For every factor, include the shared baseline as that factor's baseline value.
    for factor in FACTOR_ORDER:
        baseline_for_factor = baseline.copy()
        baseline_for_factor["factor"] = factor
        baseline_for_factor["value"] = baseline_values[factor]
        rows.append(baseline_for_factor)

        factor_rows = cell_summary[cell_summary["ofat_factor"] == factor].copy()
        if len(factor_rows):
            factor_rows["factor"] = factor
            factor_rows["value"] = factor_rows["ofat_value"].astype(str)
            rows.append(factor_rows)

    factor_summary = pd.concat(rows, ignore_index=True)

    baseline_metrics = (
        baseline[["agent", "win_rate", "avg_turns", "avg_damage_taken", "avg_final_hp"]]
        .rename(
            columns={
                "win_rate": "baseline_win_rate",
                "avg_turns": "baseline_avg_turns",
                "avg_damage_taken": "baseline_avg_damage_taken",
                "avg_final_hp": "baseline_avg_final_hp",
            }
        )
    )

    factor_summary = factor_summary.merge(baseline_metrics, on="agent", how="left")
    factor_summary["delta_win_rate"] = (
        factor_summary["win_rate"] - factor_summary["baseline_win_rate"]
    )
    factor_summary["delta_turns"] = (
        factor_summary["avg_turns"] - factor_summary["baseline_avg_turns"]
    )
    factor_summary["delta_damage_taken"] = (
        factor_summary["avg_damage_taken"] - factor_summary["baseline_avg_damage_taken"]
    )
    factor_summary["delta_final_hp"] = (
        factor_summary["avg_final_hp"] - factor_summary["baseline_avg_final_hp"]
    )

    return factor_summary


def compute_effect_sizes(factor_summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for (factor, agent), group in factor_summary.groupby(["factor", "agent"]):
        rows.append(
            {
                "factor": factor,
                "agent": agent,
                "win_rate_range": group["win_rate"].max() - group["win_rate"].min(),
                "turns_range": group["avg_turns"].max() - group["avg_turns"].min(),
                "damage_range": group["avg_damage_taken"].max()
                - group["avg_damage_taken"].min(),
                "min_win_rate": group["win_rate"].min(),
                "max_win_rate": group["win_rate"].max(),
            }
        )

    return pd.DataFrame(rows).sort_values(["agent", "win_rate_range"], ascending=[True, False])


def plot_baseline(cell_summary: pd.DataFrame, figures_dir: Path) -> None:
    baseline = cell_summary[cell_summary["ofat_factor"] == "baseline"].copy()
    baseline["agent"] = pd.Categorical(baseline["agent"], categories=AGENT_ORDER, ordered=True)
    baseline = baseline.sort_values("agent")

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(baseline))
    ax.bar(x, baseline["win_rate"])
    ax.set_xticks(x)
    ax.set_xticklabels(baseline["agent"])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Win rate")
    ax.set_title("OFAT baseline performance")

    for i, value in enumerate(baseline["win_rate"]):
        ax.text(i, value + 0.02, f"{value:.0%}", ha="center")

    fig.tight_layout()
    fig.savefig(figures_dir / "01_baseline_winrate.png", dpi=180)
    plt.close(fig)


def plot_effect_sizes(effect_sizes: pd.DataFrame, figures_dir: Path) -> None:
    factors = ordered(effect_sizes["factor"].unique().tolist(), FACTOR_ORDER)
    agents = ordered(effect_sizes["agent"].unique().tolist(), AGENT_ORDER)

    x = np.arange(len(factors))
    width = 0.8 / max(1, len(agents))

    fig, ax = plt.subplots(figsize=(11, 6))

    for i, agent in enumerate(agents):
        subset = effect_sizes[effect_sizes["agent"] == agent].set_index("factor")
        values = [subset.loc[factor, "win_rate_range"] if factor in subset.index else np.nan for factor in factors]
        ax.bar(x + (i - (len(agents) - 1) / 2) * width, values, width, label=agent)

    ax.set_xticks(x)
    ax.set_xticklabels([FACTOR_LABELS.get(f, f) for f in factors], rotation=30, ha="right")
    ax.set_ylabel("Win-rate swing across levels")
    ax.set_title("OFAT sensitivity: which factors change win rate most?")
    ax.legend()

    fig.tight_layout()
    fig.savefig(figures_dir / "02_factor_effect_sizes.png", dpi=180)
    plt.close(fig)


def plot_delta_by_factor(factor_summary: pd.DataFrame, figures_dir: Path) -> None:
    for factor in ordered(factor_summary["factor"].unique().tolist(), FACTOR_ORDER):
        subset = factor_summary[factor_summary["factor"] == factor].copy()

        preferred_values = VALUE_ORDER.get(factor, [])
        values = ordered(subset["value"].unique().astype(str).tolist(), preferred_values)
        agents = ordered(subset["agent"].unique().tolist(), AGENT_ORDER)

        x = np.arange(len(values))
        width = 0.8 / max(1, len(agents))

        fig, ax = plt.subplots(figsize=(max(8, len(values) * 1.4), 5))

        for i, agent in enumerate(agents):
            agent_subset = subset[subset["agent"] == agent].set_index("value")
            y = [
                agent_subset.loc[value, "delta_win_rate"]
                if value in agent_subset.index
                else np.nan
                for value in values
            ]
            ax.bar(x + (i - (len(agents) - 1) / 2) * width, y, width, label=agent)

        ax.axhline(0, linewidth=1)
        ax.set_xticks(x)
        ax.set_xticklabels(values)
        ax.set_ylabel("Win-rate change vs baseline")
        ax.set_title(f"OFAT: {FACTOR_LABELS.get(factor, factor)} effect relative to baseline")
        ax.legend()

        fig.tight_layout()
        fig.savefig(figures_dir / f"delta_winrate_{factor}.png", dpi=180)
        plt.close(fig)


def plot_health_curves(factor_summary: pd.DataFrame, figures_dir: Path) -> None:
    for factor in ["player_hp", "enemy_hp"]:
        subset = factor_summary[factor_summary["factor"] == factor].copy()
        if subset.empty:
            continue

        subset["value_num"] = pd.to_numeric(subset["value"], errors="coerce")
        agents = ordered(subset["agent"].unique().tolist(), AGENT_ORDER)

        fig, ax = plt.subplots(figsize=(8, 5))

        for agent in agents:
            group = subset[subset["agent"] == agent].sort_values("value_num")
            ax.plot(group["value_num"], group["win_rate"], marker="o", label=agent)

        ax.set_ylim(0, 1.05)
        ax.set_xlabel(FACTOR_LABELS[factor])
        ax.set_ylabel("Win rate")
        ax.set_title(f"Health sensitivity: {FACTOR_LABELS[factor]}")
        ax.legend()

        fig.tight_layout()
        fig.savefig(figures_dir / f"health_curve_{factor}.png", dpi=180)
        plt.close(fig)


def plot_turns_by_factor(factor_summary: pd.DataFrame, figures_dir: Path) -> None:
    factors = ["map_type", "wall_profile", "enemy_profile", "item_profile"]

    for factor in factors:
        subset = factor_summary[factor_summary["factor"] == factor].copy()
        if subset.empty:
            continue

        preferred_values = VALUE_ORDER.get(factor, [])
        values = ordered(subset["value"].unique().astype(str).tolist(), preferred_values)
        agents = ["heuristic", "mcts_small", "mcts_medium"]

        x = np.arange(len(values))
        width = 0.8 / len(agents)

        fig, ax = plt.subplots(figsize=(max(8, len(values) * 1.4), 5))

        for i, agent in enumerate(agents):
            agent_subset = subset[subset["agent"] == agent].set_index("value")
            y = [
                agent_subset.loc[value, "avg_turns"]
                if value in agent_subset.index
                else np.nan
                for value in values
            ]
            ax.bar(x + (i - (len(agents) - 1) / 2) * width, y, width, label=agent)

        ax.set_xticks(x)
        ax.set_xticklabels(values)
        ax.set_ylabel("Average turns")
        ax.set_title(f"OFAT pacing: {FACTOR_LABELS.get(factor, factor)}")
        ax.legend()

        fig.tight_layout()
        fig.savefig(figures_dir / f"turns_{factor}.png", dpi=180)
        plt.close(fig)


def write_report(
    df: pd.DataFrame,
    cell_summary: pd.DataFrame,
    factor_summary: pd.DataFrame,
    effect_sizes: pd.DataFrame,
    out_dir: Path,
) -> None:
    baseline = cell_summary[cell_summary["ofat_factor"] == "baseline"].copy()
    baseline_values = infer_baseline_values(baseline)

    lines: list[str] = []
    lines.append("# OFAT Analysis")
    lines.append("")
    lines.append(f"Episodes: {len(df)}")
    lines.append(f"Cells: {df['cell_id'].nunique() if 'cell_id' in df.columns else 'n/a'}")
    lines.append("")
    lines.append("## Baseline")
    lines.append("")
    lines.append("The OFAT experiment varies one factor at a time around this baseline:")
    lines.append("")
    for factor in FACTOR_ORDER:
        lines.append(f"- `{factor}`: `{baseline_values[factor]}`")
    lines.append("")
    lines.append("Baseline agent performance:")
    lines.append("")
    baseline_display = baseline[
        ["agent", "episodes", "win_rate", "avg_turns", "avg_damage_taken", "avg_final_hp"]
    ].copy()
    lines.append(baseline_display.to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    lines.append("## Largest win-rate effects")
    lines.append("")
    effect_pivot = effect_sizes.pivot_table(
        index="factor",
        columns="agent",
        values="win_rate_range",
        aggfunc="first",
    )
    available_agents = [a for a in AGENT_ORDER if a in effect_pivot.columns]
    effect_pivot = effect_pivot.reindex(index=[f for f in FACTOR_ORDER if f in effect_pivot.index])
    effect_pivot = effect_pivot[available_agents]
    lines.append(effect_pivot.reset_index().to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    lines.append("## Factor-level summary")
    lines.append("")
    display_cols = [
        "factor",
        "value",
        "agent",
        "win_rate",
        "delta_win_rate",
        "avg_turns",
        "delta_turns",
        "avg_damage_taken",
        "delta_damage_taken",
    ]
    compact = factor_summary[display_cols].copy()
    compact["factor"] = pd.Categorical(compact["factor"], categories=FACTOR_ORDER, ordered=True)
    compact["agent"] = pd.Categorical(compact["agent"], categories=AGENT_ORDER, ordered=True)
    compact = compact.sort_values(["factor", "value", "agent"])
    lines.append(compact.to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    report_path = out_dir / "ofat_analysis_summary.md"
    report_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze real-environment GridBattle OFAT results.")
    parser.add_argument("csv", help="Path to OFAT CSV, e.g. results/ofat_real.csv")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory. Default: results_analysis/<csv-stem>",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_dir = Path(args.out_dir) if args.out_dir else Path("results_analysis") / csv_path.stem
    figures_dir = out_dir / "figures"
    tables_dir = out_dir / "tables"

    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    df = load_results(csv_path)
    cell_summary = summarize_raw_cells(df)
    factor_summary = build_factor_summary(cell_summary)
    effect_sizes = compute_effect_sizes(factor_summary)

    cell_summary.to_csv(tables_dir / "ofat_cell_summary.csv", index=False)
    factor_summary.to_csv(tables_dir / "ofat_factor_summary.csv", index=False)
    effect_sizes.to_csv(tables_dir / "ofat_effect_sizes.csv", index=False)

    plot_baseline(cell_summary, figures_dir)
    plot_effect_sizes(effect_sizes, figures_dir)
    plot_delta_by_factor(factor_summary, figures_dir)
    plot_health_curves(factor_summary, figures_dir)
    plot_turns_by_factor(factor_summary, figures_dir)

    write_report(df, cell_summary, factor_summary, effect_sizes, out_dir)

    print(f"Wrote tables to: {tables_dir}")
    print(f"Wrote figures to: {figures_dir}")
    print(f"Wrote report to: {out_dir / 'ofat_analysis_summary.md'}")


if __name__ == "__main__":
    main()
