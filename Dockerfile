FROM python:3.11-slim

ARG SUPERCRONIC_VERSION=0.2.33
ARG TARGETARCH=amd64

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gosu \
 && curl -fsSLo /usr/local/bin/supercronic \
    "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" \
 && chmod +x /usr/local/bin/supercronic \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd -r -g 1000 appgroup \
 && useradd -r -u 1000 -g appgroup -d /app appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Stash static public files so the entrypoint can seed the mounted volume
RUN cp -r public /app/_static \
 && chmod +x /app/docker/entrypoint.sh \
 && chmod 0644 /app/docker/crontab \
 && chown -R appuser:appgroup /app

EXPOSE 8080

# Entrypoint runs as root for volume init, then drops to appuser via gosu
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -fs http://localhost:8080/ || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
