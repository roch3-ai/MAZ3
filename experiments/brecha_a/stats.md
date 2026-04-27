# Brecha A — Statistical analysis (dual-metric)

## Binary metric

### Linear regression: cycle vs mean_payoff (per strategy)

| Strategy | slope | intercept | p-value | R² | MK τ | MK p-value |
|---|---|---|---|---|---|---|
| inflator | -0.0071 | -2.0152 | 1.080e-04 | 0.143 | -0.096 | 1.581e-01 |
| underreporter | 0.0001 | -1.1600 | 9.762e-01 | 0.000 | -0.007 | 9.241e-01 |
| mixed | -0.0045 | -1.1821 | 2.112e-01 | 0.016 | -0.104 | 1.244e-01 |
| burst_recovery | -0.0014 | -1.4030 | 6.933e-01 | 0.002 | -0.045 | 5.047e-01 |
| greedy | 0.0000 | 0.0000 | nan | nan | 0.000 | 1.000e+00 |

### Kruskal-Wallis: final cum_payoff between strategies

H = 1099.000, p = 1.247e-236

## Proportional metric

### Linear regression: cycle vs mean_payoff (per strategy)

| Strategy | slope | intercept | p-value | R² | MK τ | MK p-value |
|---|---|---|---|---|---|---|
| inflator | -0.0107 | -1.2513 | 9.304e-11 | 0.350 | -0.325 | 1.728e-06 |
| underreporter | -0.0125 | -1.7726 | 8.512e-08 | 0.255 | -0.319 | 2.647e-06 |
| mixed | -0.0122 | -1.8045 | 7.749e-07 | 0.222 | -0.240 | 4.124e-04 |
| burst_recovery | -0.0106 | -1.2597 | 1.722e-10 | 0.342 | -0.291 | 1.775e-05 |
| greedy | -0.0000 | -0.6547 | 9.971e-01 | 0.000 | -0.008 | 9.075e-01 |

### Kruskal-Wallis: final cum_payoff between strategies

H = 1098.897, p = 1.313e-236

## Floor sensitivity — Binary metric

| τ_floor | slope | intercept | p-value | R² | MK τ | MK p-value |
|---|---|---|---|---|---|---|
| 0.0 | -0.0071 | -2.0152 | 1.080e-04 | 0.143 | -0.096 | 1.581e-01 |
| 0.1 | -0.0071 | -2.0152 | 1.080e-04 | 0.143 | -0.096 | 1.581e-01 |
| 0.2 | -0.0071 | -2.0152 | 1.080e-04 | 0.143 | -0.096 | 1.581e-01 |
| 0.3 | -0.0071 | -2.0152 | 1.080e-04 | 0.143 | -0.096 | 1.581e-01 |

## Floor sensitivity — Proportional metric

| τ_floor | slope | intercept | p-value | R² | MK τ | MK p-value |
|---|---|---|---|---|---|---|
| 0.0 | -0.0107 | -1.2513 | 9.304e-11 | 0.350 | -0.397 | 4.771e-09 |
| 0.1 | -0.0091 | -1.1664 | 5.689e-10 | 0.326 | -0.308 | 5.662e-06 |
| 0.2 | -0.0076 | -1.0736 | 3.484e-09 | 0.301 | -0.335 | 8.026e-07 |
| 0.3 | -0.0061 | -0.9727 | 2.199e-08 | 0.275 | -0.257 | 1.518e-04 |

## Hypothesis verdicts

### Under binary metric

**H_A1 (Mann-Kendall monotonic decay per adversarial):**

- inflator: ✗ rejected (τ=-0.096, p=1.581e-01)
- underreporter: ✗ rejected (τ=-0.007, p=9.241e-01)
- mixed: ✗ rejected (τ=-0.104, p=1.244e-01)
- burst_recovery: ✗ rejected (τ=-0.045, p=5.047e-01)

**H_A2 (linear slope < 0 with p < 0.05):**

- inflator: ✓ confirmed (slope=-0.0071, p=1.080e-04)
- underreporter: ✗ rejected (slope=0.0001, p=9.762e-01)
- mixed: ✗ rejected (slope=-0.0045, p=2.112e-01)
- burst_recovery: ✗ rejected (slope=-0.0014, p=6.933e-01)

**H_A3 (Greedy baseline shows no decay):**

- greedy: ✓ confirmed (no decay) (slope=0.0000, p=nan, τ=0.000)

**H_A4 (τ_floor relaxes decay):**

- slopes by floor: {0.0: '-0.0071', 0.1: '-0.0071', 0.2: '-0.0071', 0.3: '-0.0071'}
- range of slopes: 0.0000
- decay relaxes monotonically with floor: ✗ flat or non-monotonic

### Under proportional metric

**H_A1 (Mann-Kendall monotonic decay per adversarial):**

- inflator: ✓ confirmed (τ=-0.325, p=1.728e-06)
- underreporter: ✓ confirmed (τ=-0.319, p=2.647e-06)
- mixed: ✓ confirmed (τ=-0.240, p=4.124e-04)
- burst_recovery: ✓ confirmed (τ=-0.291, p=1.775e-05)

**H_A2 (linear slope < 0 with p < 0.05):**

- inflator: ✓ confirmed (slope=-0.0107, p=9.304e-11)
- underreporter: ✓ confirmed (slope=-0.0125, p=8.512e-08)
- mixed: ✓ confirmed (slope=-0.0122, p=7.749e-07)
- burst_recovery: ✓ confirmed (slope=-0.0106, p=1.722e-10)

**H_A3 (Greedy baseline shows no decay):**

- greedy: ✓ confirmed (no decay) (slope=-0.0000, p=9.971e-01, τ=-0.008)

**H_A4 (τ_floor relaxes decay):**

- slopes by floor: {0.0: '-0.0107', 0.1: '-0.0091', 0.2: '-0.0076', 0.3: '-0.0061'}
- range of slopes: 0.0046
- decay relaxes monotonically with floor: ✓ confirmed

