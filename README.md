# Di-Judge Ray Experiment

Entorno experimental autocontenido para comparar **Celery** (línea base) contra
**Ray** como framework de ejecución distribuida en el contexto de un juez virtual
para programación competitiva.

## Estructura del directorio

```
experiments/ray/
├── common/              Código compartido (executor, modelos, workload)
├── celery_impl/         Implementación Celery (línea base)
├── ray_impl/            Implementación Ray (experimental)
├── benchmarks/          Scripts de benchmark y medición
│   ├── power/           Medición de consumo energético (RAPL)
│   └── scenarios/       Scripts por escenario de workers
├── results/             Resultados generados (CSV, JSON, figuras)
├── init/                Inicialización de la BD
├── docs/                Manuales detallados
├── docker-compose.yml           Infraestructura base (PostgreSQL, Redis)
├── docker-compose.celery.yml    Overlay Celery
└── docker-compose.ray.yml       Overlay Ray
```

## Inicio rápido

### 1. Requisitos

- Docker Engine ≥ 24.0
- Docker Compose v2
- (Opcional) `perf` para medición de potencia

### 2. Configurar entorno

```bash
cd Di-Judge-Backend/experiments/ray
cp .env.example .env
# Ajustar EXECUTION_MODE si se desea usar Docker real
```

### 3. Construir imágenes

```bash
docker compose -f docker-compose.yml -f docker-compose.celery.yml build
docker compose -f docker-compose.yml -f docker-compose.ray.yml build
```

### 4. Iniciar infraestructura base

```bash
docker compose -f docker-compose.yml up -d
```

### 5. Ejecutar un escenario individual (Celery, 4 workers, 100 envíos)

```bash
bash benchmarks/scenarios/run_celery_scenario.sh \
    celery-4w-100s 4 100 42 ./results
```

### 6. Ejecutar un escenario individual (Ray, 4 workers, 100 envíos)

```bash
bash benchmarks/scenarios/run_ray_scenario.sh \
    ray-4w-100s 4 100 42 ./results
```

### 7. Ejecutar la matriz completa

```bash
export RESULTS_DIR=./results
bash benchmarks/run_all.sh
```

### 8. Generar figuras

```bash
python benchmarks/plot_results.py \
    --results-csv ./results/results.csv \
    --output-dir ./results/figures
```

### 9. Apagado y limpieza

```bash
docker compose -f docker-compose.yml -f docker-compose.celery.yml down
docker compose -f docker-compose.yml -f docker-compose.ray.yml down
docker volume rm exp-postgres-data exp-results exp-artifacts
```

## Modos de ejecución

| `EXECUTION_MODE` | Descripción |
|---|---|
| `simulated` | `time.sleep()` simula latencias de compilación/ejecución. No requiere Docker sandbox. Mide overhead puro del framework. |
| `docker` | Usa la imagen `dijudge-sandbox` real. Requiere Docker socket montado. Mide el sistema completo. |

## Escalabilidad

| Escenario | Workers Celery | CPU slots Ray |
|---|---|---|
| 1 worker | `--scale=1` | `RAY_NUM_CPUS=1` |
| 2 workers | `--scale=2` | `RAY_NUM_CPUS=2` |
| 4 workers | `--scale=4` | `RAY_NUM_CPUS=4` |
| 8 workers | `--scale=8` | `RAY_NUM_CPUS=8` |
| 16 workers | `--scale=16` | `RAY_NUM_CPUS=16` |
| 32 workers | `--scale=32` | `RAY_NUM_CPUS=32` |

## Métricas recolectadas

- **Throughput** (envíos/segundo)
- **Latencia** P50 / P90 / P99 (ms)
- **Speedup** relativo a 1 worker
- **Eficiencia paralela** (speedup / workers)
- **CPU %** (via `/proc/stat`)
- **Memoria** (via `/proc/meminfo`)
- **Potencia** (via RAPL sysfs o `perf stat`)

Ver `docs/experiment_manual.md` para instrucciones detalladas.
