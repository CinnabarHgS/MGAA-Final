# PCG Experiment Analysis

Episodes: 4320
Unique cells: 144

## Overall win rate by size and agent

| size   | agent       |   win_rate |   episodes |
|:-------|:------------|-----------:|-----------:|
| medium | heuristic   |      0.464 |       1080 |
| medium | mcts_medium |      0.736 |       1080 |
| medium | mcts_small  |      0.667 |       1080 |
| medium | random      |      0.042 |       1080 |

## Top balanced configurations

| size   | map_type    | enemy_profile   | item_profile   | wall_profile   | balance_label     |   balance_score |   win_rate_random |   win_rate_heuristic |   win_rate_mcts_small |   win_rate_mcts_medium |   skill_gap_mcts_medium_vs_heuristic |
|:-------|:------------|:----------------|:---------------|:---------------|:------------------|----------------:|------------------:|---------------------:|----------------------:|-----------------------:|-------------------------------------:|
| medium | baseline    | medium_plus     | many           | open           | balanced          |           1.163 |             0.000 |                0.467 |                 0.633 |                  0.833 |                                0.367 |
| medium | arena       | medium_plus     | many           | open           | balanced          |           1.147 |             0.000 |                0.433 |                 0.767 |                  0.867 |                                0.433 |
| medium | arena       | medium_plus     | normal         | normal         | balanced          |           1.147 |             0.000 |                0.300 |                 0.600 |                  0.833 |                                0.533 |
| medium | arena       | medium_plus     | many           | normal         | balanced          |           1.140 |             0.033 |                0.400 |                 0.767 |                  0.833 |                                0.433 |
| medium | arena       | medium_plus     | normal         | open           | expert-leaning    |           1.090 |             0.000 |                0.267 |                 0.567 |                  0.967 |                                0.700 |
| medium | baseline    | medium_plus     | normal         | normal         | balanced          |           1.013 |             0.000 |                0.433 |                 0.567 |                  0.700 |                                0.267 |
| medium | baseline    | medium_plus     | normal         | open           | balanced          |           0.987 |             0.033 |                0.333 |                 0.600 |                  0.700 |                                0.367 |
| medium | arena       | heavy           | normal         | open           | expert-leaning    |           0.973 |             0.000 |                0.033 |                 0.433 |                  0.700 |                                0.667 |
| medium | random_walk | medium_plus     | many           | open           | balanced          |           0.957 |             0.000 |                0.400 |                 0.633 |                  0.667 |                                0.267 |
| medium | random_walk | medium_plus     | normal         | open           | expert-leaning    |           0.943 |             0.000 |                0.267 |                 0.500 |                  0.667 |                                0.400 |
| medium | baseline    | medium_plus     | many           | normal         | balanced          |           0.933 |             0.000 |                0.567 |                 0.600 |                  0.700 |                                0.133 |
| medium | baseline    | heavy           | many           | open           | expert-leaning    |           0.930 |             0.000 |                0.133 |                 0.500 |                  0.667 |                                0.533 |
| medium | random_walk | medium_plus     | many           | normal         | balanced          |           0.897 |             0.000 |                0.333 |                 0.733 |                  0.633 |                                0.300 |
| medium | arena       | heavy           | normal         | normal         | mixed             |           0.713 |             0.000 |                0.100 |                 0.533 |                  0.533 |                                0.433 |
| medium | random_walk | heavy           | many           | open           | mixed             |           0.660 |             0.000 |                0.100 |                 0.367 |                  0.500 |                                0.400 |
| medium | arena       | heavy           | many           | normal         | mixed             |           0.653 |             0.000 |                0.033 |                 0.400 |                  0.500 |                                0.467 |
| medium | arena       | heavy           | many           | open           | mixed             |           0.637 |             0.033 |                0.033 |                 0.333 |                  0.500 |                                0.467 |
| medium | random_walk | medium_plus     | normal         | normal         | too hard          |           0.633 |             0.000 |                0.367 |                 0.500 |                  0.467 |                                0.100 |
| medium | baseline    | normal          | many           | open           | playable but easy |           0.623 |             0.000 |                0.867 |                 0.967 |                  1.000 |                                0.133 |
| medium | baseline    | normal          | normal         | open           | playable but easy |           0.620 |             0.033 |                0.867 |                 0.967 |                  0.967 |                                0.100 |

## Label counts

| label             |   count |
|:------------------|--------:|
| too easy          |      10 |
| balanced          |       9 |
| too hard          |       7 |
| expert-leaning    |       4 |
| mixed             |       4 |
| playable but easy |       2 |
