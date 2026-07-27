FROM public.ecr.aws/docker/library/python@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

# The test runner is baked in so the verifier installs nothing at grade time.
# Both resolve to prebuilt wheels, so no compiler is needed. The task itself
# needs only the standard library.
RUN pip install --no-cache-dir \
        pytest==8.3.5 \
        pytest-json-ctrf==0.5.3

WORKDIR /app

# Only the calendars, the travel matrix and the requests are shipped into the
# agent image. The generator and the expected schedule are NOT here; the answer
# lives in tests/ and is overlaid only at verification time.
COPY data/people.json /app/data/people.json
COPY data/sites.json /app/data/sites.json
COPY data/requests.json /app/data/requests.json

CMD ["/bin/bash"]
