"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routers import parse, voice
from modules.parse import service as parse_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Single-worker FIFO queue for parse jobs (also fails stale jobs on boot).
    await parse_service.start_worker()
    yield
    await parse_service.stop_worker()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Neomyth", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(voice.router)
    app.include_router(parse.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "neomyth-api", "status": "ok"}

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )


if __name__ == "__main__":
    run()
