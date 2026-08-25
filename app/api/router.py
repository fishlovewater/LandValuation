from fastapi import APIRouter

from app.auth.router import router as auth_router
from app.review.router import router as review_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(review_router)
