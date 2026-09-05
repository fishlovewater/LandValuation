from fastapi import APIRouter

from app.ai_assistant.router import router as ai_assistant_router
from app.auth.router import router as auth_router
from app.history.router import router as history_router
from app.review.router import router as review_router
from app.valuation.automation.router import router as automation_router
from app.valuation.documents.router import router as document_router
from app.valuation.extraction.router import router as extraction_router
from app.valuation.facilities.router import router as facilities_router
from app.valuation.operations.router import router as operations_router
from app.valuation.report_packages.router import router as report_package_router
from app.valuation.router import router as valuation_router
from app.valuation.rule_packs.router import router as rule_pack_router
from app.valuation.submissions.router import router as submission_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(history_router)
api_router.include_router(valuation_router, prefix="/valuation", tags=["valuation"])
api_router.include_router(document_router, prefix="/valuation", tags=["valuation-documents"])
api_router.include_router(extraction_router, prefix="/valuation", tags=["valuation-extraction"])
api_router.include_router(
    report_package_router,
    prefix="/valuation",
    tags=["valuation-report-packages"],
)
api_router.include_router(rule_pack_router, prefix="/valuation", tags=["valuation-rule-packs"])
api_router.include_router(facilities_router, prefix="/valuation", tags=["valuation-facilities"])
api_router.include_router(
    operations_router,
    prefix="/valuation",
    tags=["valuation-operations"],
)
api_router.include_router(automation_router, prefix="/valuation", tags=["valuation-auto-workflow"])
api_router.include_router(submission_router, prefix="/valuation", tags=["valuation-submissions"])
api_router.include_router(ai_assistant_router, prefix="/ai-assistant", tags=["ai-assistant"])
api_router.include_router(review_router)
