#!/usr/bin/env bash
# Docker entrypoint for Azure Container Instances.
#
# Reads the cell description from environment variables and runs exactly one
# (scenario, network, agent_type) benchmark cell with N_RUNS seeds, writing
# the CellResult JSON to OUTPUT_FILE. OUTPUT_FILE typically lives on a shared
# Azure Files volume so the orchestrator can aggregate all cells after the
# containers exit.
#
# Required env vars:
#   SCENARIO         e.g. bottleneck | asymmetric_risk
#   NETWORK_PROFILE  e.g. ideal | wifi_warehouse | lora_mesh
#   AGENT_TYPE       e.g. syncference | greedy | mixed | orca | omniscient_v2
#   N_RUNS           integer, number of seeds per cell
#   OUTPUT_FILE      absolute path where the per-cell JSON will be written
#
# Optional env vars:
#   SEED_BASE        integer (default 42)

set -euo pipefail

: "${SCENARIO:?SCENARIO is required}"
: "${NETWORK_PROFILE:?NETWORK_PROFILE is required}"
: "${AGENT_TYPE:?AGENT_TYPE is required}"
: "${N_RUNS:?N_RUNS is required}"
: "${OUTPUT_FILE:?OUTPUT_FILE is required}"
SEED_BASE="${SEED_BASE:-42}"

echo "[entrypoint] scenario=${SCENARIO} network=${NETWORK_PROFILE} agent=${AGENT_TYPE} N=${N_RUNS} seed_base=${SEED_BASE} out=${OUTPUT_FILE}"

cd /maz3
exec python -m scripts.run_single_cell \
    --scenario "${SCENARIO}" \
    --network "${NETWORK_PROFILE}" \
    --agent-type "${AGENT_TYPE}" \
    --n "${N_RUNS}" \
    --seed-base "${SEED_BASE}" \
    --output "${OUTPUT_FILE}"
