# GridBattle Demo

This repo contains a minimal demo that follows the core scope of the proposal:

1. a tiny turn-based grid battle in Griddly
2. a procedural map generator
3. a simple heuristic AI for automated evaluation

## Milestones

- `Milestone 1`: player, enemies, walls, melee combat, win/lose condition
- `Milestone 2`: random map generation with playability checks
- `Milestone 3`: baseline AI that plays generated maps and reports win rate, turns, and damage taken

## File layout

- `grid_battle/game.py`: Griddly env wrapper and state parsing
- `grid_battle/state.py`: snapshot/action dataclasses (no Griddly dep)
- `grid_battle/combat.py`: combat rules + range/damage helpers
- `grid_battle/pcg.py`: procedural map generation
- `grid_battle/agents.py`: `HeuristicAgent` and `RandomAgent`
- `grid_battle/simulator.py`: pure-python forward model used by MCTS rollouts
- `grid_battle/mcts.py`: `MctsAgent` (UCT)
- `play_demo.py`: playable demo
- `evaluate_demo.py`: batch evaluation (uses Griddly)
- `evaluate_simulator.py`: batch evaluation (pure python, no Griddly)

## Install

Python 3.11.

Windows (PowerShell):
```powershell
py -3.11 -m venv .venv
py -3.11 -m pip install --target ".venv\Lib\site-packages" -r requirements.txt
```

macOS (zsh):
```
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Griddly only ships an x86_64 wheel on pypi, so it wont install on arm64 macs. `evaluate_simulator.py` still works there.

## Run the playable demo

```powershell
& ".\.venv\Scripts\python.exe" .\play_demo.py
```

Controls:

- `move>` uses `w/a/s/d` to move, `Enter` to skip movement
- `action>` uses `i/j/k/l` to attack, `Enter` to skip the action
- `q`: quit

## Agents

- `HeuristicAgent`: greedy. Attacks if an enemy is in range, otherwise BFS toward attackable tiles. Uses items, ranged and second attacks.
- `RandomAgent`: uniformly random over legal moves. Comparison baseline.
- `MctsAgent`: UCT search. Uses the python simulator for rollouts with the heuristic as the rollout policy. Iterations set via `--mcts-iterations`.

All three control the player. Enemies always use Griddly's built-in BFS chase.

## Run AI evaluation

Both runners take the same flags: `--agent {heuristic,random,mcts}`, `--mcts-iterations`, `--size`, `--map-type`, `--episodes`, `--seed`, `--max-steps`. Use `--help` for defaults.

With Griddly (Windows, Linux, intel mac):
```powershell
& ".\.venv\Scripts\python.exe" .\evaluate_demo.py --agent mcts --episodes 50 --size small --map-type baseline --seed 11 --mcts-iterations 200
```

Without Griddly (arm64 mac):
```
.venv/bin/python evaluate_simulator.py --agent mcts --episodes 50 --size small --map-type baseline --seed 11 --mcts-iterations 200
```

The two runners wont give identical numbers (the simulator skips some terrain/item effects), but the ranking between agents stays meaningful.

## Suggested next step

If we continue from here, the most natural next increment is:

1. compare win rate across obstacle densities and map types
2. add a richer objective such as exit tiles or ranged enemies
3. tune the MCTS iteration budget and shaping reward
