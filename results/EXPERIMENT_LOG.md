# Experiment Run Log

This document records the main experiments used for the GridBattle PCG balancing project: what each experiment was meant to answer, which settings were used, and which files it produced.

The experiments all use the real Griddly-backed `GridBattleEnv`. The Pygame UI is not opened during experiments.

---

## 1. Full PCG Screening Experiment

### Purpose

The full PCG screen was the broad search experiment. It tested how procedural generation settings affect difficulty, pacing, and agent performance.

This experiment was used to identify the main balancing factors and interactions.

### Command

```bash
python experiment.py pcg-screen   --episodes 20   --workers 16   --overwrite   --csv-out results/pcg_screening.csv
```

### Settings

The default `pcg-screen` grid was used.

| Setting type | Values |
|---|---|
| Sizes | `small`, `medium`, `large` |
| Map types | `baseline`, `random_walk`, `arena` |
| Enemy profiles | `light`, `normal`, `heavy` |
| Item profiles | `few`, `normal`, `many` |
| Wall profiles | `open`, `normal` |
| Agents | `random`, `heuristic`, `mcts_small`, `mcts_medium` |
| Episodes per cell | `20` |
| Workers | `16` |

### Scale

```text
3 sizes × 3 map types × 3 enemy profiles × 3 item profiles × 2 wall profiles × 4 agents
= 648 cells

648 cells × 20 episodes
= 12,960 episodes
```

### Main output

```text
results/pcg_screening.csv
```

### Analysis output

Produced with:

```bash
python results_analysis/analyze_pcg_results.py   results/pcg_screening.csv   --out-dir results_analysis/pcg_screening
```

Returned files:

```text
results_analysis/pcg_screening/
├── analysis_summary.md
├── tables/
│   ├── episode_rows_copy.csv
│   ├── agent_summary.csv
│   └── config_summary.csv
└── figures/
    ├── 01_agent_winrate_overview.png
    ├── 02_top_balance_candidates.png
    ├── 03_chokepoints_vs_turns.png
    ├── 04_chokepoints_vs_winrate.png
    └── heatmaps/
```

### Main use in report

Use this experiment to explain:

- the global difficulty curve across map sizes,
- which PCG variables have the largest effects,
- interactions between enemy count, items, walls, and map type,
- why `medium_plus` needed to be introduced later.

---

## 2. Medium Enemy Tuning Experiment

### Purpose

The full PCG screen showed that medium maps had a gap: `normal` enemies were often too easy, while `heavy` enemies were often too hard.

This targeted experiment tested the new intermediate enemy setting: `medium_plus`.

### Command

```bash
python experiment.py pcg-screen   --episodes 30   --workers 16   --sizes medium   --map-types baseline,random_walk,arena   --enemy-profiles normal,medium_plus,heavy   --item-profiles normal,many   --wall-profiles open,normal   --agents random,heuristic,mcts_small,mcts_medium   --overwrite   --csv-out results/medium_enemy_tuning.csv
```

### Settings

| Setting type | Values |
|---|---|
| Sizes | `medium` |
| Map types | `baseline`, `random_walk`, `arena` |
| Enemy profiles | `normal`, `medium_plus`, `heavy` |
| Item profiles | `normal`, `many` |
| Wall profiles | `open`, `normal` |
| Agents | `random`, `heuristic`, `mcts_small`, `mcts_medium` |
| Episodes per cell | `30` |
| Workers | `16` |

### Scale

```text
1 size × 3 map types × 3 enemy profiles × 2 item profiles × 2 wall profiles × 4 agents
= 144 cells

144 cells × 30 episodes
= 4,320 episodes
```

### Main output

```text
results/medium_enemy_tuning.csv
```

### Analysis output

Produced with:

```bash
python results_analysis/analyze_pcg_results.py   results/medium_enemy_tuning.csv   --out-dir results_analysis/medium_enemy_tuning
```

Returned files:

```text
results_analysis/medium_enemy_tuning/
├── analysis_summary.md
├── tables/
│   ├── episode_rows_copy.csv
│   ├── agent_summary.csv
│   └── config_summary.csv
└── figures/
    ├── 01_agent_winrate_overview.png
    ├── 02_top_balance_candidates.png
    ├── 03_chokepoints_vs_turns.png
    ├── 04_chokepoints_vs_winrate.png
    └── heatmaps/
```

### Main use in report

Use this experiment to justify the final medium-map setting:

```text
medium maps -> medium_plus enemies, many items, open walls
```

The key conclusion was that `medium_plus` produced a better skill gap than either `normal` or `heavy`.

---

## 3. OFAT Sensitivity Experiment

### Purpose

The one-factor-at-a-time experiment tested local sensitivity around the tuned medium-map baseline.

It was included to compare PCG factors with combat-rule factors, especially player HP and enemy HP.

This experiment is not the main PCG balancing experiment. It is a sensitivity check.

### Command

```bash
python experiment.py ofat   --episodes 30   --workers 16   --overwrite   --csv-out results/ofat_real.csv
```

### Baseline

The OFAT baseline was:

| Factor | Baseline value |
|---|---|
| Size | `medium` |
| Map type | `baseline` |
| Enemy profile | `medium_plus` |
| Item profile | `many` |
| Wall profile | `open` |
| Player HP | `4` |
| Enemy HP | `2` |

### Varied factors

| Factor | Levels tested |
|---|---|
| Size | `small`, `medium`, `large` |
| Map type | `baseline`, `random_walk`, `arena` |
| Enemy profile | `light`, `normal`, `medium_plus`, `heavy` |
| Item profile | `few`, `normal`, `many` |
| Wall profile | `open`, `normal`, `tight` |
| Player HP | `3`, `4`, `5`, `6` |
| Enemy HP | `1`, `2`, `3` |

Only one factor was changed at a time. The baseline was included once.

### Agents

```text
random
heuristic
mcts_small
mcts_medium
```

### Scale

```text
68 cells × 30 episodes = 2,040 episodes
```

The cell count is 68 because the baseline is included once, and each non-baseline factor level is evaluated for all four agents.

### Main output

```text
results/ofat_real.csv
```

### Analysis output

Produced with:

```bash
python results_analysis/analyze_ofat_results.py   results/ofat_real.csv   --out-dir results_analysis/ofat_real
```

Returned files:

```text
results_analysis/ofat_real/
├── ofat_analysis_summary.md
├── tables/
│   ├── ofat_cell_summary.csv
│   ├── ofat_factor_summary.csv
│   └── ofat_effect_sizes.csv
└── figures/
    ├── 01_baseline_winrate.png
    ├── 02_factor_effect_sizes.png
    ├── delta_winrate_size.png
    ├── delta_winrate_map_type.png
    ├── delta_winrate_enemy_profile.png
    ├── delta_winrate_item_profile.png
    ├── delta_winrate_wall_profile.png
    ├── delta_winrate_player_hp.png
    ├── delta_winrate_enemy_hp.png
    ├── health_curve_player_hp.png
    ├── health_curve_enemy_hp.png
    ├── turns_map_type.png
    ├── turns_wall_profile.png
    ├── turns_enemy_profile.png
    └── turns_item_profile.png
```

### Main use in report

Use OFAT to show:

- enemy HP and player HP have very large effects,
- combat rules should therefore remain fixed during final PCG balancing,
- among PCG variables, enemy profile is the strongest local difficulty knob,
- item and wall profiles mostly tune fairness and pacing.

---

## 4. Final Validation Experiment

### Purpose

The final validation experiment tested only the selected final PCG defaults.

Unlike the PCG screen and tuning experiments, this run was not meant to search for settings. It was meant to produce a clean final table showing how the final generator behaves.

### Command

```bash
python experiment.py final-validation   --episodes 50   --workers 16   --overwrite   --csv-out results/final_validation.csv
```

### Selected final PCG defaults

| Size | Map type | Enemy profile | Item profile | Wall profile |
|---|---|---|---|---|
| `small` | `baseline` | `normal` | `normal` | `normal` |
| `small` | `random_walk` | `normal` | `normal` | `normal` |
| `small` | `arena` | `normal` | `normal` | `normal` |
| `medium` | `baseline` | `medium_plus` | `many` | `open` |
| `medium` | `random_walk` | `medium_plus` | `many` | `open` |
| `medium` | `arena` | `medium_plus` | `many` | `open` |
| `large` | `baseline` | `normal` | `many` | `normal` |
| `large` | `random_walk` | `normal` | `many` | `open` |
| `large` | `arena` | `normal` | `many` | `open` |

### Agents

```text
random
heuristic
mcts_small
mcts_medium
```

### Scale

```text
9 selected map settings × 4 agents = 36 cells

36 cells × 50 episodes
= 1,800 episodes
```

### Main output

```text
results/final_validation.csv
```

### Analysis output

Produced with:

```bash
python results_analysis/analyze_pcg_results.py   results/final_validation.csv   --out-dir results_analysis/final_validation
```

Returned files:

```text
results_analysis/final_validation/
├── analysis_summary.md
├── tables/
│   ├── episode_rows_copy.csv
│   ├── agent_summary.csv
│   └── config_summary.csv
└── figures/
    ├── 01_agent_winrate_overview.png
    ├── 02_top_balance_candidates.png
    ├── 03_chokepoints_vs_turns.png
    ├── 04_chokepoints_vs_winrate.png
    └── heatmaps/
```

### Main use in report

Use this as the clean headline result.

This experiment validates that:

- small maps are easy/tutorial-like,
- medium and large maps are challenging for the heuristic agent,
- MCTS agents perform substantially better,
- random mostly fails outside small maps.

---

## 5. Notebook

A notebook version of the PCG analysis is available at:

```text
results_analysis/pcg_analysis.ipynb
```

It can be used to reproduce and inspect the main PCG plots interactively.

---

## 6. Exploratory and Debug Runs

The following commands were useful during development but are not central report results:

### Smoke test

```bash
python experiment.py smoke --workers 4
```

Used to confirm that agents and the real environment run correctly.

### Balance pilot

```bash
python experiment.py balance-pilot --episodes 10 --workers 8 --overwrite
```

Used during development to check whether the PCG screen and MCTS profiles behaved sensibly.

### Replay

```bash
python experiment.py replay   --agent mcts_medium   --size large   --map-type baseline   --seed 11   --episode 3   --ui   --pause
```

Used for manually inspecting specific games. Replay is deterministic when seed, episode, agent, and settings are fixed.

---

## 7. Summary of Main Result Files

| File | Description |
|---|---|
| `results/pcg_screening.csv` | Full reduced-factorial PCG screen |
| `results/medium_enemy_tuning.csv` | Targeted medium-map enemy profile tuning |
| `results/ofat_real.csv` | One-factor-at-a-time sensitivity experiment |
| `results/final_validation.csv` | Final selected generator validation |
| `results_analysis/pcg_screening/analysis_summary.md` | Summary of full PCG screen |
| `results_analysis/medium_enemy_tuning/analysis_summary.md` | Summary of medium enemy tuning |
| `results_analysis/ofat_real/ofat_analysis_summary.md` | Summary of OFAT sensitivity |
| `results_analysis/final_validation/analysis_summary.md` | Summary of final validation |
