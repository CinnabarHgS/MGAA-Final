"""Analysis of the OFAT sweep produced by run_sweep.py.

Produces:

  figures/
    overview_winrate_heatmap.png        -- single-glance overview, all agents in one matrix
    overview_stats_heatmap.png          -- per-agent panels with significance stars and
                                           effect-size borders vs each agent's default pool
    overview_top_effects.png            -- ranked bar chart of largest Cohen's h values
    by_variable/<var>_winrate.png       -- one figure per swept variable, all agents overlaid
    by_variable/<var>_turns.png         -- same, but mean turns (won episodes only)
    by_variable/<var>_damage.png        -- same, but mean damage taken
    by_agent/<agent>_overview.png       -- one figure per agent, all variables panelled

  tables/
    summary_stats.csv                   -- per-cell win-rate, mean turns, damage, n
    effects_ranked.csv                  -- non-default-level effects vs the default pool,
                                           with Cohen's h, Fisher p, Holm-adjusted p,
                                           Mann-Whitney on turns, ranked by |effect|
    omnibus_tests.csv                   -- per (agent, variable) omnibus: does level matter?

Stats notes:

* "Default pool" = the 400 episodes per agent where every parameter matches the OFAT
  defaults. We use this as the reference cell for every non-default level. This is
  intentional and gives much higher statistical power than the per-variable default
  cell (n=50) -- the OFAT design means those rows ARE in the default pool.
* Win rate: Wilson 95 percent CIs on the plots. Pairwise comparisons vs default use
  Fisher's exact test (robust at small n, exact). Effect size is Cohen's h.
* Turns: mean with bootstrap 95 percent CI (won episodes only -- losing episodes
  hit the max_steps cap and aren't informative). Pairwise vs default uses
  Mann-Whitney U. Effect size is rank-biserial correlation.
* Multiple-testing correction: Holm, applied within each agent across all
  (variable, level != default) pairwise tests for that agent. Holm controls FWER
  and is uniformly more powerful than Bonferroni.
* Omnibus "does the variable matter at all for this agent?": chi-squared on the
  full level x won contingency, plus Kruskal-Wallis on turns.

Run:
    python analyze_ofat.py --csv ofat.csv --out-dir results_analysis
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests


# OFAT defaults, mirrored from run_sweep.py. If you change them there, change them here.
DEFAULTS: dict[str, object] = {
    "size":          "medium",
    "map_type":      "random_walk",
    "items":         "default",
    "enemy_count":   "default",
    "wall_density":  "default",
    "player_hp":     4,
    "enemy_hp":      2,
    "player_damage": 1,
    "enemy_damage":  1,
    "player_range":  1,
    "enemy_range":   1,
}

# Variables swept, in the order we want them shown. Levels are ordered such that
# the "default" level sits in the middle where possible (better for reading plots).
SWEPT_VARIABLES: dict[str, list] = {
    "size":          ["small", "medium", "large"],
    "map_type":      ["baseline", "random_walk", "arena"],
    "items":         ["none", "default", "double"],
    "enemy_count":   ["low", "default", "high"],
    "wall_density":  ["low", "default", "high"],
    "player_hp":     [3, 4, 5],
    "enemy_hp":      [1, 2, 3],
    "player_range":  [1, 2],
}

AGENTS = ("random", "heuristic", "mcts")

# Consistent colours per agent across every figure.
AGENT_COLORS = {
    "random":    "#888888",
    "heuristic": "#1f77b4",
    "mcts":      "#d62728",
}


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. Stable at p near 0 or 1."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def cohens_h(p1: float, p2: float) -> float:
    """Effect size for two proportions. |h| ~ 0.2 small, 0.5 medium, 0.8 large."""
    def phi(p: float) -> float:
        return 2.0 * np.arcsin(np.sqrt(min(1.0, max(0.0, p))))
    return phi(p1) - phi(p2)


def fisher_p(k1: int, n1: int, k2: int, n2: int) -> float:
    """Fisher exact test on the 2x2 table of (wins, losses) for two cells."""
    table = [[k1, n1 - k1], [k2, n2 - k2]]
    _, p = stats.fisher_exact(table)
    return float(p)


def rank_biserial(x: np.ndarray, y: np.ndarray) -> float:
    """Rank-biserial correlation -- effect size companion to Mann-Whitney U.

    Equivalent to (2U) / (n1 n2) - 1. Range [-1, 1]; positive means x > y in rank.
    """
    nx, ny = len(x), len(y)
    if nx == 0 or ny == 0:
        return float("nan")
    u, _ = stats.mannwhitneyu(x, y, alternative="two-sided")
    return 2 * u / (nx * ny) - 1


def bootstrap_mean_ci(values: np.ndarray, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap 95% CI for the mean. Returns (lo, hi)."""
    if len(values) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(n_boot, len(values)))
    means = values[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


# ---------------------------------------------------------------------------
# Data slicing
# ---------------------------------------------------------------------------

def default_pool(df: pd.DataFrame) -> pd.DataFrame:
    """Rows where every OFAT-controlled parameter is at its default value.

    In an OFAT design this is the union of every variable's default-level cell,
    so it pools episodes from every sweep into one large baseline. ~400 per agent.
    """
    mask = np.logical_and.reduce([df[k] == v for k, v in DEFAULTS.items()])
    return df[mask].copy()


def variable_cells(df: pd.DataFrame, variable: str) -> pd.DataFrame:
    """Rows where every parameter EXCEPT `variable` is at its default value.

    These are the cells produced when sweeping `variable` in run_sweep.py.
    """
    others = {k: v for k, v in DEFAULTS.items() if k != variable}
    mask = np.logical_and.reduce([df[k] == v for k, v in others.items()])
    return df[mask].copy()


# ---------------------------------------------------------------------------
# Summary tables
# ---------------------------------------------------------------------------

def build_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (variable, level, agent) cell, with win rate / turns / damage / n."""
    rows = []
    for variable, levels in SWEPT_VARIABLES.items():
        cells = variable_cells(df, variable)
        for level in levels:
            for agent in AGENTS:
                sub = cells[(cells[variable] == level) & (cells["agent"] == agent)]
                n = len(sub)
                wins = int(sub["won"].sum())
                win_rate = wins / n if n else float("nan")
                lo, hi = wilson_ci(wins, n)
                won_turns = sub.loc[sub["won"] == 1, "turns"].to_numpy()
                rows.append({
                    "variable":      variable,
                    "level":         str(level),
                    "agent":         agent,
                    "n":             n,
                    "wins":          wins,
                    "win_rate":      win_rate,
                    "win_rate_lo":   lo,
                    "win_rate_hi":   hi,
                    "mean_turns_won": float(won_turns.mean()) if len(won_turns) else float("nan"),
                    "mean_damage":   float(sub["damage_taken"].mean()) if n else float("nan"),
                    "mean_final_hp": float(sub["final_hp"].mean()) if n else float("nan"),
                    "is_default":    level == DEFAULTS[variable],
                })
    return pd.DataFrame(rows)


def build_omnibus_tests(df: pd.DataFrame) -> pd.DataFrame:
    """For each (agent, variable): does the variable matter?

    chi-squared on the (level x won) contingency table, plus Kruskal-Wallis on
    turns across levels (won episodes only). Effect size for chi^2 is Cramer's V.
    """
    rows = []
    for variable, levels in SWEPT_VARIABLES.items():
        cells = variable_cells(df, variable)
        for agent in AGENTS:
            sub = cells[cells["agent"] == agent]
            # win rate omnibus
            ct = pd.crosstab(sub[variable], sub["won"])
            # ensure both win=0 and win=1 columns exist
            for c in (0, 1):
                if c not in ct.columns:
                    ct[c] = 0
            ct = ct[[0, 1]]
            n = ct.values.sum()
            # If a row or column is all zero (e.g. all wins or all losses in some level),
            # chi-squared's expected-frequency calculation blows up. Drop empty columns
            # and re-test; if only one column survives the test is undefined (perfect
            # separation: every level has identical outcome), so report it explicitly.
            nonzero_cols = (ct.values.sum(axis=0) > 0)
            ct_clean = ct.loc[:, ct.columns[nonzero_cols]]
            if ct_clean.shape[1] < 2 or ct_clean.shape[0] < 2:
                # Either every episode won or every episode lost across all levels --
                # no variation to test. Report NaN p-value and a note via cramer_v=0.
                chi2, chi2_p, cramer_v = float("nan"), float("nan"), 0.0
            else:
                chi2, chi2_p, _, _ = stats.chi2_contingency(ct_clean.values)
                cramer_v = float(np.sqrt(chi2 / (n * (min(ct_clean.shape) - 1)))) if n > 0 else float("nan")

            # turns omnibus (won episodes only -- losses are right-censored at max_steps)
            won_groups = [sub[(sub[variable] == lvl) & (sub["won"] == 1)]["turns"].to_numpy() for lvl in levels]
            won_groups = [g for g in won_groups if len(g) > 0]
            if len(won_groups) >= 2:
                h, kw_p = stats.kruskal(*won_groups)
            else:
                h, kw_p = float("nan"), float("nan")
            rows.append({
                "agent":        agent,
                "variable":     variable,
                "n":            int(n),
                "chi2":         float(chi2),
                "chi2_p":       float(chi2_p),
                "cramer_v":     cramer_v,
                "kruskal_h":    float(h) if h == h else float("nan"),
                "kruskal_p":    float(kw_p) if kw_p == kw_p else float("nan"),
            })
    return pd.DataFrame(rows)


def build_effects_table(df: pd.DataFrame) -> pd.DataFrame:
    """Each non-default level vs the default pool, per agent.

    Within each agent, p-values are Holm-adjusted across all such pairwise
    tests for that agent (separately for the won-test and the turns-test).
    """
    pool = default_pool(df)
    rows = []
    for variable, levels in SWEPT_VARIABLES.items():
        cells = variable_cells(df, variable)
        for level in levels:
            if level == DEFAULTS[variable]:
                continue  # skip the default level -- by construction it IS the pool
            for agent in AGENTS:
                ref = pool[pool["agent"] == agent]
                sub = cells[(cells[variable] == level) & (cells["agent"] == agent)]
                n_ref, n_sub = len(ref), len(sub)
                if n_ref == 0 or n_sub == 0:
                    continue
                # Win-rate comparison
                k_ref, k_sub = int(ref["won"].sum()), int(sub["won"].sum())
                p_ref, p_sub = k_ref / n_ref, k_sub / n_sub
                delta_wr = p_sub - p_ref
                h = cohens_h(p_sub, p_ref)
                p_won = fisher_p(k_sub, n_sub, k_ref, n_ref)

                # Turns comparison (won episodes only)
                t_ref = ref.loc[ref["won"] == 1, "turns"].to_numpy()
                t_sub = sub.loc[sub["won"] == 1, "turns"].to_numpy()
                if len(t_ref) >= 5 and len(t_sub) >= 5:
                    _, p_turns = stats.mannwhitneyu(t_sub, t_ref, alternative="two-sided")
                    rb = rank_biserial(t_sub, t_ref)
                    delta_turns = float(t_sub.mean() - t_ref.mean())
                else:
                    p_turns, rb, delta_turns = float("nan"), float("nan"), float("nan")

                rows.append({
                    "agent":          agent,
                    "variable":       variable,
                    "level":          str(level),
                    "n_level":        n_sub,
                    "n_default":      n_ref,
                    "winrate_level":   p_sub,
                    "winrate_default": p_ref,
                    "delta_winrate":   delta_wr,
                    "cohens_h":        h,
                    "p_won":           p_won,
                    "delta_mean_turns": delta_turns,
                    "rank_biserial_turns": rb,
                    "p_turns":         p_turns,
                })
    out = pd.DataFrame(rows)
    if out.empty:
        return out

    # Holm adjustment within each agent, separately for won and turns tests.
    out["p_won_holm"] = np.nan
    out["p_turns_holm"] = np.nan
    for agent in AGENTS:
        idx = out.index[out["agent"] == agent]
        if len(idx) == 0:
            continue
        out.loc[idx, "p_won_holm"] = multipletests(out.loc[idx, "p_won"].values, method="holm")[1]
        turns_p = out.loc[idx, "p_turns"].values
        valid = ~np.isnan(turns_p)
        if valid.any():
            adj = np.full_like(turns_p, np.nan, dtype=float)
            adj[valid] = multipletests(turns_p[valid], method="holm")[1]
            out.loc[idx, "p_turns_holm"] = adj

    # Rank by absolute effect size on win rate (the headline metric).
    out["abs_h"] = out["cohens_h"].abs()
    out = out.sort_values(["abs_h"], ascending=False).reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def _save(fig: plt.Figure, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _sig_stars(p: float) -> str:
    """Conventional star encoding for an adjusted p-value."""
    if p != p:  # NaN
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


def plot_stats_overview(
    summary: pd.DataFrame,
    effects: pd.DataFrame,
    out_path: str,
    effect_size_threshold: float = 0.5,
) -> None:
    """Three-panel heatmap: one panel per agent.

    Each cell shows the win rate. Within each row (variable):
      - the default level is the reference; it's marked with a small white
        diamond glyph on the left edge of the cell (visually distinct, not
        a border, so it doesn't compete with the effect-size border)
      - non-default levels are annotated with significance stars from the
        Holm-adjusted Fisher test against the default pool for that agent
      - cells with |Cohen's h| >= effect_size_threshold get a thick directional
        border: BLUE for positive (better than default), ORANGE for negative
        (worse than default). Borders are wide enough to read clearly against
        the heatmap fill, and the color carries direction info without needing
        the user to read the number.

    Three panels (not one) because the stat tests are within-agent:
    putting them in a single panel would invite cross-agent comparisons that
    aren't what the stars test.
    """
    # Build (row_label, variable, level, is_default) in display order.
    rows: list[tuple[str, str, str, bool]] = []
    for var, levels in SWEPT_VARIABLES.items():
        for lvl in levels:
            lvl_s = str(lvl)
            is_def = str(DEFAULTS[var]) == lvl_s
            label = f"{var} = {lvl_s}" + ("  [def]" if is_def else "")
            rows.append((label, var, lvl_s, is_def))

    # Index effects by (agent, variable, level) for quick lookup.
    eff_idx = effects.set_index(["agent", "variable", "level"]) if len(effects) else None

    # Distinctive colors for the directional borders. Chosen to be visible
    # against both red and green heatmap fills.
    POS_BORDER = "#1a4a8a"   # deep blue: cell is BETTER than default
    NEG_BORDER = "#000000"   # black: cell is WORSE than default (this is the
                              # important case for "agent is brittle")

    fig, axes = plt.subplots(1, len(AGENTS), figsize=(4.2 * len(AGENTS) + 1.5, 0.30 * len(rows) + 1.8))
    if len(AGENTS) == 1:
        axes = [axes]

    for ax_idx, (ax, agent) in enumerate(zip(axes, AGENTS)):
        # Build the column matrix (single column = win rate for this agent).
        vals = np.full(len(rows), np.nan)
        for i, (_, var, lvl, _) in enumerate(rows):
            row = summary[(summary["variable"] == var) & (summary["level"] == lvl) & (summary["agent"] == agent)]
            if len(row):
                vals[i] = row["win_rate"].iloc[0]

        im = ax.imshow(vals.reshape(-1, 1), aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
        ax.set_xticks([0])
        ax.set_xticklabels(["win rate"], fontsize=9)
        ax.set_title(agent, fontsize=11, color=AGENT_COLORS[agent], fontweight="bold")

        # Annotate every cell with the win rate, stars, and direction-encoded
        # effect-size border. The default cell gets a left-edge diamond marker
        # instead of a border so the two encodings can't be confused.
        for i, (_, var, lvl, is_def) in enumerate(rows):
            v = vals[i]
            if np.isnan(v):
                continue

            stars = ""
            big_effect = False
            h_sign = 0.0
            if not is_def and eff_idx is not None:
                try:
                    row = eff_idx.loc[(agent, var, lvl)]
                    stars = _sig_stars(float(row["p_won_holm"]))
                    h_val = float(row["cohens_h"])
                    h_sign = h_val
                    big_effect = abs(h_val) >= effect_size_threshold
                except KeyError:
                    pass

            text = f"{v:.2f}" + (f" {stars}" if stars else "")
            ax.text(0, i, text, ha="center", va="center", fontsize=8,
                    color="black" if 0.2 < v < 0.8 else "white")

            if is_def:
                # Small white diamond hugging the left edge -- marks the reference
                # without putting a border around the cell.
                ax.plot(-0.42, i, marker="D", markersize=5,
                        markerfacecolor="white", markeredgecolor="black", markeredgewidth=0.8,
                        clip_on=False)
            elif big_effect:
                color = POS_BORDER if h_sign > 0 else NEG_BORDER
                # Inset the border slightly so it reads as belonging to the cell
                # rather than a grid line. Linewidth tuned so it's clearly thicker
                # than the white inter-block separators.
                ax.add_patch(plt.Rectangle((-0.46, i - 0.46), 0.92, 0.92, fill=False,
                                            edgecolor=color, linewidth=3.0))

        # Variable-block separators
        pos = 0
        for var, levels in SWEPT_VARIABLES.items():
            pos += len(levels)
            if pos < len(rows):
                ax.axhline(pos - 0.5, color="white", linewidth=2)

        # Y labels only on the leftmost panel; others get nothing.
        if ax_idx == 0:
            ax.set_yticks(range(len(rows)))
            ax.set_yticklabels([r[0] for r in rows], fontsize=8)
        else:
            ax.set_yticks([])

    # Shared colorbar.
    fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02, label="win rate")

    # Legend with the actual glyphs used in the figure, so readers don't have
    # to parse the prose caption to know what they're looking at.
    legend_handles = [
        plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="white",
                   markeredgecolor="black", markersize=8, label="default-level reference"),
        plt.Rectangle((0, 0), 1, 1, fill=False, edgecolor=NEG_BORDER, linewidth=3.0,
                      label=f"|h| \u2265 {effect_size_threshold}, worse than default"),
        plt.Rectangle((0, 0), 1, 1, fill=False, edgecolor=POS_BORDER, linewidth=3.0,
                      label=f"|h| \u2265 {effect_size_threshold}, better than default"),
    ]
    fig.legend(handles=legend_handles, loc="lower center", ncol=3, fontsize=9,
               frameon=False, bbox_to_anchor=(0.5, -0.02))

    caption = (
        "Stars: Holm-adjusted Fisher exact p-value vs that agent's default-config pool  "
        "(*** p<0.001,  ** p<0.01,  * p<0.05).    "
        "The default-config pool aggregates all default-parameter episodes across every sweep ("
        "\u2248 400 per agent), used as the reference cell for all comparisons."
    )
    fig.suptitle("Win rate by configuration, with significance vs default pool", fontsize=12, y=0.995)
    fig.text(0.5, -0.055, caption, ha="center", fontsize=8, style="italic", wrap=True)
    _save(fig, out_path)


def plot_top_effects(effects: pd.DataFrame, out_path: str, top_n: int = 15) -> None:
    """Horizontal bar chart of the largest effect sizes on win rate.

    Each bar is one (agent, variable, level) comparison vs the default pool.
    Width = Cohen's h. Color = agent. Stars on bars = Holm-adjusted significance.
    This is the "tl;dr of the study" -- what actually moves the needle and for whom.
    """
    if len(effects) == 0:
        return
    df = effects.head(top_n).iloc[::-1].copy()  # reverse so largest is on top after barh

    fig, ax = plt.subplots(figsize=(7.0, max(3.5, 0.32 * len(df) + 1.0)))
    y = np.arange(len(df))
    colors = [AGENT_COLORS[a] for a in df["agent"]]
    ax.barh(y, df["cohens_h"], color=colors, edgecolor="black", linewidth=0.4)
    ax.axvline(0, color="black", linewidth=0.6)

    labels = [f"{r.agent}: {r.variable} = {r.level}" for r in df.itertuples()]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Cohen's h  (vs default pool;  negative = worse, positive = better)")
    ax.set_title(f"Top {len(df)} effects on win rate, ranked by |Cohen's h|")
    ax.grid(axis="x", alpha=0.3)

    # Annotate each bar with Δ win rate and significance stars.
    for i, r in enumerate(df.itertuples()):
        stars = _sig_stars(float(r.p_won_holm))
        text = f"Δwr={r.delta_winrate:+.2f}  {stars}".rstrip()
        x = r.cohens_h
        ha = "left" if x >= 0 else "right"
        offset = 0.05 if x >= 0 else -0.05
        ax.text(x + offset, i, text, va="center", ha=ha, fontsize=8)

    # Padding so text doesn't get clipped at the edges. Positive bars need extra room
    # on the right because the annotation extends rightward from the bar end.
    xlo, xhi = ax.get_xlim()
    ax.set_xlim(xlo - 0.35 * abs(xlo), xhi + 0.55 * abs(xhi))

    # Agent color legend.
    handles = [plt.Rectangle((0, 0), 1, 1, color=AGENT_COLORS[a]) for a in AGENTS]
    ax.legend(handles, AGENTS, loc="upper right", fontsize=8, title="agent")

    _save(fig, out_path)


def plot_overview_heatmap(summary: pd.DataFrame, out_path: str) -> None:
    """Single heatmap: rows = (variable, level), cols = agents, cell = win rate."""
    # Build the matrix in the canonical level order so it reads top-to-bottom.
    ordered = []
    for var, levels in SWEPT_VARIABLES.items():
        for lvl in levels:
            ordered.append((var, str(lvl)))
    mat = np.full((len(ordered), len(AGENTS)), np.nan)
    labels = []
    for i, (var, lvl) in enumerate(ordered):
        labels.append(f"{var} = {lvl}" + ("  [default]" if str(DEFAULTS[var]) == lvl else ""))
        for j, agent in enumerate(AGENTS):
            row = summary[(summary["variable"] == var) & (summary["level"] == lvl) & (summary["agent"] == agent)]
            if len(row):
                mat[i, j] = row["win_rate"].iloc[0]

    fig, ax = plt.subplots(figsize=(6.5, 0.32 * len(ordered) + 1.2))
    im = ax.imshow(mat, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_xticks(range(len(AGENTS)))
    ax.set_xticklabels(AGENTS)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_title("Win rate by configuration and agent")
    # Annotate each cell
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7,
                        color="black" if 0.2 < v < 0.8 else "white")
    # Separators between variable blocks
    pos = 0
    for var, levels in SWEPT_VARIABLES.items():
        pos += len(levels)
        if pos < len(ordered):
            ax.axhline(pos - 0.5, color="white", linewidth=2)
    fig.colorbar(im, ax=ax, label="win rate", fraction=0.046, pad=0.04)
    _save(fig, out_path)


def plot_variable_winrate(summary: pd.DataFrame, variable: str, out_path: str) -> None:
    """One figure for a swept variable: x = level, y = win rate, three agents overlaid."""
    levels = [str(l) for l in SWEPT_VARIABLES[variable]]
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    x = np.arange(len(levels))
    width = 0.25
    for k, agent in enumerate(AGENTS):
        ys, lo, hi = [], [], []
        for lvl in levels:
            row = summary[(summary["variable"] == variable) & (summary["level"] == lvl) & (summary["agent"] == agent)]
            if len(row):
                ys.append(row["win_rate"].iloc[0])
                lo.append(row["win_rate_lo"].iloc[0])
                hi.append(row["win_rate_hi"].iloc[0])
            else:
                ys.append(np.nan); lo.append(np.nan); hi.append(np.nan)
        ys, lo, hi = np.array(ys), np.array(lo), np.array(hi)
        yerr = np.vstack([ys - lo, hi - ys])
        ax.bar(x + (k - 1) * width, ys, width=width, yerr=yerr, capsize=3,
               color=AGENT_COLORS[agent], label=agent, edgecolor="black", linewidth=0.4)
    ax.set_xticks(x); ax.set_xticklabels(levels)
    # Mark the default level on the x axis
    if str(DEFAULTS[variable]) in levels:
        ax.get_xticklabels()[levels.index(str(DEFAULTS[variable]))].set_fontweight("bold")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("win rate")
    ax.set_xlabel(f"{variable}  (bold = default)")
    ax.set_title(f"Win rate vs {variable}")
    ax.legend(loc="best", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    _save(fig, out_path)


def plot_variable_metric(df: pd.DataFrame, variable: str, metric: str, ylabel: str,
                         out_path: str, won_only: bool = False) -> None:
    """Generic per-variable plot for a continuous metric with bootstrap CIs."""
    levels = [str(l) for l in SWEPT_VARIABLES[variable]]
    cells = variable_cells(df, variable)
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    x = np.arange(len(levels))
    width = 0.25
    for k, agent in enumerate(AGENTS):
        ys, lo, hi = [], [], []
        for lvl in levels:
            sub = cells[(cells[variable].astype(str) == lvl) & (cells["agent"] == agent)]
            if won_only:
                sub = sub[sub["won"] == 1]
            vals = sub[metric].to_numpy()
            if len(vals) == 0:
                ys.append(np.nan); lo.append(np.nan); hi.append(np.nan); continue
            ys.append(float(vals.mean()))
            l, h = bootstrap_mean_ci(vals, seed=hash((variable, lvl, agent)) % (2**32))
            lo.append(l); hi.append(h)
        ys, lo, hi = np.array(ys), np.array(lo), np.array(hi)
        yerr = np.vstack([ys - lo, hi - ys])
        ax.bar(x + (k - 1) * width, ys, width=width, yerr=yerr, capsize=3,
               color=AGENT_COLORS[agent], label=agent, edgecolor="black", linewidth=0.4)
    ax.set_xticks(x); ax.set_xticklabels(levels)
    if str(DEFAULTS[variable]) in levels:
        ax.get_xticklabels()[levels.index(str(DEFAULTS[variable]))].set_fontweight("bold")
    ax.set_ylabel(ylabel)
    ax.set_xlabel(f"{variable}  (bold = default)")
    suffix = "  (won episodes only)" if won_only else ""
    ax.set_title(f"{ylabel} vs {variable}{suffix}")
    ax.legend(loc="best", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    _save(fig, out_path)


def plot_agent_overview(summary: pd.DataFrame, agent: str, out_path: str) -> None:
    """One figure for an agent: every swept variable as a small subplot of win rate vs level."""
    variables = list(SWEPT_VARIABLES.keys())
    n = len(variables)
    cols = 4
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(3.0 * cols, 2.4 * rows), sharey=True)
    axes = np.atleast_1d(axes).flatten()
    for ax, variable in zip(axes, variables):
        levels = [str(l) for l in SWEPT_VARIABLES[variable]]
        ys, lo, hi = [], [], []
        for lvl in levels:
            row = summary[(summary["variable"] == variable) & (summary["level"] == lvl) & (summary["agent"] == agent)]
            if len(row):
                ys.append(row["win_rate"].iloc[0])
                lo.append(row["win_rate_lo"].iloc[0])
                hi.append(row["win_rate_hi"].iloc[0])
            else:
                ys.append(np.nan); lo.append(np.nan); hi.append(np.nan)
        ys, lo, hi = np.array(ys), np.array(lo), np.array(hi)
        x = np.arange(len(levels))
        yerr = np.vstack([ys - lo, hi - ys])
        ax.bar(x, ys, yerr=yerr, capsize=3, color=AGENT_COLORS[agent], edgecolor="black", linewidth=0.4)
        ax.set_xticks(x); ax.set_xticklabels(levels, fontsize=8)
        if str(DEFAULTS[variable]) in levels:
            ax.get_xticklabels()[levels.index(str(DEFAULTS[variable]))].set_fontweight("bold")
        ax.set_title(variable, fontsize=10)
        ax.set_ylim(0, 1.05)
        ax.grid(axis="y", alpha=0.3)
    # Hide any unused subplots
    for ax in axes[len(variables):]:
        ax.axis("off")
    fig.suptitle(f"Win rate across all sweeps -- agent: {agent}", fontsize=12)
    fig.supylabel("win rate")
    fig.tight_layout()
    _save(fig, out_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--csv", default="results/ofat.csv", help="Path to the OFAT results CSV.")
    p.add_argument("--out-dir", default="results_analysis", help="Where to write figures/tables.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.csv)
    print(f"Loaded {len(df)} rows from {args.csv}")

    figdir = os.path.join(args.out_dir, "figures")
    tabdir = os.path.join(args.out_dir, "tables")
    os.makedirs(figdir, exist_ok=True)
    os.makedirs(tabdir, exist_ok=True)

    # ---- tables ----
    summary = build_summary_table(df)
    summary.to_csv(os.path.join(tabdir, "summary_stats.csv"), index=False)
    print(f"wrote summary_stats.csv  ({len(summary)} rows)")

    omnibus = build_omnibus_tests(df)
    omnibus.to_csv(os.path.join(tabdir, "omnibus_tests.csv"), index=False)
    print(f"wrote omnibus_tests.csv  ({len(omnibus)} rows)")

    effects = build_effects_table(df)
    effects.to_csv(os.path.join(tabdir, "effects_ranked.csv"), index=False)
    print(f"wrote effects_ranked.csv ({len(effects)} rows)")

    # ---- overview figures ----
    plot_overview_heatmap(summary, os.path.join(figdir, "overview_winrate_heatmap.png"))
    print("wrote overview_winrate_heatmap.png")
    plot_stats_overview(summary, effects, os.path.join(figdir, "overview_stats_heatmap.png"))
    print("wrote overview_stats_heatmap.png")
    plot_top_effects(effects, os.path.join(figdir, "overview_top_effects.png"))
    print("wrote overview_top_effects.png")

    # ---- per-variable figures ----
    for variable in SWEPT_VARIABLES:
        plot_variable_winrate(summary, variable, os.path.join(figdir, "by_variable", f"{variable}_winrate.png"))
        plot_variable_metric(df, variable, "turns", "mean turns (won)",
                             os.path.join(figdir, "by_variable", f"{variable}_turns.png"), won_only=True)
        plot_variable_metric(df, variable, "damage_taken", "mean damage taken",
                             os.path.join(figdir, "by_variable", f"{variable}_damage.png"))
        print(f"wrote by_variable/{variable}_*.png")

    # ---- per-agent overview figures ----
    for agent in AGENTS:
        plot_agent_overview(summary, agent, os.path.join(figdir, "by_agent", f"{agent}_overview.png"))
        print(f"wrote by_agent/{agent}_overview.png")

    # ---- console summary: top 10 effects ----
    print("\nTop 10 effects on win rate vs default pool (sorted by |Cohen's h|):")
    cols = ["agent", "variable", "level", "winrate_default", "winrate_level",
            "delta_winrate", "cohens_h", "p_won", "p_won_holm"]
    with pd.option_context("display.width", 200, "display.max_columns", None, "display.precision", 3):
        print(effects[cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()