FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /experiment

COPY ray_impl/requirements.txt /experiment/ray_impl/requirements.txt
COPY celery_impl/requirements.txt /experiment/celery_impl/requirements.txt
RUN pip install --no-cache-dir \
    -r ray_impl/requirements.txt \
    -r celery_impl/requirements.txt

COPY common/ /experiment/common/
COPY ray_impl/ /experiment/ray_impl/
COPY celery_impl/ /experiment/celery_impl/
COPY benchmarks/ /experiment/benchmarks/

ENV PYTHONPATH=/experiment
ENV PYTHONUNBUFFERED=1

# Default: start the Ray worker daemon.
# Overridden to 'python ray_impl/ray_driver.py' for the driver container.
CMD ["ray", "start", "--head", "--num-cpus=1", "--block"]
