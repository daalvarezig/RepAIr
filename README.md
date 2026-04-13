# RepAIr — Gestión inteligente para talleres de motos

> Sistema de reservas y planificación con IA para talleres.  
> Los clientes reservan por Telegram · La IA optimiza el día · El owner gestiona desde el dashboard.

[![Live](https://img.shields.io/badge/dashboard-repair.itopy.ai-6366f1?style=flat-square)](https://repair.itopy.ai)
[![API](https://img.shields.io/badge/API-FastAPI-009688?style=flat-square)](https://repair.itopy.ai)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python)](https://python.org)

---

## ¿Qué hace?

- **Bot de Telegram** — El cliente reserva, cancela o consulta el estado de su cita en segundos
- **API REST** — FastAPI con motor de planificación que asigna mecánicos y slots de forma óptima
- **Dashboard** — Panel en tiempo real con Gantt por mecánico, KPIs y reoptimización on-demand

---

## Arquitectura

```
Cliente (Telegram)
       ↓
   Bot de reservas
       ↓
   API FastAPI  ←→  SQLite DB
       ↓
 Motor de planificación IA
       ↓
 Dashboard (HTML estático via nginx)
```

| Servicio | Puerto | Descripción |
|---|---|---|
| `repair` (systemd) | `8010` | API FastAPI |
| `repair_bot` (systemd) | — | Bot Telegram |
| nginx | `443` | Frontend en `repair.itopy.ai` |

---

## Stack

| Capa | Tecnología |
|---|---|
| API | Python · FastAPI · SQLite |
| Bot | python-telegram-bot |
| Frontend | HTML/CSS/JS estático |
| Servidor | nginx · systemd · VPS Ubuntu |

---

## Estructura

```
RepAIr/
├── api/
│   ├── main.py              # Entrada FastAPI
│   ├── routers/             # jobs, customers, mechanics, plan
│   ├── engine/              # Motor de planificación IA
│   ├── db/                  # Base de datos SQLite + schema
│   └── schemas/             # Modelos Pydantic
├── bot/
│   ├── main.py              # Entrada Telegram bot
│   ├── handlers/            # client, owner, common
│   └── utils/               # Llamadas a la API
└── frontend/
    ├── index.html           # Dashboard (repair.itopy.ai)
    ├── demo.html            # Presentación para clientes
    └── mockup.html          # Mockup para demos
```

---

## Instalación

```bash
# API
cd api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Editar variables

# Bot
cd bot
pip install -r requirements.txt
cp .env.example .env   # Editar token de Telegram
```

### Variables de entorno

**`api/.env`**
```env
DATABASE_URL=sqlite:////opt/itopy.ai/data/repair/repair.db
```

**`bot/.env`**
```env
TELEGRAM_TOKEN=tu_token
API_BASE_URL=http://127.0.0.1:8010
OWNER_CHAT_ID=tu_chat_id
```

---

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/jobs/` | Crear cita |
| `GET` | `/jobs/` | Listar citas (filtros por fecha, estado) |
| `PATCH` | `/jobs/{id}/status` | Cambiar estado |
| `POST` | `/plan/` | Generar plan optimizado del día |
| `GET` | `/acceptance/` | Comprobar disponibilidad |
| `GET` | `/health` | Health check |

Swagger disponible en `http://127.0.0.1:8010/docs`

---

## Estados de una cita

```
pending → confirmed → in_progress → done
                   ↘ waiting_parts ↗
                   ↘ cancelled
                   ↘ no_show
```

---

## Comandos útiles

```bash
# Reiniciar servicios
sudo systemctl restart repair repair_bot

# Logs en vivo
journalctl -u repair -f
journalctl -u repair_bot -f

# Health check
curl http://127.0.0.1:8010/health
```

---

## URLs

| Recurso | URL |
|---|---|
| Dashboard | https://repair.itopy.ai |
| Demo | https://repair.itopy.ai/demo.html |
| API Docs | http://127.0.0.1:8010/docs |

---

*Parte del ecosistema [itopy.ai](https://itopy.ai) — IA para negocios locales*
