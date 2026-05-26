# PCG Experiment Analysis

Episodes: 1800
Unique cells: 36

## Overall win rate by size and agent

| size   | agent       |   win_rate |   episodes |
|:-------|:------------|-----------:|-----------:|
| large  | heuristic   |      0.353 |        150 |
| large  | mcts_medium |      0.827 |        150 |
| large  | mcts_small  |      0.747 |        150 |
| large  | random      |      0.013 |        150 |
| medium | heuristic   |      0.373 |        150 |
| medium | mcts_medium |      0.787 |        150 |
| medium | mcts_small  |      0.727 |        150 |
| medium | random      |      0.013 |        150 |
| small  | heuristic   |      1.000 |        150 |
| small  | mcts_medium |      1.000 |        150 |
| small  | mcts_small  |      1.000 |        150 |
| small  | random      |      0.627 |        150 |

## Top balanced configurations

| size   | map_type    | enemy_profile   | item_profile   | wall_profile   | balance_label   |   balance_score |   win_rate_random |   win_rate_heuristic |   win_rate_mcts_small |   win_rate_mcts_medium |   skill_gap_mcts_medium_vs_heuristic |
|:-------|:------------|:----------------|:---------------|:---------------|:----------------|----------------:|------------------:|---------------------:|----------------------:|-----------------------:|-------------------------------------:|
| medium | baseline    | medium_plus     | many           | open           | balanced        |           1.156 |             0.020 |                0.360 |                 0.760 |                  0.800 |                                0.440 |
| medium | arena       | medium_plus     | many           | open           | balanced        |           1.138 |             0.000 |                0.400 |                 0.780 |                  0.880 |                                0.480 |
| large  | arena       | normal          | many           | open           | expert-leaning  |           1.128 |             0.000 |                0.220 |                 0.660 |                  0.860 |                                0.640 |
| large  | baseline    | normal          | many           | normal         | balanced        |           1.128 |             0.040 |                0.420 |                 0.760 |                  0.860 |                                0.440 |
| large  | random_walk | normal          | many           | open           | balanced        |           1.108 |             0.000 |                0.420 |                 0.820 |                  0.760 |                                0.340 |
| medium | random_walk | medium_plus     | many           | open           | balanced        |           0.964 |             0.020 |                0.360 |                 0.640 |                  0.680 |                                0.320 |
| small  | random_walk | normal          | normal         | normal         | too easy        |           0.160 |             0.580 |                1.000 |                 1.000 |                  1.000 |                                0.000 |
| small  | arena       | normal          | normal         | normal         | too easy        |           0.130 |             0.640 |                1.000 |                 1.000 |                  1.000 |                                0.000 |
| small  | baseline    | normal          | normal         | normal         | too easy        |           0.120 |             0.660 |                1.000 |                 1.000 |                  1.000 |                                0.000 |

## Label counts

| label          |   count |
|:---------------|--------:|
| balanced       |       5 |
| too easy       |       3 |
| expert-leaning |       1 |
