from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import AsyncSessionFactory
from app.storage.dependencies import Storage

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/ready")
async def ready(storage: Storage):
    services = {"postgresql": "error", "minio": "error"}
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        services["postgresql"] = "ok"
    except Exception:
        pass

    try:
        if await storage.bucket_ready():
            services["minio"] = "ok"
    except Exception:
        pass

    is_ready = all(value == "ok" for value in services.values())
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"status": "ready" if is_ready else "not_ready", "services": services},
    )
