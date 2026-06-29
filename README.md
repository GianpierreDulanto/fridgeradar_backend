# FridgeRadar — Backend

API REST en **FastAPI + SQLAlchemy 2 + PostgreSQL** con migraciones con Alembic y un scheduler en background para alertas de caducidad.

- App: `app/main.py` (puerto `8000` por defecto)
- Documentacion interactiva: <http://localhost:8000/docs>
- Healthcheck: <http://localhost:8000/api/health>

## Requisitos

- Python 3.13+
- PostgreSQL 14+ corriendo en local
- Dos bases creadas: `fridge_inventory` (dev) y `fridge_inventory_test` (tests)

## Setup

```powershell
# 1. Crear las BDs (solo la primera vez)
psql -U postgres -c "CREATE DATABASE fridge_inventory;"
psql -U postgres -c "CREATE DATABASE fridge_inventory_test;"

# 2. Entorno virtual + dependencias
cd fridgeradar_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

# 3. Variables de entorno
Copy-Item .env.example .env
# Editar .env -> ajustar DATABASE_URL y (opcional) GEMINI_API_KEY
```

Equivalentes en CMD / bash:

```cmd
python -m venv .venv && .venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
```

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Variables de entorno (`.env`)

| Variable | Obligatoria | Descripcion |
|---|---|---|
| `DATABASE_URL` | si | `postgresql+psycopg://USER:PASS@localhost:5432/fridge_inventory` |
| `TEST_DATABASE_URL` | si | URL de la BD de tests |
| `JWT_SECRET` | si | String largo para firmar tokens (en dev sirve el del `.env.example`) |
| `ENVIRONMENT` | no | `local` / `staging` / `production` |
| `GEMINI_API_KEY` | no | Habilita el chat IA en `/api/ai/chat`. Sin ella, ese endpoint responde 501 pero el resto funciona |
| `RATE_LIMIT_ENABLED` | no | `true` / `false` (los tests lo fuerzan a `false`) |
| `ENABLE_SCHEDULER` | no | `true` / `false`. Enciende el escaneo periodico de caducidades |
| `SCAN_INTERVAL_MINUTES` | no | Cada cuantos minutos corre el scan (default `60`) |

## Cargar el esquema y datos de prueba

Recomendado: el script `reset_db.py` (esquema + seed consistente para inventario, alertas y recetas):

```powershell
python scripts/reset_db.py
```

Crea usuarios de prueba con password `pass1234`:

- `alice@example.com`
- `bob@example.com`
- `lbizarro@gmail.com`

Alternativa solo-esquema con Alembic:

```powershell
alembic upgrade head
```

Verificacion rapida:

```powershell
python scripts/verify_db.py    # debe terminar con "Overall: PASS"
```

## Levantar el servidor

```powershell
uvicorn app.main:app --reload --port 8000
```

Al arrancar, `app.workers.scheduler` levanta APScheduler y escanea el inventario cada `SCAN_INTERVAL_MINUTES` para generar alertas de caducidad. Para apagarlo en dev: `ENABLE_SCHEDULER=false` en `.env`.

## Tests

```powershell
pytest
```

`tests/conftest.py` crea y limpia automaticamente la BD `fridge_inventory_test` (fuerza `RATE_LIMIT_ENABLED=false`, `ENABLE_SCHEDULER=false` y `GEMINI_API_KEY=""`).

## Estructura

```
fridgeradar_backend/
├── app/
│   ├── main.py            # FastAPI app + CORS + lifespan (scheduler)
│   ├── core/              # config, db, security, rate-limit, dependencies
│   ├── models/            # SQLAlchemy
│   ├── schemas/           # Pydantic
│   ├── repositories/      # acceso a datos
│   ├── services/          # logica de negocio
│   ├── routers/           # endpoints (auth, household, inventory, ...)
│   └── workers/           # APScheduler (alertas de caducidad)
├── alembic/               # migraciones
├── scripts/               # reset_db, verify_db, inspect_db
├── tests/                 # pytest
├── requirements.txt
├── alembic.ini
└── .env.example
```

## Endpoints principales

Prefijo comun: `/api`. Algunos routers:

- `auth` — login, refresh, logout, registro
- `household`, `invitation` — hogares compartidos
- `refrigerator`, `zone` — frigorificos y zonas
- `inventory` — items
- `expiry`, `alert` — caducidades y alertas
- `shopping` — lista de la compra
- `recipes` — recetas
- `activity` — bitacora
- `ai` — chat con Gemini (requiere `GEMINI_API_KEY`)

La lista exacta y los schemas viven en Swagger: <http://localhost:8000/docs>.
