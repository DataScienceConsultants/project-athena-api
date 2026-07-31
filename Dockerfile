FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY config ./config
COPY data ./data

RUN python -m pip install --no-cache-dir . \
    && python - <<'PY'
from pathlib import Path
import shutil
import src

# Athena 0.4.1's wheel does not include its regions.json package data. Install
# this API's matching deployment configuration where Athena's public builder
# resolves it until the upstream package includes that file.
target = Path(src.__file__).resolve().parent.parent / "config"
target.mkdir(exist_ok=True)
shutil.copyfile("config/regions.json", target / "regions.json")
PY

EXPOSE 8000
CMD ["python", "-m", "app"]
