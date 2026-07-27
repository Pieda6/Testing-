FROM public.ecr.aws/docker/library/python@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

# Numeric tooling the agent may reach for, plus the test runner baked in so the
# verifier installs nothing at grade time. All resolve to prebuilt cp313
# manylinux wheels, so no compiler is needed.
RUN pip install --no-cache-dir \
        numpy==2.2.4 \
        scipy==1.15.2 \
        pytest==8.3.5 \
        pytest-json-ctrf==0.5.3

WORKDIR /app

# Only the recovered archive and its partial catalogue are shipped into the
# agent image. The generator, the true sample formats and the canonical digests
# are NOT here; the expected answers live in tests/ and are overlaid only at
# verification time.
COPY data/manifest.json /app/data/manifest.json
COPY data/raw /app/data/raw

CMD ["/bin/bash"]
