# Brecha B — Statistical analysis

## Kruskal-Wallis: ACS across 6 agent types

H = 598.913, p = 3.474e-127

## Pairwise Mann-Whitney U: Syncference > each other type
Bonferroni α = 0.05/5 = 0.0100

| Comparison | U | p-value | Cliff's δ | Significant @ Bonf |
|---|---|---|---|---|
| Sync vs greedy | 10000 | 1.761e-45 | 1.000 | ✓ |
| Sync vs inflator | 10000 | 1.761e-45 | 1.000 | ✓ |
| Sync vs underreporter | 10000 | 1.761e-45 | 1.000 | ✓ |
| Sync vs mixed | 10000 | 2.881e-45 | 1.000 | ✓ |
| Sync vs burst_recovery | 10000 | 1.761e-45 | 1.000 | ✓ |

## Hypothesis verdicts

**H_B1 (Sync ACS > 0.95 sustained):** ✓ confirmed (mean = 1.0000)

**H_B2 (all non-Sync types ACS significantly lower):** ✓ confirmed (5/5 significant @ Bonf)

**H_B3 (Integrity_ext drives discrimination):** ✓ confirmed (I_ext range = 0.950, S range = 0.000)
