# GridBattle

GridBattle is a turn-based tactical gridworld project for Modern Game AI Algorithms. The project combines a playable Pygame game, Griddly-backed simulation, procedural content generation (PCG), and agent-based evaluation.

The current project focus is **PCG balancing with agents**: generated maps are structurally valid by construction, and experiments evaluate whether they are also fair, interesting, and appropriately difficult for agents of different strength.

Main entry points:

```bash
python play.py
python experiment.py ...
```

- `play.py` starts the playable Pygame version.
- `experiment.py` runs headless real-environment experiments and agent replays.

---

## After unzipping `code.zip`

The zip is intended to be self-contained for running the game, reproducing the
experiments, and regenerating the analysis summaries/figures.

```bash
unzip code.zip
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run these commands from the directory containing `README.md`,
`requirements.txt`, `play.py`, and `experiment.py`.

The existing result CSV files are included under `results/`, so the report
analysis can be regenerated without rerunning all experiments. To check that the
environment works, run:

```bash
python experiment.py smoke --workers 4
```

To regenerate the final validation analysis from the included CSV:

```bash
python results_analysis/analyze_pcg_results.py \
  results/final_validation.csv \
  --out-dir results_analysis/final_validation
```

To recompute the final validation itself:

```bash
python experiment.py final-validation \
  --episodes 50 \
  --workers 16 \
  --overwrite \
  --csv-out results/final_validation.csv
```

To reproduce all main experiment CSVs from scratch, run the commands in the
Experiments section below.

---

## Installation

Use Python 3.11.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The playable game and experiments require a working Griddly installation.

---

## Game overview

GridBattle is a small turn-based tactical combat game on a 2D grid.

The player wins by defeating all enemies. The player loses when health reaches zero, or when the turn limit is reached during experiments.

Each player turn can include movement, item activation, and attacks. Enemies then move toward the player and attack when possible.

### Terrain

- **Hill**: increases attack range.
- **Bush**: gives a chance to dodge incoming damage.
- **Bunker**: absorbs 1 incoming damage once, then collapses. Bunkers do not trap or block the player.

### Items

- **Dual berettas**: allows a second attack while active.
- **Shotgun**: strengthens close-range attacking.
- **Golden gun**: provides a short powerful attack effect.
- **Vehicle**: allows extended movement while active.

Items are part of the core game and are included in all final PCG configurations.

### Enemy behavior

Enemies use pathfinding to move toward the player through walkable tiles. If an enemy can reach or attack the player, it deals damage according to the current combat rules.

---

## Procedural map generation

PCG is implemented in `grid_battle/pcg.py`.

The generator first creates a map and then validates it structurally. A map is only accepted if the player can reach positions from which all enemies are attackable. This means maps are theoretically playable, but not necessarily balanced.

The experiments therefore evaluate generated maps with agents.

### Map types

- **baseline**: scattered obstacle layout with general-purpose tactical structure.
- **random_walk**: cave-like layout produced by random walk carving; tends to create corridors and chokepoints.
- **arena**: more open combat-focused layout.

### Size presets

The final public sizes are:

```text
small   = easy / tutorial-like
medium  = main balanced setting
large   = hard setting
```

### PCG profiles

Experiments use profile names rather than raw numbers:

- **enemy profile**: `light`, `normal`, `medium_plus`, `heavy`
- **item profile**: `few`, `normal`, `many`
- **wall profile**: `open`, `normal`, `tight`

The important tuned profile is `medium_plus`, which adds one enemy above the normal medium-map setting. This was introduced because `normal` enemies were too easy on medium maps, while `heavy` enemies were often too harsh.

---

## Agents

### Random agent

Chooses legal actions randomly. It is mainly a sanity check. If random wins often on medium or large maps, the map is probably too easy.

### Heuristic agent

A greedy tactical baseline. It generally:

1. activates useful items,
2. attacks immediately if possible,
3. otherwise moves toward a tile from which an enemy can be attacked,
4. attacks after moving if possible,
5. uses a second attack when dual berettas are active.

This represents a competent non-searching player.

### MCTS agent

The MCTS agent uses Monte Carlo Tree Search with UCT. It plans with an internal forward model and executes actions in the real `GridBattleEnv`.

Available profiles:

```text
mcts_small   = 50 iterations,  rollout depth 10
mcts_medium  = 200 iterations, rollout depth 30
mcts_strong  = 800 iterations, rollout depth 40
```

Most experiments use `mcts_small` and `mcts_medium`.

---

## Play the game

Start a regular game:

```bash
python play.py
```

Example generated map:

```bash
python play.py --size medium --map-type random_walk --seed 42
```

Show options:

```bash
python play.py --help
```

---

## Experiments

Experiments are headless and use the real Griddly-backed environment. Use `--workers` to parallelize episodes.

Quick smoke test:

```bash
python experiment.py smoke --workers 4
```

Single evaluation:

```bash
python experiment.py eval \
  --agent mcts_medium \
  --size large \
  --map-type arena \
  --episodes 20 \
  --workers 8
```

### PCG screening

The full PCG screen explores combinations of size, map type, enemy profile, item profile, wall profile, and agent.

```bash
python experiment.py pcg-screen \
  --episodes 20 \
  --workers 16 \
  --overwrite \
  --csv-out results/pcg_screening.csv
```

Preview cells without running:

```bash
python experiment.py pcg-screen --dry-run
```

### Medium enemy tuning

This targeted experiment compares `normal`, `medium_plus`, and `heavy` enemy profiles on medium maps.

```bash
python experiment.py pcg-screen \
  --episodes 30 \
  --workers 16 \
  --sizes medium \
  --map-types baseline,random_walk,arena \
  --enemy-profiles normal,medium_plus,heavy \
  --item-profiles normal,many \
  --wall-profiles open,normal \
  --agents random,heuristic,mcts_small,mcts_medium \
  --overwrite \
  --csv-out results/medium_enemy_tuning.csv
```

### OFAT sensitivity experiment

The one-factor-at-a-time experiment varies one factor around the tuned medium-map baseline. It includes PCG parameters and combat-rule parameters such as player HP and enemy HP.

```bash
python experiment.py ofat \
  --episodes 30 \
  --workers 16 \
  --overwrite \
  --csv-out results/ofat_real.csv
```

This experiment is used to show which parameters are most sensitive. In particular, player HP and enemy HP strongly affect difficulty, so final PCG balancing keeps combat rules fixed.

### Final validation

After choosing final PCG defaults, run the final validation:

```bash
python experiment.py final-validation \
  --episodes 50 \
  --workers 16 \
  --overwrite \
  --csv-out results/final_validation.csv
```

This validates the selected final generator settings:

```text
small:
  all map types -> normal enemies, normal items, normal walls

medium:
  all map types -> medium_plus enemies, many items, open walls

large:
  baseline    -> normal enemies, many items, normal walls
  random_walk -> normal enemies, many items, open walls
  arena       -> normal enemies, many items, open walls
```

---

## Replay a game

Replay a specific generated game by using the same seed and episode index.

Text replay:

```bash
python experiment.py replay \
  --agent mcts_medium \
  --size large \
  --map-type baseline \
  --seed 11 \
  --episode 3
```

Write a replay log:

```bash
python experiment.py replay \
  --agent mcts_medium \
  --size large \
  --map-type baseline \
  --seed 11 \
  --episode 3 \
  --log-out results/replays/mcts_medium_large_baseline_ep3.txt
```

Replay in the normal Pygame UI:

```bash
python experiment.py replay \
  --agent mcts_medium \
  --size large \
  --map-type baseline \
  --seed 11 \
  --episode 3 \
  --ui \
  --pause
```

Controls:

```text
Space        pause/resume
Enter/Right  step once
R            reset same replay
Esc/Q        quit
```

Replay uses deterministic seeding, so the same seed, episode, agent, and settings should reproduce the same game.

---

## Analysis

Analysis is kept separate from `experiment.py`.

### PCG analysis

```bash
python results_analysis/analyze_pcg_results.py \
  results/pcg_screening.csv \
  --out-dir results_analysis/pcg_screening
```

For the medium tuning run:

```bash
python results_analysis/analyze_pcg_results.py \
  results/medium_enemy_tuning.csv \
  --out-dir results_analysis/medium_enemy_tuning
```

For final validation:

```bash
python results_analysis/analyze_pcg_results.py \
  results/final_validation.csv \
  --out-dir results_analysis/final_validation
```

### OFAT analysis

```bash
python results_analysis/analyze_ofat_results.py \
  results/ofat_real.csv \
  --out-dir results_analysis/ofat_real
```

The analysis scripts create summary tables, Markdown summaries, and figures under `results_analysis/`.

A notebook version is also available at:

```text
results_analysis/pcg_analysis.ipynb
```

---

## Current experimental conclusions

The experiments support the following design decisions:

- Small maps are intentionally easy and tutorial-like.
- Medium maps need `medium_plus` enemies to create meaningful skill separation.
- Large maps are hard enough with `normal` enemies; `heavy` is usually too punishing.
- More items make difficult maps fairer and give MCTS more tactical opportunities.
- Random-walk maps are often slower because they create more chokepoints.
- Player HP and enemy HP are highly sensitive, so the final PCG evaluation keeps combat rules fixed.

The final validation should be used as the clean headline result for the report.

---

## Repository layout

```text
.
├── play.py
├── experiment.py
├── requirements.txt
├── grid_battle/
│   ├── agents.py
│   ├── combat.py
│   ├── game.py
│   ├── mcts.py
│   ├── pcg.py
│   ├── simulator.py
│   ├── state.py
│   └── ui_pygame.py
├── results/
│   ├── pcg_screening.csv
│   ├── medium_enemy_tuning.csv
│   ├── ofat_real.csv
│   └── final_validation.csv
└── results_analysis/
    ├── analyze_pcg_results.py
    ├── analyze_ofat_results.py
    └── pcg_analysis.ipynb
```

---

## Recommended workflow

```bash
python play.py
python experiment.py smoke --workers 4
python experiment.py final-validation --episodes 50 --workers 16 --overwrite
python results_analysis/analyze_pcg_results.py results/final_validation.csv --out-dir results_analysis/final_validation
```

## Full reproduction workflow

The following commands recreate the main CSV files used in the report. The
runtime depends on hardware and worker count; reduce `--workers` if needed.

```bash
python experiment.py pcg-screen \
  --episodes 20 \
  --workers 16 \
  --overwrite \
  --csv-out results/pcg_screening.csv

python experiment.py pcg-screen \
  --episodes 30 \
  --workers 16 \
  --sizes medium \
  --map-types baseline,random_walk,arena \
  --enemy-profiles normal,medium_plus,heavy \
  --item-profiles normal,many \
  --wall-profiles open,normal \
  --agents random,heuristic,mcts_small,mcts_medium \
  --overwrite \
  --csv-out results/medium_enemy_tuning.csv

python experiment.py ofat \
  --episodes 30 \
  --workers 16 \
  --overwrite \
  --csv-out results/ofat_real.csv

python experiment.py final-validation \
  --episodes 50 \
  --workers 16 \
  --overwrite \
  --csv-out results/final_validation.csv
```

After regenerating the CSVs, recreate the analysis summaries and figures:

```bash
python results_analysis/analyze_pcg_results.py \
  results/pcg_screening.csv \
  --out-dir results_analysis/pcg_screening

python results_analysis/analyze_pcg_results.py \
  results/medium_enemy_tuning.csv \
  --out-dir results_analysis/medium_enemy_tuning

python results_analysis/analyze_ofat_results.py \
  results/ofat_real.csv \
  --out-dir results_analysis/ofat_real

python results_analysis/analyze_pcg_results.py \
  results/final_validation.csv \
  --out-dir results_analysis/final_validation

python results_analysis/make_report_assets.py
```
