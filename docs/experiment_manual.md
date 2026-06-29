# Manual del Experimento

## Diseño experimental

### Objetivo

Comparar Celery 5.3 y Ray 2.10 como frameworks de ejecución distribuida de tareas
en el contexto de un juez virtual para programación competitiva.

La variable independiente es el **número de workers** (1, 2, 4, 8, 16, 32).
Las variables dependientes son **throughput**, **latencia** y **consumo de potencia**.
El **workload** es idéntico para ambos frameworks (mismo seed aleatorio).

### Carga de trabajo sintética

Cada "envío" consiste en:
1. **Compilación**: latencia ~ Uniform(500ms, 2000ms) en modo simulado
2. **Evaluación**: 10 casos de prueba × Uniform(100ms, 500ms) cada uno

El `seed=42` garantiza que ambos frameworks procesen exactamente la misma
secuencia de latencias, haciendo la comparación controlada.

### Modo de ejecución

Se recomienda comenzar con `EXECUTION_MODE=simulated` para:
1. Medir el overhead puro del framework de despacho de tareas
2. Reproducir resultados sin dependencias externas (Docker sandbox)

El modo `docker` puede usarse para validar que las conclusiones se mantienen
con carga real de compilación y ejecución.

## Escenarios

### Escenario N° de workers

| N | Celery | Ray |
|---|---|---|
| 1 | `--scale celery-compile-worker=1 --scale celery-judge-worker=1` | `RAY_NUM_CPUS=1` |
| 2 | `--scale=2` (ambas colas) | `RAY_NUM_CPUS=2` |
| 4 | `--scale=4` | `RAY_NUM_CPUS=4` |
| 8 | `--scale=8` | `RAY_NUM_CPUS=8` |
| 16 | `--scale=16` | `RAY_NUM_CPUS=16` |
| 32 | `--scale=32` | `RAY_NUM_CPUS=32` |

### Volumen de carga

Se evalúan dos volúmenes:
- **Pequeño**: 100 envíos simultáneos
- **Grande**: 500 envíos simultáneos

## Ejecución paso a paso

### Paso 1: Iniciar infraestructura

```bash
cd Di-Judge-Backend/experiments/ray
docker compose -f docker-compose.yml up -d
sleep 10  # esperar que PostgreSQL esté listo
```

### Paso 2: Ejecutar escenario Celery individual

```bash
bash benchmarks/scenarios/run_celery_scenario.sh \
    celery-w4-s100 4 100 42 ./results
```

### Paso 3: Ejecutar escenario Ray individual

```bash
bash benchmarks/scenarios/run_ray_scenario.sh \
    ray-w4-s100 4 100 42 ./results
```

### Paso 4: Ejecutar la matriz completa

```bash
bash benchmarks/run_all.sh
```

Este script ejecuta 24 escenarios (2 frameworks × 6 configuraciones de workers
× 2 volúmenes de carga) en secuencia, con medición de potencia continua.

Tiempo estimado total:
- Modo simulado: ~4-6 horas
- Modo Docker: ~8-16 horas

## Recolección de métricas durante un benchmark

Para recolectar métricas de sistema manualmente durante un benchmark:

```bash
# Terminal 1: iniciar recolector
python benchmarks/collect_metrics.py \
    --run-id mi-experimento \
    --interval 1.0 \
    --output ./results/sys_metrics_mi-experimento.csv &
COLLECTOR_PID=$!

# Terminal 2: ejecutar el benchmark
bash benchmarks/scenarios/run_ray_scenario.sh ray-test 4 100 42 ./results

# Detener recolector
kill $COLLECTOR_PID
```

## Interpretación de resultados

### CSV principal (`results/results.csv`)

| Columna | Descripción |
|---|---|
| `run_id` | Identificador único del run |
| `framework` | `celery` o `ray` |
| `num_workers` | Número de workers configurados |
| `n_submissions` | Total de envíos procesados |
| `wall_time_s` | Tiempo de pared total (segundos) |
| `throughput_per_s` | Envíos procesados por segundo |
| `latency_p50_ms` | Mediana de latencia end-to-end |
| `latency_p90_ms` | Percentil 90 de latencia |
| `latency_p99_ms` | Percentil 99 de latencia |
| `latency_mean_ms` | Media de latencia |

### CSV de métricas de sistema (`results/sys_metrics_*.csv`)

| Columna | Descripción |
|---|---|
| `timestamp` | Timestamp de la muestra (perf_counter) |
| `run_id` | Identificador del run |
| `cpu_pct` | Utilización CPU total (%) |
| `mem_used_mb` | Memoria utilizada (MB) |
| `power_w` | Potencia estimada (W, vacío si RAPL no disponible) |

## Generación de figuras

```bash
python benchmarks/plot_results.py \
    --results-csv ./results/results.csv \
    --sys-csv "./results/sys_metrics_*.csv" \
    --output-dir ./results/figures
```

Genera 6 figuras PDF listas para incluir en el paper `ray.tex`.
