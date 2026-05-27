FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends cron \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Stash static public files so the entrypoint can seed the mounted volume
RUN cp -r public /app/_static \
 && chmod +x /app/docker/entrypoint.sh \
 && chmod 0644 /app/docker/crontab \
 && crontab /app/docker/crontab

EXPOSE 8080

ENTRYPOINT ["/app/docker/entrypoint.sh"]
