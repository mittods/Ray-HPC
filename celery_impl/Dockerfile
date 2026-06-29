FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /experiment

# Install common + celery deps
COPY celery_impl/requirements.txt /experiment/celery_impl/requirements.txt
RUN pip install --no-cache-dir -r celery_impl/requirements.txt

# Copy source tree
COPY common/ /experiment/common/
COPY celery_impl/ /experiment/celery_impl/

ENV PYTHONPATH=/experiment
ENV PYTHONUNBUFFERED=1

# Default command – overridden per-service in docker-compose
CMD ["celery", "-A", "celery_impl.celery_app", "worker", "--loglevel=info"]
