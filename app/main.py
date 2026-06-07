from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from db.database import get_pool, close_pool
from api.routes import router as api_router
from api.auth_routes import router as auth_router
from observability.tracer import setup_phoenix


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_phoenix()        # wire OTEL → Phoenix before first request
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="Acme Operations Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
