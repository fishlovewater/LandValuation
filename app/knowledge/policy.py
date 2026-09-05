from app.auth.models import User
from app.auth.service import permission_codes


KNOWLEDGE_READ_PERMISSION = "knowledge.read"
CASE_READ_PERMISSION = "case.read"
REVIEW_READ_PERMISSION = "review.read"


def may_view_review_result(user: User) -> bool:
    """Review data is not exposed merely because a user can search regulations."""

    return REVIEW_READ_PERMISSION in permission_codes(user)
