# Brecha A — Antifragility Decay (dual-metric)

Total runs: 1400

Wall time: 234.0s

## Per-strategy means (final cumulative payoff)

### Binary metric

| Strategy | n | mean | std | min | max |
|---|---|---|---|---|---|
| inflator | 300 | -237.500 | 0.000 | -237.500 | -237.500 |
| underreporter | 200 | -115.500 | 0.000 | -115.500 | -115.500 |
| mixed | 200 | -141.000 | 0.000 | -141.000 | -141.000 |
| burst_recovery | 200 | -147.500 | 0.000 | -147.500 | -147.500 |
| greedy | 200 | 0.000 | 0.000 | 0.000 | 0.000 |

### Proportional metric

| Strategy | n | mean | std | min | max |
|---|---|---|---|---|---|
| inflator | 300 | -179.261 | 0.000 | -179.261 | -179.261 |
| underreporter | 200 | -240.509 | 0.000 | -240.509 | -240.509 |
| mixed | 200 | -242.238 | 0.035 | -242.736 | -242.236 |
| burst_recovery | 200 | -179.535 | 0.000 | -179.535 | -179.535 |
| greedy | 200 | -65.498 | 0.000 | -65.498 | -65.498 |

## Floor sensitivity (inflator focal)

### Binary

| τ_floor | n | mean cum_payoff | std |
|---|---|---|---|
| 0.0 | 300 | -237.500 | 0.000 |
| 0.1 | 100 | -237.500 | 0.000 |
| 0.2 | 100 | -237.500 | 0.000 |
| 0.3 | 100 | -237.500 | 0.000 |

### Proportional

| τ_floor | n | mean cum_payoff | std |
|---|---|---|---|
| 0.0 | 300 | -179.261 | 0.000 |
| 0.1 | 100 | -162.517 | 0.000 |
| 0.2 | 100 | -145.515 | 0.000 |
| 0.3 | 100 | -128.257 | 0.000 |
