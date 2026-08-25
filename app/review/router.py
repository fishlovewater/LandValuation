from fastapi import APIRouter, Depends

from app.auth.dependencies import require_permissions

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/cases")
async def list_review_cases(
    user=Depends(require_permissions("review.execute")),
) -> list[dict]:
    return []
