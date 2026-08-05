# The single container image — built for BOTH the agent run and the verifier (canonical
# TB2: there is no separate tests/Dockerfile). Install every system dependency / package
# the task needs here, plus the verifier's deps (pytest). Do NOT COPY solution/ or tests/
# into this image — Harbor overlays tests/ at /tests only at verify time, so ground truth
# stays out of the agent's reach.
FROM public.ecr.aws/docker/library/ubuntu:24.04@sha256:0d39fcc8335d6d74d5502f6df2d30119ff4790ebbb60b364818d5112d9e3e932

# build-essential is the toolchain the project itself needs. faketime and locales
# exist so that a rebuild can be performed under a different clock and a different
# collation — the agent needs them to check its own work, and the verifier uses
# them to check the agent's. pytest is the verifier's, baked at BUILD time and
# pinned so the verifier installs nothing when it runs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential faketime locales python3 python3-pip \
    && sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && pip install --no-cache-dir --break-system-packages \
        pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    && useradd --uid 1001 --create-home builder \
    && rm -rf /var/lib/apt/lists/*

# The project whose release bundle has to become reproducible. This is the only
# thing the agent is given; there is no answer key to hide, because correctness
# is a property of what the build produces rather than a stored result.
COPY project /app

WORKDIR /app
