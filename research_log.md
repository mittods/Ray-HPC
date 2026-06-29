# Research Log — Ray vs Celery en Di-Judge

**Proyecto**: Di-Judge HPC — Evaluación experimental de Ray  
**Investigador**: Martín Vicente Maza Delgado  
**Curso**: INFO335 HPC — Universidad Austral de Chile  
**Fecha de inicio**: 2026-06-28  

---

## Propósito de este documento

Este log documenta el proceso de diseño del entorno experimental, incluyendo
cada decisión técnica relevante, las alternativas consideradas, y la justificación
de la opción elegida. El objetivo es que otro investigador pueda reconstruir
el razonamiento completo sin haber estado presente durante el diseño.

No es un resumen de lo que se implementó. Es una explicación de **por qué** se
implementó de esa manera.

---

## 1. Análisis del backend existente

### 1.1 Módulos evaluados

Se analizó la totalidad del backend en `Di-Judge-Backend/src/`. Los módulos
relevantes para el experimento son:

| Módulo | Relevancia |
|---|---|
| `worker/celery_app.py` | Configuración del broker Celery/Redis |
| `worker/compile_worker/tasks.py` | Tarea de compilación |
| `worker/judge_worker/tasks.py` | Tarea de evaluación |
| `worker/executor.py` | `DockerSandboxRunner` — ejecución real |
| `worker/runtime.py` | Gestión de artefactos en disco |
| `worker/fair_scheduler.py` | Scheduler de equidad por usuario |
| `app/services/testcase_cache.py` | Cache en memoria de casos de prueba |
| `app/models/models.py` | Esquema de base de datos |
| `app/config.py` | Settings |

**Módulos descartados** (no relevantes para el benchmark de ejecución distribuida):

| Módulo | Razón del descarte |
|---|---|
| `routers/` (toda la capa HTTP) | El benchmark no usa la API REST |
| `services/auth_service.py` | Sin autenticación en el experimento |
| `services/contest_service.py` | Sin concursos |
| `services/leaderboard_service.py` | Sin rankings |
| `worker/maintenance_worker/` | Sin mantenimiento periódico |
| `worker/rejudge_worker.py` | Sin re-evaluaciones |
| `app/services/submission_priority.py` | Sin prioridades variables |
| Discord bot, monitoring stack | Fuera del scope |

### 1.2 Flujo crítico identificado

El flujo mínimo para evaluar una sumisión es:

```
1. Crear registro en BD (status=queued)
2. Compilar código → artefacto en disco (status=compiled)
3. Ejecutar artefacto contra N casos de prueba (status=running)
4. Persistir veredicto y métricas (status=done)
```

Este flujo tiene dos etapas de cómputo distribuible: compilación y evaluación.
En Celery, estas son dos tareas en dos colas separadas (`compile` → `judge`).
En Ray, son dos funciones remotas encadenadas vía ObjectRef.

### 1.3 El fair scheduler: decisión de omisión

**Problema**: el `fair_scheduler.py` usa Redis para garantizar que ningún usuario
monopolice los workers. Depende de `redis.Redis` con `set(key, '1', nx=True, ex=120)`.

**Alternativas**:
1. Incluirlo en el experimento → pero añade latencia de Redis en ambas implementaciones
2. Omitirlo → carga homogénea, sin contención entre usuarios

**Decisión**: Omitido. El objetivo del experimento es medir el overhead del
framework de tareas distribuidas, no el fair scheduler. Bajo carga homogénea
(todos los usuarios tienen igual prioridad), el scheduler no impacta el resultado.
Si se incluye, añade un RTT de Redis (~0.1ms) por tarea, que afecta ambas
implementaciones por igual — pero distorsiona la comparación porque Ray no tiene
un equivalente natural.

**Riesgo**: Los resultados no incluyen el overhead real del scheduler. Esto debe
mencionarse explícitamente como limitación en el paper.

---

## 2. Decisión de arquitectura experimental

### 2.1 ¿Entorno acoplado o desacoplado?

**Problema**: ¿debe el experimento depender del backend de producción o ser completamente
independiente?

**Alternativas**:
1. Acoplar al backend → reutilizar modelos, config, etc.
2. Desacoplar completamente → copiar el código mínimo necesario

**Decisión**: Desacoplado. El experimento vive en `experiments/ray/` y no importa
ningún módulo de `src/`. Razones:
- El objetivo es NO contaminar el código de producción
- Las dependencias circulares complicarían el setup
- El aislamiento permite versionar el experimento independientemente
- Facilita la reproducibilidad en otra máquina sin la pila completa

**Costo**: algunos módulos se copian (executor.py, runtime.py). Si el productor
cambia, el experimento no lo refleja automáticamente. Esto es aceptable: el
experimento captura el sistema en un punto en el tiempo.

### 2.2 ¿Ejecución real con Docker o simulada?

**Problema**: el `DockerSandboxRunner` requiere Docker-in-Docker, lo que complica
el entorno de benchmark. Además, el overhead de Docker sandbox domina los tiempos
de ejecución (~100ms-2s por caso), haciendo difícil medir el overhead del framework
(~1-10ms).

**Alternativas**:
1. Ejecución real con Docker → mide el sistema completo pero es difícil de reproducir
2. Ejecución simulada (sleep) → mide el overhead del framework de forma aislada
3. Ejecución en subprocess (sin sandbox) → compromiso, pero introduce riesgos de seguridad

**Decisión**: Modo simulado por defecto, con soporte opcional para Docker real.
Justificación:
- La pregunta de investigación es "¿cómo se comparan los frameworks de distribución
  de tareas?", no "¿cuánto tarda la sandbox?"
- El modo simulado permite controlar exactamente las latencias de cómputo
- La misma seed garantiza que ambos frameworks procesen exactamente las mismas latencias
- El modo Docker está disponible para validación

**Riesgo**: los resultados del modo simulado no miden el throughput del sistema real.
Esto debe declararse explícitamente en la metodología del paper.

---

## 3. Implementación Ray

### 3.1 API usada: `@ray.remote` functions vs Actors

**Problema**: Ray ofrece dos primitivas: funciones remotas (`@ray.remote def`) y
actores (`@ray.remote class`). ¿Cuál usar para el pipeline compile → judge?

**Alternativas**:
1. **Funciones remotas**: `compile.remote()` y `judge.remote()` como tareas
   independientes encadenables. Sin estado compartido.
2. **Actores**: un `JudgeActor` con estado persistente por worker (útil para
   reutilizar conexiones DB, caches, etc.)

**Decisión**: Funciones remotas (`@ray.remote def`). Justificación:
- Es el patrón central de los ejemplos del curso (main00.py, main02.py, Factorizacion.py)
- La presentacion.txt dice explícitamente: "Ray transforma funciones normales de Python
  en tareas remotas" — esta es la abstracción que debemos evaluar
- El pipeline compile → judge es stateless (cada tarea lee de la BD y escribe al disco)
- Los actores añadirían complejidad de ciclo de vida sin beneficio claro para este caso
- La comparación con Celery es más directa: Celery tasks ↔ Ray remote functions

**Desviación de las alternativas de los ejemplos**: los ejemplos del curso trabajan
con datos numéricos (primos, factorización). El dominio del juez virtual implica
E/S (disco, BD), lo que cambia el perfil de rendimiento. Se mantiene el mismo
patrón `@ray.remote` pero el contenido de las funciones es E/S, no cómputo puro.

### 3.2 Encadenamiento de futures

**Problema**: el pipeline tiene dos etapas dependientes: compile → judge.
¿Cómo expresar esta dependencia en Ray?

**Alternativas**:
1. **Encadenamiento explícito en el driver**: `compile_ref = compile.remote(...)`,
   luego `judge.remote(ray.get(compile_ref), ...)`. Bloquea el driver entre etapas.
2. **Encadenamiento implícito**: `judge.remote(compile.remote(...))`. Ray pasa el
   ObjectRef como argumento y lo resuelve internamente.
3. **ray.wait() en el driver**: procesar compilaciones a medida que terminan,
   despachar juicios inmediatamente. No bloquea entre etapas.

**Decisión**: Opción 3 — `ray.wait()` en el driver. Este es exactamente el patrón
de `main02.py` y `Factorizacion.py` del curso:
```python
while pending_compile:
    ready, pending_compile = ray.wait(pending_compile, num_returns=1, timeout=60)
    for ref in ready:
        result = ray.get(ref)
        judge_ref = judge.remote(result, ...)
        judge_futures.append(judge_ref)
```

Ventajas:
- Implementa paralelismo de pipeline real: los juicios empiezan sin esperar a que
  terminen todas las compilaciones
- El código del driver es explícito y fácil de entender
- Coherente con el material del curso
- Permite monitorear el progreso (se puede imprimir avance después de cada `ray.wait`)

**Diferencia vs opción 2**: la opción 2 (encadenamiento implícito) daría el mismo
resultado pero el código sería menos legible y no aprovecharía el patrón `ray.wait()`
que queremos mostrar.

### 3.3 Control de paralelismo

**Problema**: en Celery la escalabilidad se controla con `--scale` y `--concurrency`.
¿Cómo controlar el número de workers paralelos en Ray?

**Alternativas**:
1. `ray.init(num_cpus=N)` — asigna N CPU slots al cluster
2. `@ray.remote(num_cpus=1)` — cada tarea pide 1 CPU; N slots → N paralelas
3. Variables de entorno (OMP_NUM_THREADS, etc.)

**Decisión**: Combinación de 1 y 2. Ray se inicializa con `num_cpus=N` (controlado
por `RAY_NUM_CPUS` env var), y cada tarea declara `@ray.remote(num_cpus=1)`. Esto
garantiza que exactamente N tareas corran en paralelo, haciéndolo comparable con
N workers de Celery.

La presentacion.txt menciona explícitamente:
```
@ray.remote(num_cpus=2)
def tarea_cpu():
    ...
```
Esta es la forma canónica de declarar requerimientos de recursos en Ray. Seguimos
el mismo patrón.

### 3.4 Inicialización de Ray

**Problema**: los ejemplos del curso tienen inicializaciones variadas:
- `ray.init()` — local mode automático
- `ray.init(_node_ip_address='172.16.115.137')` — cluster con IP explícita
- `ray.init(ignore_reinit_error=True)` — robusto ante re-inicializaciones

**Decisión**: Usar `ray.init(ignore_reinit_error=True, include_dashboard=False)` en
modo local. Para cluster, usar `ray.init(address=RAY_ADDRESS)`.

`ignore_reinit_error=True` aparece en Factorizacion.py y ray_demo_complete.py del
curso, lo que indica que es la forma canónica para código de investigación.
`include_dashboard=False` reduce el overhead en benchmarks.

---

## 4. Implementación Celery (baseline)

### 4.1 Configuración mínima

La implementación de Celery para el experimento omite:
- `task_queue_max_priority` / prioridades
- `broker_transport_options` (priority_steps)
- Métricas Prometheus
- Fair scheduler Redis

Mantenemos:
- `worker_prefetch_multiplier=1` — justo, toma una tarea a la vez
- `task_acks_late=True` — no pierde tareas si el worker muere
- `task_reject_on_worker_lost=True` — re-encola si el worker falla

Estas opciones están presentes en la producción y son importantes para la
semántica correcta. Sin `task_acks_late=True`, Celery puede perder tareas
bajo condiciones de fallo, lo que distorsionaría el benchmark.

### 4.2 Una cola vs dos colas

**Decisión**: Mantener dos colas (`exp-compile` y `exp-judge`), igual que en
producción. Esto permite escalar el pool de compiladores y el de jueces
independientemente.

**Alternativa descartada**: Cola única "exp-submissions" — perdería la capacidad
de escalar cada etapa independientemente y no sería representativo de la
arquitectura real.

### 4.3 Concurrencia por worker

`--concurrency=1` por contenedor + `--scale=N` para escalar a N workers.

Esto es más representativo que `--concurrency=N` en un solo contenedor porque:
1. Refleja cómo se desplegaría en producción real (un worker por proceso)
2. Evita el GIL compartido entre threads del mismo proceso
3. Hace la comparación con Ray directa: N contenedores Celery ↔ N CPU slots Ray

---

## 5. Base de datos del experimento

### 5.1 Esquema simplificado

Se creó un modelo `ExperimentSubmission` con campos de timing explícitos:
- `queued_at`, `compile_started_at`, `compile_finished_at`
- `judge_started_at`, `judge_finished_at`
- `queue_time_ms`, `compile_time_ms`, `judge_time_ms`, `total_time_ms`

**Razón**: los campos de timing calculados deben ser derivables de los timestamps.
En lugar de calcularlos solo al final, se persisten para facilitar la depuración.

### 5.2 PostgreSQL vs SQLite

**Decisión**: PostgreSQL. Misma BD que en producción, para que la sobrecarga de
escrituras a la BD sea comparable. SQLite sería más rápido pero no representaría
el comportamiento real del sistema.

**Nota**: la BD del experimento usa un esquema diferente (`dijudge_exp`) y corre
en el puerto 5433 para no interferir con la BD de producción.

---

## 6. Diseño del benchmark

### 6.1 Métricas seleccionadas

| Métrica | Justificación |
|---|---|
| Throughput (envíos/s) | Métrica principal de capacidad del sistema |
| Latencia P50/P90/P99 | Distribución de experiencia de usuario |
| Speedup vs 1 worker | Normaliza diferencias absolutas entre frameworks |
| Eficiencia paralela | Mide qué fracción del speedup ideal se alcanza |
| Utilización CPU % | Cuantifica saturación de recursos |
| Consumo de potencia (W) | Métrica de eficiencia energética |

Se descartaron:
- Latencia de red (no aplicable en setup single-node)
- Disk I/O (no relevante en modo simulado)
- Context switches (difícil de atribuir a un solo framework)

### 6.2 Semilla aleatoria fija

Ambas implementaciones usan `seed=42`. Esto garantiza que:
1. Los mismos `submission_id`s se generan en el mismo orden
2. Las latencias simuladas (compile_time_ms, judge_time_ms) son idénticas
3. La comparación es justa: ambos frameworks procesan exactamente la misma carga

### 6.3 Warm-up

**Problema**: Celery tiene overhead de inicialización de workers. Ray tiene overhead
de `ray.init()`. Ambos deberían estar "calientes" al inicio del benchmark.

**Decisión**: Esperar 8-10 segundos después de iniciar los workers antes de empezar
el benchmark. Esto es suficiente para que los workers de Celery estén registrados
en Redis y Ray haya completado su inicialización.

No se implementa un "warm-up run" separado para simplificar la implementación.
Si el overhead de inicio es significativo, aparecerá como latencia alta en los
primeros envíos — esto es información válida, no ruido a eliminar.

### 6.4 Escenarios de workers elegidos: 1, 2, 4, 8, 16, 32

Potencias de dos hasta 32 (la mitad de los cores del Threadripper PRO 5975WX).
No se llega a 64 workers por defecto porque en modo simulado (sin Docker),
el thread scheduler del sistema operativo puede introducir variabilidad alta
con 64 tareas simultáneas que solo hacen sleep.

El escenario de 64 workers puede activarse modificando `WORKERS_LIST` en `run_all.sh`.

---

## 7. Medición de potencia

### 7.1 Herramienta elegida: RAPL sysfs

**Alternativas consideradas**:
1. `perf stat -e power/energy-pkg/` — requiere root o paranoia level bajo
2. `powerstat` — herramienta de alto nivel, menos reproducible
3. `turbostat` — muy detallado, requiere root
4. RAPL sysfs (`/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj`) — sin privilegios especiales

**Decisión**: RAPL sysfs como método primario, `perf stat` como fallback.
Justificación:
- RAPL sysfs es el mismo contador que usan todas las herramientas
- No requiere root (permisos de lectura por defecto en muchas distros)
- La lectura es atómica y de bajo overhead (una syscall `read`)
- El contador se incrementa en µJ, lo que permite calcular potencia promedio
  con alta precisión durante intervalos ≥ 100ms

**Para AMD Threadripper PRO 5975WX (Zen 3)**:
El kernel Linux ≥ 5.13 expone RAPL en AMD mediante el mismo subsystem
`powercap`. El path es `/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj`
(el nombre "intel-rapl" es el nombre del subsystem, no indica que sea Intel).

### 7.2 Frecuencia de muestreo

**Decisión**: Muestrear cada 1 segundo (`--interval 1.0`).

Justificación:
- Las tareas tienen latencias de 0.5–20s en modo simulado
- 1s es suficientemente granular para capturar variaciones de carga
- Muestrear más rápido (< 0.1s) puede introducir overhead del collector

### 7.3 Integración con el benchmark

El power monitor corre en background durante cada benchmark. Su PID se guarda
en un archivo para permitir terminación limpia. Ver `benchmarks/power/power_monitor.sh`.

---

## 8. Infraestructura Docker

### 8.1 Decisión: tres docker-compose files

Se usan tres archivos compose:
- `docker-compose.yml` — infraestructura base (postgres, redis)
- `docker-compose.celery.yml` — workers Celery
- `docker-compose.ray.yml` — head node Ray

**Razón**: permite combinar los archivos con `-f` para diferentes configuraciones,
y escalar solo los servicios del framework activo. Alternativas:
- Un solo archivo con profiles → más complejo, menos claro
- Archivos separados por escenario → demasiada duplicación

### 8.2 Shared memory para Ray

Ray usa shared memory (plasma store) para el object store. Se configura
`shm_size: '4gb'` en el contenedor ray-head. Sin esto, Ray falla con objetos
grandes o muchos objetos concurrentes.

### 8.3 Imagen compartida para bench y ray-head

El container `bench` (driver del benchmark) usa la misma imagen que `ray-head`
(`ray_impl/Dockerfile`). Esto simplifica el build y garantiza que el driver
tiene las mismas dependencias que los workers.

El comando del `bench` container se sobreescribe en `docker compose run`:
```bash
docker compose ... run --rm bench python benchmarks/run_ray_bench.py ...
```

---

## 9. Workload sintético

### 9.1 Elección del workload

Se crearon 5 programas C++ sintéticos:
1. Suma de dos enteros (SumAB)
2. Factorial (Factorial)
3. Fibonacci (Fibonacci)
4. Invertir string (Reverse)
5. Contar primos hasta N (CountPrimes)

**Razón**: estos programas son representativos de la dificultad fácil/media de
un juez virtual competitivo. No requieren librerías externas y son correctamente
deterministas (mismo input → mismo output).

### 9.2 Generación determinista de casos de prueba

Los casos de prueba se generan con `random.Random(seed)` para cada problema.
La seed combina el problem_id y un salt string para garantizar que:
- Los casos de prueba de cada problema son reproducibles
- Los casos de problemas distintos son estadísticamente independientes

### 9.3 Latencias simuladas fijas por submission_id

La latencia simulada de cada submission se deriva del `submission_id` usando
`random.Random(hash((submission_id, salt)) & 0xFFFF_FFFF)`. Esto garantiza
que el mismo `submission_id` siempre produce la misma latencia, independientemente
del framework o el orden de procesamiento.

---

## 10. Limitaciones del diseño

1. **Modo simulado no mide I/O real**: el overhead de Docker sandbox (~100ms de
   startup) no está incluido. Esto subestima la latencia absoluta del sistema real.

2. **Fair scheduler omitido**: bajo carga heterogénea (usuarios con prioridades
   distintas), Celery puede comportarse diferente al agregar el scheduler.

3. **Configuración single-node para Ray**: Ray puede correr en múltiples máquinas.
   Este experimento usa un solo nodo. El overhead de Ray en multi-nodo (serialización,
   red) no se mide.

4. **Sin warmup explícito**: el overhead de inicialización incluye los primeros
   envíos. Esto puede inflar ligeramente la latencia P99 en cargas pequeñas.

5. **PostgreSQL compartida**: ambas implementaciones usan la misma BD. Bajo alta
   concurrencia, la BD puede convertirse en un cuello de botella común.

---

## 11. Preguntas abiertas para el experimentador

1. ¿Es el throughput de Ray superior al de Celery para 1 worker? (sin overhead de broker)
2. ¿A qué número de workers converge el speedup de ambos frameworks?
3. ¿Ray tiene menor overhead de despacho por tarea que Celery?
4. ¿El consumo de potencia de Ray es proporcional al de Celery a igual workload?
5. ¿La eficiencia paralela cae de igual forma en ambos frameworks al aumentar workers?

Estas preguntas deben responderse con los datos del experimento. **No asumir
que Ray es mejor**: puede que Celery sea más eficiente para este workload
específico (tareas con alta E/S y corta duración).

---

## 12. Consideraciones futuras (fuera del scope actual)

- Evaluación en modo multi-nodo (2+ máquinas) para medir el overhead de red de Ray
- Comparación con otros frameworks: Dask, Dramatiq, ARQ
- Medición con cargas heterogéneas (mezcla de tareas rápidas y lentas)
- Análisis del object store de Ray (cuánto overhead añade para objetos grandes)
- Integración con Ray Serve para comparar con un API Gateway Ray-native
