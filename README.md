# GridBattle Demo

This repo contains a minimal tactical grid-battle prototype built around four layers:

1. a Griddly battle environment
2. a procedural map generator
3. several AI baselines plus MCTS evaluation
4. a pygame presentation layer for mouse-driven play

## File Layout

- `grid_battle/game.py`: Griddly env wrapper and turn encoding
- `grid_battle/state.py`: snapshot/action dataclasses with no Griddly dependency
- `grid_battle/combat.py`: combat rules plus range/damage helpers
- `grid_battle/pcg.py`: procedural map generation, presets, and structural analysis
- `grid_battle/agents.py`: `HeuristicAgent`, `RandomAgent`, and `heuristic_turn()`
- `grid_battle/simulator.py`: pure-Python forward model used by MCTS
- `grid_battle/mcts.py`: `MctsAgent` (UCT search)
- `play_demo.py`: command-line playable demo
- `play_pygame.py`: pygame window demo with mouse-driven turn planning
- `evaluate_demo.py`: batch evaluation through Griddly
- `evaluate_simulator.py`: batch evaluation through the pure-Python simulator
- `inspect_pcg.py`: structural map inspection helper
- `run_sweep.py`: OFAT sweep runner for experiment batches

## Install

Python 3.11.

Windows (PowerShell):

```powershell
py -3.11 -m venv .venv
py -3.11 -m pip install --target ".venv\Lib\site-packages" -r requirements.txt
```

macOS / Linux:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`griddly` only ships an x86_64 wheel on PyPI, so it does not install on arm64 macs. The simulator-based tooling still works there.

## Play The Demo

CLI:

```powershell
& ".\.venv\Scripts\python.exe" .\play_demo.py
```

Pygame UI:

```powershell
& ".\.venv\Scripts\python.exe" .\play_pygame.py
```

Window controls:

- click the player to select it
- click a blue tile to preview movement
- click a red enemy to choose an attack
- select an inventory item from the action panel to activate it this turn
- `End Turn`: confirm the planned move, item use, and attacks
- `Esc`: cancel the current preview or selection
- `R`: reset the current map

## Agents

- `HeuristicAgent`: attacks immediately when possible, otherwise moves toward attackable tiles
- `RandomAgent`: uniformly random legal-move baseline
- `MctsAgent`: UCT search using the pure-Python simulator for rollouts

All three control the player. Enemies always use the built-in chase logic from the environment.

## Evaluation

Both evaluation runners support preset PCG maps via `--size` and `--map-type`.

Griddly evaluation:

```powershell
& ".\.venv\Scripts\python.exe" .\evaluate_demo.py --agent mcts --episodes 50 --size small --map-type baseline --seed 11 --mcts-iterations 200
```

Pure-Python evaluation:

```powershell
& ".\.venv\Scripts\python.exe" .\evaluate_simulator.py --agent mcts --episodes 50 --size small --map-type baseline --seed 11 --mcts-iterations 200
```

The simulator does not reproduce every Griddly behavior exactly, but it is useful for agent ranking and sweep automation when Griddly is unavailable.

## PCG Inspection

```powershell
& ".\.venv\Scripts\python.exe" .\inspect_pcg.py --count 3 --size small --map-type random_walk
```

## Sweeps

```powershell
& ".\.venv\Scripts\python.exe" .\run_sweep.py --episodes 50
```

Outputs are written under `results_analysis/` and CSV experiment logs.
