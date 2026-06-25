from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # ← Importar CORS


from app.core.config import settings
from app.routers import auth, household, zone, inventory, alert, shopping, activity, refrigerator, invitation, ai, products, recipes


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

# ← Configurar CORS ANTES de incluir los routers
origins = [
    "http://localhost:3000",      # Tu frontend Next.js
    "http://localhost:3001",
    "http://localhost",
    "http://127.0.0.1:3000",     # Alternativa
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,              # Orígenes permitidos
    allow_credentials=True,             # Cookies, Authorization headers
    allow_methods=["*"],                # GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],                # Todos los headers
)

# ← Registra tus routers (AHORA después del CORS)
app.include_router(auth.router)
app.include_router(household.router)
app.include_router(zone.router)
app.include_router(inventory.router)
app.include_router(alert.router)
app.include_router(shopping.router)
app.include_router(activity.router)
app.include_router(refrigerator.router)
app.include_router(invitation.router)
app.include_router(ai.router)
app.include_router(products.router)
app.include_router(recipes.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "environment": settings.environment}