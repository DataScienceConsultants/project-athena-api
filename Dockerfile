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
RUN python -m pip install --no-cache-dir . \
    && python -c "from pathlib import Path; import shutil; import src; target = Path(src.__file__).resolve().parent.parent / 'config'; target.mkdir(exist_ok=True); shutil.copyfile('config/regions.json', target / 'regions.json')"

EXPOSE 8000

CMD ["sh", "-c", "python -m app.bootstrap_catalog && exec python -m app"]
