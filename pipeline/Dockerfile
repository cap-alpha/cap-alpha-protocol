FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pipeline/requirements.txt pipeline/requirements.txt
RUN pip install --no-cache-dir -r pipeline/requirements.txt

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_BIN=/usr/bin/chromium-driver
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/pipeline

COPY pipeline/ pipeline/
COPY scripts/ scripts/

CMD ["tail", "-f", "/dev/null"]
