# GridBattle

GridBattle is a turn-based tactical grid game for the Modern Game AI Algorithms final project. The project includes:

- a playable Pygame interface (`play.py`);
- a Griddly-backed game environment;
- procedural map generation;
- agent-based experiments for evaluating difficulty and balance.

## Installation

Use Python 3.11.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
````

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Playing the game

Start the default playable game:

```bash
python play.py
```

Recommended first-time player command:

```bash
python play.py --size small --map-type baseline --items normal --enemy-count default --wall-density default --seed 1
```

This starts a small baseline map with normal item placement and the default enemy/wall settings. It is the easiest way to learn the controls before trying harder generated maps.

Recommended next maps:

```bash
python play.py --size medium --map-type arena --items many --enemy-count medium_plus --wall-density low --seed 2
python play.py --size large --map-type random_walk --items many --enemy-count default --wall-density low --seed 3
```

### Controls

* Left click: select the player, destination, target, item, or UI button.
* Space: select the player.
* Enter: commit the selected turn.
* Escape: cancel the current selection.
* R: restart the current map.

## `play.py` arguments

```bash
python play.py [options]
```

| Argument          |                                        Values / type |    Default | Description                                                                          |
| ----------------- | ---------------------------------------------------: | ---------: | ------------------------------------------------------------------------------------ |
| `--default-map`   |                                                 flag |        off | Use the fixed default map instead of generating a map.                               |
| `--seed`          |                                              integer |     random | Seed for generated maps. Use this to reproduce a map.                                |
| `--size`          |                           `small`, `medium`, `large` |    `small` | Generated map size.                                                                  |
| `--map-type`      |                   `baseline`, `random_walk`, `arena` | `baseline` | PCG generator type.                                                                  |
| `--items`         | `few`, `normal`, `many`, `none`, `default`, `double` |  `default` | Item density preset.                                                                 |
| `--enemy-count`   |              `low`, `default`, `medium_plus`, `high` |  `default` | Enemy count preset.                                                                  |
| `--wall-density`  |                             `low`, `default`, `high` |  `default` | Wall density preset.                                                                 |
| `--max-steps`     |                                              integer |      `120` | Maximum number of player turns.                                                      |
| `--tile-size`     |                                              integer |       `68` | Pixel size of each tile in the Pygame UI.                                            |
| `--auto-close-ms` |                                              integer |        `0` | Automatically close the window after this many milliseconds. Useful for smoke tests. |

Examples:

```bash
python play.py --default-map
python play.py --size small --map-type baseline --seed 42
python play.py --size medium --map-type arena --items many --enemy-count medium_plus --wall-density low --seed 42
python play.py --size large --map-type random_walk --items many --enemy-count default --wall-density low --seed 42
```

## Running experiments

Experiments are run with:

```bash
python experiment.py <command> [options]
```

Most experiment commands support:

| Argument      | Description                                                                                             |
| ------------- | ------------------------------------------------------------------------------------------------------- |
| `--episodes`  | Number of episodes per configuration.                                                                   |
| `--seed`      | Base random seed.                                                                                       |
| `--max-steps` | Maximum number of player turns per episode.                                                             |
| `--csv-out`   | Output CSV path.                                                                                        |
| `--overwrite` | Overwrite an existing CSV output file.                                                                  |
| `--dry-run`   | Print planned configurations without running them. Available for screening, OFAT, and final validation. |
| `--workers`   | Number of parallel worker processes.                                                                    |

Valid agents are:

```text
random, heuristic, mcts_small, mcts_medium, mcts_strong, mcts_weak
```

`mcts_weak` is an alias for `mcts_small`.

## Experiment commands

### Smoke test

Quick sanity check that the real environment runs:

```bash
python experiment.py smoke --episodes 2 --workers 4
```

Arguments:

| Argument      | Default |
| ------------- | ------: |
| `--episodes`  |     `2` |
| `--seed`      |    `11` |
| `--max-steps` |    `60` |
| `--workers`   |     `1` |

### Single evaluation

Run one configuration with one agent:

```bash
python experiment.py eval \
  --agent heuristic \
  --size medium \
  --map-type random_walk \
  --items normal \
  --enemy-count default \
  --wall-density default \
  --episodes 20 \
  --csv-out results/eval.csv \
  --workers 4
```

Arguments:

| Argument         | Values / default                                                       |
| ---------------- | ---------------------------------------------------------------------- |
| `--agent`        | default `heuristic`; one of the valid agents listed above              |
| `--episodes`     | default `20`                                                           |
| `--seed`         | default `11`                                                           |
| `--size`         | default `medium`; `small`, `medium`, `large`                           |
| `--map-type`     | default `random_walk`; `baseline`, `random_walk`, `arena`              |
| `--items`        | default `normal`; `few`, `normal`, `many`, `none`, `default`, `double` |
| `--enemy-count`  | default `default`; `low`, `default`, `medium_plus`, `high`             |
| `--wall-density` | default `default`; `low`, `default`, `high`                            |
| `--max-steps`    | default `120`                                                          |
| `--csv-out`      | default none                                                           |
| `--quiet`        | suppress per-episode output                                            |
| `--workers`      | default `1`                                                            |

### Balance pilot

Quick sweep over size, map type, and validation agents:

```bash
python experiment.py balance-pilot \
  --episodes 10 \
  --items normal \
  --enemy-count default \
  --wall-density default \
  --csv-out results/balance_pilot.csv \
  --overwrite \
  --workers 4
```

### PCG screening

Reduced factorial screen over PCG profiles:

```bash
python experiment.py pcg-screen \
  --episodes 20 \
  --sizes small,medium,large \
  --map-types baseline,random_walk,arena \
  --enemy-profiles light,normal,heavy \
  --item-profiles few,normal,many \
  --wall-profiles open,normal \
  --agents random,heuristic,mcts_small,mcts_medium \
  --csv-out results/pcg_screening.csv \
  --overwrite \
  --workers 8
```

Profile values:

```text
enemy-profiles: light, normal, medium_plus, heavy
item-profiles:  few, normal, many
wall-profiles:  open, normal, tight
```

Preview the full set of cells without running:

```bash
python experiment.py pcg-screen --dry-run
```

### Medium enemy tuning

This is a targeted screen for medium maps:

```bash
python experiment.py pcg-screen \
  --episodes 30 \
  --sizes medium \
  --map-types baseline,random_walk,arena \
  --enemy-profiles normal,medium_plus,heavy \
  --item-profiles normal,many \
  --wall-profiles open,normal \
  --agents random,heuristic,mcts_small,mcts_medium \
  --csv-out results/medium_enemy_tuning.csv \
  --overwrite \
  --workers 8
```

### OFAT sensitivity

One-factor-at-a-time sensitivity around a tuned baseline:

```bash
python experiment.py ofat \
  --episodes 30 \
  --csv-out results/ofat_real.csv \
  --overwrite \
  --workers 8
```

Important arguments:

| Argument                   | Default                                                                    |
| -------------------------- | -------------------------------------------------------------------------- |
| `--factors`                | `size,map_type,enemy_profile,item_profile,wall_profile,player_hp,enemy_hp` |
| `--agents`                 | `random,heuristic,mcts_small,mcts_medium`                                  |
| `--baseline-size`          | tuned baseline size                                                        |
| `--baseline-map-type`      | tuned baseline map type                                                    |
| `--baseline-enemy-profile` | tuned baseline enemy profile                                               |
| `--baseline-item-profile`  | tuned baseline item profile                                                |
| `--baseline-wall-profile`  | tuned baseline wall profile                                                |
| `--baseline-player-hp`     | tuned baseline player HP                                                   |
| `--baseline-enemy-hp`      | tuned baseline enemy HP                                                    |
| `--player-hp-levels`       | comma-separated positive integers                                          |
| `--enemy-hp-levels`        | comma-separated positive integers                                          |

Example with only HP factors:

```bash
python experiment.py ofat \
  --factors player_hp,enemy_hp \
  --player-hp-levels 3,4,5,6 \
  --enemy-hp-levels 1,2,3 \
  --episodes 30 \
  --workers 8
```

### Final validation

Run the final selected generator defaults:

```bash
python experiment.py final-validation \
  --episodes 50 \
  --csv-out results/final_validation.csv \
  --overwrite \
  --workers 8
```

Optional arguments:

| Argument      | Default                                   |
| ------------- | ----------------------------------------- |
| `--agents`    | `random,heuristic,mcts_small,mcts_medium` |
| `--episodes`  | `50`                                      |
| `--seed`      | `11`                                      |
| `--max-steps` | `120`                                     |
| `--csv-out`   | `results/final_validation.csv`            |
| `--dry-run`   | off                                       |
| `--workers`   | `1`                                       |

### Replay

Replay one generated episode as text or in the Pygame UI:

```bash
python experiment.py replay \
  --agent mcts_medium \
  --size large \
  --map-type arena \
  --items many \
  --enemy-count default \
  --wall-density low \
  --seed 11 \
  --episode 0
```

Save a replay log:

```bash
python experiment.py replay \
  --agent mcts_medium \
  --size large \
  --map-type arena \
  --episode 0 \
  --log-out results/replay.txt
```

Replay with UI:

```bash
python experiment.py replay \
  --agent mcts_medium \
  --size large \
  --map-type arena \
  --episode 0 \
  --ui \
  --pause
```

Replay-specific arguments:

| Argument      | Description                                           |
| ------------- | ----------------------------------------------------- |
| `--agent`     | Agent to replay.                                      |
| `--episode`   | Episode index to replay.                              |
| `--pause`     | Start paused.                                         |
| `--log-out`   | Write replay text to a file.                          |
| `--ui`        | Show the replay in the Pygame UI.                     |
| `--delay-ms`  | Delay between replay steps in UI mode. Default `600`. |
| `--tile-size` | Tile size in UI mode. Default `68`.                   |