from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Run Alembic migrations via subprocess to avoid event-loop conflicts.
    # The desktop app migrates in its launcher instead (no python.exe to spawn).
    import subprocess, os, sys, logging
    logger = logging.getLogger("app.startup")
    if os.environ.get("DOCTOR_PROSPECTOR_SKIP_MIGRATIONS") != "1":
        alembic_dir = os.path.dirname(os.path.dirname(__file__))
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=alembic_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Alembic migration failed:\n%s\n%s", result.stdout, result.stderr)
        else:
            logger.info("Alembic migrations applied successfully")

    # Start background data refresh scheduler
    from app.services.scheduler import start_scheduler, stop_scheduler
    start_scheduler()

    yield

    # Shutdown: stop scheduler
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include API router
    from app.api.routes import api_router
    app.include_router(api_router)

    @app.get("/api/v1/health", tags=["health"])
    async def health_check():
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "auth_enabled": settings.auth_enabled,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    _mount_frontend(app, settings)
    return app


def _mount_frontend(app: FastAPI, settings) -> None:
    """Serve the built React app from the API (standalone install: one port).

    Mirrors nginx.conf: real files are served as-is, any other non-API path
    gets index.html so client-side routes like /hospitals/123 work on reload.
    Skipped when frontend/dist doesn't exist (e.g. the Docker API image).
    """
    dist = Path(settings.frontend_dist).resolve()
    if not settings.serve_frontend or not (dist / "index.html").is_file():
        return

    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist in candidate.parents:
            return FileResponse(candidate)
        # A missing file (has an extension) is a real 404; anything else is a
        # client-side route like /hospitals/123
        if Path(full_path).suffix:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(dist / "index.html")


app = create_app()
