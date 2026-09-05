"""Standalone development app for manually exercising Case-history.

This module is intentionally outside the production router graph. Run it only
for local verification; it mounts the existing Auth endpoints and History.
"""

import os
from contextlib import asynccontextmanager
from urllib.parse import quote_plus

# The source tree mount includes the host .env, whose DATABASE_URL commonly
# points at localhost. In a one-off Compose container PostgreSQL is the `db`
# service, so normalize the URL before app.db.session is imported below.
if os.getenv("POSTGRES_HOST"):
    user = quote_plus(os.getenv("POSTGRES_USER", "app_user"))
    password = quote_plus(os.getenv("POSTGRES_PASSWORD", "change_me"))
    host = os.environ["POSTGRES_HOST"]
    port = os.getenv("POSTGRES_PORT", "5432")
    database = quote_plus(os.getenv("POSTGRES_DB", "land_valuation"))
    os.environ["DATABASE_URL"] = (
        f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"
    )

from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.core.error_handlers import register_error_handlers
from app.db.session import dispose_engine
from app.history.router import router as history_router
from app.health.router import router as health_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await dispose_engine()


app = FastAPI(title="Case-history Test App", lifespan=lifespan)
register_error_handlers(app)
app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(history_router, prefix="/api/v1")
