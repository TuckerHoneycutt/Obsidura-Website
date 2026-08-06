FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91

RUN apt-get update -qq && \
    apt-get install -y -qq docker.io curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir typer pyyaml

WORKDIR /app

RUN mkdir -p /output

ENV PYTHONPATH=/app
ENV CADDY_CONFIG_DIR=/output

ENTRYPOINT ["python", "-m", "dev_administration.cli"]
