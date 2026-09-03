from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.error_handlers import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.swagger_docs import register_swagger_docs
from app.db.session import dispose_engine
from app.health.router import router as health_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url="/redoc" if settings.docs_enabled else None,
    )
    application.add_middleware(RequestContextMiddleware)
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(api_router, prefix=settings.api_prefix)
    if settings.docs_enabled:
        register_swagger_docs(application, title=settings.app_name)
    return application


app = create_app()
