# FridgeRadar — Guia de Instalacion Completa

Aplicacion full-stack para gestion de inventario de refrigerador, congelador y despensa.
Stack: **FastAPI + PostgreSQL + Next.js 16 + React 19**.

```
UI UX/
├── fridgeradar_backend/    # API (Python 3.13+, FastAPI 0.115, SQLAlchemy 2, Alembic)
└── fridgradar_frontend/    # UI (Next.js 16.2, React 19, TypeScript, Tailwind 4)
```

---

## 0. Requisitos previos

| Herramienta | Version minima | Verificar |
|---|---|---|
| Python | 3.13 | `python --version` |
| Node.js | 20.x (soporta Next 16) | `node --version` |
| npm | 10.x | `npm --version` |
| PostgreSQL | 14+ (recomendado 16) | `psql --version` |
| Git | cualquiera | `git --version` |

Windows: instala Python desde [python.org](https://www.python.org/downloads/) (marca "Add to PATH"), Node desde [nodejs.org](https://nodejs.org/), y PostgreSQL desde [postgresql.org](https://www.postgresql.org/download/windows/) o usa `choco install postgresql` / `winget install PostgreSQL.PostgreSQL`.

---

## 1. Preparar la base de datos PostgreSQL

El backend espera dos bases de datos en el servidor local de Postgres:

- `fridge_inventory` — base principal de desarrollo
- `fridge_inventory_test` — base efimera usada por pytest

Por defecto el proyecto se conecta con usuario `postgres` y password `portugal` (definido en `fridgeradar_backend/.env`). Si tu Postgres tiene otras credenciales, ajustalas en el `.env` despues.

### Windows (PowerShell)

```powershell
# Abrir psql como el usuario postgres (te pedira la contrasena que pusiste al instalar)
psql -U postgres

# Dentro de psql:
CREATE DATABASE fridge_inventory;
CREATE DATABASE fridge_inventory_test;
\l        -- listar para confirmar
\q        -- salir
```

### Si tu usuario postgres no se llama "postgres" o tiene otra password

Edita el archivo `fridgeradar_backend/.env` (copia de `.env.example`):

```
DATABASE_URL=postgresql+psycopg://TU_USUARIO:TU_PASSWORD@localhost:5432/fridge_inventory
TEST_DATABASE_URL=postgresql+psycopg://TU_USUARIO:TU_PASSWORD@localhost:5432/fridge_inventory_test
JWT_SECRET=local-dev-secret-change-in-production
ENVIRONMENT=local
GEMINI_API_KEY=
RATE_LIMIT_ENABLED=true
ENABLE_SCHEDULER=true
SCAN_INTERVAL_MINUTES=60
```

> El asistente de IA (boton flotante "Sparkles") requiere `GEMINI_API_KEY`. Sin la clave, el endpoint `/api/ai/chat` responde 501. El resto de la app funciona sin ella.

---

## 2. Backend (FastAPI)

### 2.1 Crear entorno virtual e instalar dependencias

PowerShell:

```powershell
cd "C:\Users\sebas\Desktop\sebas\repos\UI UX\fridgeradar_backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

CMD equivalente:

```cmd
cd "C:\Users\sebas\Desktop\sebas\repos\UI UX\fridgeradar_backend"
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS / Linux:

```bash
cd "fridgeradar_backend"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.2 Variables de entorno

Si no existe `.env`, copia la plantilla:

```powershell
Copy-Item .env.example .env
```

Edita `fridgeradar_backend/.env` y rellena:

- `DATABASE_URL` — apuntando a tu Postgres local y la BD `fridge_inventory`.
- `JWT_SECRET` — cualquier string largo (en dev sirve el que viene).
- `GEMINI_API_KEY` — opcional, para el chat IA. Conseguila en [aistudio.google.com](https://aistudio.google.com/app/apikey).

### 2.3 Crear las tablas y datos de prueba

Tienes dos caminos. **Recomendado: el script `reset_db.py`** (crea el esquema Y siembra datos consistentes para las 3 areas: inventario, caducidad, recetas):

```powershell
python scripts/reset_db.py
```

Salida esperada (fragmento):

```
[reset_db] All tables dropped
[reset_db] All tables created
[reset_db] Seed complete:
  Users:           3
  Households:      1
  Refrigerators:   2
  Zones:           2
  Products:        49 (across 24 categories)
  Inventory items: 20 active (...)
  Alerts:          ...
  Shopping items:  3
  Dev credentials (password for all): pass1234
    alice@example.com   / pass1234
    bob@example.com     / pass1234
    lbizarro@gmail.com  / pass1234
```

Alternativa con Alembic (solo crea el esquema, sin datos):

```powershell
alembic upgrade head
```

> `alembic.ini` y `alembic/env.py` leen `DATABASE_URL` desde `.env`, asi que no necesitas exportarlo manualmente.

### 2.4 Verificar la base

```powershell
python scripts/verify_db.py
```

Debe terminar con `Overall: PASS` y exit code `0`.

### 2.5 Levantar el servidor

```powershell
uvicorn app.main:app --reload --port 8000
```

- API: <http://localhost:8000>
- Documentacion interactiva (Swagger): <http://localhost:8000/docs>
- Healthcheck: <http://localhost:8000/api/health>

Al arrancar, `app.workers.scheduler` levanta APScheduler en background y escanea el inventario cada `SCAN_INTERVAL_MINUTES` (default 60) para generar alertas de caducidad. Para desactivarlo en dev: `ENABLE_SCHEDULER=false` en `.env`.

### 2.6 Imagenes de productos (opcional)

El seed crea los 49 productos con `image_url=NULL` para que el seed sea rapido. Si quieres poblar las imagenes desde Open Food Facts (util para ver las cards con foto), hay 2 caminos:

```powershell
# A) Script dedicado (recomendado, idempotente, solo actualiza los NULL):
python scripts/fetch_product_images.py            # solo Casa de Alice
python scripts/fetch_product_images.py --all      # todos los households

# B) Forzar dentro del propio seed:
FETCH_IMAGES=1 python scripts/reset_db.py
```

El script serializa las llamadas (~3s por producto, ~2.5 min para 49 productos) porque Open Food Facts rate-limita IPs compartidas. Si un producto devuelve 503/timeout, queda con `image_url=NULL` y sigue con el siguiente.

### 2.6 Tests

```powershell
pytest
```

`tests/conftest.py` crea/limpia automaticamente la base `fridge_inventory_test` (forzando `RATE_LIMIT_ENABLED=false`, `ENABLE_SCHEDULER=false`, `GEMINI_API_KEY=""`).

---

## 3. Frontend (Next.js)

### 3.1 Instalar dependencias

En otra terminal (sin activar el venv de Python):

```powershell
cd "C:\Users\sebas\Desktop\sebas\repos\UI UX\fridgradar_frontend"
npm install
```

### 3.2 Variables de entorno del frontend (opcional)

Por defecto el frontend habla contra `http://localhost:8000`. Si tu backend esta en otra URL o puerto, crea `fridgradar_frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

> Solo es necesaria esa variable. El `localStorage` guarda `access_token` y `refresh_token` despues del login.

### 3.3 Levantar el servidor de desarrollo

```powershell
npm run dev
```

- App: <http://localhost:3000>
- Build de produccion: `npm run build && npm start`
- Lint: `npm run lint`

La primera vez que abras `/` sin sesion, te redirige a `/login`. Logueate con `alice@example.com` / `pass1234` (tambien valen `bob@example.com` y `lbizarro@gmail.com` con la misma clave, o registra uno nuevo en `/register`).

---

## 4. Flujo end-to-end de verificacion

1. Arranca Postgres y confirma que existen las dos bases (`fridge_inventory` y `fridge_inventory_test`).
2. Backend: `pip install -r requirements.txt` -> `python scripts/reset_db.py` -> `uvicorn app.main:app --reload --port 8000`.
3. Frontend: `npm install` -> `npm run dev`.
4. Abre <http://localhost:3000>, inicia sesion con `alice@example.com / pass1234` (tambien valen `bob@example.com` y `lbizarro@gmail.com`).
5. Deberias ver el dashboard con: inventario activo, alertas (incluidas criticas por items ya vencidos del seed), lista de compras, y el asistente IA flotante.
6. Si configuraste `GEMINI_API_KEY`, prueba el chat IA. Si no, el frontend muestra un error controlado pero el resto funciona.

---

## 5. Solucion de problemas

| Sintoma | Causa probable | Solucion |
|---|---|---|
| `psql: error: connection to server ...` | Postgres no esta corriendo | Inicia el servicio: `net start postgresql-x64-16` (o desde Servicios de Windows) |
| Backend no arranca: `password authentication failed for user "postgres"` | Credenciales en `.env` no coinciden | Ajusta `DATABASE_URL` y `TEST_DATABASE_URL` en `fridgeradar_backend/.env` |
| `alembic upgrade head` falla con "database does not exist" | Falta crear la BD | `CREATE DATABASE fridge_inventory;` en psql |
| `pytest` falla al crear la BD de test | Permisos del usuario Postgres | Conectate como superuser o concede `CREATEDB` al rol |
| Frontend: "Network Error" / no carga datos | Backend caido o CORS | Verifica que uvicorn este corriendo y que el origen (3000) este en la whitelist CORS de `app/main.py` |
| Chat IA devuelve 501 | `GEMINI_API_KEY` vacia | Rellenala en `fridgeradar_backend/.env` y reinicia uvicorn |
| 429 Too Many Requests | Rate limit (100/min global, 10/min en auth) | Baja `RATE_LIMIT_ENABLED=false` en dev, o espera |
| Alertas no se generan automaticamente | Scheduler desactivado o BD recien creada | `ENABLE_SCHEDULER=true` y reinicia; o dispara `POST /api/alerts/run-preview` manualmente |

---

## 6. Resumen rapido (TL;DR)

```powershell
# --- Una sola vez ---
# 1) Crear BDs en Postgres
psql -U postgres -c "CREATE DATABASE fridge_inventory;"
psql -U postgres -c "CREATE DATABASE fridge_inventory_test;"

# 2) Backend
cd "C:\Users\sebas\Desktop\sebas\repos\UI UX\fridgeradar_backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env       # edita DATABASE_URL y GEMINI_API_KEY si aplica
python scripts/reset_db.py

# 3) Frontend (en otra terminal)
cd "C:\Users\sebas\Desktop\sebas\repos\UI UX\fridgradar_frontend"
npm install

# --- Cada dia de trabajo ---
# Terminal 1
cd "C:\Users\sebas\Desktop\sebas\repos\UI UX\fridgeradar_backend"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# Terminal 2
cd "C:\Users\sebas\Desktop\sebas\repos\UI UX\fridgradar_frontend"
npm run dev
```

Abre <http://localhost:3000> y entra con `alice@example.com` / `pass1234` (tambien valen `bob@example.com` y `lbizarro@gmail.com` con la misma clave).
