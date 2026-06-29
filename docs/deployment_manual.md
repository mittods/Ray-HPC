# Manual de Despliegue

## Requisitos de hardware

| Componente | Mínimo recomendado | Configuración objetivo |
|---|---|---|
| CPU | 8 núcleos físicos | AMD Ryzen Threadripper PRO 5975WX (32 cores / 64 threads) |
| RAM | 16 GB | 128 GB DDR4 3200 MHz |
| Disco | 20 GB libres | SSD 2 TB |
| OS | Linux (kernel ≥ 5.13) | Arch Linux 7.0.9-arch2-1 |

## Requisitos de software

```bash
# Docker Engine
docker --version        # ≥ 24.0
docker compose version  # v2.x

# Python (solo para ejecución directa, sin Docker)
python --version        # ≥ 3.11

# Opcional: medición de potencia
perf --version
ls /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj
```

## Instalación de Docker (Arch Linux)

```bash
sudo pacman -Sy docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Cerrar sesión y volver a entrar
```

## Clonar y configurar el experimento

```bash
cd Di-Judge-Backend/experiments/ray
cp .env.example .env
```

Editar `.env` con los valores apropiados.  El parámetro más importante:

```bash
# Para medir overhead del framework (sin Docker):
EXECUTION_MODE=simulated

# Para medir el sistema completo (requiere Docker socket):
EXECUTION_MODE=docker
```

## Construir las imágenes

```bash
# Construir todas las imágenes del experimento
docker compose -f docker-compose.yml -f docker-compose.celery.yml build
docker compose -f docker-compose.yml -f docker-compose.ray.yml build
```

Esto genera tres imágenes:
- `exp-bench:latest` — driver de benchmarks
- `exp-celery:latest` — workers Celery
- `exp-ray:latest` — head node / workers Ray

## Iniciar la infraestructura base

```bash
docker compose -f docker-compose.yml up -d
```

Verifica que los servicios estén saludables:

```bash
docker compose -f docker-compose.yml ps
# exp-postgres: healthy
# exp-redis:    healthy
```

## Verificar acceso a RAPL

```bash
# Si el archivo existe y es legible, RAPL está disponible
cat /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj

# Si no está disponible, activar en el kernel:
sudo modprobe intel_rapl_common
# O ajustar permisos:
sudo chmod o+r /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj
```

## Estructura de volúmenes

| Volumen Docker | Propósito |
|---|---|
| `exp-postgres-data` | Datos PostgreSQL |
| `exp-results` | CSVs, JSONs, figuras generadas |
| `exp-artifacts` | Artefactos compilados (compartido entre workers) |

## Limpieza completa

```bash
# Detener y eliminar todos los contenedores del experimento
docker compose -f docker-compose.yml down -v

# Eliminar imágenes construidas
docker rmi exp-bench:latest exp-celery:latest exp-ray:latest 2>/dev/null || true

# Eliminar resultados (IRREVERSIBLE)
# rm -rf ./results/*
```
