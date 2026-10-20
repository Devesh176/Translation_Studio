FROM python:3.11-slim

WORKDIR /app

# Install system build dependencies, HarfBuzz, FreeType, and Google Noto fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    pkg-config \
    fonts-noto-core \
    fonts-noto-extra \
    fonts-noto-cjk \
    fonts-noto-hinted \
    fonts-indic \
    fonts-deva \
    fontconfig \
    libharfbuzz-dev \
    libfreetype6-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*


# Layer-cached dependency installation
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Install project package
RUN pip install --no-cache-dir -e .

CMD ["celery", "-A", "apps.worker.worker_config.celery_app", "worker", "--loglevel=info"]
