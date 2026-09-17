# The project pins old dependency versions (cffi 1.15.1, PyYAML 6.0, ...) that
# only ship prebuilt wheels up to Python 3.10, so use python:3.10-slim to avoid
# needing a compiler toolchain at build time.
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first so rebuilds reuse the cached layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code. settings/ ships sample_config.yml only; the real
# config.yml is mounted from the host (see docker-compose.yml).
COPY monitor.py .
COPY broadlink_ac_mqtt/ broadlink_ac_mqtt/
COPY settings/ settings/
COPY LICENSE .

# Default: publish AC state to MQTT. Reads config from /app/settings/config.yml
# (default lookup) and writes logs to /app/log/out.log.
# Logging verbosity is controlled by the LOGLEVEL env var (default INFO);
# set LOGLEVEL=DEBUG in docker-compose.yml to match the old -d behaviour.
CMD ["python", "monitor.py"]