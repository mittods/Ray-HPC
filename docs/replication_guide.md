# Guía de Replicación

Esta guía permite a otro investigador reproducir exactamente todos los
resultados reportados en el paper `hpc/ray.tex` a partir de los artefactos
de este repositorio.

## Hardware objetivo

| Componente | Especificación |
|---|---|
| CPU | AMD Ryzen Threadripper PRO 5975WX |
| Núcleos físicos | 32 (64 hilos lógicos) |
| RAM | 128 GB DDR4 3200 MHz |
| Almacenamiento | SSD 2 TB |
| OS | Linux (kernel ≥ 5.13) |

> **Nota**: Los experimentos pueden ejecutarse en hardware diferente.
> Los valores absolutos de throughput y latencia cambiarán, pero las
> tendencias comparativas (Celery vs Ray, speedup vs workers) deben
> mantenerse cualitativamente similares.

## Pasos de replicación

### 1. Preparación del entorno (≈10 min)

```bash
# Clonar el repositorio
git clone <URL_REPO> Di-Judge-Backend
cd Di-Judge-Backend/experiments/ray

# Configurar entorno
cp .env.example .env

# Construir imágenes Docker
docker compose -f docker-compose.yml -f docker-compose.celery.yml build
docker compose -f docker-compose.yml -f docker-compose.ray.yml build
```

### 2. Verificar RAPL (medición de potencia)

```bash
# Debe retornar un entero positivo (µJ)
cat /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj
```

Si RAPL no está disponible, la columna `power_w` en los CSVs aparecerá
vacía. El resto de métricas no se ve afectado.

### 3. Iniciar infraestructura base

```bash
docker compose -f docker-compose.yml up -d
# Esperar ~15 segundos para que PostgreSQL esté listo
docker compose -f docker-compose.yml ps
```

### 4. Ejecutar la matriz completa

```bash
export RESULTS_DIR=./results
export WORKERS_LIST="1 2 4 8 16 32"
export SUBMISSIONS_LIST="100 500"
bash benchmarks/run_all.sh 2>&1 | tee results/experiment_log.txt
```

El script ejecuta 24 escenarios en secuencia, recoge métricas de sistema
por cada uno, y genera las figuras al final.

### 5. Verificar resultados

```bash
# Debe haber 24 filas (12 Celery + 12 Ray)
wc -l results/results.csv

# Ver primeras filas
head -5 results/results.csv

# Verificar que las figuras se generaron
ls results/figures/
```

### 6. Insertar resultados en el paper

Los archivos PDF generados en `results/figures/` deben copiarse a
`hpc/benchmarks/figures/` para ser incluidos por el paper:

```bash
mkdir -p ../../hpc/benchmarks/figures
cp results/figures/*.pdf ../../hpc/benchmarks/figures/
```

Luego actualizar las macros `\PH` en `hpc/ray.tex` con los valores
numéricos del archivo `results/results.csv`.

### 7. Reproducibilidad de cada figura

| Figura en el paper | Archivo generado | Datos requeridos |
|---|---|---|
| Throughput vs workers | `01_throughput_vs_workers.pdf` | `results.csv` completo |
| Latencia P50/P90/P99 | `02_latency_p50_p90_p99.pdf` | `results.csv` completo |
| Speedup vs workers | `03_speedup_vs_workers.pdf` | `results.csv` + runs con 1 worker |
| Eficiencia paralela | `04_parallel_efficiency.pdf` | `results.csv` + runs con 1 worker |
| Consumo de potencia | `06_power_consumption.pdf` | `sys_metrics_*.csv` + RAPL disponible |

### 8. Diferencias esperadas entre replicas

Los resultados pueden diferir del paper en:
- ±5-15% en throughput absoluto (variación de carga del sistema)
- ±10% en latencias absolutas
- Las tendencias relativas (speedup, eficiencia) deben ser consistentes

Si se usa hardware diferente:
- Escalar 1 worker en hardware diferente como referencia
- Calcular speedup siempre relativo a la medición de 1 worker propia

## Semilla aleatoria

Todos los experimentos usan `--seed 42`. Cambiar la semilla cambia el
orden y las latencias de la carga de trabajo, pero no debe cambiar las
conclusiones sobre throughput comparativo.

## Tiempo estimado total

| Configuración | Tiempo estimado |
|---|---|
| Modo simulado, hardware objetivo | 4–6 horas |
| Modo Docker, hardware objetivo | 8–16 horas |
| Modo simulado, laptop de desarrollo | 8–12 horas |
