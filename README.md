# GridBattle Demo

This repo contains a minimal demo that follows the core scope of the proposal:

1. a tiny turn-based grid battle in Griddly
2. a procedural map generator
3. a simple heuristic AI for automated evaluation

## What is implemented

- `Milestone 1`: player, enemies, walls, melee combat, win/lose condition
- `Milestone 2`: random map generation with playability checks
- `Milestone 3`: baseline AI that plays generated maps and reports win rate, turns, and damage taken

## File layout

- `grid_battle/game.py`: Griddly environment wrapper and state parsing
- `grid_battle/pcg.py`: procedural map generation
- `grid_battle/agents.py`: heuristic baseline agent
- `play_demo.py`: command-line playable demo
- `evaluate_demo.py`: batch evaluation over generated maps

## Install

The local environment in this workspace uses Python 3.11.

```powershell
py -3.11 -m venv .venv
py -3.11 -m pip install --target ".venv\Lib\site-packages" -r requirements.txt
```

## Run the playable demo

```powershell
& ".\.venv\Scripts\python.exe" .\play_demo.py
```

Controls:

- `w/a/s/d`: move up/left/down/right
- `i/j/k/l`: attack up/left/down/right
- `q`: quit

## Run AI evaluation

```powershell
& ".\.venv\Scripts\python.exe" .\evaluate_demo.py --episodes 20
```

You can vary generation parameters, for example:

```powershell
& ".\.venv\Scripts\python.exe" .\evaluate_demo.py --episodes 30 --width 11 --height 9 --enemies 3 --obstacle-density 0.18
```

## Suggested next step

If we continue from here, the most natural next increment is:

1. replace the heuristic with MCTS
2. compare win rate across obstacle densities
3. add a richer objective such as exit tiles or ranged enemies

