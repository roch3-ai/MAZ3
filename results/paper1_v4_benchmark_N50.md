# Paper 1 v4 — Benchmark Results

Generated: 2026-04-18 19:19:30

Runs per cell: 50


## Primary metrics (collision rate, task completion, deadlock frequency)


### Scenario: Asymmetric_risk


#### Network: ideal

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 0.712 ± 0.000 |
| greedy | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.997 ± 0.000 |
| orca | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.995 ± 0.001 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 1.000 ± 0.000 |

#### Network: wifi_warehouse

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 0.711 ± 0.001 |
| greedy | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.994 ± 0.001 |
| orca | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.991 ± 0.001 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 1.000 ± 0.000 |

#### Network: lora_mesh

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 0.708 ± 0.002 |
| greedy | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.986 ± 0.001 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 1.000 ± 0.000 |

### Scenario: Bottleneck


#### Network: ideal

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.995 ± 0.000 |
| greedy | 0.1600 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.891 ± 0.000 |
| mixed | 0.0608 ± 0.0225 | 0.470 ± 0.120 | 0.00 | 0.954 ± 0.013 |
| orca | 0.0000 ± 0.0000 | 0.333 ± 0.000 | 0.00 | 0.995 ± 0.000 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.968 ± 0.000 |

#### Network: wifi_warehouse

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.991 ± 0.002 |
| greedy | 0.1600 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.888 ± 0.001 |
| mixed | 0.0608 ± 0.0225 | 0.470 ± 0.120 | 0.00 | 0.952 ± 0.013 |
| orca | 0.0000 ± 0.0000 | 0.333 ± 0.000 | 0.00 | 0.991 ± 0.001 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.968 ± 0.000 |

#### Network: lora_mesh

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.975 ± 0.004 |
| greedy | 0.1600 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.880 ± 0.002 |
| mixed | 0.0613 ± 0.0232 | 0.470 ± 0.120 | 0.00 | 0.944 ± 0.013 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.968 ± 0.000 |

## Algorithmic convergence time (excludes network δ)

| Scenario | Network | Agent Type | Convergence (ms) |
|---|---|---|---|
| bottleneck | ideal | syncference | 0.0081 ± 0.0015 |
| bottleneck | ideal | greedy | 0.0079 ± 0.0002 |
| bottleneck | ideal | mixed | 0.0082 ± 0.0020 |
| bottleneck | ideal | orca | 0.0076 ± 0.0001 |
| bottleneck | ideal | omniscient_v2 | 0.0078 ± 0.0003 |
| bottleneck | wifi_warehouse | syncference | 0.0081 ± 0.0016 |
| bottleneck | wifi_warehouse | greedy | 0.0080 ± 0.0004 |
| bottleneck | wifi_warehouse | mixed | 0.0079 ± 0.0004 |
| bottleneck | wifi_warehouse | orca | 0.0093 ± 0.0115 |
| bottleneck | wifi_warehouse | omniscient_v2 | 0.0078 ± 0.0004 |
| bottleneck | lora_mesh | syncference | 0.0079 ± 0.0004 |
| bottleneck | lora_mesh | greedy | 0.0079 ± 0.0002 |
| bottleneck | lora_mesh | mixed | 0.0079 ± 0.0002 |
| bottleneck | lora_mesh | omniscient_v2 | 0.0076 ± 0.0001 |
| asymmetric_risk | ideal | syncference | 0.0189 ± 0.0007 |
| asymmetric_risk | ideal | greedy | 0.0108 ± 0.0017 |
| asymmetric_risk | ideal | orca | 0.0129 ± 0.0120 |
| asymmetric_risk | ideal | omniscient_v2 | 0.0684 ± 0.0013 |
| asymmetric_risk | wifi_warehouse | syncference | 0.0192 ± 0.0024 |
| asymmetric_risk | wifi_warehouse | greedy | 0.0104 ± 0.0007 |
| asymmetric_risk | wifi_warehouse | orca | 0.0123 ± 0.0118 |
| asymmetric_risk | wifi_warehouse | omniscient_v2 | 0.0684 ± 0.0019 |
| asymmetric_risk | lora_mesh | syncference | 0.0188 ± 0.0006 |
| asymmetric_risk | lora_mesh | greedy | 0.0106 ± 0.0014 |
| asymmetric_risk | lora_mesh | omniscient_v2 | 0.0759 ± 0.0102 |

## Sovereign Behavioral Equivalence (Syncference vs OmniscientV2, Asymmetric_risk)

| Network | Syncference H_p | OmniscientV2 H_p | Δ | Coll (Sync) | Coll (Omni) | Task (Sync) | Task (Omni) | Deadlock (Sync) | Deadlock (Omni) |
|---|---|---|---|---|---|---|---|---|---|
| ideal | 0.7121 ± 0.0001 | 1.0000 ± 0.0000 | -0.2879 | 0.0000 | 0.0000 | 0.400 | 0.400 | 0.00 | 0.00 |
| wifi_warehouse | 0.7112 ± 0.0005 | 1.0000 ± 0.0000 | -0.2888 | 0.0000 | 0.0000 | 0.400 | 0.400 | 0.00 | 0.00 |
| lora_mesh | 0.7080 ± 0.0015 | 1.0000 ± 0.0000 | -0.2920 | 0.0000 | 0.0000 | 0.400 | 0.400 | 0.00 | 0.00 |

## Sovereign Behavioral Equivalence (Syncference vs OmniscientV2, Bottleneck)

| Network | Syncference H_p | OmniscientV2 H_p | Δ | Coll (Sync) | Coll (Omni) | Task (Sync) | Task (Omni) | Deadlock (Sync) | Deadlock (Omni) |
|---|---|---|---|---|---|---|---|---|---|
| ideal | 0.9953 ± 0.0003 | 0.9677 ± 0.0002 | +0.0276 | 0.0000 | 0.0000 | 0.000 | 0.000 | 0.00 | 0.00 |
| wifi_warehouse | 0.9907 ± 0.0019 | 0.9677 ± 0.0000 | +0.0230 | 0.0000 | 0.0000 | 0.000 | 0.000 | 0.00 | 0.00 |
| lora_mesh | 0.9749 ± 0.0040 | 0.9677 ± 0.0000 | +0.0072 | 0.0000 | 0.0000 | 0.000 | 0.000 | 0.00 | 0.00 |