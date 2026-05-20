# Analysis methods and findings

This document describes the analysis pipeline used to evaluate the gridworld
agents across the OFAT sweep, and summarises the main insights the analysis
surfaces. It is intended to feed directly into the methods section of the
report and to act as a guide to the generated figures and tables.

The pipeline is implemented in `analyze_ofat.py` and consumes the CSV produced
by `run_sweep.py`.

---

## Methods

### Experimental design

A **one-factor-at-a-time (OFAT) ablation** was used: each swept variable is
varied across 2&ndash;3 levels while all other variables are held at their
defaults (medium map, random-walk generation, default item / enemy / wall
density, player 4 HP / 1 dmg / 1 rng, enemy 2 HP / 1 dmg / 1 rng). For every
(variable, level, agent) cell, 50 independent episodes were run &mdash; 3
agents (random, heuristic, MCTS) &times; 50 episodes &times; 23 variable&ndash;level
combinations, &asymp; 3,450 episodes in total. All runs used a fixed master
seed (11) and a 120-step episode cap; MCTS was given 200 iterations per move.

OFAT trades statistical power against scope: it cannot detect interactions
between parameters, but it isolates the marginal effect of each variable
cleanly, which is what is needed to characterise an agent's failure modes.

### The default-configuration pool

A useful property of the OFAT layout is that the "default level" of every
variable produces episodes at the *fully default configuration*. Across all
eight sweeps, this yields **&asymp; 400 default-configuration episodes per
agent**, not 50. Because these episodes are i.i.d. samples from the same
parameter setting (differing only in episode seed), they can be pooled
validly. Every non-default cell is compared against this pooled reference,
raising the effective sample-size ratio from 50:50 to 50:400 and substantially
increasing power for moderate effects.

### Primary outcome: win rate

The headline metric is the binary win indicator per episode. For each cell,
the proportion of wins is reported together with a **95 % Wilson score
interval**, preferred to the Wald interval for proportions near 0 or 1
&mdash; relevant here since the heuristic agent wins 100 % on default-like
maps.

### Hypothesis tests vs the default pool

For each agent, every non-default cell is tested against that agent's default
pool &mdash; 15 comparisons per agent, 45 in total. Two tests are run per
comparison:

- **Fisher's exact test** on the 2&times;2 contingency table of wins vs
  losses. Fisher is preferred over &chi;&sup2; because several cells exhibit
  perfect separation (e.g. the heuristic agent wins 400/400 default
  episodes), which produces zero expected frequencies under &chi;&sup2;;
  Fisher is exact in those cases.
- **Mann&ndash;Whitney *U*** on turns-to-win, restricted to won episodes.
  Losing episodes are right-censored at the 120-step cap and would distort
  means if included.

Effect sizes are reported alongside p-values:

- **Cohen's *h*** for win-rate comparisons:
  *h* = 2&middot;arcsin(&radic;p&#8321;) &minus; 2&middot;arcsin(&radic;p&#8322;).
  Unlike a raw &Delta; win-rate, *h* is not compressed near 0 or 1, which
  matters because a shift from 0.98 to 0.46 (MCTS on `enemy_hp=3`) is the
  kind of change that should register as "large."
- **Rank-biserial correlation** for the Mann&ndash;Whitney tests.

|*h*| &ge; 0.5 (Cohen's conventional "medium" threshold) is used as the
*practical-significance* cutoff in the figures; at n = 400 the statistical-
significance bar is easily cleared even by trivially small effects, so
effect-size filtering is essential.

### Multiple-testing correction

Because 15 comparisons per agent inflate the family-wise false-positive rate,
p-values are adjusted using the **Holm&ndash;Bonferroni step-down procedure**
within each agent (separately for the win-rate and turns tests). Holm
controls the FWER at the same level as Bonferroni but is uniformly more
powerful. Correction is applied within-agent rather than across all 45 tests
because the per-agent analyses are treated as independent research questions.

### Omnibus tests

For each (agent, variable) pair, an omnibus test reports whether the variable
has *any* effect on outcome: **&chi;&sup2; on the (level &times; won)
contingency table** with **Cram&eacute;r's V** as the associated effect size,
and **Kruskal&ndash;Wallis on turns** across levels. These complement the
pairwise tests by answering "does this variable matter at all for this
agent?" before drilling into which specific levels are responsible.

### Visualisation

Three figure families summarise the results:

1. **Per-variable bar charts** with all three agents overlaid &mdash; Wilson
   CIs for win rate, percentile-bootstrap CIs (2,000 resamples) for
   continuous metrics. The default level is bolded on the x-axis.
2. **Per-agent panel figures** showing all eight variables in one image,
   for assessing a single agent's overall robustness profile.
3. **A three-panel significance heatmap** (one panel per agent) annotating
   each cell with its Holm-adjusted significance star and using directional
   border colour (black = significantly worse than default, blue =
   significantly better) to mark cells crossing the |*h*| &ge; 0.5 threshold.
   Tests are within-agent, hence the three-panel split.

A **top-effects bar chart** of the largest |Cohen's *h*| values across all
(agent, variable, level) comparisons provides a single-figure summary of
which parameter changes matter most and to which agent.

---

## Insights

### Headline findings

- **Heuristic dominates on default maps but is the most brittle agent.** Five
  of the seven largest negative effects in the study belong to the heuristic
  agent, all with |*h*| > 2.0 &mdash; `map_type=arena`, `enemy_hp=3`,
  `size=large`, `player_hp=3`, `enemy_count=high` each drop its win rate from
  &asymp; 1.00 to 0.08&ndash;0.28. This supports a "narrow competence, no
  planning depth" framing.
- **MCTS degrades more gracefully.** Its failure modes are the same *kinds*
  of stressors as the heuristic's, but the win-rate drops are roughly half
  the magnitude (e.g. arena: heuristic 0.08 vs MCTS 0.72). This is the
  standard story for search-based methods &mdash; they don't need a
  hand-crafted policy to handle off-distribution maps.
- **Random can be made competitive.** The two positive effects in the study
  both belong to the random agent: `enemy_hp=1` (0.16 &rarr; 0.72) and
  `player_range=2` (0.16 &rarr; 0.36). Both reduce the *skill* required per
  kill &mdash; one-shot wins encounters; ranged attacks remove positioning
  requirements. This is methodologically useful: it shows the random agent
  is a real lower bound rather than a degenerate one, which strengthens any
  claim of separation between agents.
- **Some variables are inert.** `items` and `wall_density` produce no large
  effects for any agent (no |*h*| &ge; 0.5 on either axis). Either these
  axes are under-parameterised or the agents are equally blind to them
  &mdash; worth a sentence acknowledging this rather than reporting all
  sweeps as equally informative.
- **`player_hp=3` is asymmetrically hard for MCTS.** It barely affects the
  heuristic (1.00 &rarr; 1.00) but drops MCTS to 0.74. Plausible explanation:
  with 3 HP and only 200 iterations, MCTS's rollouts encounter losing
  terminal states more often, biasing its tree expansion. Interactions with
  the search budget are exactly the kind of thing a follow-up study could
  quantify.
- **Methodological honesty about OFAT.** The design cannot reveal *interactions*
  (e.g. does high enemy count compound with large size?). At least one
  paragraph in limitations should note this; a full factorial over even the
  discrete levels here would have been 3&#8312; &times; 3 agents &asymp;
  20k cells, infeasible without subsampling. A small follow-up 2&sup3;
  factorial on the three strongest variables (`size`, `enemy_count`,
  `enemy_hp`) would be a defensible compromise.

### Reading `overview_top_effects.png`

The top-effects bar chart ranks all 45 (agent, variable, level) comparisons
by |Cohen's *h*| and shows the 15 largest. The plot rewards careful reading
&mdash; a few things to point out in the report:

- **The top half of the chart is monochrome (heuristic blue).** The five
  largest effects in the entire study are all heuristic failures, with
  *h* &le; &minus;2.0 each. In Cohen's terms |*h*| &ge; 0.8 is "large"; these
  are 2.5&times; that threshold. The visual monopoly is itself the finding:
  no single parameter change moves random or MCTS as much as the moderate
  ones move the heuristic. This is direct evidence that the heuristic
  occupies a narrow competence band &mdash; it is near-perfect on default
  configurations and near-useless once any single stressor pushes the
  environment off-distribution.
- **MCTS forms a coherent middle cluster.** The four MCTS bars
  (`size=large`, `enemy_hp=3`, `enemy_count=high`, `map_type=arena`) sit
  between *h* &asymp; &minus;0.8 and &minus;1.6 &mdash; ordered roughly by
  how much pure forward-planning depth they require. All four involve
  either more enemies to track, more HP per enemy (longer engagement
  sequences), or an open map where positioning has no walls to anchor it.
  The pattern fits the diagnosis that MCTS's failures are budget-bound
  rather than knowledge-bound: more iterations would plausibly close the
  gap, whereas no amount of heuristic tweaking would, since the heuristic
  fails *qualitatively differently* in the same conditions.
- **The two positive bars are diagnostic of the random baseline.** Random
  reaching *h* = +1.20 on `enemy_hp=1` is a sanity check: when an encounter
  can be won in a single bump, even random motion suffices. That the
  random agent's *only* large positive effects are precisely the parameter
  changes that lower the skill ceiling (one-shot kills, ranged attacks)
  rather than the ones that lower the difficulty floor (more items, fewer
  enemies) is reassurance that the random agent reflects a genuine "no
  policy" baseline. If `items=double` had produced a large positive effect
  for random, that would have been evidence the game was trivially solvable
  by exploration; it does not, and that is informative.
- **Three variables that one might expect to dominate, don't.** `items`,
  `wall_density`, and `player_range` produce only two entries in the
  top-15 between them (random's `player_range=2` is +0.61). Their
  absence is informative: in the regime studied, the dominant factors are
  *encounter difficulty* (enemy HP, enemy count, agent HP) and *map shape*
  (size, arena vs random_walk), not loot or maze structure. This is worth
  a sentence in discussion because it suggests that further work on the
  agents should target combat decision-making rather than navigation.
- **What the &Delta; win-rate annotations add.** Each bar is also labelled
  with the raw &Delta; win-rate, which preserves the substantive scale
  Cohen's *h* compresses. Cohen's *h* makes 0.98 &rarr; 0.46 look "larger"
  than 0.16 &rarr; 0.72 (because the latter starts further from the
  proportion boundary), but in *practical* terms a +0.56 swing for random
  is more behaviourally striking than a &minus;0.52 swing for MCTS. Both
  framings are valid; reporting both in one figure lets the reader pick.
- **Holm-adjusted stars are present on every bar.** Every entry in the top
  15 survives multiple-testing correction at *p* < 0.001 &mdash; the
  effects are not artefacts of running 45 tests. This means the ordering
  in the figure is interpretable as a real ranking, not noise.

### A defensible discussion arc

If the report needs a one-paragraph summary of agent comparison, the
top-effects chart supports a tight argument:

> The three agents differ not just in mean performance but in the *shape*
> of their failure modes. The heuristic agent is near-perfect on default
> configurations but collapses catastrophically under five distinct
> stressors (|*h*| > 2 in each case), revealing a narrow band of
> competence. MCTS shows the same qualitative weaknesses but with effect
> sizes roughly half as large, consistent with a search-based method
> trading depth for robustness. The random agent's only meaningful gains
> appear when the environment is altered to lower the skill ceiling rather
> than the difficulty floor, confirming it as a genuine no-policy
> baseline.

This phrasing avoids over-claiming and stays close to what the figure
actually shows.

---

## Generated artefacts

```
results_analysis/
  figures/
    overview_winrate_heatmap.png        single-glance overview, all agents in one matrix
    overview_stats_heatmap.png          three-panel heatmap with significance and effect-size markers
    overview_top_effects.png            ranked bar chart of largest Cohen's h values
    by_variable/<var>_winrate.png       one figure per swept variable, all agents overlaid
    by_variable/<var>_turns.png         same, but mean turns (won episodes only)
    by_variable/<var>_damage.png        same, but mean damage taken
    by_agent/<agent>_overview.png       one figure per agent, all variables panelled

  tables/
    summary_stats.csv                   per-cell win rate (+ Wilson CI), mean turns, mean damage, n
    omnibus_tests.csv                   chi^2 + Cramer's V and Kruskal-Wallis per (agent, variable)
    effects_ranked.csv                  every non-default level vs default pool, ranked by |h|,
                                        with Holm-adjusted p-values for both win and turns tests
```
