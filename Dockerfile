# Dockerfile for Paper 1 v4 N=500 benchmark on Azure Container Instances.
# Each ACI task runs one (scenario, network, agent_type) cell via the
# entrypoint script, which reads the cell description from env vars.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /maz3

# Install deps first so source-only edits don't bust the layer cache.
COPY requirements.txt /maz3/requirements.txt
RUN pip install -r /maz3/requirements.txt

# Copy the rest of the repo. .dockerignore keeps .git, results/, caches out.
COPY . /maz3

RUN chmod +x /maz3/scripts/docker_entrypoint.sh

ENTRYPOINT ["/maz3/scripts/docker_entrypoint.sh"]
