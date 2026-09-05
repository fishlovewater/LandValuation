from types import SimpleNamespace

from app.knowledge.policy import may_view_review_result


def user_with_permissions(*codes: str):
    permissions = [SimpleNamespace(permission_code=code) for code in codes]
    return SimpleNamespace(roles=[SimpleNamespace(is_active=True, permissions=permissions)])


def test_review_result_requires_review_read_permission() -> None:
    assert may_view_review_result(user_with_permissions("knowledge.read", "case.read")) is False
    assert may_view_review_result(user_with_permissions("review.read")) is True
