# OFAT Analysis

Episodes: 2040
Cells: 68

## Baseline

The OFAT experiment varies one factor at a time around this baseline:

- `size`: `medium`
- `map_type`: `baseline`
- `enemy_profile`: `medium_plus`
- `item_profile`: `many`
- `wall_profile`: `open`
- `player_hp`: `4`
- `enemy_hp`: `2`

Baseline agent performance:

| agent       |   episodes |   win_rate |   avg_turns |   avg_damage_taken |   avg_final_hp |
|:------------|-----------:|-----------:|------------:|-------------------:|---------------:|
| heuristic   |         30 |      0.467 |       9.600 |              3.433 |          0.567 |
| mcts_medium |         30 |      0.833 |      18.033 |              2.533 |          1.467 |
| mcts_small  |         30 |      0.633 |      15.767 |              3.000 |          1.000 |
| random      |         30 |      0.000 |      12.900 |              4.000 |          0.000 |

## Largest win-rate effects

| factor        |   random |   heuristic |   mcts_small |   mcts_medium |
|:--------------|---------:|------------:|-------------:|--------------:|
| size          |    0.667 |       0.533 |        0.333 |         0.267 |
| map_type      |    0.000 |       0.067 |        0.133 |         0.200 |
| enemy_profile |    0.667 |       0.867 |        0.500 |         0.333 |
| item_profile  |    0.033 |       0.200 |        0.233 |         0.300 |
| wall_profile  |    0.033 |       0.167 |        0.033 |         0.200 |
| player_hp     |    0.100 |       0.833 |        0.500 |         0.433 |
| enemy_hp      |    0.533 |       0.967 |        0.833 |         0.700 |

## Factor-level summary

| factor        | value       | agent       |   win_rate |   delta_win_rate |   avg_turns |   delta_turns |   avg_damage_taken |   delta_damage_taken |
|:--------------|:------------|:------------|-----------:|-----------------:|------------:|--------------:|-------------------:|---------------------:|
| size          | large       | random      |      0.000 |            0.000 |      16.300 |         3.400 |              4.000 |                0.000 |
| size          | large       | heuristic   |      0.467 |            0.000 |      11.567 |         1.967 |              3.233 |               -0.200 |
| size          | large       | mcts_small  |      0.733 |            0.100 |      19.167 |         3.400 |              2.700 |               -0.300 |
| size          | large       | mcts_medium |      0.733 |           -0.100 |      19.533 |         1.500 |              2.533 |                0.000 |
| size          | medium      | random      |      0.000 |            0.000 |      12.900 |         0.000 |              4.000 |                0.000 |
| size          | medium      | heuristic   |      0.467 |            0.000 |       9.600 |         0.000 |              3.433 |                0.000 |
| size          | medium      | mcts_small  |      0.633 |            0.000 |      15.767 |         0.000 |              3.000 |                0.000 |
| size          | medium      | mcts_medium |      0.833 |            0.000 |      18.033 |         0.000 |              2.533 |                0.000 |
| size          | small       | random      |      0.667 |            0.667 |      13.800 |         0.900 |              2.667 |               -1.333 |
| size          | small       | heuristic   |      1.000 |            0.533 |       4.467 |        -5.133 |              1.233 |               -2.200 |
| size          | small       | mcts_small  |      0.967 |            0.333 |      11.700 |        -4.067 |              1.867 |               -1.133 |
| size          | small       | mcts_medium |      1.000 |            0.167 |      10.767 |        -7.267 |              1.200 |               -1.333 |
| map_type      | arena       | random      |      0.000 |            0.000 |      13.933 |         1.033 |              4.000 |                0.000 |
| map_type      | arena       | heuristic   |      0.433 |           -0.033 |      11.933 |         2.333 |              3.433 |                0.000 |
| map_type      | arena       | mcts_small  |      0.767 |            0.133 |      18.967 |         3.200 |              2.900 |               -0.100 |
| map_type      | arena       | mcts_medium |      0.867 |            0.033 |      17.900 |        -0.133 |              2.400 |               -0.133 |
| map_type      | baseline    | random      |      0.000 |            0.000 |      12.900 |         0.000 |              4.000 |                0.000 |
| map_type      | baseline    | heuristic   |      0.467 |            0.000 |       9.600 |         0.000 |              3.433 |                0.000 |
| map_type      | baseline    | mcts_small  |      0.633 |            0.000 |      15.767 |         0.000 |              3.000 |                0.000 |
| map_type      | baseline    | mcts_medium |      0.833 |            0.000 |      18.033 |         0.000 |              2.533 |                0.000 |
| map_type      | random_walk | random      |      0.000 |            0.000 |      23.000 |        10.100 |              4.000 |                0.000 |
| map_type      | random_walk | heuristic   |      0.400 |           -0.067 |      15.933 |         6.333 |              3.400 |               -0.033 |
| map_type      | random_walk | mcts_small  |      0.633 |            0.000 |      28.100 |        12.333 |              3.033 |                0.033 |
| map_type      | random_walk | mcts_medium |      0.667 |           -0.167 |      36.500 |        18.467 |              2.700 |                0.167 |
| enemy_profile | heavy       | random      |      0.000 |            0.000 |      11.533 |        -1.367 |              4.000 |                0.000 |
| enemy_profile | heavy       | heuristic   |      0.133 |           -0.333 |       9.733 |         0.133 |              3.800 |                0.367 |
| enemy_profile | heavy       | mcts_small  |      0.500 |           -0.133 |      15.933 |         0.167 |              3.300 |                0.300 |
| enemy_profile | heavy       | mcts_medium |      0.667 |           -0.167 |      16.900 |        -1.133 |              3.000 |                0.467 |
| enemy_profile | light       | random      |      0.667 |            0.667 |      18.500 |         5.600 |              2.733 |               -1.267 |
| enemy_profile | light       | heuristic   |      1.000 |            0.533 |       5.733 |        -3.867 |              1.400 |               -2.033 |
| enemy_profile | light       | mcts_small  |      1.000 |            0.367 |      13.933 |        -1.833 |              1.633 |               -1.367 |
| enemy_profile | light       | mcts_medium |      1.000 |            0.167 |      12.067 |        -5.967 |              1.200 |               -1.333 |
| enemy_profile | medium_plus | random      |      0.000 |            0.000 |      12.900 |         0.000 |              4.000 |                0.000 |
| enemy_profile | medium_plus | heuristic   |      0.467 |            0.000 |       9.600 |         0.000 |              3.433 |                0.000 |
| enemy_profile | medium_plus | mcts_small  |      0.633 |            0.000 |      15.767 |         0.000 |              3.000 |                0.000 |
| enemy_profile | medium_plus | mcts_medium |      0.833 |            0.000 |      18.033 |         0.000 |              2.533 |                0.000 |
| enemy_profile | normal      | random      |      0.000 |            0.000 |      14.933 |         2.033 |              4.000 |                0.000 |
| enemy_profile | normal      | heuristic   |      0.867 |            0.400 |       8.300 |        -1.300 |              2.600 |               -0.833 |
| enemy_profile | normal      | mcts_small  |      0.967 |            0.333 |      15.933 |         0.167 |              2.300 |               -0.700 |
| enemy_profile | normal      | mcts_medium |      1.000 |            0.167 |      16.100 |        -1.933 |              1.833 |               -0.700 |
| item_profile  | few         | random      |      0.000 |            0.000 |      11.833 |        -1.067 |              4.000 |                0.000 |
| item_profile  | few         | heuristic   |      0.267 |           -0.200 |       9.100 |        -0.500 |              3.733 |                0.300 |
| item_profile  | few         | mcts_small  |      0.400 |           -0.233 |      15.400 |        -0.367 |              3.433 |                0.433 |
| item_profile  | few         | mcts_medium |      0.533 |           -0.300 |      15.733 |        -2.300 |              3.400 |                0.867 |
| item_profile  | many        | random      |      0.000 |            0.000 |      12.900 |         0.000 |              4.000 |                0.000 |
| item_profile  | many        | heuristic   |      0.467 |            0.000 |       9.600 |         0.000 |              3.433 |                0.000 |
| item_profile  | many        | mcts_small  |      0.633 |            0.000 |      15.767 |         0.000 |              3.000 |                0.000 |
| item_profile  | many        | mcts_medium |      0.833 |            0.000 |      18.033 |         0.000 |              2.533 |                0.000 |
| item_profile  | normal      | random      |      0.033 |            0.033 |      12.533 |        -0.367 |              3.967 |               -0.033 |
| item_profile  | normal      | heuristic   |      0.333 |           -0.133 |       9.233 |        -0.367 |              3.633 |                0.200 |
| item_profile  | normal      | mcts_small  |      0.600 |           -0.033 |      16.100 |         0.333 |              3.167 |                0.167 |
| item_profile  | normal      | mcts_medium |      0.700 |           -0.133 |      16.500 |        -1.533 |              2.667 |                0.133 |
| wall_profile  | normal      | random      |      0.000 |            0.000 |      14.967 |         2.067 |              4.000 |                0.000 |
| wall_profile  | normal      | heuristic   |      0.567 |            0.100 |      10.867 |         1.267 |              3.300 |               -0.133 |
| wall_profile  | normal      | mcts_small  |      0.600 |           -0.033 |      17.100 |         1.333 |              3.133 |                0.133 |
| wall_profile  | normal      | mcts_medium |      0.700 |           -0.133 |      18.800 |         0.767 |              2.867 |                0.333 |
| wall_profile  | open        | random      |      0.000 |            0.000 |      12.900 |         0.000 |              4.000 |                0.000 |
| wall_profile  | open        | heuristic   |      0.467 |            0.000 |       9.600 |         0.000 |              3.433 |                0.000 |
| wall_profile  | open        | mcts_small  |      0.633 |            0.000 |      15.767 |         0.000 |              3.000 |                0.000 |
| wall_profile  | open        | mcts_medium |      0.833 |            0.000 |      18.033 |         0.000 |              2.533 |                0.000 |
| wall_profile  | tight       | random      |      0.033 |            0.033 |      14.233 |         1.333 |              3.967 |               -0.033 |
| wall_profile  | tight       | heuristic   |      0.400 |           -0.067 |      10.333 |         0.733 |              3.433 |                0.000 |
| wall_profile  | tight       | mcts_small  |      0.633 |            0.000 |      17.300 |         1.533 |              3.000 |                0.000 |
| wall_profile  | tight       | mcts_medium |      0.633 |           -0.200 |      20.700 |         2.667 |              2.900 |                0.367 |
| player_hp     | 3           | random      |      0.000 |            0.000 |      11.067 |        -1.833 |              3.000 |               -1.000 |
| player_hp     | 3           | heuristic   |      0.100 |           -0.367 |       8.100 |        -1.500 |              2.900 |               -0.533 |
| player_hp     | 3           | mcts_small  |      0.467 |           -0.167 |      12.933 |        -2.833 |              2.233 |               -0.767 |
| player_hp     | 3           | mcts_medium |      0.567 |           -0.267 |      15.300 |        -2.733 |              1.933 |               -0.600 |
| player_hp     | 4           | random      |      0.000 |            0.000 |      12.900 |         0.000 |              4.000 |                0.000 |
| player_hp     | 4           | heuristic   |      0.467 |            0.000 |       9.600 |         0.000 |              3.433 |                0.000 |
| player_hp     | 4           | mcts_small  |      0.633 |            0.000 |      15.767 |         0.000 |              3.000 |                0.000 |
| player_hp     | 4           | mcts_medium |      0.833 |            0.000 |      18.033 |         0.000 |              2.533 |                0.000 |
| player_hp     | 5           | random      |      0.033 |            0.033 |      15.033 |         2.133 |              4.967 |                0.967 |
| player_hp     | 5           | heuristic   |      0.833 |            0.367 |      10.100 |         0.500 |              3.600 |                0.167 |
| player_hp     | 5           | mcts_small  |      0.933 |            0.300 |      18.633 |         2.867 |              3.267 |                0.267 |
| player_hp     | 5           | mcts_medium |      1.000 |            0.167 |      18.100 |         0.067 |              2.667 |                0.133 |
| player_hp     | 6           | random      |      0.100 |            0.100 |      17.000 |         4.100 |              5.867 |                1.867 |
| player_hp     | 6           | heuristic   |      0.933 |            0.467 |      10.467 |         0.867 |              3.667 |                0.233 |
| player_hp     | 6           | mcts_small  |      0.967 |            0.333 |      19.833 |         4.067 |              3.967 |                0.967 |
| player_hp     | 6           | mcts_medium |      1.000 |            0.167 |      18.633 |         0.600 |              3.467 |                0.933 |
| enemy_hp      | 1           | random      |      0.533 |            0.533 |      17.733 |         4.833 |              3.133 |               -0.867 |
| enemy_hp      | 1           | heuristic   |      0.967 |            0.500 |      12.100 |         2.500 |              0.900 |               -2.533 |
| enemy_hp      | 1           | mcts_small  |      1.000 |            0.367 |      15.733 |        -0.033 |              1.500 |               -1.500 |
| enemy_hp      | 1           | mcts_medium |      0.933 |            0.100 |      14.600 |        -3.433 |              1.233 |               -1.300 |
| enemy_hp      | 2           | random      |      0.000 |            0.000 |      12.900 |         0.000 |              4.000 |                0.000 |
| enemy_hp      | 2           | heuristic   |      0.467 |            0.000 |       9.600 |         0.000 |              3.433 |                0.000 |
| enemy_hp      | 2           | mcts_small  |      0.633 |            0.000 |      15.767 |         0.000 |              3.000 |                0.000 |
| enemy_hp      | 2           | mcts_medium |      0.833 |            0.000 |      18.033 |         0.000 |              2.533 |                0.000 |
| enemy_hp      | 3           | random      |      0.000 |            0.000 |      12.867 |        -0.033 |              4.000 |                0.000 |
| enemy_hp      | 3           | heuristic   |      0.000 |           -0.467 |       8.000 |        -1.600 |              4.000 |                0.567 |
| enemy_hp      | 3           | mcts_small  |      0.167 |           -0.467 |      11.567 |        -4.200 |              3.833 |                0.833 |
| enemy_hp      | 3           | mcts_medium |      0.233 |           -0.600 |      13.900 |        -4.133 |              3.700 |                1.167 |
