FROM public.ecr.aws/docker/library/python@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

# Lattice-reduction and ECDSA tooling available to the agent, plus the test
# runner baked in so the verifier installs nothing at grade time.
# All wheels are prebuilt (manylinux); no compiler/build deps required.
RUN pip install --no-cache-dir \
        fpylll==0.6.4 \
        cysignals==1.12.6 \
        ecdsa==0.19.1 \
        pytest==8.3.5 \
        pytest-json-ctrf==0.5.3

WORKDIR /app

# Only the PUBLIC challenge corpus is shipped into the agent image.
# The private key, the nonce prefix, and the generator/seed are NOT here.
COPY data/signatures.json /app/data/signatures.json

CMD ["/bin/bash"]
