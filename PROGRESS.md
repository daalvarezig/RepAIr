# RepAIr — Progreso de desarrollo

> Planificador de capacidad inteligente para taller de motos

---

## Estado general: 🟢 FASE 1 + BOT TELEGRAM COMPLETADOS (con mejoras)

**Última actualización:** 2026-04-09

---

## Fases

| Fase | Descripción | Estado |
|------|-------------|--------|
| 0 | Infraestructura y modelo SQL | ✅ Completo |
| 1 | Motor de reglas (FastAPI) | ✅ Completo |
| 2 | Bot Telegram (clientes + owner) | ✅ Completo |
| 3 | Vista diaria por mecánico (frontend) | ⬜ Pendiente |
| 4 | V2 features (esperas, piezas, WhatsApp) | ⬜ Pendiente |
| 5 | V3 / SaaS / KPIs | ⬜ Pendiente |

---

## Decisiones tomadas

| Decisión | Valor |
|----------|-------|
| Stack backend | Python 3.12 + FastAPI + SQLite |
| Ubicación | `/opt/itopy.ai/apps/RepAIr/` |
| DB path | `/opt/itopy.ai/data/repair/repair.db` |
| Puerto API | 8010 |
| Subdominio | repair.itopy.ai (pendiente nginx) |
| Duración rápida | 60 min (45 base + 15 buffer) |
| Duración standard | 120 min (90 base + 30 buffer) |
| Duración compleja | 300 min (240 base + 60 buffer) — CRUZA COMIDA |
| Capacidad diaria | 3 mecánicos × 8h = 1440 min, reservable 85% = 1224 min |
| Horario | 10:00–14:00 y 15:00–19:00 |
| Máx. complejas/día | 2 |

### Decisión técnica importante: calendar_end vs duration
Una compleja de 300 min empieza a las 10:00 y termina a las **16:00** (no 15:00).
El sistema trabaja en "minutos de trabajo" y convierte a tiempo de calendario
sumando la pausa de comida si el trabajo la atraviesa.
- `calendar_end(600, 300)` → 960 (16:00) ✓

---

## Estructura del proyecto

```
/opt/itopy.ai/apps/RepAIr/
├── PROGRESS.md
├── api/
│   ├── main.py                  ← FastAPI app, startup, CORS
│   ├── requirements.txt
│   ├── .env                     ← DATABASE_PATH
│   ├── repair.service           ← systemd unit API (puerto 8010)
│   ├── db/
│   │   ├── database.py          ← get_connection(), init_db()
│   │   └── schema.sql           ← DDL completo con datos iniciales
│   ├── engine/
│   │   ├── rules.py             ← can_accept_job, JobSnapshot
│   │   ├── planner.py           ← plan_day, calendar_end, score_slot
│   │   └── reoptimizer.py       ← reoptimize_day, handle_job_delay
│   ├── routers/
│   │   ├── jobs.py              ← CRUD + status transitions + delay
│   │   ├── plan.py              ← can-accept, day, reoptimize, delay
│   │   ├── mechanics.py         ← CRUD mecánicos
│   │   └── customers.py         ← GET/POST /customers/ (filtro por phone)
│   └── schemas/
│       └── models.py            ← Pydantic schemas
└── bot/
    ├── main.py                  ← ApplicationBuilder, handlers registrados
    ├── requirements.txt         ← python-telegram-bot, httpx, python-dotenv
    ├── .env                     ← TELEGRAM_TOKEN, OWNER_ID, API_BASE
    ├── repair_bot.service       ← systemd unit bot
    ├── handlers/
    │   ├── common.py            ← /start, /help
    │   ├── owner.py             ← /plan, /citas, /reoptimizar (solo owner)
    │   └── client.py            ← /disponibilidad, /reservar (ConversationHandler)
    └── utils/
        └── api.py               ← Cliente HTTP → API RepAIr
```

---

## Endpoints disponibles (Puerto 8010)

### Jobs
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/jobs/?workshop_id=1&scheduled_date=YYYY-MM-DD` | Listar trabajos del día |
| POST | `/jobs/` | Crear trabajo |
| GET | `/jobs/{id}` | Obtener trabajo |
| PATCH | `/jobs/{id}/status?new_status=confirmed` | Cambiar estado |
| PATCH | `/jobs/{id}/delay` | Registrar alargue |

### Plan
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/plan/can-accept` | ¿Cabe este trabajo en este día? |
| POST | `/plan/day?workshop_id=1&plan_date=YYYY-MM-DD` | Generar plan del día |
| POST | `/plan/reoptimize?workshop_id=1&plan_date=YYYY-MM-DD&trigger=apertura` | Reoptimizar (apertura o intraday) |
| POST | `/plan/delay?workshop_id=1&plan_date=...&delayed_job_id=1&extra_minutes=30&now_min=700` | Aplicar delay + replanificar |
| GET | `/plan/day?workshop_id=1&plan_date=YYYY-MM-DD` | Ver plan activo del día |

### Mechanics
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/mechanics/?workshop_id=1` | Listar mecánicos |
| POST | `/mechanics/` | Crear mecánico |
| PATCH | `/mechanics/{id}/toggle` | Activar/desactivar mecánico |

### Customers
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/customers/?workshop_id=1&phone=XXX` | Buscar cliente por teléfono |
| POST | `/customers/` | Crear cliente |
| GET | `/customers/{id}` | Detalle cliente |

---

## Tablas SQL

| Tabla | Descripción |
|-------|-------------|
| `workshops` | Config del taller (horario, ratios, máx complejas) |
| `mechanics` | Mecánicos (activo/inactivo) |
| `repair_types` | Tipos con duración configurable por taller |
| `customers` | Clientes |
| `vehicles` | Vehículos (principalmente motos) |
| `jobs` | Trabajos/reservas con ciclo de vida completo |
| `daily_plans` | Snapshot de cada planificación |
| `plan_blocks` | Asignación job→mecánico→hora |
| `job_status_history` | Auditoría de cambios de estado |
| `job_delays` | Historial de alargues intradiarios |

### Ciclo de vida de un job
```
pending → confirmed → in_progress → done
                    ↘ waiting_parts → in_progress
         ↘ cancelled
         ↘ no_show
unschedulable → pending (revisión manual)
```

---

## Algoritmo — resumen

### Orden de planificación
1. Complejas (empiezan a las 10:00, primera ola)
2. Standard (distribuidas por score)
3. Rápidas (rellenan huecos)

### Score de asignación
- `+100` compleja arranca ≤ 10:30
- `-80`  compleja arranca > 10:30
- `+20`  rápida rellena hueco
- `-0.05 × carga_mecanico` penalizar sobrecarga
- `-30`  trabajo termina > 18:00
- `+10`  mecánico menos cargado (equilibrio)

### Reoptimización
- **Apertura (10:00):** solo planifica `confirmed`/`pending` presentes
- **Intraday:** extiende el bloque afectado, saca los no-iniciados bloqueados, replanifica

---

## Log de avance

### 2026-04-09 — Fase 1 completada
- [x] Exploración de infraestructura
- [x] Nombre: RepAIr, subdominio: repair.itopy.ai
- [x] Modelo SQL (10 tablas, constraints, datos iniciales)
- [x] Motor de reglas (`rules.py`)
- [x] Planificador con `calendar_end` para cruzar comida correctamente
- [x] Reoptimizador (apertura + intraday delay)
- [x] Todos los endpoints FastAPI
- [x] API testeada: health ✓, can-accept ✓, crear jobs ✓, plan/day ✓
- [x] systemd unit generado (`repair.service`)
- [x] Bug fix: `overlaps_lunch` → `calendar_end` (compleja 10:00–16:00, no 15:00)
- [x] Bug fix: INSERT jobs 13→14 values

### 2026-04-09 — Bot Telegram completado
- [x] `bot/utils/api.py` — cliente HTTP wrapping todos los endpoints de la API
- [x] `bot/handlers/common.py` — /start y /help (msg diferente owner vs cliente)
- [x] `bot/handlers/owner.py` — /plan (timeline por mecánico), /citas, /reoptimizar
- [x] `bot/handlers/client.py` — /disponibilidad (7 días) y /reservar (ConversationHandler 5 estados)
- [x] `api/routers/customers.py` — GET+POST /customers/ para lookup por teléfono
- [x] `repair_bot.service` instalado y activo (systemd)
- [x] Bug fix: `repair.service` WorkingDirectory → raíz del proyecto (`uvicorn api.main:app`)
- [x] Push a GitHub (daalvarezig/RepAIr)

### 2026-04-09 — Mejoras bot
- [x] Notificación al owner (OWNER_ID) en cada nueva reserva confirmada
- [x] `/estado <id>` — consulta estado de cualquier cita por número
- [x] `/start` y `/help` actualizados con el nuevo comando
- [x] `get_job()` añadido a `utils/api.py`

---

## Próximos pasos (Fase 3)

### Servicios en producción
- `repair.service` → API en http://127.0.0.1:8010 ✅
- `repair_bot.service` → Bot Telegram activo ✅
- nginx → repair.itopy.ai → 127.0.0.1:8010 ✅

### Fase 3: Vista diaria (frontend)
- `/opt/itopy.ai/apps/RepAIr/frontend/` — HTML/JS servido por nginx
- Timeline tipo Gantt por mecánico (10:00–19:00)
- Botón "Reoptimizar día" → POST /plan/reoptimize
- Indicadores: % ocupación, nº complejas, huecos muertos
- Lista de citas del día con estados y emojis

### Mejoras bot pendientes
- Comando `/cancelar_cita` para el cliente (ConversationHandler: pide teléfono → lista citas activas → cancela la elegida)

---

## Arrancar la API (sin systemd)
```bash
cd /opt/itopy.ai/apps/RepAIr
DATABASE_PATH=/opt/itopy.ai/data/repair/repair.db \
  /home/david/itopyzone/venv/bin/uvicorn api.main:app \
  --host 127.0.0.1 --port 8010
```

Documentación interactiva: http://127.0.0.1:8010/docs
