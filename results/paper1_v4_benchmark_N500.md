# Paper 1 v4 — Benchmark Results

Generated: 2026-04-19 13:00:29

Runs per cell: 500


## Primary metrics (collision rate, task completion, deadlock frequency)


### Scenario: Asymmetric_risk


#### Network: ideal

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 0.711 ± 0.000 |
| greedy | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.989 ± 0.000 |
| orca | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.985 ± 0.001 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 1.000 ± 0.000 |

#### Network: wifi_warehouse

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 0.699 ± 0.004 |
| greedy | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.966 ± 0.006 |
| orca | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.967 ± 0.006 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 1.000 ± 0.000 |

#### Network: lora_mesh

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 0.653 ± 0.008 |
| greedy | 0.0000 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.898 ± 0.012 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.400 ± 0.000 | 0.00 | 1.000 ± 0.000 |

### Scenario: Bottleneck


#### Network: ideal

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.986 ± 0.001 |
| greedy | 0.1600 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.886 ± 0.000 |
| mixed | 0.0595 ± 0.0129 | 0.444 ± 0.158 | 0.00 | 0.949 ± 0.008 |
| orca | 0.2180 ± 0.1378 | 0.054 ± 0.143 | 0.00 | 0.847 ± 0.060 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.966 ± 0.005 |

#### Network: wifi_warehouse

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.964 ± 0.008 |
| greedy | 0.1600 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.869 ± 0.007 |
| mixed | 0.0599 ± 0.0145 | 0.442 ± 0.160 | 0.00 | 0.935 ± 0.011 |
| orca | 0.2707 ± 0.1193 | 0.034 ± 0.121 | 0.00 | 0.807 ± 0.058 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.967 ± 0.001 |

#### Network: lora_mesh

| Agent Type | Collisions/cycle | Task Completion | Deadlock Freq | H_p (secondary) |
|---|---|---|---|---|
| syncference | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.892 ± 0.017 |
| greedy | 0.1600 ± 0.0000 | 1.000 ± 0.000 | 0.00 | 0.811 ± 0.014 |
| mixed | 0.0602 ± 0.0144 | 0.441 ± 0.161 | 0.00 | 0.879 ± 0.016 |
| omniscient_v2 | 0.0000 ± 0.0000 | 0.000 ± 0.000 | 0.00 | 0.967 ± 0.002 |

## Algorithmic convergence time (excludes network δ)

| Scenario | Network | Agent Type | Convergence (ms) |
|---|---|---|---|
| bottleneck | ideal | syncference | 0.0210 ± 0.0027 |
| bottleneck | ideal | greedy | 0.0212 ± 0.0026 |
| bottleneck | ideal | mixed | 0.0214 ± 0.0036 |
| bottleneck | ideal | orca | 0.0227 ± 0.0142 |
| bottleneck | ideal | omniscient_v2 | 0.0205 ± 0.0025 |
| bottleneck | wifi_warehouse | syncference | 0.0241 ± 0.0019 |
| bottleneck | wifi_warehouse | greedy | 0.0236 ± 0.0016 |
| bottleneck | wifi_warehouse | mixed | 0.0193 ± 0.0038 |
| bottleneck | wifi_warehouse | orca | 0.0214 ± 0.0088 |
| bottleneck | wifi_warehouse | omniscient_v2 | 0.0188 ± 0.0015 |
| bottleneck | lora_mesh | syncference | 0.0183 ± 0.0028 |
| bottleneck | lora_mesh | greedy | 0.0221 ± 0.0038 |
| bottleneck | lora_mesh | mixed | 0.0210 ± 0.0025 |
| bottleneck | lora_mesh | omniscient_v2 | 0.0206 ± 0.0014 |
| asymmetric_risk | ideal | syncference | 0.0413 ± 0.0044 |
| asymmetric_risk | ideal | greedy | 0.0277 ± 0.0028 |
| asymmetric_risk | ideal | orca | 0.0297 ± 0.0192 |
| asymmetric_risk | ideal | omniscient_v2 | 0.1087 ± 0.0052 |
| asymmetric_risk | wifi_warehouse | syncference | 0.0383 ± 0.0042 |
| asymmetric_risk | wifi_warehouse | greedy | 0.0302 ± 0.0037 |
| asymmetric_risk | wifi_warehouse | orca | 0.0241 ± 0.0154 |
| asymmetric_risk | wifi_warehouse | omniscient_v2 | 0.1085 ± 0.0058 |
| asymmetric_risk | lora_mesh | syncference | 0.0380 ± 0.0037 |
| asymmetric_risk | lora_mesh | greedy | 0.0265 ± 0.0036 |
| asymmetric_risk | lora_mesh | omniscient_v2 | 0.1086 ± 0.0049 |

## Sovereign Behavioral Equivalence (Syncference vs OmniscientV2, Asymmetric_risk)

| Network | Syncference H_p | OmniscientV2 H_p | Δ | Coll (Sync) | Coll (Omni) | Task (Sync) | Task (Omni) | Deadlock (Sync) | Deadlock (Omni) |
|---|---|---|---|---|---|---|---|---|---|
| ideal | 0.7106 ± 0.0003 | 1.0000 ± 0.0000 | -0.2894 | 0.0000 | 0.0000 | 0.400 | 0.400 | 0.00 | 0.00 |
| wifi_warehouse | 0.6994 ± 0.0037 | 1.0000 ± 0.0000 | -0.3006 | 0.0000 | 0.0000 | 0.400 | 0.400 | 0.00 | 0.00 |
| lora_mesh | 0.6527 ± 0.0080 | 1.0000 ± 0.0000 | -0.3473 | 0.0000 | 0.0000 | 0.400 | 0.400 | 0.00 | 0.00 |

## Sovereign Behavioral Equivalence (Syncference vs OmniscientV2, Bottleneck)

| Network | Syncference H_p | OmniscientV2 H_p | Δ | Coll (Sync) | Coll (Omni) | Task (Sync) | Task (Omni) | Deadlock (Sync) | Deadlock (Omni) |
|---|---|---|---|---|---|---|---|---|---|
| ideal | 0.9858 ± 0.0007 | 0.9656 ± 0.0047 | +0.0202 | 0.0000 | 0.0000 | 0.000 | 0.000 | 0.00 | 0.00 |
| wifi_warehouse | 0.9639 ± 0.0082 | 0.9675 ± 0.0012 | -0.0035 | 0.0000 | 0.0000 | 0.000 | 0.000 | 0.00 | 0.00 |
| lora_mesh | 0.8917 ± 0.0169 | 0.9666 ± 0.0024 | -0.0749 | 0.0000 | 0.0000 | 0.000 | 0.000 | 0.00 | 0.00 |