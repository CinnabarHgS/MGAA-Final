# PCG Experiment Analysis

Episodes: 12960
Unique cells: 648

## Overall win rate by size and agent

| size   | agent       |   win_rate |   episodes |
|:-------|:------------|-----------:|-----------:|
| large  | heuristic   |      0.437 |       1080 |
| large  | mcts_medium |      0.585 |       1080 |
| large  | mcts_small  |      0.540 |       1080 |
| large  | random      |      0.021 |       1080 |
| medium | heuristic   |      0.666 |       1080 |
| medium | mcts_medium |      0.801 |       1080 |
| medium | mcts_small  |      0.766 |       1080 |
| medium | random      |      0.244 |       1080 |
| small  | heuristic   |      0.992 |       1080 |
| small  | mcts_medium |      1.000 |       1080 |
| small  | mcts_small  |      0.992 |       1080 |
| small  | random      |      0.689 |       1080 |

## Top balanced configurations

| size   | map_type    | enemy_profile   | item_profile   | wall_profile   | balance_label   |   balance_score |   win_rate_random |   win_rate_heuristic |   win_rate_mcts_small |   win_rate_mcts_medium |   skill_gap_mcts_medium_vs_heuristic |
|:-------|:------------|:----------------|:---------------|:---------------|:----------------|----------------:|------------------:|---------------------:|----------------------:|-----------------------:|-------------------------------------:|
| large  | baseline    | normal          | many           | normal         | balanced        |           1.160 |             0.000 |                0.300 |                 0.750 |                  0.800 |                                0.500 |
| medium | baseline    | heavy           | many           | open           | expert-leaning  |           1.140 |             0.000 |                0.100 |                 0.450 |                  0.800 |                                0.700 |
| large  | arena       | normal          | many           | normal         | expert-leaning  |           1.130 |             0.000 |                0.200 |                 0.500 |                  0.850 |                                0.650 |
| large  | arena       | normal          | many           | open           | balanced        |           1.125 |             0.000 |                0.350 |                 0.450 |                  0.900 |                                0.550 |
| large  | baseline    | normal          | many           | open           | balanced        |           1.115 |             0.000 |                0.550 |                 0.700 |                  0.800 |                                0.250 |
| large  | baseline    | normal          | normal         | open           | balanced        |           1.085 |             0.000 |                0.350 |                 0.850 |                  0.750 |                                0.400 |
| large  | arena       | normal          | normal         | open           | expert-leaning  |           1.070 |             0.000 |                0.200 |                 0.650 |                  0.750 |                                0.550 |
| medium | arena       | heavy           | normal         | open           | expert-leaning  |           1.055 |             0.000 |                0.050 |                 0.400 |                  0.750 |                                0.700 |
| large  | arena       | normal          | normal         | normal         | expert-leaning  |           0.990 |             0.000 |                0.200 |                 0.450 |                  0.700 |                                0.500 |
| large  | random_walk | normal          | many           | open           | balanced        |           0.940 |             0.000 |                0.500 |                 0.800 |                  0.650 |                                0.150 |
| large  | baseline    | normal          | normal         | normal         | expert-leaning  |           0.890 |             0.050 |                0.250 |                 0.550 |                  0.650 |                                0.400 |
| large  | random_walk | normal          | normal         | normal         | balanced        |           0.845 |             0.000 |                0.350 |                 0.650 |                  0.600 |                                0.250 |
| large  | baseline    | normal          | few            | open           | mixed           |           0.770 |             0.000 |                0.400 |                 0.750 |                  0.550 |                                0.150 |
| large  | baseline    | normal          | few            | normal         | mixed           |           0.760 |             0.000 |                0.300 |                 0.550 |                  0.550 |                                0.250 |
| medium | arena       | heavy           | normal         | normal         | mixed           |           0.740 |             0.000 |                0.100 |                 0.500 |                  0.550 |                                0.450 |
| medium | arena       | heavy           | many           | normal         | mixed           |           0.735 |             0.000 |                0.050 |                 0.350 |                  0.550 |                                0.500 |
| large  | baseline    | heavy           | normal         | open           | mixed           |           0.735 |             0.000 |                0.050 |                 0.250 |                  0.550 |                                0.500 |
| large  | arena       | light           | normal         | normal         | mixed           |           0.700 |             0.050 |                0.850 |                 0.550 |                  0.800 |                               -0.050 |
| large  | random_walk | normal          | normal         | open           | mixed           |           0.695 |             0.000 |                0.450 |                 0.650 |                  0.500 |                                0.050 |
| large  | arena       | normal          | few            | normal         | mixed           |           0.665 |             0.000 |                0.150 |                 0.200 |                  0.500 |                                0.350 |

## Label counts

| label             |   count |
|:------------------|--------:|
| too easy          |      98 |
| too hard          |      31 |
| mixed             |      18 |
| balanced          |       6 |
| expert-leaning    |       6 |
| playable but easy |       3 |
