FROM public.ecr.aws/docker/library/python@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

# General-purpose numeric/algebra tooling the agent may reach for, plus the test
# runner baked in so the verifier installs nothing at grade time.
# All wheels are prebuilt (manylinux); no compiler/build deps required.
RUN pip install --no-cache-dir \
        numpy==2.2.4 \
        sympy==1.13.3 \
        galois==0.4.2 \
        pytest==8.3.5 \
        pytest-json-ctrf==0.5.3

WORKDIR /app

# Only the PUBLIC archive and the unsigned challenge records are shipped into the
# agent image. The tag routine itself and the correct challenge tags are NOT here;
# the expected tags live in tests/ and are overlaid only at verification time.
COPY data/samples.json /app/data/samples.json
COPY data/challenge.json /app/data/challenge.json

CMD ["/bin/bash"]
