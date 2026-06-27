from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import (
    activity, ai, alert, auth, household, inventory, invitation,
    products, recipes, refrigerator, shopping, zone,
)
from app.workers.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
